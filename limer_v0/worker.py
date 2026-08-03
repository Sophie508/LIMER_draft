"""CPU worker for the framed AllReduce-like ring workload."""

from __future__ import annotations

import argparse
import json
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, TextIO, Tuple

from .protocol import FrameHeader, crc32, recv_frame, send_frame
from .route_plan import RoutePlan
from .state import RouteState


@dataclass(frozen=True)
class FabricConfig:
    name: str
    local_ip: str
    next_ip: str
    port: int

    @classmethod
    def parse(cls, value: str) -> "FabricConfig":
        fields = value.split(",")
        if len(fields) != 4:
            raise argparse.ArgumentTypeError(
                "fabric must be NAME,LOCAL_IP,NEXT_IP,PORT"
            )
        name, local_ip, next_ip, port_text = fields
        if name not in {"A", "B"}:
            raise argparse.ArgumentTypeError("fabric name must be A or B")
        try:
            port = int(port_text)
        except ValueError as exc:
            raise argparse.ArgumentTypeError("fabric port must be an integer") from exc
        if not 1 <= port <= 65535:
            raise argparse.ArgumentTypeError("fabric port is out of range")
        return cls(name, local_ip, next_ip, port)


@dataclass
class FabricSockets:
    incoming: socket.socket
    outgoing: socket.socket

    def close(self) -> None:
        for sock in (self.incoming, self.outgoing):
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass
            sock.close()


class RingWorker:
    def __init__(
        self,
        rank: int,
        world_size: int,
        fabrics: List[FabricConfig],
        chunk_bytes: int,
        initial_routing_policy: str = "single_fabric",
        step_telemetry: bool = False,
        output: TextIO = sys.stdout,
    ) -> None:
        if world_size < 2:
            raise ValueError("world_size must be at least 2")
        if not 0 <= rank < world_size:
            raise ValueError("rank must be within world_size")
        if chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be positive")
        names = [fabric.name for fabric in fabrics]
        if len(names) != len(set(names)):
            raise ValueError("fabric names must be unique")
        if "A" not in names:
            raise ValueError("fabric A is required")
        if initial_routing_policy == "single_fabric":
            initial_plan = RoutePlan.single_fabric(world_size, "A")
        elif initial_routing_policy == "balanced_active_active":
            if "B" not in names:
                raise ValueError(
                    "balanced_active_active routing requires fabrics A and B"
                )
            initial_plan = RoutePlan.balanced_active_active(world_size)
        else:
            raise ValueError(
                "initial_routing_policy must be single_fabric or "
                "balanced_active_active"
            )
        self.rank = rank
        self.world_size = world_size
        self.configs = {fabric.name: fabric for fabric in fabrics}
        self.chunk_bytes = chunk_bytes
        self.step_telemetry = bool(step_telemetry)
        self.output = output
        self.route_state = RouteState(initial_plan)
        self.sockets: Dict[str, FabricSockets] = {}
        self.listeners: Dict[str, socket.socket] = {}

    def emit(self, event: str, **payload: object) -> None:
        record = {
            "event": event,
            "t_monotonic_ns": time.monotonic_ns(),
            "rank": self.rank,
        }
        record.update(payload)
        self.output.write(json.dumps(record, sort_keys=True) + "\n")
        self.output.flush()

    def _open_listeners(self) -> None:
        for name, config in sorted(self.configs.items()):
            listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            listener.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            listener.bind((config.local_ip, config.port))
            listener.listen(1)
            listener.settimeout(60.0)
            self.listeners[name] = listener

    @staticmethod
    def _connect(config: FabricConfig, deadline_s: float = 30.0) -> socket.socket:
        deadline = time.monotonic() + deadline_s
        last_error: Optional[OSError] = None
        while time.monotonic() < deadline:
            outgoing = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            outgoing.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            outgoing.settimeout(60.0)
            try:
                outgoing.connect((config.next_ip, config.port))
                return outgoing
            except OSError as exc:
                last_error = exc
                outgoing.close()
                time.sleep(0.05)
        raise TimeoutError(
            f"could not connect fabric {config.name} to "
            f"{config.next_ip}:{config.port}: {last_error}"
        )

    def start(self) -> None:
        self._open_listeners()
        outgoing: Dict[str, socket.socket] = {}
        for name, config in sorted(self.configs.items()):
            outgoing[name] = self._connect(config)
        for name, listener in sorted(self.listeners.items()):
            incoming, _peer = listener.accept()
            incoming.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
            incoming.settimeout(60.0)
            self.sockets[name] = FabricSockets(incoming, outgoing[name])
            listener.close()
        self.listeners.clear()
        self.emit(
            "WORKER_READY",
            fabrics=sorted(self.sockets),
            routing_policy=self.route_state.active_plan.policy,
            route_plan_fingerprint=self.route_state.active_plan.fingerprint,
        )

    def _receive_one(
        self,
        incoming: socket.socket,
        result: List[Tuple[FrameHeader, bytes]],
        errors: List[BaseException],
    ) -> None:
        try:
            result.append(recv_frame(incoming))
        except BaseException as exc:  # captured and re-raised on the control thread
            errors.append(exc)

    def run_round(self, round_id: int, chunk_bytes: Optional[int] = None) -> Dict[str, object]:
        plan, version = self.route_state.plan_for(round_id)
        if plan.world_size != self.world_size:
            raise ValueError("active route plan world_size does not match worker")
        missing_fabrics = sorted(
            {route for row in plan.routes for route in row} - set(self.sockets)
        )
        if missing_fabrics:
            raise ValueError(
                "active route plan uses unavailable fabrics: "
                + ", ".join(missing_fabrics)
            )
        size = self.chunk_bytes if chunk_bytes is None else int(chunk_bytes)
        if size <= 0:
            raise ValueError("round chunk_bytes must be positive")
        payload = bytes([self.rank & 0xFF]) * size
        payload_checksum = crc32(payload)
        steps = plan.steps
        step_durations_ns: List[int] = []
        send_routes: List[str] = []
        receive_routes: List[str] = []
        send_steps_by_fabric = {"A": 0, "B": 0}
        receive_steps_by_fabric = {"A": 0, "B": 0}
        bytes_sent_by_fabric = {"A": 0, "B": 0}
        bytes_received_by_fabric = {"A": 0, "B": 0}
        bytes_sent = 0
        bytes_received = 0
        checksum_errors = 0
        version_errors = 0
        round_start = time.monotonic_ns()

        for step_id in range(steps):
            send_route = plan.route_for(self.rank, step_id)
            predecessor = (self.rank - 1) % self.world_size
            receive_route = plan.route_for(predecessor, step_id)
            send_sockets = self.sockets[send_route]
            receive_sockets = self.sockets[receive_route]
            received: List[Tuple[FrameHeader, bytes]] = []
            errors: List[BaseException] = []
            receiver = threading.Thread(
                target=self._receive_one,
                args=(receive_sockets.incoming, received, errors),
                daemon=True,
            )
            step_start = time.monotonic_ns()
            receiver.start()
            header = FrameHeader(
                round_id=round_id,
                step_id=step_id,
                version=version,
                payload_len=size,
                checksum=payload_checksum,
            )
            send_frame(send_sockets.outgoing, header, payload)
            receiver.join(timeout=65.0)
            if receiver.is_alive():
                raise TimeoutError(f"receive timed out at round {round_id} step {step_id}")
            if errors:
                raise errors[0]
            if len(received) != 1:
                raise RuntimeError("receive thread did not return exactly one frame")
            received_header, received_payload = received[0]
            if (
                received_header.round_id != round_id
                or received_header.step_id != step_id
            ):
                raise ValueError("received frame round/step does not match current step")
            if received_header.version != version:
                version_errors += 1
                raise ValueError("received frame version does not match active version")
            if len(received_payload) != size:
                raise ValueError("received payload length does not match current chunk")
            if crc32(received_payload) != received_header.checksum:
                checksum_errors += 1
                raise ValueError("received payload checksum mismatch")
            step_durations_ns.append(time.monotonic_ns() - step_start)
            if self.step_telemetry:
                self.emit(
                    "STEP_DONE",
                    round_id=round_id,
                    step_id=step_id,
                    version=version,
                    send_route=send_route,
                    duration_ns=step_durations_ns[-1],
                )
            send_routes.append(send_route)
            receive_routes.append(receive_route)
            send_steps_by_fabric[send_route] += 1
            receive_steps_by_fabric[receive_route] += 1
            bytes_sent_by_fabric[send_route] += size
            bytes_received_by_fabric[receive_route] += size
            bytes_sent += size
            bytes_received += size

        duration_ns = time.monotonic_ns() - round_start
        return {
            "event": "ROUND_DONE",
            "round_id": round_id,
            "version": version,
            "route_plan_fingerprint": plan.fingerprint,
            "routing_policy": plan.policy,
            "send_routes": send_routes,
            "receive_routes": receive_routes,
            "send_steps_by_fabric": send_steps_by_fabric,
            "receive_steps_by_fabric": receive_steps_by_fabric,
            "bytes_sent_by_fabric": bytes_sent_by_fabric,
            "bytes_received_by_fabric": bytes_received_by_fabric,
            "step_durations_ns": step_durations_ns,
            "duration_ns": duration_ns,
            "bytes_sent": bytes_sent,
            "bytes_received": bytes_received,
            "frame_count": steps,
            "checksum_errors": checksum_errors,
            "version_errors": version_errors,
        }

    def close(self) -> None:
        for sockets in self.sockets.values():
            sockets.close()
        self.sockets.clear()
        for listener in self.listeners.values():
            listener.close()
        self.listeners.clear()

    def control_loop(self, input_stream: TextIO = sys.stdin) -> int:
        for line in input_stream:
            if not line.strip():
                continue
            command = json.loads(line)
            name = command.get("command")
            try:
                if name == "run_round":
                    result = self.run_round(
                        int(command["round_id"]), command.get("chunk_bytes")
                    )
                    event_name = str(result.pop("event"))
                    self.emit(event_name, **result)
                elif name == "prepare":
                    plan = RoutePlan.from_dict(command["plan"])
                    plan_fingerprint = str(command["plan_fingerprint"])
                    if plan.fingerprint != plan_fingerprint:
                        raise ValueError(
                            "prepare plan fingerprint does not match plan content"
                        )
                    unavailable = sorted(
                        {route for row in plan.routes for route in row}
                        - set(self.sockets)
                    )
                    if unavailable:
                        raise ValueError(
                            "prepare plan uses unavailable fabrics: "
                            + ", ".join(unavailable)
                        )
                    self.route_state.prepare(
                        int(command["version"]),
                        plan,
                        int(command["effective_round"]),
                    )
                    self.emit(
                        "READY",
                        version=int(command["version"]),
                        plan_fingerprint=plan_fingerprint,
                        routing_policy=plan.policy,
                        effective_round=int(command["effective_round"]),
                    )
                elif name == "commit":
                    if self.route_state.prepared is None:
                        raise ValueError("no prepared transition to commit")
                    plan_fingerprint = self.route_state.prepared.plan.fingerprint
                    self.route_state.commit(int(command["version"]))
                    self.emit(
                        "COMMITTED",
                        version=int(command["version"]),
                        plan_fingerprint=plan_fingerprint,
                    )
                elif name == "abort":
                    self.route_state.abort(int(command["version"]))
                    self.emit("ABORTED", version=int(command["version"]))
                elif name == "shutdown":
                    self.emit("SHUTDOWN_COMPLETE")
                    return 0
                else:
                    raise ValueError(f"unknown worker command: {name!r}")
            except BaseException as exc:
                self.emit(
                    "WORKER_ERROR",
                    command=name,
                    error_type=type(exc).__name__,
                    error=str(exc),
                )
                return 1
        return 0


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--rank", type=int, required=True)
    parser.add_argument("--world-size", type=int, required=True)
    parser.add_argument("--fabric", action="append", type=FabricConfig.parse, required=True)
    parser.add_argument("--chunk-bytes", type=int, default=2 * 1024 * 1024)
    parser.add_argument(
        "--initial-routing-policy",
        choices=("single_fabric", "balanced_active_active"),
        default="single_fabric",
    )
    parser.add_argument("--step-telemetry", action="store_true")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    worker = RingWorker(
        args.rank,
        args.world_size,
        args.fabric,
        args.chunk_bytes,
        initial_routing_policy=args.initial_routing_policy,
        step_telemetry=args.step_telemetry,
    )
    try:
        worker.start()
        return worker.control_loop()
    except BaseException as exc:
        worker.emit(
            "WORKER_ERROR",
            command="startup",
            error_type=type(exc).__name__,
            error=str(exc),
        )
        return 1
    finally:
        worker.close()


if __name__ == "__main__":
    raise SystemExit(main())
