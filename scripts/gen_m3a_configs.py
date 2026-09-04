"""Generate the M3a switch-cost loss-sweep configs.

One directory per loss level, each holding the stay arm (AA9_STAY: keep
using the lossy egress, measure the retransmission cost) and the switch arm
(AA10_SWITCH: oracle localized reroute, measure the displacement cost).
The constrained-B variant repeats one level with worker 2's Fabric B access
capped, so the surviving plane no longer has free headroom.
"""

from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "configs" / "m3a_loss_sweep"
LOSS_LEVELS = [0.5, 1.0, 2.0, 5.0, 10.0, 25.0]
CONSTRAINED = {"level": 5.0, "b_rate_mbit": 50.0, "dir": "cb50_l5"}

COMMON = {
    "condition": None,
    "topology": "dual",
    "chunk_bytes": 2097152,
    "warmup_rounds": 1,
    "baseline_rounds": 2,
    "post_fault_rounds": 8,
    "fault_rate_mbit": 100.0,
    "fault_loss_pct": None,
    "transient_ms": 0,
    "experiment_family": "active_active_v1",
    "routing_policy": "balanced_active_active",
    "fault_scope": {"rank": 2, "fabric": "A", "direction": "egress"},
}


def stay_config(loss_pct: float) -> dict:
    config = dict(COMMON)
    config.update(
        {
            "condition": "C1",
            "fault_loss_pct": loss_pct,
            "detector": False,
            "recovery": False,
            "oracle": False,
            "recovery_policy": "none",
            "scenario_id": "AA9_STAY",
            "step_timeout_s": 300.0,
            "what_changes": (
                f"Worker 2's Fabric A egress drops {loss_pct}% of packets at "
                "random while the link stays up and full rate; no detection "
                "and no recovery run, so the measured retention is the pure "
                "cost of staying on the lossy link and paying TCP "
                "retransmissions."
            ),
            "expected": (
                "The run completes with zero checksum and version errors and "
                "reports the stay-arm retention for this loss level; no "
                "retention bound is asserted because this is the measured "
                "quantity."
            ),
        }
    )
    return config


def switch_config(loss_pct: float) -> dict:
    config = dict(COMMON)
    config.update(
        {
            "condition": "C4",
            "fault_loss_pct": loss_pct,
            "detector": False,
            "recovery": True,
            "oracle": True,
            "recovery_policy": "localized",
            "scenario_id": "AA10_SWITCH",
            "what_changes": (
                f"The same {loss_pct}% loss fault, but an oracle immediately "
                "commits the localized reroute, so worker 2's traffic leaves "
                "the lossy egress; the measured retention is the pure cost "
                "of displacing that traffic onto Fabric B."
            ),
            "expected": (
                "Exactly three worker-2 slots move, correctness holds, and "
                "the post-recovery retention for this loss level is "
                "reported; no retention bound is asserted."
            ),
        }
    )
    return config


def write(directory: Path, config: dict, name: str) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    (directory / name).write_text(json.dumps(config, indent=4) + "\n")


def main() -> None:
    for loss_pct in LOSS_LEVELS:
        level_dir = OUT / f"l{str(loss_pct).replace('.', 'p').removesuffix('p0')}"
        write(level_dir, stay_config(loss_pct), "aa9_stay.json")
        write(level_dir, switch_config(loss_pct), "aa10_switch.json")
    constrained_dir = OUT / CONSTRAINED["dir"]
    for build in (stay_config, switch_config):
        config = build(CONSTRAINED["level"])
        config["b_access_rate_mbit"] = CONSTRAINED["b_rate_mbit"]
        config["what_changes"] += (
            " Worker 2's Fabric B access is additionally capped to "
            f"{CONSTRAINED['b_rate_mbit']:.0f} Mbit before any round runs, so "
            "the surviving plane has no free headroom and the switch cost "
            "becomes visible; the matched baseline shares the same cap."
        )
        name = (
            "aa9_stay.json" if build is stay_config else "aa10_switch.json"
        )
        write(constrained_dir, config, name)
    print(f"configs written under {OUT}")


if __name__ == "__main__":
    main()
