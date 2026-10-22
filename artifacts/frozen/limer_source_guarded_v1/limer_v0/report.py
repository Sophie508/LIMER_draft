"""Aggregate immutable LIMER CPU v0 runs into auditable tables and SVGs."""

from __future__ import annotations

import argparse
import csv
import html
import json
import re
import statistics
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence


FORMAL_RUN = re.compile(r"^c([0-5])_rep([0-9]{2})$")
ACTIVE_RUN = re.compile(
    r"^(aa(?:0_healthy|1_fault|2_detect|3_local|3_global|4_oracle|5_transient"
    r"|6_stepdetect|7_hard|8_grayfast|9_stay|10_switch|11_lossdetect|12_policy|13_lossfast))_rep([0-9]{2})$"
)
REQUIRED_ARTIFACTS = {
    "manifest.json",
    "events.jsonl",
    "switch_timeseries.csv",
    "worker_rounds.csv",
    "aggregate_rounds.csv",
    "version_commits.csv",
    "correctness.json",
    "summary.json",
}
CONDITION_LABELS = {
    "C0": "Fault-free",
    "C1": "Fault / no detector",
    "C2": "Detect only",
    "C3": "Full proxy closed loop",
    "C4": "Oracle recovery",
    "C5": "100 ms transient",
}
ACTIVE_SCENARIO_LABELS = {
    "AA0_HEALTHY": "Fault-free active-active",
    "AA1_FAULT": "Persistent fault / no detector",
    "AA2_DETECT": "Switch detection only",
    "AA3_LOCAL": "Closed-loop localized recovery",
    "AA3_GLOBAL": "Closed-loop global failover baseline",
    "AA4_ORACLE": "Oracle localized recovery",
    "AA5_TRANSIENT": "Transient suppression",
    "AA6_STEPDETECT": "Step-level detection closed loop",
    "AA7_HARD": "Hard link-down immediate failover",
    "AA8_GRAYFAST": "Fast gray step-cutover recovery",
    "AA9_STAY": "Loss fault, stay and retransmit (measurement arm)",
    "AA10_SWITCH": "Loss fault, oracle localized switch (measurement arm)",
    "AA11_LOSSDETECT": "Loss fault, detector armed (detectability measurement)",
    "AA12_POLICY": "Loss fault, switch/stay policy decides (demonstration)",
    "AA13_LOSSFAST": "Loss fault, deep-stall fast detection (latency measurement)",
}
AA6_L_SWITCH_GATE_MS = 200.0
AA6_L_DETECTION_GATE_MS = 1500.0
AA7_L_SWITCH_GATE_MS = 10.0
AA8_L_SWITCH_GATE_MS = 200.0
RESTORE_GATE_MS = 1000.0
GRAY_PROGRESS_GATE_MS = 1300.0
SUMMARY_FIELDS = [
    "run_id",
    "experiment_family",
    "scenario_id",
    "condition",
    "topology",
    "status",
    "correctness_status",
    "link_operstate",
    "detector_operstate",
    "fault_interface",
    "detector_interface",
    "injector_detector_isolated",
    "selected_retention",
    "fault_period_retention",
    "post_recovery_retention",
    "baseline_median_mbit_s",
    "selected_median_mbit_s",
    "switch_triggered",
    "l_switch_ms",
    "host_action",
    "l_host_ms",
    "recovery_committed",
    "l_coordination_ms",
    "l_fault_to_commit_ms",
    "l_detection_ms",
    "l_commit_to_recovered_round_ms",
    "l_fault_to_recovered_round_complete_ms",
    "recovery_policy",
    "changed_slot_count",
    "changed_sender_ranks",
    "active_active_use_passed",
    "locality_passed",
    "checksum_errors",
    "version_errors",
    "gate_pass",
    "gate_failures",
    "run_directory",
]


def _iqr(values: Sequence[float]) -> float:
    if len(values) < 2:
        return 0.0
    quartiles = statistics.quantiles(sorted(values), n=4, method="inclusive")
    return quartiles[2] - quartiles[0]


def select_retention(summary: Mapping[str, Any]) -> float:
    condition = str(summary["condition"])
    scenario = str(summary.get("scenario_id", ""))
    field = (
        "post_recovery_retention"
        if scenario
        in {
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA4_ORACLE",
            "AA6_STEPDETECT",
            "AA7_HARD",
            "AA8_GRAYFAST",
            "AA10_SWITCH",
        }
        or (
            summary.get("experiment_family") != "active_active_v1"
            and condition in {"C3", "C4"}
        )
        else "fault_period_retention"
    )
    value = summary.get(field)
    if value is None:
        raise ValueError(f"{condition} is missing {field}")
    return float(value)


def evaluate_run(summary: Mapping[str, Any]) -> List[str]:
    failures: List[str] = []
    condition = str(summary.get("condition"))
    if summary.get("status") != "complete":
        failures.append("run status must be complete")
    if summary.get("correctness_status") != "pass":
        failures.append("correctness must pass")
    fault_kind = str(summary.get("fault_kind", "rate_cap"))
    if fault_kind == "link_down":
        # A hard fault is only real if the port actually went down; the
        # switch-side peer of a downed access link cannot stay up either.
        if summary.get("fault_interface_operstate_after") == "up":
            failures.append("link_down fault interface must actually be down")
        if summary.get("detector_interface_operstate_after") == "up":
            failures.append("link_down detector interface must reflect carrier loss")
    else:
        if summary.get("fault_interface_operstate_after") != "up":
            failures.append("fault interface must remain up")
        if summary.get("detector_interface_operstate_after") != "up":
            failures.append("detector interface must remain up")
    isolation = summary.get("fault_observation_isolation", {})
    if isolation.get("same_interface") is not False:
        failures.append("fault injector and detector interfaces must be distinct")
    if isolation.get("detector_reads_injector_qdisc") is not False:
        failures.append("detector must not read the injector qdisc")
    try:
        selected = select_retention(summary)
    except (KeyError, TypeError, ValueError) as exc:
        failures.append(str(exc))
        return failures

    detection = summary.get("switch_detection", {})
    host = summary.get("host_refinement", {})
    recovery = summary.get("recovery", {})
    if summary.get("experiment_family") == "active_active_v1":
        scenario = str(summary.get("scenario_id"))
        routing = summary.get("routing") or {}
        changed_slots = list(routing.get("changed_slots") or [])
        changed_ranks = sorted(
            {int(change.get("sender_rank", -1)) for change in changed_slots}
        )
        if routing.get("initial_policy") != "balanced_active_active":
            failures.append("v1 initial routing must be balanced active-active")
        latency_target = (summary.get("latency") or {}).get("latency_target") or {}
        if latency_target.get("numeric_target_ms") is not None:
            failures.append("numeric latency target must remain unspecified")

        if scenario == "AA0_HEALTHY":
            if not 0.8 <= selected <= 1.2:
                failures.append("AA0 retention must stay within [0.8, 1.2]")
            if recovery.get("committed"):
                failures.append("AA0 must not commit recovery")
        elif scenario == "AA1_FAULT":
            if selected >= 0.8:
                failures.append("AA1 must show measurable degradation below 0.8")
            if detection.get("triggered") or recovery.get("committed"):
                failures.append("AA1 must not detect or recover")
        elif scenario == "AA2_DETECT":
            if not detection.get("triggered"):
                failures.append("AA2 switch detector must trigger")
            if recovery.get("committed"):
                failures.append("AA2 must not commit recovery")
            if selected >= 0.8:
                failures.append("AA2 must remain degraded below 0.8")
        elif scenario in {
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA6_STEPDETECT",
            "AA7_HARD",
            "AA8_GRAYFAST",
        }:
            if not detection.get("triggered"):
                failures.append(f"{scenario} switch detector must trigger")
            if host.get("action") != "confirm":
                failures.append(f"{scenario} host gate must confirm")
            if not recovery.get("committed"):
                failures.append(f"{scenario} recovery must commit")
            if selected < 0.9:
                failures.append(f"{scenario} post-recovery retention must be at least 0.9")
            if scenario in {"AA3_LOCAL", "AA6_STEPDETECT", "AA8_GRAYFAST"} and (
                len(changed_slots) != 3 or changed_ranks != [2]
            ):
                failures.append(
                    f"{scenario} must change exactly three worker 2 route slots"
                )
            if scenario == "AA7_HARD" and (
                len(changed_slots) != 6 or changed_ranks != [1, 2]
            ):
                failures.append(
                    "AA7_HARD must move exactly the six slots that traverse "
                    "the failed access link (senders 1 and 2)"
                )
            if scenario == "AA6_STEPDETECT":
                l_switch = (summary.get("latency") or {}).get("l_switch_ms")
                if l_switch is None or float(l_switch) >= AA6_L_SWITCH_GATE_MS:
                    failures.append(
                        "AA6 switch suspicion must land within "
                        f"{AA6_L_SWITCH_GATE_MS:.0f} ms"
                    )
                l_detection = (summary.get("latency") or {}).get("l_detection_ms")
                if (
                    l_detection is None
                    or float(l_detection) >= AA6_L_DETECTION_GATE_MS
                ):
                    failures.append(
                        "AA6 fault-to-confirm must land within "
                        f"{AA6_L_DETECTION_GATE_MS:.0f} ms"
                    )
                if host.get("gate_mode") != "step":
                    failures.append("AA6 host gate must run in step mode")
            if scenario in {"AA7_HARD", "AA8_GRAYFAST"}:
                latency_block = summary.get("latency") or {}
                l_switch = latency_block.get("l_switch_ms")
                switch_gate = (
                    AA7_L_SWITCH_GATE_MS
                    if scenario == "AA7_HARD"
                    else AA8_L_SWITCH_GATE_MS
                )
                if l_switch is None or float(l_switch) >= switch_gate:
                    failures.append(
                        f"{scenario} switch suspicion must land within "
                        f"{switch_gate:.0f} ms"
                    )
                traffic_off = latency_block.get("l_suspect_to_commit_ms")
                if traffic_off is None or float(traffic_off) >= RESTORE_GATE_MS:
                    failures.append(
                        f"{scenario} must take traffic off the failed port "
                        f"within {RESTORE_GATE_MS:.0f} ms of detection"
                    )
                progress_gate = (
                    RESTORE_GATE_MS
                    if scenario == "AA7_HARD"
                    else GRAY_PROGRESS_GATE_MS
                )
                restore = latency_block.get("l_suspect_to_first_recovered_step_ms")
                if restore is None or float(restore) >= progress_gate:
                    failures.append(
                        f"{scenario} must complete a recovered-plan step within "
                        f"{progress_gate:.0f} ms of detection"
                    )
                expected_mode = (
                    "immediate" if scenario == "AA7_HARD" else "step_cutover"
                )
                if host.get("gate_mode") != expected_mode:
                    failures.append(
                        f"{scenario} host gate must run in {expected_mode} mode"
                    )
            if scenario == "AA3_GLOBAL" and (
                len(changed_slots) != 12 or changed_ranks != [0, 1, 2, 3]
            ):
                failures.append(
                    "AA3_GLOBAL must change all twelve baseline-A route slots"
                )
        elif scenario == "AA4_ORACLE":
            if not recovery.get("committed"):
                failures.append("AA4 oracle recovery must commit")
            if selected < 0.9:
                failures.append("AA4 post-recovery retention must be at least 0.9")
            if len(changed_slots) != 3 or changed_ranks != [2]:
                failures.append(
                    "AA4_ORACLE must change exactly three worker 2 route slots"
                )
        elif scenario == "AA12_POLICY":
            # Policy demonstration: the branch taken depends on the arm's
            # topology, so the machine gate only requires that a policy
            # decision was actually made and correctness held; the branch
            # expectations are asserted by the campaign analysis.
            if host.get("action") not in {"confirm", "suppress"}:
                failures.append("AA12_POLICY must reach a policy decision")
        elif scenario == "AA13_LOSSFAST":
            # Detection-latency measurement with the deep-stall fast path;
            # latency is the measured quantity, recovery stays off.
            if recovery.get("committed"):
                failures.append("AA13_LOSSFAST must not commit recovery")
        elif scenario == "AA11_LOSSDETECT":
            # Detectability measurement: whether the burst rule fires on a
            # loss-type fault IS the measured quantity, so neither a trigger
            # nor a retention bound is asserted; recovery must stay off.
            if recovery.get("committed"):
                failures.append("AA11_LOSSDETECT must not commit recovery")
        elif scenario == "AA9_STAY":
            # Measurement arm: quantify staying on a lossy link. Retention is
            # the measured quantity, so it carries no pass bound here.
            if detection.get("triggered") or recovery.get("committed"):
                failures.append("AA9_STAY must not detect or recover")
        elif scenario == "AA10_SWITCH":
            # Measurement arm: quantify the cost of switching. Locality still
            # gates; retention is the measured quantity, so no bound.
            if not recovery.get("committed"):
                failures.append("AA10_SWITCH oracle recovery must commit")
            if len(changed_slots) != 3 or changed_ranks != [2]:
                failures.append(
                    "AA10_SWITCH must change exactly three worker 2 route slots"
                )
        elif scenario == "AA5_TRANSIENT":
            if host.get("action") != "suppress":
                failures.append("AA5 host gate must suppress")
            if recovery.get("committed"):
                failures.append("AA5 must not commit recovery")
        else:
            failures.append(f"unsupported active-active scenario: {scenario}")
        return failures

    if condition == "C0":
        if not 0.8 <= selected <= 1.2:
            failures.append("C0 retention must stay within [0.8, 1.2]")
    elif condition == "C1":
        if selected >= 0.6:
            failures.append("C1 retention must be below 0.6")
    elif condition == "C2":
        if not detection.get("triggered"):
            failures.append("C2 switch detector must trigger")
        if selected >= 0.6:
            failures.append("C2 must remain degraded below 0.6")
    elif condition == "C3":
        if not detection.get("triggered"):
            failures.append("C3 switch detector must trigger")
        if host.get("action") != "confirm":
            failures.append("C3 host gate must confirm")
        if not recovery.get("committed"):
            failures.append("C3 recovery must commit")
        if selected < 0.9:
            failures.append("C3 post-recovery retention must be at least 0.9")
    elif condition == "C4":
        if not recovery.get("committed"):
            failures.append("C4 oracle recovery must commit")
        if selected < 0.9:
            failures.append("C4 post-recovery retention must be at least 0.9")
    elif condition == "C5":
        if host.get("action") != "suppress":
            failures.append("C5 host gate must suppress")
        if recovery.get("committed"):
            failures.append("C5 must not commit recovery")
    else:
        failures.append(f"unsupported condition: {condition}")
    return failures


def _json(path: Path) -> Dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        value = json.load(handle)
    if not isinstance(value, dict):
        raise ValueError(f"expected JSON object: {path}")
    return value


def _events(path: Path) -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            try:
                value = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"invalid event JSON at {path}:{line_number}") from exc
            if not isinstance(value, dict):
                raise ValueError(f"non-object event at {path}:{line_number}")
            records.append(value)
    return records


def _selected_throughput(summary: Mapping[str, Any]) -> Optional[float]:
    scenario = str(summary.get("scenario_id", ""))
    section = (
        "post_recovery"
        if scenario
        in {
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA4_ORACLE",
            "AA6_STEPDETECT",
            "AA7_HARD",
            "AA8_GRAYFAST",
            "AA10_SWITCH",
        }
        or (
            summary.get("experiment_family") != "active_active_v1"
            and summary["condition"] in {"C3", "C4"}
        )
        else "post_fault"
    )
    value = summary.get(section)
    if not isinstance(value, dict):
        return None
    throughput = value.get("median_throughput_bps")
    return None if throughput is None else float(throughput) / 1_000_000.0


def _row(run_dir: Path) -> Dict[str, Any]:
    missing = sorted(REQUIRED_ARTIFACTS - {path.name for path in run_dir.iterdir()})
    if missing:
        raise ValueError(f"{run_dir.name} missing artifacts: {', '.join(missing)}")
    summary = _json(run_dir / "summary.json")
    correctness = _json(run_dir / "correctness.json")
    if summary.get("run_id") != run_dir.name:
        raise ValueError(f"run_id mismatch in {run_dir}")
    failures = evaluate_run(summary)
    baseline = summary.get("baseline") or {}
    detection = summary.get("switch_detection") or {}
    host = summary.get("host_refinement") or {}
    recovery = summary.get("recovery") or {}
    isolation = summary.get("fault_observation_isolation") or {}
    try:
        selected_retention: Optional[float] = select_retention(summary)
    except (KeyError, TypeError, ValueError):
        selected_retention = None
    latency = summary.get("latency") or {}
    routing = summary.get("routing") or {}
    active_use = correctness.get("active_active_use") or {}
    locality = correctness.get("locality") or {}
    return {
        "run_id": run_dir.name,
        "experiment_family": summary.get("experiment_family", "legacy_v0"),
        "scenario_id": summary.get("scenario_id", summary.get("condition")),
        "condition": summary.get("condition"),
        "topology": summary.get("topology"),
        "status": summary.get("status"),
        "correctness_status": summary.get("correctness_status"),
        "link_operstate": summary.get("fault_interface_operstate_after"),
        "detector_operstate": summary.get("detector_interface_operstate_after"),
        "fault_interface": summary.get("fault_interface"),
        "detector_interface": summary.get("detector_interface"),
        "injector_detector_isolated": (
            isolation.get("same_interface") is False
            and isolation.get("detector_reads_injector_qdisc") is False
        ),
        "selected_retention": selected_retention,
        "fault_period_retention": summary.get("fault_period_retention"),
        "post_recovery_retention": summary.get("post_recovery_retention"),
        "baseline_median_mbit_s": (
            float(baseline["median_throughput_bps"]) / 1_000_000.0
            if baseline.get("median_throughput_bps") is not None
            else None
        ),
        "selected_median_mbit_s": _selected_throughput(summary),
        "switch_triggered": bool(detection.get("triggered")),
        "l_switch_ms": detection.get("l_switch_ms"),
        "host_action": host.get("action"),
        "l_host_ms": host.get("l_host_ms"),
        "recovery_committed": bool(recovery.get("committed")),
        "l_coordination_ms": recovery.get("l_coordination_ms"),
        "l_fault_to_commit_ms": recovery.get("l_fault_to_commit_ms"),
        "l_detection_ms": latency.get("l_detection_ms"),
        "l_commit_to_recovered_round_ms": latency.get(
            "l_commit_to_recovered_round_ms"
        ),
        "l_fault_to_recovered_round_complete_ms": latency.get(
            "l_fault_to_recovered_round_complete_ms"
        ),
        "recovery_policy": routing.get("recovery_policy"),
        "changed_slot_count": len(routing.get("changed_slots") or []),
        "changed_sender_ranks": json.dumps(
            sorted(
                {
                    int(change.get("sender_rank", -1))
                    for change in routing.get("changed_slots") or []
                }
            )
        ),
        "active_active_use_passed": active_use.get("passed"),
        "locality_passed": locality.get("passed"),
        "checksum_errors": int(correctness.get("checksum_errors", -1)),
        "version_errors": int(correctness.get("version_errors", -1)),
        "gate_pass": not failures,
        "gate_failures": " | ".join(failures),
        "run_directory": str(run_dir),
    }


def render_throughput_svg(
    groups: Mapping[str, Sequence[float]],
    labels: Optional[Mapping[str, str]] = None,
    title: str = "LIMER CPU v0: selected performance retention",
    subtitle: str = (
        "CPU/Mininet framed AllReduce-like; C3/C4 use post-recovery, "
        "others use post-marker/fault"
    ),
) -> str:
    width, height = 940, 520
    left, top, chart_w, chart_h = 82, 70, 800, 330
    ymax = 1.2
    labels = CONDITION_LABELS if labels is None else labels
    conditions = [condition for condition in labels if groups.get(condition)]
    slot = chart_w / max(1, len(conditions))
    legacy_colors = {
        "C0": "#5b8ff9",
        "C1": "#e8684a",
        "C2": "#f6bd16",
        "C3": "#5ad8a6",
        "C4": "#5d7092",
        "C5": "#6dc8ec",
    }
    palette = ["#5b8ff9", "#e8684a", "#f6bd16", "#5ad8a6", "#5d7092", "#6dc8ec", "#9270ca"]
    colors = {
        condition: legacy_colors.get(condition, palette[index % len(palette)])
        for index, condition in enumerate(conditions)
    }
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="470" y="30" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">{html.escape(title)}</text>',
        f'<text x="470" y="51" text-anchor="middle" font-family="sans-serif" font-size="12">{html.escape(subtitle)}</text>',
    ]
    for tick in (0.0, 0.2, 0.4, 0.6, 0.8, 1.0, 1.2):
        y = top + chart_h - (tick / ymax) * chart_h
        lines.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{left + chart_w}" y2="{y:.1f}" stroke="#dddddd"/>'
        )
        lines.append(
            f'<text x="{left - 10}" y="{y + 4:.1f}" text-anchor="end" font-family="sans-serif" font-size="11">{tick:.1f}</text>'
        )
    lines.append(
        f'<line x1="{left}" y1="{top}" x2="{left}" y2="{top + chart_h}" stroke="#333"/>'
    )
    lines.append(
        f'<line x1="{left}" y1="{top + chart_h}" x2="{left + chart_w}" y2="{top + chart_h}" stroke="#333"/>'
    )
    for index, condition in enumerate(conditions):
        values = [float(value) for value in groups[condition]]
        median = statistics.median(values)
        bar_h = min(median, ymax) / ymax * chart_h
        x = left + index * slot + slot * 0.22
        y = top + chart_h - bar_h
        bar_w = slot * 0.56
        lines.append(
            f'<rect x="{x:.1f}" y="{y:.1f}" width="{bar_w:.1f}" height="{bar_h:.1f}" fill="{colors[condition]}" rx="3"/>'
        )
        for point_index, value in enumerate(values):
            px = x + bar_w * (0.25 + 0.25 * point_index)
            py = top + chart_h - min(value, ymax) / ymax * chart_h
            lines.append(
                f'<circle cx="{px:.1f}" cy="{py:.1f}" r="3.5" fill="#222"/>'
            )
        lines.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{y - 8:.1f}" text-anchor="middle" font-family="sans-serif" font-size="12">{median:.3f}</text>'
        )
        lines.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + chart_h + 20}" text-anchor="middle" font-family="sans-serif" font-size="12" font-weight="bold">{condition}</text>'
        )
        lines.append(
            f'<text x="{x + bar_w / 2:.1f}" y="{top + chart_h + 37}" text-anchor="middle" font-family="sans-serif" font-size="10">{html.escape(labels[condition])}</text>'
        )
    lines.extend(
        [
            '<text x="20" y="235" transform="rotate(-90 20 235)" text-anchor="middle" font-family="sans-serif" font-size="12">Retention vs matched pre-fault baseline</text>',
            '<text x="470" y="485" text-anchor="middle" font-family="sans-serif" font-size="11">Dots are three independent formal runs; bars are medians. Dual-fabric recovery assumption applies to C3/C4.</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def render_timeline_svg(summary: Mapping[str, Any], events: Sequence[Mapping[str, Any]]) -> str:
    fault_event = next(event for event in events if event.get("event") == "FAULT_APPLIED")
    fault_t = int(fault_event["record"]["t_after_ns"])
    names = [
        ("SWITCH_SUSPECT", "L1 switch suspect"),
        ("HOST_CONFIRM", "L2 host confirm"),
        ("RECOVERY_COMMIT", "All-rank commit"),
    ]
    points = [("Fault applied", 0.0)]
    for event_name, label in names:
        event = next(event for event in events if event.get("event") == event_name)
        points.append((label, (int(event["t_monotonic_ns"]) - fault_t) / 1_000_000.0))
    active_v1 = summary.get("experiment_family") == "active_active_v1"
    latency = summary.get("latency") or {}
    recovered_value = latency.get("l_fault_to_recovered_round_complete_ms")
    if recovered_value is None:
        recovered_value = summary["recovery"][
            "l_fault_to_recovered_round_complete_ms"
        ]
    recovered_ms = float(recovered_value)
    points.append(
        (
            "First localized-plan round complete"
            if active_v1
            else "First B round complete",
            recovered_ms,
        )
    )
    width, height = 960, 360
    left, right, axis_y = 100, 900, 180
    xmax = max(value for _label, value in points) * 1.08
    lines = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" viewBox="0 0 {width} {height}">',
        '<rect width="100%" height="100%" fill="white"/>',
        f'<text x="480" y="32" text-anchor="middle" font-family="sans-serif" font-size="20" font-weight="bold">{html.escape(str(summary.get("scenario_id", "C3")))} event timeline: {html.escape(str(summary["run_id"]))}</text>',
        (
            '<text x="480" y="54" text-anchor="middle" font-family="sans-serif" font-size="12">CPU/Mininet AllReduce-like; active-active baseline and coordinated localized route plan</text>'
            if active_v1
            else '<text x="480" y="54" text-anchor="middle" font-family="sans-serif" font-size="12">CPU/Mininet AllReduce-like; fabric A gray degradation, coordinated whole-ring switch to fabric B</text>'
        ),
        f'<line x1="{left}" y1="{axis_y}" x2="{right}" y2="{axis_y}" stroke="#333" stroke-width="2"/>',
    ]
    colors = ["#e8684a", "#f6bd16", "#5b8ff9", "#5ad8a6", "#5d7092"]
    for index, (label, value) in enumerate(points):
        x = left + (value / xmax) * (right - left) if xmax else left
        y_text = 110 if index % 2 == 0 else 245
        y_line_end = 128 if index % 2 == 0 else 224
        lines.append(
            f'<line x1="{x:.1f}" y1="{axis_y}" x2="{x:.1f}" y2="{y_line_end}" stroke="{colors[index]}" stroke-width="2"/>'
        )
        lines.append(
            f'<circle cx="{x:.1f}" cy="{axis_y}" r="7" fill="{colors[index]}"/>'
        )
        lines.append(
            f'<text x="{x:.1f}" y="{y_text}" text-anchor="middle" font-family="sans-serif" font-size="11">{html.escape(label)}</text>'
        )
        lines.append(
            f'<text x="{x:.1f}" y="{y_text + 16}" text-anchor="middle" font-family="sans-serif" font-size="10">{value:.1f} ms</text>'
        )
    lines.extend(
        [
            '<text x="480" y="318" text-anchor="middle" font-family="sans-serif" font-size="11">Measured limitation: host confirmation waits for the degraded round to finish; this dominates end-to-end recovery latency.</text>',
            "</svg>",
        ]
    )
    return "\n".join(lines) + "\n"


def _write_csv(path: Path, rows: Iterable[Mapping[str, Any]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_FIELDS)
        writer.writeheader()
        for row in rows:
            writer.writerow(dict(row))


def _generate_active_active_report(
    results_dir: Path, run_dirs: Sequence[Path]
) -> Dict[str, Any]:
    rows = [_row(path) for path in run_dirs]
    scenario_rows: Dict[str, List[Dict[str, Any]]] = {
        scenario: [] for scenario in ACTIVE_SCENARIO_LABELS
    }
    for row in rows:
        scenario = str(row["scenario_id"])
        if scenario not in scenario_rows:
            raise ValueError(f"unsupported active-active scenario: {scenario}")
        scenario_rows[scenario].append(row)

    aggregate_scenarios: Dict[str, Any] = {}
    plot_groups: Dict[str, List[float]] = {}
    for scenario, relevant in scenario_rows.items():
        values = [
            float(row["selected_retention"])
            for row in relevant
            if row["selected_retention"] is not None
        ]
        plot_groups[scenario] = values
        aggregate_scenarios[scenario] = {
            "label": ACTIVE_SCENARIO_LABELS[scenario],
            "run_count": len(relevant),
            "measured_retention_count": len(values),
            "gate_pass_count": sum(bool(row["gate_pass"]) for row in relevant),
            "retention_values": values,
            "median_retention": statistics.median(values) if values else None,
            "iqr_retention": _iqr(values),
            "l_switch_ms_values": [
                float(row["l_switch_ms"])
                for row in relevant
                if row["l_switch_ms"] is not None
            ],
            "l_detection_ms_values": [
                float(row["l_detection_ms"])
                for row in relevant
                if row["l_detection_ms"] is not None
            ],
            "l_coordination_ms_values": [
                float(row["l_coordination_ms"])
                for row in relevant
                if row["l_coordination_ms"] is not None
            ],
            "l_fault_to_recovered_round_complete_ms_values": [
                float(row["l_fault_to_recovered_round_complete_ms"])
                for row in relevant
                if row["l_fault_to_recovered_round_complete_ms"] is not None
            ],
            "checksum_errors": sum(int(row["checksum_errors"]) for row in relevant),
            "version_errors": sum(int(row["version_errors"]) for row in relevant),
        }

    present_scenarios = [
        scenario
        for scenario in ACTIVE_SCENARIO_LABELS
        if scenario_rows[scenario]
    ]
    absent_scenarios = [
        scenario
        for scenario in ACTIVE_SCENARIO_LABELS
        if not scenario_rows[scenario]
    ]
    expected_run_count = 3 * len(present_scenarios)
    count_gate = bool(present_scenarios) and all(
        len(scenario_rows[scenario]) == 3 for scenario in present_scenarios
    )
    run_gates = bool(rows) and all(bool(row["gate_pass"]) for row in rows)
    aggregate = {
        "schema_version": "limer-cpu-active-active-report.1",
        "experiment_family": "active_active_v1",
        "formal_run_pattern": ACTIVE_RUN.pattern,
        "formal_run_count": len(rows),
        "expected_formal_run_count": expected_run_count,
        "scenarios_present": present_scenarios,
        "scenarios_absent": absent_scenarios,
        "three_runs_per_scenario": count_gate,
        "all_run_gates_pass": run_gates,
        "overall_acceptance": (
            count_gate and run_gates and len(rows) == expected_run_count
        ),
        "latency_target": {
            "unit": "ms",
            "numeric_target_ms": None,
            "status": "not_formally_specified",
        },
        "gate_scope": (
            "Four-worker CPU/Mininet active-active route-plan semantics, raw "
            "latency stages, framed transport, and performance retention only."
        ),
        "scenarios": aggregate_scenarios,
        "metric_definition": (
            "Recovery scenarios use post-recovery throughput; other scenarios "
            "use post-marker or fault-window throughput. Every value is divided "
            "by the same run's balanced active-active pre-fault median."
        ),
        "interpretation_boundary": (
            "CPU/Mininet framed AllReduce-like traffic with a directed worker-2 "
            "Fabric-A egress degradation; not a bidirectional cable fault, NCCL, "
            "RDMA, real GPUs, or switch-resident detection."
        ),
    }

    _write_csv(results_dir / "summary.csv", rows)
    with (results_dir / "aggregate_summary.json").open(
        "w", encoding="utf-8"
    ) as handle:
        json.dump(aggregate, handle, indent=2, sort_keys=True)
        handle.write("\n")

    throughput_svg = render_throughput_svg(
        plot_groups,
        labels=ACTIVE_SCENARIO_LABELS,
        title="LIMER active-active v1: selected performance retention",
        subtitle=(
            "Balanced A/B fault-free baseline; localized recovery compared with "
            "the global-failover baseline"
        ),
    )
    (results_dir / "throughput.svg").write_text(throughput_svg, encoding="utf-8")

    representative = results_dir / "aa3_local_rep01"
    if representative.is_dir():
        representative_summary = _json(representative / "summary.json")
        try:
            timeline_svg = render_timeline_svg(
                representative_summary,
                _events(representative / "events.jsonl"),
            )
        except (KeyError, StopIteration, TypeError, ValueError):
            timeline_svg = (
                '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="180">'
                '<rect width="100%" height="100%" fill="white"/>'
                '<text x="480" y="90" text-anchor="middle" font-family="sans-serif">'
                "AA3_LOCAL timeline unavailable because the representative run is incomplete."
                "</text></svg>\n"
            )
    else:
        timeline_svg = (
            '<svg xmlns="http://www.w3.org/2000/svg" width="960" height="180">'
            '<rect width="100%" height="100%" fill="white"/>'
            '<text x="480" y="90" text-anchor="middle" font-family="sans-serif">'
            "AA3_LOCAL representative run is missing.</text></svg>\n"
        )
    (results_dir / "timeline.svg").write_text(timeline_svg, encoding="utf-8")
    ET.fromstring(throughput_svg)
    ET.fromstring(timeline_svg)

    readme_lines = [
        "# LIMER active-active v1 results",
        "",
        "These results are generated from preserved run directories; failed repeats are not discarded.",
        (
            "Run-level experiment matrix: **PASS**."
            if aggregate["overall_acceptance"]
            else "Run-level experiment matrix: **NOT ALL PREDECLARED GATES PASS**; inspect the denominator, gate column, and raw run folders."
        ),
        "The numeric millisecond target is not formally specified; raw latency stages are reported without an invented threshold.",
        "The impairment is worker 2's directed Fabric A egress while operstate remains UP.",
        "",
        "| Scenario | Runs | Median selected retention | Gate pass |",
        "|---|---:|---:|---:|",
    ]
    for scenario, label in ACTIVE_SCENARIO_LABELS.items():
        entry = aggregate_scenarios[scenario]
        median = entry["median_retention"]
        median_text = "n/a" if median is None else f"{median:.3f}"
        readme_lines.append(
            f"| {scenario} {label} | {entry['run_count']} | {median_text} | "
            f"{entry['gate_pass_count']}/{entry['run_count']} |"
        )
    failed_rows = [row for row in rows if not bool(row["gate_pass"])]
    if failed_rows:
        readme_lines.extend(["", "Observed gate failures:", ""])
        for row in failed_rows:
            retention = row["selected_retention"]
            retention_text = "n/a" if retention is None else f"{float(retention):.3f}"
            readme_lines.append(
                f"- `{row['run_id']}`: {row['gate_failures']} "
                f"(selected retention {retention_text})."
            )
    readme_lines.extend(
        [
            "",
            "Artifacts:",
            "",
            "- `summary.csv`: one row per discovered formal run.",
            "- `aggregate_summary.json`: scenario denominators, raw values, and gate accounting.",
            "- `throughput.svg`: retention by scenario.",
            "- `timeline.svg`: AA3_LOCAL event timing when the representative run is complete.",
            "",
            "This remains a CPU framed-transport prototype, not numerical NCCL AllReduce.",
        ]
    )
    (results_dir / "README.md").write_text(
        "\n".join(readme_lines) + "\n", encoding="utf-8"
    )
    return aggregate


def generate_report(results_dir: Path) -> Dict[str, Any]:
    active_dirs = sorted(
        path
        for path in results_dir.iterdir()
        if path.is_dir() and ACTIVE_RUN.fullmatch(path.name)
    )
    if active_dirs:
        return _generate_active_active_report(results_dir, active_dirs)
    formal_dirs = sorted(
        path
        for path in results_dir.iterdir()
        if path.is_dir() and FORMAL_RUN.fullmatch(path.name)
    )
    rows = [_row(path) for path in formal_dirs]
    groups: Dict[str, List[float]] = {condition: [] for condition in CONDITION_LABELS}
    condition_rows: Dict[str, List[Dict[str, Any]]] = {
        condition: [] for condition in CONDITION_LABELS
    }
    for row in rows:
        condition = str(row["condition"])
        groups[condition].append(float(row["selected_retention"]))
        condition_rows[condition].append(row)
    aggregate_conditions: Dict[str, Any] = {}
    for condition, values in groups.items():
        relevant = condition_rows[condition]
        aggregate_conditions[condition] = {
            "label": CONDITION_LABELS[condition],
            "run_count": len(values),
            "gate_pass_count": sum(bool(row["gate_pass"]) for row in relevant),
            "retention_values": values,
            "median_retention": statistics.median(values) if values else None,
            "iqr_retention": _iqr(values),
            "l_switch_ms_values": [
                float(row["l_switch_ms"])
                for row in relevant
                if row["l_switch_ms"] is not None
            ],
            "checksum_errors": sum(int(row["checksum_errors"]) for row in relevant),
            "version_errors": sum(int(row["version_errors"]) for row in relevant),
        }
    count_gate = all(len(groups[condition]) == 3 for condition in CONDITION_LABELS)
    run_gates = all(bool(row["gate_pass"]) for row in rows)
    aggregate = {
        "schema_version": "limer-cpu-v0-report.2",
        "formal_run_pattern": FORMAL_RUN.pattern,
        "formal_run_count": len(rows),
        "expected_formal_run_count": 18,
        "three_runs_per_condition": count_gate,
        "all_run_gates_pass": run_gates,
        "overall_acceptance": count_gate and run_gates and len(rows) == 18,
        "gate_scope": (
            "Implemented C0-C5 run-level gates only. This does not cover switch "
            "residency/resource budgets, C6/C7 ablations, numerical reduction, "
            "NCCL/RDMA semantics, or paper-level statistical sufficiency."
        ),
        "conditions": aggregate_conditions,
        "metric_definition": (
            "Selected retention uses post-recovery throughput for C3/C4 and "
            "post-marker/fault throughput for C0/C1/C2/C5, each divided by the "
            "matched run's pre-fault baseline median. Throughput counts aggregate "
            "application payload bytes from fully completed ranks and is a wire-volume "
            "proxy, not unique tensor bytes."
        ),
        "interpretation_boundary": (
            "CPU/Mininet framed AllReduce-like workload; not NCCL, RDMA, real GPUs, "
            "or production switch hardware. The Python detector is an off-switch "
            "management-plane proxy reading switch-facing counters, and C3/C4 assume "
            "a healthy second fabric."
        ),
    }
    _write_csv(results_dir / "summary.csv", rows)
    with (results_dir / "aggregate_summary.json").open("w", encoding="utf-8") as handle:
        json.dump(aggregate, handle, indent=2, sort_keys=True)
        handle.write("\n")
    throughput_svg = render_throughput_svg(groups)
    (results_dir / "throughput.svg").write_text(throughput_svg, encoding="utf-8")
    representative = results_dir / "c3_rep01"
    representative_summary = _json(representative / "summary.json")
    timeline_svg = render_timeline_svg(
        representative_summary, _events(representative / "events.jsonl")
    )
    (results_dir / "timeline.svg").write_text(timeline_svg, encoding="utf-8")
    ET.fromstring(throughput_svg)
    ET.fromstring(timeline_svg)
    readme_lines = [
        "# LIMER CPU v0 results",
        "",
        "These results were generated from 18 immutable formal run directories (three per condition).",
        (
            "C0-C5 run-level acceptance: **PASS**."
            if aggregate["overall_acceptance"]
            else "C0-C5 run-level acceptance: **NO-GO**; at least one predeclared run gate failed."
        ),
        f"Gate scope: {aggregate['gate_scope']}",
        "The workload is CPU/Mininet framed **AllReduce-like** traffic, not NCCL or RDMA.",
        "The detector is an off-switch management-plane proxy reading switch-facing counters; it is not switch-resident logic.",
        "The fault injector and detector are on opposite interfaces of the access link; the detector cannot read the injector qdisc.",
        "C3 and C4 recovery results assume a healthy second fabric B.",
        "",
        "| Condition | Runs | Median selected retention | IQR | Gate pass |",
        "|---|---:|---:|---:|---:|",
    ]
    for condition in CONDITION_LABELS:
        entry = aggregate_conditions[condition]
        readme_lines.append(
            f"| {condition} {CONDITION_LABELS[condition]} | {entry['run_count']} | "
            f"{entry['median_retention']:.3f} | {entry['iqr_retention']:.3f} | "
            f"{entry['gate_pass_count']}/{entry['run_count']} |"
        )
    failed_rows = [row for row in rows if not bool(row["gate_pass"])]
    if failed_rows:
        readme_lines.extend(
            [
                "",
                "Failed formal gates:",
                "",
            ]
        )
        for row in failed_rows:
            readme_lines.append(
                f"- `{row['run_id']}`: {row['gate_failures']} "
                f"(selected retention {float(row['selected_retention']):.3f})."
            )
    readme_lines.extend(
        [
            "",
            "Files:",
            "",
            "- `summary.csv`: one row per formal run; no failed formal run is discarded.",
            "- `aggregate_summary.json`: denominators, raw retention arrays, and acceptance gates.",
            "- `throughput.svg`: median and raw selected retention by condition.",
            "- `timeline.svg`: representative C3 event timeline.",
            "",
            "No failed formal repeat is discarded or silently converted into a pass.",
            "The measured C3 host-confirmation delay is dominated by waiting for a whole degraded round to finish. Streaming step-level host evidence is the next latency improvement.",
        ]
    )
    (results_dir / "README.md").write_text(
        "\n".join(readme_lines) + "\n", encoding="utf-8"
    )
    return aggregate


def parse_args(argv: Optional[List[str]] = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-dir", required=True, type=Path)
    return parser.parse_args(argv)


def main(argv: Optional[List[str]] = None) -> int:
    args = parse_args(argv)
    aggregate = generate_report(args.results_dir)
    print(json.dumps(aggregate, indent=2, sort_keys=True))
    return 0 if aggregate["overall_acceptance"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
