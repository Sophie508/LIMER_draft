"""Replay sentinel rules over preserved switch_timeseries.csv evidence.

Read-only validation harness: replays the legacy and burst-aware detector
rules against every preserved formal run, and optionally reconstructs the
step-level host-gate decision from worker_rounds.csv step durations. Never
modifies run directories.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from limer_v0.qdisc import PortSample
from limer_v0.report import ACTIVE_RUN
from limer_v0.sentinel import BurstAwareSentinelRule, SentinelRule


STEP_SLOWDOWN_FACTOR = 1.5
MIN_SLOW_STEPS = 2


def _events(path: Path) -> List[Dict[str, Any]]:
    return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]


def _first(events: List[Dict[str, Any]], name: str) -> Optional[Dict[str, Any]]:
    return next((event for event in events if event.get("event") == name), None)


def _samples(path: Path) -> List[Tuple[int, PortSample, str]]:
    rows: List[Tuple[int, PortSample, str]] = []
    with path.open() as handle:
        for row in csv.DictReader(handle):
            sample = PortSample(
                interface=row["interface"],
                t_ns=int(row["t_ns"]),
                kind=row["kind"],
                bytes=int(row["bytes"]),
                packets=int(row["packets"]),
                drops=int(row["drops"]),
                overlimits=int(row["overlimits"]),
                requeues=int(row["requeues"]),
                backlog_bytes=int(row["backlog_bytes"]),
                qlen=int(row["qlen"]),
                rx_bytes=int(row["rx_bytes"]),
                rx_packets=int(row["rx_packets"]),
                rx_dropped=int(row["rx_dropped"]),
                tx_bytes=int(row["tx_bytes"]),
                tx_packets=int(row["tx_packets"]),
                tx_dropped=int(row["tx_dropped"]),
            )
            rows.append((int(row["t_ns"]), sample, row["operstate"]))
    return rows


@dataclass
class ReplayResult:
    run_id: str
    freeze_t_ns: Optional[int]
    fault_t_ns: Optional[int]
    trigger_t_ns: Optional[int]
    trigger_mode: Optional[str]
    pre_fault_trigger: bool
    baseline_median_bps: Optional[float]
    degraded_transitions: List[Tuple[int, bool]]

    def trigger_ms_after_fault(self) -> Optional[float]:
        if self.trigger_t_ns is None or self.fault_t_ns is None:
            return None
        return (self.trigger_t_ns - self.fault_t_ns) / 1e6


def replay_rule(run_dir: Path, rule_name: str) -> ReplayResult:
    events = _events(run_dir / "events.jsonl")
    frozen = _first(events, "SWITCH_BASELINE_FROZEN")
    fault = _first(events, "FAULT_APPLIED")
    fault_t_ns = int(fault["record"]["t_after_ns"]) if fault else None
    freeze_t_ns = int(frozen["t_monotonic_ns"]) if frozen else None
    samples = _samples(run_dir / "switch_timeseries.csv")
    interface = samples[0][1].interface if samples else "unknown"
    rule: Any
    if rule_name == "legacy":
        rule = SentinelRule(interface)
    elif rule_name == "burst":
        rule = BurstAwareSentinelRule(interface)
    else:
        raise ValueError(f"unknown rule: {rule_name!r}")

    # Feed calibration exactly as the live run did: everything before the
    # freeze event calibrates, then the baseline freezes.
    trigger_t_ns: Optional[int] = None
    trigger_mode: Optional[str] = None
    pre_fault_trigger = False
    frozen_applied = freeze_t_ns is None
    degraded_transitions: List[Tuple[int, bool]] = []
    last_active = False
    for t_ns, sample, operstate in samples:
        if not frozen_applied and t_ns > freeze_t_ns:
            rule.freeze_baseline()
            frozen_applied = True
        suspect = rule.observe(sample, operstate=operstate)
        if isinstance(rule, BurstAwareSentinelRule):
            active = rule.rate_degraded_burst_active()
            if active != last_active:
                degraded_transitions.append((t_ns, active))
                last_active = active
        if suspect is not None and trigger_t_ns is None:
            trigger_t_ns = int(suspect["t_monotonic_ns"])
            trigger_mode = suspect["signals"].get("mode")
            if fault_t_ns is None or trigger_t_ns < fault_t_ns:
                pre_fault_trigger = True
    return ReplayResult(
        run_id=run_dir.name,
        freeze_t_ns=freeze_t_ns,
        fault_t_ns=fault_t_ns,
        trigger_t_ns=trigger_t_ns,
        trigger_mode=trigger_mode,
        pre_fault_trigger=pre_fault_trigger,
        baseline_median_bps=rule.baseline_median_bps,
        degraded_transitions=degraded_transitions,
    )


def _degraded_active_at(
    transitions: List[Tuple[int, bool]], t_ns: int
) -> bool:
    active = False
    for change_t, state in transitions:
        if change_t > t_ns:
            break
        active = state
    return active


def replay_step_gate(run_dir: Path, replay: ReplayResult) -> Dict[str, Any]:
    """Reconstruct the step-level confirm decision from preserved evidence.

    Historical runs carry no STEP_DONE events, but each rank's per-step
    durations are preserved; step completion times are reconstructed from
    the round's orchestrator command start plus the rank's cumulative step
    durations. Confirm fires at the second distinct slow step whose
    completion lands while the burst-aware rule still reports a degraded
    burst symptom.
    """
    with (run_dir / "worker_rounds.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    with (run_dir / "aggregate_rounds.csv").open() as handle:
        round_start_ns = {
            int(row["round_id"]): int(row["orchestrator_command_start_ns"])
            for row in csv.DictReader(handle)
        }
    baseline_steps: List[float] = []
    for row in rows:
        if row["period"] == "baseline":
            baseline_steps.extend(
                value / 1e9 for value in json.loads(row["step_durations_ns"])
            )
    if not baseline_steps:
        return {"decision": "no-baseline"}
    ordered = sorted(baseline_steps)
    step_p95_s = (
        ordered[0]
        if len(ordered) == 1
        else statistics.quantiles(ordered, n=20, method="inclusive")[18]
    )
    threshold_s = STEP_SLOWDOWN_FACTOR * step_p95_s
    slow_completions: List[Tuple[int, int, int, float]] = []
    for row in rows:
        if row["period"] != "post_fault":
            continue
        cumulative = round_start_ns[int(row["round_id"])]
        for step_id, duration_ns in enumerate(json.loads(row["step_durations_ns"])):
            cumulative += duration_ns
            if duration_ns / 1e9 > threshold_s:
                slow_completions.append(
                    (cumulative, int(row["rank"]), step_id, duration_ns / 1e9)
                )
    slow_completions.sort()
    confirmable = [
        entry
        for entry in slow_completions
        if _degraded_active_at(replay.degraded_transitions, entry[0])
    ]
    confirm_t_ns = confirmable[MIN_SLOW_STEPS - 1][0] if len(confirmable) >= MIN_SLOW_STEPS else None
    return {
        "step_p95_ms": step_p95_s * 1e3,
        "threshold_ms": threshold_s * 1e3,
        "slow_steps": len(slow_completions),
        "slow_steps_while_degraded": len(confirmable),
        "decision": "confirm" if confirm_t_ns is not None else "no-confirm",
        "confirm_ms_after_fault": (
            (confirm_t_ns - replay.fault_t_ns) / 1e6
            if confirm_t_ns is not None and replay.fault_t_ns is not None
            else None
        ),
    }


def main(argv: Optional[List[str]] = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    parser.add_argument("--rule", choices=("legacy", "burst"), default="burst")
    parser.add_argument("--step-gate", action="store_true")
    args = parser.parse_args(argv)
    run_dirs = sorted(
        path
        for path in args.results_dir.iterdir()
        if path.is_dir() and ACTIVE_RUN.fullmatch(path.name)
    )
    report: List[Dict[str, Any]] = []
    for run_dir in run_dirs:
        replay = replay_rule(run_dir, args.rule)
        entry: Dict[str, Any] = {
            "run_id": replay.run_id,
            "rule": args.rule,
            "baseline_median_mbps": (
                replay.baseline_median_bps / 1e6
                if replay.baseline_median_bps is not None
                else None
            ),
            "trigger_ms_after_fault": replay.trigger_ms_after_fault(),
            "trigger_mode": replay.trigger_mode,
            "pre_fault_trigger": replay.pre_fault_trigger,
        }
        if args.step_gate and args.rule == "burst":
            entry["step_gate"] = replay_step_gate(run_dir, replay)
        report.append(entry)
        print(json.dumps(entry, sort_keys=True))
    pre_fault = [entry["run_id"] for entry in report if entry["pre_fault_trigger"]]
    print(
        json.dumps(
            {
                "runs": len(report),
                "pre_fault_triggers": pre_fault,
            },
            sort_keys=True,
        )
    )
    return 1 if pre_fault else 0


if __name__ == "__main__":
    raise SystemExit(main())
