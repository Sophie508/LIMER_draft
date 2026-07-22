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
    return {
        "meta": {
            "title": "LIMER CPU-Only Emulation Prototype",
            "formal_run_count": run_count,
            "gate_pass_count": pass_count,
            "overall_acceptance": bool(aggregate["overall_acceptance"]),
            "source": "results/aggregate_summary.json",
        },
        "conditions": normalized_conditions,
        "c3_runs": [
            build_c3_run(root, f"c3_rep0{repeat}")
            for repeat in range(1, 4)
        ],
        "boundaries": [
            "CPU/Mininet emulation",
            "AllReduce-like framed traffic",
            "Management-plane switch-counter proxy",
            "Healthy Fabric B assumed",
            "No GPU, NCCL, RDMA, or numerical reduction",
        ],
        "roadmap": [
            "standby_path",
            "step_level_confirmation",
            "orthogonal_loss_matrix",
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
