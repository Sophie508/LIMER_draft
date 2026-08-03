from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List


EVENT_NAMES = (
    "FAULT_APPLIED",
    "SWITCH_SUSPECT",
    "HOST_CONFIRM",
    "RECOVERY_COMMIT",
)


def load_json(path: Path) -> Dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_events(path: Path) -> List[Dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def event_index(events: List[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    found = {
        event["event"]: event
        for event in events
        if event.get("event") in EVENT_NAMES
    }
    missing = sorted(set(EVENT_NAMES) - set(found))
    if missing:
        raise ValueError(f"Missing required C3 events: {', '.join(missing)}")
    return found


def build_c3_run(root: Path, run_id: str) -> Dict[str, Any]:
    summary_rel = Path("results") / run_id / "summary.json"
    events_rel = Path("results") / run_id / "events.jsonl"
    correctness_rel = Path("results") / run_id / "correctness.json"
    summary = load_json(root / summary_rel)
    events = event_index(load_events(root / events_rel))
    correctness = load_json(root / correctness_rel)
    recovery = summary["recovery"]
    retention = float(summary["post_recovery_retention"])
    return {
        "id": run_id,
        "mode": "legacy_global",
        "family_label": "Legacy CPU v0",
        "gate": "PASS" if retention >= 0.9 else "FAIL",
        "switch_detection_ms": float(summary["switch_detection"]["l_switch_ms"]),
        "host_confirmation_ms": float(summary["host_refinement"]["l_host_ms"]),
        "coordination_ms": float(recovery["l_coordination_ms"]),
        "fault_to_recovered_round_ms": float(
            recovery["l_fault_to_recovered_round_complete_ms"]
        ),
        "fault_retention": float(
            summary["fault_window"]["fault_period_retention"]
        ),
        "post_recovery_retention": retention,
        "checksum_errors": int(correctness["checksum_errors"]),
        "version_errors": int(correctness["version_errors"]),
        "events": [
            {
                "name": name,
                "t_monotonic_ns": events[name]["t_monotonic_ns"],
            }
            for name in EVENT_NAMES
        ],
        "source_summary": summary_rel.as_posix(),
        "source_events": events_rel.as_posix(),
        "source_correctness": correctness_rel.as_posix(),
    }


def build_active_run(root: Path, run_id: str) -> Dict[str, Any]:
    base_rel = Path("results_active_active") / run_id
    summary_rel = base_rel / "summary.json"
    events_rel = base_rel / "events.jsonl"
    correctness_rel = base_rel / "correctness.json"
    missing = [
        path.as_posix()
        for path in (summary_rel, events_rel, correctness_rel)
        if not (root / path).is_file()
    ]
    if missing:
        raise ValueError(
            f"Active-active replay {run_id} is missing: {', '.join(missing)}"
        )

    summary = load_json(root / summary_rel)
    correctness = load_json(root / correctness_rel)
    events = event_index(load_events(root / events_rel))
    if summary.get("run_id") != run_id:
        raise ValueError(f"Active-active replay run_id mismatch: {run_id}")
    if summary.get("status") != "complete":
        raise ValueError(f"Active-active replay run is incomplete: {run_id}")
    if summary.get("experiment_family") != "active_active_v1":
        raise ValueError(f"Active-active replay has wrong family: {run_id}")
    if summary.get("scenario_id") != "AA3_LOCAL":
        raise ValueError(f"Active-active replay must be AA3_LOCAL: {run_id}")
    if correctness.get("status") != "pass":
        raise ValueError(f"Active-active replay correctness failed: {run_id}")

    routing = summary.get("routing") or {}
    changed_slots = list(routing.get("changed_slots") or [])
    changed_ranks = sorted(
        {int(change.get("sender_rank", -1)) for change in changed_slots}
    )
    if len(changed_slots) != 3 or changed_ranks != [2]:
        raise ValueError(
            f"Active-active replay must contain exactly three worker-2 changes: {run_id}"
        )
    active_use = correctness.get("active_active_use") or {}
    baseline_fabric_bytes = dict(active_use.get("baseline_send_bytes") or {})
    if (
        active_use.get("passed") is not True
        or set(baseline_fabric_bytes) != {"A", "B"}
        or any(int(baseline_fabric_bytes[fabric]) <= 0 for fabric in ("A", "B"))
    ):
        raise ValueError(
            f"Active-active replay lacks measured A/B baseline use: {run_id}"
        )
    locality = correctness.get("locality") or {}
    if locality.get("passed") is not True:
        raise ValueError(f"Active-active replay locality failed: {run_id}")

    latency = summary.get("latency") or {}
    required_latency = (
        "l_switch_ms",
        "l_host_ms",
        "l_coordination_ms",
        "l_fault_to_recovered_round_complete_ms",
    )
    if any(latency.get(field) is None for field in required_latency):
        raise ValueError(f"Active-active replay latency is incomplete: {run_id}")
    retention = summary.get("post_recovery_retention")
    fault_retention = summary.get("fault_period_retention")
    if retention is None or fault_retention is None:
        raise ValueError(f"Active-active replay retention is incomplete: {run_id}")

    return {
        "id": run_id,
        "mode": "active_active_local",
        "family_label": "Active-active v1",
        "gate": "PASS" if float(retention) >= 0.9 else "FAIL",
        "switch_detection_ms": float(latency["l_switch_ms"]),
        "host_confirmation_ms": float(latency["l_host_ms"]),
        "coordination_ms": float(latency["l_coordination_ms"]),
        "fault_to_recovered_round_ms": float(
            latency["l_fault_to_recovered_round_complete_ms"]
        ),
        "fault_retention": float(fault_retention),
        "post_recovery_retention": float(retention),
        "checksum_errors": int(correctness["checksum_errors"]),
        "version_errors": int(correctness["version_errors"]),
        "initial_plan_fingerprint": str(routing["initial_plan_fingerprint"]),
        "recovered_plan_fingerprint": str(
            routing["recovered_plan_fingerprint"]
        ),
        "changed_slot_count": len(changed_slots),
        "changed_sender_ranks": changed_ranks,
        "baseline_fabric_bytes": {
            fabric: int(baseline_fabric_bytes[fabric]) for fabric in ("A", "B")
        },
        "events": [
            {
                "name": name,
                "t_monotonic_ns": events[name]["t_monotonic_ns"],
            }
            for name in EVENT_NAMES
        ],
        "source_summary": summary_rel.as_posix(),
        "source_events": events_rel.as_posix(),
        "source_correctness": correctness_rel.as_posix(),
    }


def build_payload(root: Path) -> Dict[str, Any]:
    aggregate = load_json(root / "results/aggregate_summary.json")
    conditions = aggregate["conditions"]
    normalized_conditions = {
        condition_id: {
            "label": value["label"],
            "run_count": int(value["run_count"]),
            "median_retention": float(value["median_retention"]),
            "retention_values": [
                float(item) for item in value["retention_values"]
            ],
            "gate_pass_count": int(value["gate_pass_count"]),
        }
        for condition_id, value in sorted(conditions.items())
    }
    run_count = sum(
        item["run_count"] for item in normalized_conditions.values()
    )
    pass_count = sum(
        item["gate_pass_count"] for item in normalized_conditions.values()
    )
    if run_count != 18 or pass_count != 16:
        raise ValueError(f"Unexpected aggregate counts: {pass_count}/{run_count}")
    legacy_runs = [
        build_c3_run(root, f"c3_rep0{repeat}")
        for repeat in range(1, 4)
    ]
    active_root = root / "results_active_active"
    active_ids = sorted(
        path.name
        for path in active_root.glob("aa3_local_rep*")
        if path.is_dir()
    )
    expected_active_ids = [f"aa3_local_rep0{repeat}" for repeat in range(1, 4)]
    if active_ids and active_ids != expected_active_ids:
        raise ValueError(
            "Active-active replay requires exactly aa3_local_rep01..03; "
            f"found {active_ids}"
        )
    active_runs = [build_active_run(root, run_id) for run_id in active_ids]
    active_status = "measured" if active_runs else "not_measured"
    return {
        "meta": {
            "title": "LIMER CPU-Only Emulation Prototype",
            "formal_run_count": run_count,
            "gate_pass_count": pass_count,
            "overall_acceptance": bool(aggregate["overall_acceptance"]),
            "source": "results/aggregate_summary.json",
            "active_active_status": active_status,
            "active_active_source": (
                "results_active_active/aggregate_summary.json"
                if active_runs
                else None
            ),
        },
        "conditions": normalized_conditions,
        "c3_runs": legacy_runs,
        "active_active_runs": active_runs,
        "active_active_status": active_status,
        "replay_runs": legacy_runs + active_runs,
        "boundaries": [
            "CPU/Mininet emulation",
            "AllReduce-like framed traffic",
            "Management-plane switch-counter proxy",
            "Legacy v0 uses whole-ring failover",
            "Active-active v1 models a directed worker-2 egress fault",
            "No GPU, NCCL, RDMA, or numerical reduction",
        ],
        "roadmap": [
            "step_level_confirmation",
            "bidirectional_fault_profiles",
            "simai_up_to_128",
        ],
    }


def render_payload(payload: Dict[str, Any]) -> str:
    return json.dumps(
        payload,
        ensure_ascii=False,
        indent=2,
        sort_keys=True,
    ) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "docs/assets/data/demo-data.json"
    rendered = render_payload(build_payload(root))
    if args.write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        return 0
    if not output.exists() or output.read_text(encoding="utf-8") != rendered:
        print("docs/assets/data/demo-data.json is stale")
        return 1
    print("demo-data.json matches archived evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
