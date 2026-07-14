"""Experiment lifecycle orchestration for LIMER CPU v0."""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import queue
import statistics
import subprocess
import sys
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, TextIO

from .coordinator import RecoveryCoordinator, TransitionDecision
from .faults import TcProfile, read_operstate, sample_qdisc
from .metrics import summarize_rounds
from .refiner import HostRefiner, RefinerDecision
from .sentinel import SentinelRule
from .topology import BASE_PROFILE, WORLD_SIZE, TopologyDescriptor, build_topology


CONDITIONS = {"C0", "C1", "C2", "C3", "C4", "C5"}
TOPOLOGIES = {"single", "dual"}
REQUIRED_CONFIG_FIELDS = {
    "condition",
    "topology",
    "chunk_bytes",
    "warmup_rounds",
    "baseline_rounds",
    "post_fault_rounds",
    "fault_rate_mbit",
    "fault_loss_pct",
    "detector",
    "recovery",
    "oracle",
    "transient_ms",
    "what_changes",
    "expected",
}
WORKER_CSV_FIELDS = [
    "rank",
    "round_id",
    "period",
    "route",
    "version",
    "duration_ns",
    "duration_s",
    "bytes_sent",
    "bytes_received",
    "frame_count",
    "checksum_errors",
    "version_errors",
    "step_durations_ns",
]
AGGREGATE_CSV_FIELDS = [
    "round_id",
    "period",
    "route",
    "version",
    "duration_ns",
    "duration_s",
    "bytes_completed",
    "rank_count",
    "checksum_errors",
    "version_errors",
    "orchestrator_command_start_ns",
    "orchestrator_command_end_ns",
    "orchestrator_duration_ns",
]
SWITCH_CSV_FIELDS = [
    "poll_iteration",
    "poll_start_ns",
    "poll_end_ns",
    "poll_interval_ns",
    "interface",
    "operstate",
    "t_ns",
    "kind",
    "bytes",
    "packets",
    "drops",
    "overlimits",
    "requeues",
    "backlog_bytes",
    "qlen",
    "rx_bytes",
    "rx_packets",
    "rx_dropped",
    "tx_bytes",
    "tx_packets",
    "tx_dropped",
]
VERSION_CSV_FIELDS = [
    "t_monotonic_ns",
    "event",
    "rank",
    "version",
    "route",
    "effective_round",
]


def validate_config(config: Mapping[str, Any]) -> Dict[str, Any]:
    missing = sorted(REQUIRED_CONFIG_FIELDS - set(config))
    if missing:
        raise ValueError(f"missing config fields: {', '.join(missing)}")
    result = dict(config)
    if result["condition"] not in CONDITIONS:
        raise ValueError(f"unknown condition: {result['condition']!r}")
    if result["topology"] not in TOPOLOGIES:
        raise ValueError(f"unknown topology: {result['topology']!r}")
    for field in ("what_changes", "expected"):
        if not isinstance(result[field], str) or not result[field].strip():
            raise ValueError(f"{field} must be a non-empty string")
        result[field] = result[field].strip()
    for field in ("chunk_bytes", "baseline_rounds", "post_fault_rounds"):
        if int(result[field]) <= 0:
            raise ValueError(f"{field} must be positive")
        result[field] = int(result[field])
    if int(result["warmup_rounds"]) < 0:
        raise ValueError("warmup_rounds must be non-negative")
    result["warmup_rounds"] = int(result["warmup_rounds"])
    if float(result["fault_rate_mbit"]) <= 0:
        raise ValueError("fault_rate_mbit must be positive")
    result["fault_rate_mbit"] = float(result["fault_rate_mbit"])
    if not 0 <= float(result["fault_loss_pct"]) < 100:
        raise ValueError("fault_loss_pct must be in [0, 100)")
    result["fault_loss_pct"] = float(result["fault_loss_pct"])
    if int(result["transient_ms"]) < 0:
        raise ValueError("transient_ms must be non-negative")
    result["transient_ms"] = int(result["transient_ms"])
    for field in ("detector", "recovery", "oracle"):
        result[field] = bool(result[field])
    if result["recovery"] and result["topology"] != "dual":
        raise ValueError("recovery requires the dual topology")
    if result["oracle"] and not result["recovery"]:
        raise ValueError("oracle requires recovery")
    if result["condition"] in {"C3", "C4", "C5"} and result["topology"] != "dual":
        raise ValueError(f"{result['condition']} requires the dual topology")
    if result["condition"] == "C2" and not result["detector"]:
        raise ValueError("C2 requires the switch detector")
    if result["condition"] == "C3" and (
        not result["detector"] or not result["recovery"] or result["oracle"]
    ):
        raise ValueError("C3 requires detector and recovery without oracle")
    if result["condition"] == "C4" and (
        not result["recovery"] or not result["oracle"]
    ):
        raise ValueError("C4 requires oracle recovery")
    if result["condition"] == "C5" and (
        not result["detector"]
        or not result["recovery"]
        or result["transient_ms"] <= 0
    ):
        raise ValueError("C5 requires detector, recovery, and a transient duration")
    return result


def aggregate_round_events(
    events: Sequence[Mapping[str, Any]], period: str, world_size: int = WORLD_SIZE
) -> Dict[str, Any]:
    """Collapse rank events into one collective round measurement."""
    if len(events) != world_size:
        raise ValueError(f"expected {world_size} ranks, received {len(events)}")
    ranks = {int(event["rank"]) for event in events}
    if ranks != set(range(world_size)):
        raise ValueError(f"round ranks do not match 0..{world_size - 1}: {sorted(ranks)}")
    round_ids = {int(event["round_id"]) for event in events}
    if len(round_ids) != 1:
        raise ValueError(f"round_id split across ranks: {sorted(round_ids)}")
    routes = {str(event["route"]) for event in events}
    if len(routes) != 1:
        raise ValueError(f"route split across ranks: {sorted(routes)}")
    versions = {int(event["version"]) for event in events}
    if len(versions) != 1:
        raise ValueError(f"version split across ranks: {sorted(versions)}")
    duration_ns = max(int(event["duration_ns"]) for event in events)
    if duration_ns <= 0:
        raise ValueError("collective duration must be positive")
    return {
        "round_id": round_ids.pop(),
        "period": period,
        "route": routes.pop(),
        "version": versions.pop(),
        "duration_ns": duration_ns,
        "duration_s": duration_ns / 1_000_000_000.0,
        "bytes_completed": sum(int(event["bytes_sent"]) for event in events),
        "rank_count": world_size,
        "checksum_errors": sum(int(event.get("checksum_errors", 0)) for event in events),
        "version_errors": sum(int(event.get("version_errors", 0)) for event in events),
    }


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _write_json(path: Path, value: Any) -> None:
    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, indent=2, sort_keys=True)
        handle.write("\n")


def _write_csv(path: Path, fieldnames: Sequence[str], rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


class EventLog:
    def __init__(self, path: Path) -> None:
        self._handle = path.open("w", encoding="utf-8", buffering=1)
        self._lock = threading.Lock()
        self.records: List[Dict[str, Any]] = []

    def append(self, record: Mapping[str, Any]) -> Dict[str, Any]:
        materialized = dict(record)
        with self._lock:
            self.records.append(materialized)
            self._handle.write(json.dumps(materialized, sort_keys=True) + "\n")
        return materialized

    def emit(self, event: str, **payload: Any) -> Dict[str, Any]:
        record = {
            "event": event,
            "source": "orchestrator",
            "t_monotonic_ns": time.monotonic_ns(),
        }
        record.update(payload)
        return self.append(record)

    def close(self) -> None:
        with self._lock:
            self._handle.flush()
            self._handle.close()


@dataclass
class WorkerHandle:
    rank: int
    process: subprocess.Popen
    event_log: EventLog
    stderr_path: Path

    def __post_init__(self) -> None:
        self.events: "queue.Queue[Dict[str, Any]]" = queue.Queue()
        self.pending: List[Dict[str, Any]] = []
        self._stdout_thread = threading.Thread(target=self._read_stdout, daemon=True)
        self._stderr_thread = threading.Thread(target=self._read_stderr, daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

    def _read_stdout(self) -> None:
        assert self.process.stdout is not None
        for line in self.process.stdout:
            try:
                record = json.loads(line)
                if not isinstance(record, dict):
                    raise ValueError("worker event is not a JSON object")
            except (json.JSONDecodeError, ValueError) as exc:
                record = {
                    "event": "WORKER_ERROR",
                    "rank": self.rank,
                    "command": "stdout_parser",
                    "error_type": type(exc).__name__,
                    "error": str(exc),
                    "raw_line": line.rstrip("\n"),
                    "t_monotonic_ns": time.monotonic_ns(),
                }
            record.setdefault("rank", self.rank)
            record["source"] = "worker"
            record["received_t_monotonic_ns"] = time.monotonic_ns()
            self.event_log.append(record)
            self.events.put(record)
        self.events.put(
            {
                "event": "WORKER_EOF",
                "rank": self.rank,
                "returncode": self.process.poll(),
            }
        )

    def _read_stderr(self) -> None:
        assert self.process.stderr is not None
        with self.stderr_path.open("w", encoding="utf-8") as handle:
            for line in self.process.stderr:
                handle.write(line)
                handle.flush()

    def send(self, command: Mapping[str, Any]) -> None:
        if self.process.poll() is not None:
            raise RuntimeError(f"worker {self.rank} exited with {self.process.returncode}")
        assert self.process.stdin is not None
        self.process.stdin.write(json.dumps(dict(command), sort_keys=True) + "\n")
        self.process.stdin.flush()

    def wait_for(self, expected: Sequence[str], timeout_s: float = 90.0) -> Dict[str, Any]:
        expected_set = set(expected)
        for index, record in enumerate(self.pending):
            if record.get("event") in expected_set:
                return self.pending.pop(index)
        deadline = time.monotonic() + timeout_s
        while True:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError(
                    f"worker {self.rank} did not emit {sorted(expected_set)} within {timeout_s}s"
                )
            try:
                record = self.events.get(timeout=remaining)
            except queue.Empty as exc:
                raise TimeoutError(
                    f"worker {self.rank} did not emit {sorted(expected_set)} within {timeout_s}s"
                ) from exc
            event = str(record.get("event"))
            if event == "WORKER_ERROR":
                raise RuntimeError(
                    f"worker {self.rank} error during {record.get('command')}: "
                    f"{record.get('error_type')}: {record.get('error')}"
                )
            if event == "WORKER_EOF":
                raise RuntimeError(
                    f"worker {self.rank} stdout closed; returncode={record.get('returncode')}"
                )
            if event in expected_set:
                return record
            self.pending.append(record)

    def stop(self) -> None:
        if self.process.poll() is None:
            try:
                self.send({"command": "shutdown"})
                self.wait_for(["SHUTDOWN_COMPLETE"], timeout_s=10.0)
            except BaseException:
                pass
        try:
            self.process.wait(timeout=10.0)
        except subprocess.TimeoutExpired:
            self.process.terminate()
            try:
                self.process.wait(timeout=5.0)
            except subprocess.TimeoutExpired:
                self.process.kill()
                self.process.wait(timeout=5.0)
        for stream in (self.process.stdin, self.process.stdout, self.process.stderr):
            if stream is not None and not stream.closed:
                stream.close()
        self._stdout_thread.join(timeout=2.0)
        self._stderr_thread.join(timeout=2.0)


class SwitchSampler:
    def __init__(
        self,
        interfaces: Sequence[str],
        event_log: EventLog,
        poll_interval_s: float = 0.020,
        sentinel_rule: Optional[SentinelRule] = None,
    ) -> None:
        if not interfaces:
            raise ValueError("at least one switch interface is required")
        if poll_interval_s <= 0:
            raise ValueError("poll interval must be positive")
        self.interfaces = list(interfaces)
        self.event_log = event_log
        self.poll_interval_s = poll_interval_s
        self.sentinel_rule = sentinel_rule
        self.records: List[Dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread = threading.Thread(target=self._run, daemon=True)

    def start(self) -> None:
        self._thread.start()

    def _run(self) -> None:
        iteration = 0
        previous_poll_start_ns: Optional[int] = None
        next_deadline = time.monotonic()
        while not self._stop.is_set():
            poll_start_ns = time.monotonic_ns()
            interval_ns = (
                0 if previous_poll_start_ns is None else poll_start_ns - previous_poll_start_ns
            )
            previous_poll_start_ns = poll_start_ns
            for interface in self.interfaces:
                try:
                    sample = sample_qdisc(interface)
                    record = {
                        "poll_iteration": iteration,
                        "poll_start_ns": poll_start_ns,
                        "poll_end_ns": time.monotonic_ns(),
                        "poll_interval_ns": interval_ns,
                        "operstate": read_operstate(interface),
                    }
                    record.update(sample.to_dict())
                    self.records.append(record)
                    if (
                        self.sentinel_rule is not None
                        and interface == self.sentinel_rule.interface
                    ):
                        suspect = self.sentinel_rule.observe(
                            sample, operstate=str(record["operstate"])
                        )
                        if suspect is not None:
                            self.event_log.append(suspect)
                except BaseException as exc:
                    self.event_log.emit(
                        "SWITCH_SAMPLE_ERROR",
                        interface=interface,
                        error_type=type(exc).__name__,
                        error=str(exc),
                    )
            iteration += 1
            next_deadline += self.poll_interval_s
            delay = next_deadline - time.monotonic()
            if delay > 0:
                self._stop.wait(delay)
            else:
                next_deadline = time.monotonic()

    def stop(self) -> None:
        self._stop.set()
        self._thread.join(timeout=5.0)

    def freeze_detector_baseline(self) -> Optional[float]:
        if self.sentinel_rule is None:
            return None
        return self.sentinel_rule.freeze_baseline()


def _launch_workers(
    descriptor: TopologyDescriptor,
    chunk_bytes: int,
    workdir: Path,
    run_dir: Path,
    event_log: EventLog,
) -> List[WorkerHandle]:
    handles: List[WorkerHandle] = []
    for rank in range(WORLD_SIZE):
        command = [
            sys.executable,
            "-u",
            "-m",
            "limer_v0.worker",
            "--rank",
            str(rank),
            "--world-size",
            str(WORLD_SIZE),
            "--chunk-bytes",
            str(chunk_bytes),
        ]
        for route in sorted(descriptor.fabrics):
            command.extend(
                ["--fabric", descriptor.fabrics[route][rank].worker_argument()]
            )
        process = descriptor.hosts[rank].popen(
            command,
            cwd=str(workdir),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            env=dict(os.environ, PYTHONUNBUFFERED="1"),
        )
        handles.append(
            WorkerHandle(rank, process, event_log, run_dir / f"worker_{rank}.stderr.log")
        )
    for handle in handles:
        ready = handle.wait_for(["WORKER_READY"], timeout_s=60.0)
        if sorted(ready.get("fabrics", [])) != sorted(descriptor.fabrics):
            raise RuntimeError(
                f"worker {handle.rank} fabric mismatch: {ready.get('fabrics')}"
            )
    event_log.emit("ALL_WORKERS_READY", ranks=list(range(WORLD_SIZE)))
    return handles


def _run_collective_round(
    handles: Sequence[WorkerHandle],
    round_id: int,
    period: str,
    chunk_bytes: int,
    event_log: EventLog,
) -> tuple[List[Dict[str, Any]], Dict[str, Any]]:
    command_start_ns = time.monotonic_ns()
    command = {
        "command": "run_round",
        "round_id": round_id,
        "chunk_bytes": chunk_bytes,
    }
    event_log.emit("ROUND_COMMAND", round_id=round_id, period=period)
    for handle in handles:
        handle.send(command)
    events = [handle.wait_for(["ROUND_DONE"], timeout_s=120.0) for handle in handles]
    command_end_ns = time.monotonic_ns()
    for event in events:
        event["period"] = period
        event["duration_s"] = int(event["duration_ns"]) / 1_000_000_000.0
        event["orchestrator_command_start_ns"] = command_start_ns
        event["orchestrator_command_end_ns"] = command_end_ns
    aggregate = aggregate_round_events(events, period, world_size=len(handles))
    aggregate["orchestrator_command_start_ns"] = command_start_ns
    aggregate["orchestrator_command_end_ns"] = command_end_ns
    aggregate["orchestrator_duration_ns"] = command_end_ns - command_start_ns
    event_log.emit("ROUND_AGGREGATED", **aggregate)
    return events, aggregate


def _baseline_median_bps(rows: Sequence[Mapping[str, Any]]) -> float:
    throughputs = [
        int(row["bytes_completed"]) * 8.0 / float(row["duration_s"]) for row in rows
    ]
    if not throughputs:
        raise ValueError("baseline has no aggregate rounds")
    return statistics.median(throughputs)


def _p95_duration_s(rows: Sequence[Mapping[str, Any]]) -> float:
    values = sorted(float(row["duration_s"]) for row in rows)
    if not values or values[0] <= 0:
        raise ValueError("positive baseline durations are required")
    if len(values) == 1:
        return values[0]
    return statistics.quantiles(values, n=20, method="inclusive")[18]


def _assess_standby_probe(
    current: Mapping[str, Any], baseline: Mapping[str, Any]
) -> Dict[str, Any]:
    result = dict(current)
    baseline_max = baseline.get("max_latency_ms")
    current_max = current.get("max_latency_ms")
    latency_limit_ms: Optional[float] = None
    latency_ok = False
    if baseline_max is not None and current_max is not None:
        latency_limit_ms = max(float(baseline_max) * 2.0, float(baseline_max) + 2.0)
        latency_ok = float(current_max) <= latency_limit_ms
    result["baseline_max_latency_ms"] = baseline_max
    result["latency_limit_ms"] = latency_limit_ms
    result["healthy"] = bool(current.get("healthy", False)) and latency_ok
    return result


def _execute_handover(
    handles: Sequence[WorkerHandle],
    event_log: EventLog,
    current_round: int,
    effective_round: int,
    prepare_timeout_s: float = 10.0,
) -> TransitionDecision:
    if prepare_timeout_s <= 0:
        raise ValueError("prepare timeout must be positive")
    coordinator = RecoveryCoordinator(world_size=len(handles))
    proposal = coordinator.propose(
        route="B", effective_round=effective_round, current_round=current_round
    )
    event_log.emit(
        "RECOVERY_PROPOSE",
        **proposal.to_dict(),
        prepare_timeout_s=prepare_timeout_s,
        cutover_contract={
            "safe_point": "completed_collective_round_boundary",
            "last_completed_round": current_round,
            "first_new_route_round": effective_round,
            "in_flight_application_frames_at_prepare": 0,
            "old_route_kept_open": True,
            "rollback_allowed_until_effective_round": True,
        },
    )
    command = {
        "command": "prepare",
        "version": proposal.version,
        "route": proposal.route,
        "effective_round": proposal.effective_round,
    }
    for handle in handles:
        handle.send(command)
    prepare_error: Optional[BaseException] = None
    for handle in handles:
        try:
            ready = handle.wait_for(["READY"], timeout_s=prepare_timeout_s)
            if (
                int(ready["version"]) != proposal.version
                or str(ready["route"]) != proposal.route
                or int(ready["effective_round"]) != proposal.effective_round
            ):
                raise RuntimeError(f"worker {handle.rank} returned mismatched READY")
            coordinator.record_ready(handle.rank, proposal.version)
        except BaseException as exc:
            prepare_error = exc
            break
    decision = coordinator.commit_or_abort()
    if decision.action == "abort":
        abort_failures: List[Dict[str, Any]] = []
        for handle in handles:
            try:
                handle.send({"command": "abort", "version": decision.version})
            except BaseException as exc:
                abort_failures.append(
                    {
                        "rank": handle.rank,
                        "stage": "send_abort",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        for handle in handles:
            if any(item["rank"] == handle.rank for item in abort_failures):
                continue
            try:
                handle.wait_for(["ABORTED"], timeout_s=prepare_timeout_s)
            except BaseException as exc:
                abort_failures.append(
                    {
                        "rank": handle.rank,
                        "stage": "wait_abort",
                        "error_type": type(exc).__name__,
                        "error": str(exc),
                    }
                )
        event_log.emit(
            "RECOVERY_ABORT",
            **decision.to_dict(),
            reason=(
                f"prepare failed: {type(prepare_error).__name__}: {prepare_error}"
                if prepare_error is not None
                else "not all ranks became READY before the decision"
            ),
            abort_failures=abort_failures,
            liveness_boundary=(
                "Configuration consistency is restored before the effective round; "
                "forward progress on the degraded old route is not guaranteed."
            ),
        )
        if abort_failures:
            raise RuntimeError(
                "handover abort could not be acknowledged by every rank: "
                + json.dumps(abort_failures, sort_keys=True)
            )
    else:
        for handle in handles:
            handle.send({"command": "commit", "version": decision.version})
        committed_ranks: List[int] = []
        try:
            for handle in handles:
                committed = handle.wait_for(["COMMITTED"], timeout_s=prepare_timeout_s)
                if int(committed["version"]) != decision.version:
                    raise RuntimeError(f"worker {handle.rank} committed a wrong version")
                committed_ranks.append(handle.rank)
        except BaseException as exc:
            rollback_failures: List[Dict[str, Any]] = []
            for handle in handles:
                try:
                    handle.send({"command": "abort", "version": decision.version})
                    handle.wait_for(["ABORTED"], timeout_s=prepare_timeout_s)
                except BaseException as rollback_exc:
                    rollback_failures.append(
                        {
                            "rank": handle.rank,
                            "error_type": type(rollback_exc).__name__,
                            "error": str(rollback_exc),
                        }
                    )
            event_log.emit(
                "RECOVERY_ROLLBACK",
                version=decision.version,
                route=decision.route,
                effective_round=decision.effective_round,
                committed_ranks=committed_ranks,
                reason=f"commit acknowledgement failed: {type(exc).__name__}: {exc}",
                rollback_failures=rollback_failures,
            )
            raise RuntimeError("handover commit failed before the effective round") from exc
        event_log.emit("RECOVERY_COMMIT", **decision.to_dict())
    return decision


def _correctness_report(
    config: Mapping[str, Any],
    worker_rows: Sequence[Mapping[str, Any]],
    aggregate_rows: Sequence[Mapping[str, Any]],
    event_records: Sequence[Mapping[str, Any]],
) -> Dict[str, Any]:
    expected_rounds = (
        int(config["warmup_rounds"])
        + int(config["baseline_rounds"])
        + int(config["post_fault_rounds"])
    )
    worker_errors = [
        dict(record) for record in event_records if record.get("event") == "WORKER_ERROR"
    ]
    route_version_cardinality = {
        str(row["round_id"]): 1 for row in aggregate_rows
    }
    checksum_errors = sum(int(row.get("checksum_errors", 0)) for row in worker_rows)
    version_errors = sum(int(row.get("version_errors", 0)) for row in worker_rows)
    complete = (
        len(aggregate_rows) == expected_rounds
        and len(worker_rows) == expected_rounds * WORLD_SIZE
        and not worker_errors
        and checksum_errors == 0
        and version_errors == 0
        and all(int(row.get("rank_count", 0)) == WORLD_SIZE for row in aggregate_rows)
    )
    return {
        "status": "pass" if complete else "fail",
        "mode": "framed-transport-integrity",
        "expected_collective_rounds": expected_rounds,
        "observed_collective_rounds": len(aggregate_rows),
        "observed_worker_rounds": len(worker_rows),
        "checksum_errors": checksum_errors,
        "version_errors": version_errors,
        "worker_error_count": len(worker_errors),
        "worker_errors": worker_errors,
        "route_version_cardinality": route_version_cardinality,
        "limitation": (
            "This checks framed byte transport and route-version agreement; "
            "it is not the deferred true-reduction correctness mode."
        ),
    }


def _ensure_output_contract(run_dir: Path) -> None:
    if not (run_dir / "switch_timeseries.csv").exists():
        _write_csv(run_dir / "switch_timeseries.csv", SWITCH_CSV_FIELDS, [])
    if not (run_dir / "worker_rounds.csv").exists():
        _write_csv(run_dir / "worker_rounds.csv", WORKER_CSV_FIELDS, [])
    if not (run_dir / "version_commits.csv").exists():
        _write_csv(run_dir / "version_commits.csv", VERSION_CSV_FIELDS, [])
    if not (run_dir / "correctness.json").exists():
        _write_json(run_dir / "correctness.json", {"status": "not_completed"})
    if not (run_dir / "summary.json").exists():
        _write_json(run_dir / "summary.json", {"status": "not_completed"})


def execute_run(
    raw_config: Mapping[str, Any],
    results_dir: Path,
    workdir: Path,
    run_id: Optional[str] = None,
) -> Dict[str, Any]:
    config = validate_config(raw_config)
    if run_id is None:
        run_id = (
            datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
            + f"_{config['condition'].lower()}"
        )
    run_dir = results_dir / run_id
    run_dir.mkdir(parents=True, exist_ok=False)
    manifest: Dict[str, Any] = {
        "schema_version": "limer-cpu-v0.1",
        "run_id": run_id,
        "status": "starting",
        "started_at_utc": _utc_now(),
        "started_t_monotonic_ns": time.monotonic_ns(),
        "config": config,
        "what_changes": config["what_changes"],
        "expected": config["expected"],
        "host": {
            "platform": platform.platform(),
            "python": sys.version,
            "hostname": platform.node(),
        },
        "detector_execution_boundary": {
            "process_placement": "orchestrator/root namespace management-plane proxy",
            "switch_resident": False,
            "data_source": "switch-facing Linux interface counters",
            "resource_budget_enforced": False,
            "claim_boundary": (
                "Demonstrates a switch-counter-first interface and closed-loop "
                "control scaffold; does not satisfy the final switch-hardware "
                "placement or ASIC resource-footprint requirement."
            ),
        },
        "workload": {
            "name": "framed-ring-AllReduce-like",
            "world_size": WORLD_SIZE,
            "steps_per_round": 2 * (WORLD_SIZE - 1),
            "chunk_bytes_per_step_per_rank": config["chunk_bytes"],
            "bytes_per_rank_per_round": config["chunk_bytes"] * 2 * (WORLD_SIZE - 1),
            "metric_denominator": (
                "sum of application payload bytes reported sent by all ranks in a "
                "fully completed round, divided by the slowest rank duration; this "
                "is an aggregate wire-volume proxy, not unique tensor bytes"
            ),
            "retry_accounting": (
                "TCP retransmissions are below the application counter and do not "
                "increase bytes_completed; an incomplete rank makes the run fail"
            ),
        },
    }
    _write_json(run_dir / "manifest.json", manifest)
    event_log = EventLog(run_dir / "events.jsonl")
    descriptor: Optional[TopologyDescriptor] = None
    sampler: Optional[SwitchSampler] = None
    handles: List[WorkerHandle] = []
    worker_rows: List[Dict[str, Any]] = []
    aggregate_rows: List[Dict[str, Any]] = []
    fault_record: Optional[Dict[str, Any]] = None
    standby_baseline_probe: Optional[Dict[str, Any]] = None
    refiner_decision: Optional[RefinerDecision] = None
    transition_decision: Optional[TransitionDecision] = None
    transient_thread: Optional[threading.Thread] = None
    transient_restore_errors: List[Dict[str, str]] = []
    summary: Dict[str, Any] = {"run_id": run_id, "status": "failed"}
    error_record: Optional[Dict[str, str]] = None

    try:
        from mininet.clean import cleanup
        from mininet.log import setLogLevel

        setLogLevel("warning")
        cleanup()
        event_log.emit(
            "RUN_INTENT",
            run_id=run_id,
            condition=config["condition"],
            what_changes=config["what_changes"],
            expected=config["expected"],
        )
        descriptor = build_topology(config["topology"])
        ping = descriptor.ping_ring()
        expected_pings = WORLD_SIZE * len(descriptor.fabrics)
        if ping["successes"] != expected_pings:
            raise RuntimeError(
                f"topology ping failed: {ping['successes']}/{expected_pings}"
            )
        fault_interface = descriptor.fault_interface("A", 2)
        detector_interface = descriptor.detector_interface("A", 2)
        if fault_interface == detector_interface:
            raise RuntimeError("fault injector and detector interfaces must be distinct")
        manifest["topology"] = {
            "kind": descriptor.kind,
            "fabrics": sorted(descriptor.fabrics),
            "fault_route": "A",
            "fault_rank": 2,
            "fault_interface": fault_interface,
            "detector_interface": detector_interface,
            "fault_observation_isolation": {
                "injector_location": "worker-side egress qdisc",
                "detector_location": "peer switch-facing interface counters",
                "same_interface": False,
                "detector_reads_injector_qdisc": False,
                "observed_signal": "switch-port RX byte rate while operstate stays up",
            },
            "ping_successes": ping["successes"],
            "ping_attempts": ping["attempts"],
            "base_profile": {
                "rate_mbit": BASE_PROFILE.rate_mbit,
                "delay_ms": BASE_PROFILE.delay_ms,
                "loss_pct": BASE_PROFILE.loss_pct,
            },
            "profile_records": descriptor.profile_records,
        }
        _write_json(run_dir / "manifest.json", manifest)
        event_log.emit(
            "TOPOLOGY_READY",
            kind=descriptor.kind,
            fault_interface=fault_interface,
            detector_interface=detector_interface,
            ping_successes=ping["successes"],
            ping_attempts=ping["attempts"],
        )
        sentinel_rule = (
            SentinelRule(detector_interface) if config["detector"] else None
        )
        sampler = SwitchSampler(
            [detector_interface],
            event_log,
            poll_interval_s=0.020,
            sentinel_rule=sentinel_rule,
        )
        sampler.start()
        handles = _launch_workers(
            descriptor, config["chunk_bytes"], workdir, run_dir, event_log
        )
        if "B" in descriptor.fabrics:
            standby_baseline_probe = descriptor.ping_fabric("B")
            if not standby_baseline_probe["healthy"]:
                raise RuntimeError("standby fabric B failed its baseline health probe")
            event_log.emit(
                "STANDBY_BASELINE_PROBE",
                route="B",
                probe=standby_baseline_probe,
            )

        round_id = 0
        for period, count in (
            ("warmup", config["warmup_rounds"]),
            ("baseline", config["baseline_rounds"]),
        ):
            for _ in range(count):
                events, aggregate = _run_collective_round(
                    handles, round_id, period, config["chunk_bytes"], event_log
                )
                worker_rows.extend(events)
                aggregate_rows.append(aggregate)
                round_id += 1

        if config["detector"]:
            detector_baseline_bps = sampler.freeze_detector_baseline()
            event_log.emit(
                "SWITCH_BASELINE_FROZEN",
                interface=detector_interface,
                baseline_median_bps=detector_baseline_bps,
                positive_rate_sample_count=(
                    sentinel_rule.calibration_sample_count
                    if sentinel_rule is not None
                    else 0
                ),
                threshold_fraction=(
                    sentinel_rule.threshold_fraction
                    if sentinel_rule is not None
                    else None
                ),
            )

        if config["condition"] == "C0":
            event_log.emit(
                "NO_FAULT_CONTROL",
                fault_interface=fault_interface,
                detector_interface=detector_interface,
                fault_operstate=descriptor.fault_operstate("A", 2),
                detector_operstate=read_operstate(detector_interface),
            )
        else:
            degraded_profile = TcProfile(
                rate_mbit=config["fault_rate_mbit"],
                delay_ms=BASE_PROFILE.delay_ms,
                loss_pct=config["fault_loss_pct"],
            )
            fault_record = descriptor.apply_fault_profile(
                degraded_profile, "A", 2
            )
            event_log.emit(
                "FAULT_APPLIED",
                interface=fault_interface,
                condition=config["condition"],
                record=fault_record,
            )
            if config["transient_ms"]:
                def restore_transient() -> None:
                    time.sleep(config["transient_ms"] / 1000.0)
                    try:
                        restore_record = descriptor.apply_fault_profile(
                            BASE_PROFILE, "A", 2
                        )
                        event_log.emit(
                            "FAULT_RESTORED",
                            interface=fault_interface,
                            record=restore_record,
                        )
                    except BaseException as exc:
                        transient_restore_errors.append(
                            {"error_type": type(exc).__name__, "error": str(exc)}
                        )

                transient_thread = threading.Thread(
                    target=restore_transient, daemon=True
                )
                transient_thread.start()

        baseline_rows_for_gate = [
            row for row in aggregate_rows if row["period"] == "baseline"
        ]
        baseline_p95_s = _p95_duration_s(baseline_rows_for_gate)
        if config["oracle"]:
            event_log.emit(
                "ORACLE_TRIGGER",
                fault_t_monotonic_ns=(
                    fault_record["t_after_ns"] if fault_record is not None else None
                ),
                next_safe_round=round_id,
            )
            transition_decision = _execute_handover(
                handles,
                event_log,
                current_round=round_id - 1,
                effective_round=round_id,
            )

        host_refiner = HostRefiner()
        for _ in range(config["post_fault_rounds"]):
            events, aggregate = _run_collective_round(
                handles, round_id, "post_fault", config["chunk_bytes"], event_log
            )
            worker_rows.extend(events)
            aggregate_rows.append(aggregate)
            round_id += 1

            if (
                config["recovery"]
                and not config["oracle"]
                and transition_decision is None
                and refiner_decision is None
            ):
                switch_suspects_so_far = [
                    record
                    for record in event_log.records
                    if record.get("event") == "SWITCH_SUSPECT"
                ]
                if switch_suspects_so_far:
                    if standby_baseline_probe is None:
                        raise RuntimeError("recovery requires a standby baseline probe")
                    current_probe = descriptor.ping_fabric("B")
                    assessed_probe = _assess_standby_probe(
                        current_probe, standby_baseline_probe
                    )
                    event_log.emit(
                        "STANDBY_CONFIRMATION_PROBE",
                        route="B",
                        probe=assessed_probe,
                    )
                    refiner_decision = host_refiner.evaluate(
                        switch_suspects_so_far[0],
                        aggregate,
                        baseline_p95_s,
                        assessed_probe,
                    )
                    decision_event = {
                        "confirm": "HOST_CONFIRM",
                        "suppress": "RECOVERY_SUPPRESSED",
                        "defer": "HOST_DEFER",
                    }[refiner_decision.action]
                    event_log.emit(
                        decision_event,
                        action=refiner_decision.action,
                        reasons=refiner_decision.reasons,
                        confidence=refiner_decision.confidence,
                        calibration_version=refiner_decision.calibration_version,
                        evaluated_round_id=aggregate["round_id"],
                        evaluated_round_duration_s=aggregate["duration_s"],
                        baseline_p95_s=baseline_p95_s,
                    )
                    if refiner_decision.action == "confirm":
                        transition_decision = _execute_handover(
                            handles,
                            event_log,
                            current_round=int(aggregate["round_id"]),
                            effective_round=round_id,
                        )

        if transient_thread is not None:
            transient_thread.join(timeout=5.0)
            if transient_thread.is_alive():
                raise TimeoutError("transient fault restore did not finish")
            if transient_restore_errors:
                raise RuntimeError(
                    "transient fault restore failed: "
                    + json.dumps(transient_restore_errors, sort_keys=True)
                )

        if config["recovery"] and not config["oracle"] and refiner_decision is None:
            action = "suppress" if config["condition"] == "C5" else "defer"
            reason = (
                "No persistent switch-side suspicion survived the three-sample gate."
            )
            refiner_decision = RefinerDecision(action, [reason])
            event_log.emit(
                "RECOVERY_SUPPRESSED" if action == "suppress" else "HOST_DEFER",
                action=action,
                reasons=refiner_decision.reasons,
                confidence=None,
                calibration_version=None,
                evaluated_round_id=None,
                evaluated_round_duration_s=None,
                baseline_p95_s=baseline_p95_s,
            )

        sampler.stop()
        baseline_rows = [row for row in aggregate_rows if row["period"] == "baseline"]
        post_rows = [row for row in aggregate_rows if row["period"] == "post_fault"]
        baseline_median_bps = _baseline_median_bps(baseline_rows)
        baseline_summary = summarize_rounds(baseline_rows, baseline_median_bps)
        post_summary = summarize_rounds(post_rows, baseline_median_bps)
        fault_window_rows = [row for row in post_rows if row["route"] == "A"]
        post_recovery_rows = [row for row in post_rows if row["route"] == "B"]
        fault_window_summary = (
            summarize_rounds(fault_window_rows, baseline_median_bps)
            if fault_window_rows
            else None
        )
        post_recovery_summary = (
            summarize_rounds(post_recovery_rows, baseline_median_bps)
            if post_recovery_rows
            else None
        )
        correctness = _correctness_report(
            config, worker_rows, aggregate_rows, event_log.records
        )
        _write_json(run_dir / "correctness.json", correctness)
        switch_rows = list(sampler.records)
        actual_intervals_ms = [
            row["poll_interval_ns"] / 1_000_000.0
            for row in switch_rows
            if row["poll_interval_ns"] > 0
        ]
        switch_suspects = [
            dict(record)
            for record in event_log.records
            if record.get("event") == "SWITCH_SUSPECT"
        ]
        fault_t_ns = fault_record["t_after_ns"] if fault_record is not None else None
        first_suspect_t_ns = (
            int(switch_suspects[0]["t_monotonic_ns"])
            if switch_suspects
            else None
        )
        host_decision_events = [
            dict(record)
            for record in event_log.records
            if record.get("event")
            in {"HOST_CONFIRM", "RECOVERY_SUPPRESSED", "HOST_DEFER"}
        ]
        recovery_commit_events = [
            dict(record)
            for record in event_log.records
            if record.get("event") == "RECOVERY_COMMIT"
        ]
        first_host_decision_t_ns = (
            int(host_decision_events[0]["t_monotonic_ns"])
            if host_decision_events
            else None
        )
        first_commit_t_ns = (
            int(recovery_commit_events[0]["t_monotonic_ns"])
            if recovery_commit_events
            else None
        )
        first_recovered_round = (
            min(post_recovery_rows, key=lambda row: int(row["round_id"]))
            if post_recovery_rows
            else None
        )
        summary = {
            "run_id": run_id,
            "status": "complete" if correctness["status"] == "pass" else "failed",
            "condition": config["condition"],
            "topology": config["topology"],
            "fault_interface": fault_interface,
            "detector_interface": detector_interface,
            "fault_applied": fault_record is not None,
            "fault_interface_operstate_after": descriptor.fault_operstate("A", 2),
            "detector_interface_operstate_after": read_operstate(detector_interface),
            "fault_observation_isolation": {
                "same_interface": fault_interface == detector_interface,
                "detector_reads_injector_qdisc": False,
                "injector_location": "worker-side egress qdisc",
                "detector_location": "switch-facing peer interface counters",
                "observed_counter": "rx_bytes",
            },
            "baseline": baseline_summary,
            "post_fault": post_summary,
            "fault_period_retention": post_summary["fault_period_retention"],
            "fault_window": fault_window_summary,
            "post_recovery": post_recovery_summary,
            "post_recovery_retention": (
                post_recovery_summary["post_recovery_retention"]
                if post_recovery_summary is not None
                else None
            ),
            "switch_sampling": {
                "target_interval_ms": 20.0,
                "sample_count": len(switch_rows),
                "median_actual_interval_ms": (
                    statistics.median(actual_intervals_ms) if actual_intervals_ms else None
                ),
                "max_actual_interval_ms": max(actual_intervals_ms) if actual_intervals_ms else None,
            },
            "switch_detection": {
                "enabled": bool(config["detector"]),
                "triggered": bool(switch_suspects),
                "suspect_count": len(switch_suspects),
                "rule_version": (
                    sentinel_rule.rule_version if sentinel_rule is not None else None
                ),
                "interface": detector_interface,
                "execution_boundary": manifest["detector_execution_boundary"],
                "state_proxy": {
                    "monitored_ports": 1,
                    "calibration_rate_samples": (
                        sentinel_rule.calibration_sample_count
                        if sentinel_rule is not None
                        else 0
                    ),
                    "max_consecutive_evidence_samples": (
                        sentinel_rule.consecutive_required
                        if sentinel_rule is not None
                        else 0
                    ),
                    "rss_isolated_or_budgeted": False,
                },
                "baseline_median_bps": (
                    sentinel_rule.baseline_median_bps
                    if sentinel_rule is not None
                    else None
                ),
                "fault_t_monotonic_ns": fault_t_ns,
                "first_suspect_t_monotonic_ns": first_suspect_t_ns,
                "l_switch_ms": (
                    (first_suspect_t_ns - fault_t_ns) / 1_000_000.0
                    if first_suspect_t_ns is not None and fault_t_ns is not None
                    else None
                ),
            },
            "host_refinement": {
                "enabled": bool(config["recovery"] and not config["oracle"]),
                "action": (
                    refiner_decision.action if refiner_decision is not None else None
                ),
                "reasons": (
                    refiner_decision.reasons if refiner_decision is not None else []
                ),
                "confidence": None,
                "baseline_p95_s": baseline_p95_s,
                "decision_t_monotonic_ns": first_host_decision_t_ns,
                "l_host_ms": (
                    (first_host_decision_t_ns - first_suspect_t_ns) / 1_000_000.0
                    if first_host_decision_t_ns is not None
                    and first_suspect_t_ns is not None
                    else None
                ),
            },
            "recovery": {
                "enabled": bool(config["recovery"]),
                "oracle": bool(config["oracle"]),
                "committed": bool(recovery_commit_events),
                "decision": (
                    transition_decision.to_dict()
                    if transition_decision is not None
                    else None
                ),
                "commit_t_monotonic_ns": first_commit_t_ns,
                "l_coordination_ms": (
                    (first_commit_t_ns - first_host_decision_t_ns) / 1_000_000.0
                    if first_commit_t_ns is not None
                    and first_host_decision_t_ns is not None
                    else None
                ),
                "l_fault_to_commit_ms": (
                    (first_commit_t_ns - fault_t_ns) / 1_000_000.0
                    if first_commit_t_ns is not None and fault_t_ns is not None
                    else None
                ),
                "first_recovered_round_id": (
                    int(first_recovered_round["round_id"])
                    if first_recovered_round is not None
                    else None
                ),
                "l_fault_to_recovered_round_complete_ms": (
                    (
                        int(first_recovered_round["orchestrator_command_end_ns"])
                        - fault_t_ns
                    )
                    / 1_000_000.0
                    if first_recovered_round is not None and fault_t_ns is not None
                    else None
                ),
            },
            "correctness_status": correctness["status"],
            "interpretation_boundary": (
                "CPU/Mininet framed AllReduce-like workload; not NCCL, RDMA, "
                "a real GPU cluster, or Huawei switch hardware."
            ),
        }
        _write_json(run_dir / "summary.json", summary)
        _write_csv(run_dir / "switch_timeseries.csv", SWITCH_CSV_FIELDS, switch_rows)
        _write_csv(
            run_dir / "worker_rounds.csv",
            WORKER_CSV_FIELDS,
            (
                dict(row, step_durations_ns=json.dumps(row.get("step_durations_ns", [])))
                for row in worker_rows
            ),
        )
        _write_csv(run_dir / "aggregate_rounds.csv", AGGREGATE_CSV_FIELDS, aggregate_rows)
        version_rows = [
            row
            for row in event_log.records
            if row.get("event")
            in {
                "RECOVERY_PROPOSE",
                "READY",
                "COMMITTED",
                "ABORTED",
                "RECOVERY_COMMIT",
                "RECOVERY_ABORT",
                "RECOVERY_ROLLBACK",
            }
        ]
        _write_csv(run_dir / "version_commits.csv", VERSION_CSV_FIELDS, version_rows)
        manifest["status"] = summary["status"]
    except BaseException as exc:
        error_record = {"error_type": type(exc).__name__, "error": str(exc)}
        event_log.emit("RUN_FAILED", **error_record)
        summary = {
            "run_id": run_id,
            "status": "failed",
            "condition": config["condition"],
            **error_record,
        }
        _write_json(run_dir / "summary.json", summary)
        manifest["status"] = "failed"
        manifest["error"] = error_record
    finally:
        if sampler is not None:
            sampler.stop()
            if not (run_dir / "switch_timeseries.csv").exists():
                _write_csv(
                    run_dir / "switch_timeseries.csv", SWITCH_CSV_FIELDS, sampler.records
                )
        for handle in handles:
            handle.stop()
        if descriptor is not None:
            descriptor.stop()
        try:
            from mininet.clean import cleanup

            cleanup()
        except BaseException as cleanup_exc:
            event_log.emit(
                "CLEANUP_ERROR",
                error_type=type(cleanup_exc).__name__,
                error=str(cleanup_exc),
            )
            if error_record is None:
                summary["cleanup_error"] = str(cleanup_exc)
                summary["status"] = "failed"
                manifest["status"] = "failed"
                _write_json(run_dir / "summary.json", summary)
        manifest["finished_at_utc"] = _utc_now()
        manifest["finished_t_monotonic_ns"] = time.monotonic_ns()
        _write_json(run_dir / "manifest.json", manifest)
        _ensure_output_contract(run_dir)
        event_log.close()
    return summary


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", required=True, type=Path)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--workdir", type=Path, default=Path.cwd())
    parser.add_argument("--run-id")
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    with args.config.open("r", encoding="utf-8") as handle:
        raw_config = json.load(handle)
    summary = execute_run(raw_config, args.results_dir, args.workdir, args.run_id)
    print(json.dumps(summary, indent=2, sort_keys=True))
    return 0 if summary.get("status") == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
