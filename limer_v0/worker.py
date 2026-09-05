"""CPU worker for the framed AllReduce-like ring workload.

The control channel (stdin) is consumed by a dedicated reader thread, so
route-plan prepare/commit can be processed while a collective round is in
flight. Data commands (run_round, shutdown) are queued for the main thread.
A commit may carry an effective (round, step) point, sockets to close so a
step blocked on a dead path unblocks, and frames to re-send; the interrupted
step is then safely redone under the new plan, with duplicate frames from
the old attempt discarded by header comparison.
"""

from __future__ import annotations

import argparse
import json
import queue
import socket
import sys
import threading
import time
from dataclasses import dataclass
from typing import Dict, List, Optional, Set, TextIO, Tuple

from .protocol import FrameHeader, crc32, recv_frame, send_frame
from .route_plan import RoutePlan
from .state import RouteState


MAX_STEP_RETRIES = 3
MAX_DUPLICATE_DISCARDS = 8


class _StepAborted(Exception):
    """The in-flight step failed because a cutover interrupted it."""


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


def _shutdown_socket(sock: socket.socket) -> None:
    try:
        sock.shutdown(socket.SHUT_RDWR)
    except OSError:
        pass
    try:
        sock.close()
    except OSError:
        pass


class RingWorker:
    def __init__(
        self,
        rank: int,
        world_size: int,
        fabrics: List[FabricConfig],
        chunk_bytes: int,
        initial_routing_policy: str = "single_fabric",
        step_telemetry: bool = False,
        step_timeout_s: float = 65.0,
        output: TextIO = sys.stdout,
    ) -> None:
        if world_size < 2:
            raise ValueError("world_size must be at least 2")
        if not 0 <= rank < world_size:
            raise ValueError("rank must be within world_size")
        if chunk_bytes <= 0:
            raise ValueError("chunk_bytes must be positive")
        if step_timeout_s <= 0:
            raise ValueError("step_timeout_s must be positive")
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
        self.step_timeout_s = float(step_timeout_s)
        self.output = output
        self.route_state = RouteState(initial_plan)
        self.sockets: Dict[str, FabricSockets] = {}
        self.listeners: Dict[str, socket.socket] = {}
        self._route_lock = threading.Lock()
        self._emit_lock = threading.Lock()
        self._data_commands: "queue.Queue[Dict[str, object]]" = queue.Queue()
        self._control_failure: Optional[Dict[str, str]] = None
        self._cutover_generation = 0
        self._pending_resends: List[Tuple[int, int]] = []
        self._step_progress: Dict[Tuple[int, int], Dict[str, bool]] = {}
        self._early_frames: Dict[Tuple[int, int], Tuple[FrameHeader, bytes]] = {}
        self._closed_outgoing: Set[str] = set()
        self._resent_keys: Set[Tuple[int, int]] = set()
        self._handled_generation = 0

    def emit(self, event: str, **payload: object) -> None:
        record = {
            "event": event,
            "t_monotonic_ns": time.monotonic_ns(),
            "rank": self.rank,
        }
        record.update(payload)
        with self._emit_lock:
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

    # ------------------------------------------------------------------
    # Control channel (reader thread)
    # ------------------------------------------------------------------

    def _handle_prepare(self, command: Dict[str, object]) -> None:
        plan = RoutePlan.from_dict(command["plan"])
        plan_fingerprint = str(command["plan_fingerprint"])
        if plan.fingerprint != plan_fingerprint:
            raise ValueError("prepare plan fingerprint does not match plan content")
        unavailable = sorted(
            {route for row in plan.routes for route in row} - set(self.sockets)
        )
        if unavailable:
            raise ValueError(
                "prepare plan uses unavailable fabrics: " + ", ".join(unavailable)
            )
        effective_step = int(command.get("effective_step", 0))
        with self._route_lock:
            self.route_state.prepare(
                int(command["version"]),
                plan,
                int(command["effective_round"]),
                effective_step,
            )
        self.emit(
            "READY",
            version=int(command["version"]),
            plan_fingerprint=plan_fingerprint,
            routing_policy=plan.policy,
            effective_round=int(command["effective_round"]),
            effective_step=effective_step,
        )

    def _handle_commit(self, command: Dict[str, object]) -> None:
        close_incoming = [str(name) for name in command.get("close_incoming", [])]
        close_outgoing = [str(name) for name in command.get("close_outgoing", [])]
        resend_steps = [
            (int(entry["round_id"]), int(entry["step_id"]))
            for entry in command.get("resend_steps", [])
        ]
        with self._route_lock:
            if self.route_state.prepared is None:
                raise ValueError("no prepared transition to commit")
            plan_fingerprint = self.route_state.prepared.plan.fingerprint
            self.route_state.commit(int(command["version"]))
            self._pending_resends.extend(resend_steps)
            self._resent_keys.update(resend_steps)
            self._closed_outgoing.update(close_outgoing)
            self._cutover_generation += 1
        # Closing after the state flip: any step now failing on these sockets
        # observes the new generation and is redone instead of crashing.
        for name in close_incoming:
            if name in self.sockets:
                _shutdown_socket(self.sockets[name].incoming)
        for name in close_outgoing:
            if name in self.sockets:
                _shutdown_socket(self.sockets[name].outgoing)
        self.emit(
            "COMMITTED",
            version=int(command["version"]),
            plan_fingerprint=plan_fingerprint,
            closed_incoming=close_incoming,
            closed_outgoing=close_outgoing,
            resend_steps=[
                {"round_id": round_id, "step_id": step_id}
                for round_id, step_id in resend_steps
            ],
        )

    def _control_reader(self, input_stream: TextIO) -> None:
        for line in input_stream:
            if not line.strip():
                continue
            try:
                command = json.loads(line)
                name = command.get("command")
                if name == "prepare":
                    self._handle_prepare(command)
                elif name == "commit":
                    self._handle_commit(command)
                elif name == "abort":
                    with self._route_lock:
                        self.route_state.abort(int(command["version"]))
                    self.emit("ABORTED", version=int(command["version"]))
                elif name in {"run_round", "shutdown"}:
                    self._data_commands.put(command)
                else:
                    raise ValueError(f"unknown worker command: {name!r}")
            except BaseException as exc:
                self._control_failure = {
                    "command": str(command.get("command") if isinstance(command, dict) else None),
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                }
                self.emit("WORKER_ERROR", **self._control_failure)
                self._data_commands.put({"command": "__control_failure__"})
                return
        self._data_commands.put({"command": "__eof__"})

    # ------------------------------------------------------------------
    # Data path (main thread)
    # ------------------------------------------------------------------

    def _receive_expected(
        self,
        incoming: socket.socket,
        round_id: int,
        step_id: int,
        result: List[Tuple[FrameHeader, bytes]],
        errors: List[BaseException],
    ) -> None:
        try:
            stashed = self._early_frames.pop((round_id, step_id), None)
            if stashed is not None:
                result.append(stashed)
                return
            for _ in range(MAX_DUPLICATE_DISCARDS):
                header, payload = recv_frame(incoming)
                key = (header.round_id, header.step_id)
                if key < (round_id, step_id):
                    # A frame from an attempt superseded by the cutover; the
                    # sender re-sent it on the new route, so drop this copy.
                    self.emit(
                        "DUPLICATE_FRAME_DISCARDED",
                        round_id=header.round_id,
                        step_id=header.step_id,
                        expected_round_id=round_id,
                        expected_step_id=step_id,
                    )
                    continue
                if key > (round_id, step_id):
                    # The sender ran ahead on the surviving fabric before the
                    # cutover interrupted this receiver; hold the frame until
                    # this worker reaches that step.
                    if len(self._early_frames) >= MAX_DUPLICATE_DISCARDS:
                        raise RuntimeError("early-frame buffer overflow")
                    self._early_frames[key] = (header, payload)
                    self.emit(
                        "EARLY_FRAME_BUFFERED",
                        round_id=header.round_id,
                        step_id=header.step_id,
                        expected_round_id=round_id,
                        expected_step_id=step_id,
                    )
                    continue
                result.append((header, payload))
                return
            raise RuntimeError("too many duplicate frames discarded")
        except BaseException as exc:  # re-raised on the data thread
            errors.append(exc)

    def _perform_pending_resends(self, size: int, payload: bytes, checksum: int) -> None:
        while True:
            with self._route_lock:
                if not self._pending_resends:
                    return
                round_id, step_id = self._pending_resends.pop(0)
                plan, version = self.route_state.plan_for(round_id, step_id)
            send_route = plan.route_for(self.rank, step_id)
            header = FrameHeader(
                round_id=round_id,
                step_id=step_id,
                version=version,
                payload_len=size,
                checksum=checksum,
            )
            send_frame(self.sockets[send_route].outgoing, header, payload)
            self.emit(
                "STEP_RESENT",
                round_id=round_id,
                step_id=step_id,
                version=version,
                send_route=send_route,
            )

    def _run_step(
        self,
        round_id: int,
        step_id: int,
        plan: RoutePlan,
        version: int,
        size: int,
        payload: bytes,
        payload_checksum: int,
    ) -> Dict[str, object]:
        progress = self._step_progress.setdefault(
            (round_id, step_id), {"sent": False, "received": False}
        )
        send_route = plan.route_for(self.rank, step_id)
        if progress["sent"] and progress.get("sent_route") != send_route:
            # The earlier attempt buffered the frame into a socket that a
            # cutover has since closed; the bytes died with it. Re-send on
            # the new route — if the old copy survived after all, the
            # receiver's duplicate handling discards one of them.
            progress["sent"] = False
            self.emit(
                "STEP_SEND_ROUTE_CHANGED",
                round_id=round_id,
                step_id=step_id,
                old_route=progress.get("sent_route"),
                new_route=send_route,
            )
        predecessor = (self.rank - 1) % self.world_size
        receive_route = plan.route_for(predecessor, step_id)
        received: List[Tuple[FrameHeader, bytes]] = []
        errors: List[BaseException] = []
        receiver: Optional[threading.Thread] = None
        if not progress["received"]:
            receiver = threading.Thread(
                target=self._receive_expected,
                args=(
                    self.sockets[receive_route].incoming,
                    round_id,
                    step_id,
                    received,
                    errors,
                ),
                daemon=True,
            )
            receiver.start()
        if not progress["sent"]:
            header = FrameHeader(
                round_id=round_id,
                step_id=step_id,
                version=version,
                payload_len=size,
                checksum=payload_checksum,
            )
            send_frame(self.sockets[send_route].outgoing, header, payload)
            progress["sent"] = True
            progress["sent_route"] = send_route
        if receiver is not None:
            receiver.join(timeout=self.step_timeout_s)
            if receiver.is_alive():
                raise TimeoutError(
                    f"receive timed out at round {round_id} step {step_id}"
                )
            if errors:
                raise errors[0]
            if len(received) != 1:
                raise RuntimeError("receive thread did not return exactly one frame")
            received_header, received_payload = received[0]
            if (
                received_header.round_id != round_id
                or received_header.step_id != step_id
            ):
                raise ValueError(
                    "received frame round/step does not match current step"
                )
            if received_header.version != version:
                # A frame sent just before a cutover legitimately carries the
                # superseded version; accept it only when the slot's route is
                # identical under both plans, so torn-plan application still
                # surfaces as an error.
                with self._route_lock:
                    previous_plan = self.route_state.previous_plan
                    previous_version = self.route_state.previous_version
                acceptable_cross_version = (
                    previous_plan is not None
                    and received_header.version == previous_version
                    and previous_plan.route_for(predecessor, step_id)
                    == receive_route
                )
                if not acceptable_cross_version:
                    # Keep the frame: if a cutover superseded this attempt,
                    # the redo re-validates it under the new plan instead of
                    # losing it with the aborted attempt.
                    self._early_frames[(round_id, step_id)] = (
                        received_header,
                        received_payload,
                    )
                    raise ValueError(
                        "received frame version does not match active version"
                    )
                self.emit(
                    "CROSS_VERSION_FRAME_ACCEPTED",
                    round_id=round_id,
                    step_id=step_id,
                    frame_version=received_header.version,
                    active_version=version,
                )
            if len(received_payload) != size:
                raise ValueError(
                    "received payload length does not match current chunk"
                )
            if crc32(received_payload) != received_header.checksum:
                raise ValueError("received payload checksum mismatch")
            progress["received"] = True
        return {"send_route": send_route, "receive_route": receive_route}

    def run_round(self, round_id: int, chunk_bytes: Optional[int] = None) -> Dict[str, object]:
        size = self.chunk_bytes if chunk_bytes is None else int(chunk_bytes)
        if size <= 0:
            raise ValueError("round chunk_bytes must be positive")
        payload = bytes([self.rank & 0xFF]) * size
        payload_checksum = crc32(payload)
        with self._route_lock:
            first_plan, _ = self.route_state.plan_for(round_id, 0)
        steps = first_plan.steps
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
        redo_count = 0
        round_start = time.monotonic_ns()
        last_version = 0
        last_fingerprint = first_plan.fingerprint
        last_policy = first_plan.policy

        step_id = 0
        while step_id < steps:
            with self._route_lock:
                plan, version = self.route_state.plan_for(round_id, step_id)
                generation = self._cutover_generation
                previous_plan = self.route_state.previous_plan
                closed_outgoing = set(self._closed_outgoing)
                if (
                    generation != self._handled_generation
                    and previous_plan is not None
                    and closed_outgoing
                ):
                    # Frames this worker already pushed into a now-closed
                    # socket died with its buffer even though their steps
                    # completed locally; re-send them under the new plan.
                    # The receiver discards any copy that made it through.
                    for done_step in range(step_id):
                        key = (round_id, done_step)
                        if (
                            previous_plan.route_for(self.rank, done_step)
                            in closed_outgoing
                            and key not in self._resent_keys
                        ):
                            self._pending_resends.append(key)
                            self._resent_keys.add(key)
                    self._handled_generation = generation
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
            self._perform_pending_resends(size, payload, payload_checksum)
            step_start = time.monotonic_ns()
            try:
                routes = self._run_step(
                    round_id, step_id, plan, version, size, payload, payload_checksum
                )
            except BaseException as exc:
                with self._route_lock:
                    cutover_seen = self._cutover_generation != generation
                # A connection error on the send side can race ahead of this
                # worker's own commit: a peer closed the socket for the
                # cutover while this worker's commit command is still queued
                # on the control thread. Give the commit a brief window to
                # land before treating the error as fatal, so the step is
                # redone under the new plan rather than crashing the worker.
                if (
                    not cutover_seen
                    and isinstance(exc, (OSError, EOFError))
                    and self.route_state.prepared is not None
                ):
                    deadline = time.monotonic() + 1.0
                    while time.monotonic() < deadline:
                        with self._route_lock:
                            if self._cutover_generation != generation:
                                cutover_seen = True
                                break
                        time.sleep(0.005)
                if cutover_seen and redo_count < MAX_STEP_RETRIES * steps:
                    redo_count += 1
                    self.emit(
                        "STEP_REDO",
                        round_id=round_id,
                        step_id=step_id,
                        reason=type(exc).__name__,
                        detail=str(exc),
                    )
                    continue
                if isinstance(exc, ValueError) and "version" in str(exc):
                    version_errors += 1
                if isinstance(exc, ValueError) and "checksum" in str(exc):
                    checksum_errors += 1
                raise
            duration_ns = time.monotonic_ns() - step_start
            step_durations_ns.append(duration_ns)
            if self.step_telemetry:
                self.emit(
                    "STEP_DONE",
                    round_id=round_id,
                    step_id=step_id,
                    version=version,
                    send_route=routes["send_route"],
                    duration_ns=duration_ns,
                )
            send_routes.append(routes["send_route"])
            receive_routes.append(routes["receive_route"])
            send_steps_by_fabric[routes["send_route"]] += 1
            receive_steps_by_fabric[routes["receive_route"]] += 1
            bytes_sent_by_fabric[routes["send_route"]] += size
            bytes_received_by_fabric[routes["receive_route"]] += size
            bytes_sent += size
            bytes_received += size
            last_version = version
            last_fingerprint = plan.fingerprint
            last_policy = plan.policy
            self._step_progress.pop((round_id, step_id), None)
            step_id += 1

        duration_ns = time.monotonic_ns() - round_start
        return {
            "event": "ROUND_DONE",
            "round_id": round_id,
            "version": last_version,
            "route_plan_fingerprint": last_fingerprint,
            "routing_policy": last_policy,
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
            "redo_count": redo_count,
        }

    def close(self) -> None:
        for sockets in self.sockets.values():
            sockets.close()
        self.sockets.clear()
        for listener in self.listeners.values():
            listener.close()
        self.listeners.clear()

    def control_loop(self, input_stream: TextIO = sys.stdin) -> int:
        reader = threading.Thread(
            target=self._control_reader, args=(input_stream,), daemon=True
        )
        reader.start()
        while True:
            command = self._data_commands.get()
            name = command.get("command")
            if name == "__control_failure__":
                return 1
            if name == "__eof__":
                return 0
            try:
                if name == "run_round":
                    result = self.run_round(
                        int(command["round_id"]), command.get("chunk_bytes")
                    )
                    event_name = str(result.pop("event"))
                    self.emit(event_name, **result)
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
    parser.add_argument("--step-timeout", type=float, default=65.0)
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
        step_timeout_s=args.step_timeout,
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
