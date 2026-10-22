"""Build the M3a switch-cost curve from the loss-sweep results.

Reads every level directory under the sweep results root, recomputes both
arms' retention from the raw aggregate_rounds.csv (never from summaries),
and prints a per-level table plus the stay-vs-switch comparison. Exits
non-zero if any run is missing, failed, or breaks a measurement-arm gate.
"""

from __future__ import annotations

import argparse
import csv
import json
import statistics
import sys
from pathlib import Path
from typing import Dict, List, Optional


def _throughput(row: Dict[str, str]) -> float:
    return int(row["bytes_completed"]) * 8.0 / float(row["duration_s"])


def _retention(run_dir: Path, post_recovery: bool) -> float:
    with (run_dir / "aggregate_rounds.csv").open() as handle:
        rows = list(csv.DictReader(handle))
    baseline = [_throughput(r) for r in rows if r["period"] == "baseline"]
    if post_recovery:
        selected = [
            _throughput(r)
            for r in rows
            if r["period"] == "post_fault" and int(r["version"]) > 0
        ]
    else:
        selected = [_throughput(r) for r in rows if r["period"] == "post_fault"]
    return statistics.median(selected) / statistics.median(baseline)


def _loss_pct(run_dir: Path) -> float:
    manifest = json.loads((run_dir / "manifest.json").read_text())
    return float(manifest["config"]["fault_loss_pct"])


def analyze(results_root: Path) -> int:
    levels = sorted(d for d in results_root.iterdir() if d.is_dir())
    failures: List[str] = []
    table: List[Dict[str, object]] = []
    for level_dir in levels:
        entry: Dict[str, object] = {"level": level_dir.name}
        for arm, scenario, post in (
            ("stay", "aa9_stay", False),
            ("switch", "aa10_switch", True),
        ):
            values: List[float] = []
            for rep in ("01", "02", "03"):
                run_dir = level_dir / f"{scenario}_rep{rep}"
                if not run_dir.is_dir():
                    failures.append(f"{level_dir.name}/{scenario}_rep{rep} missing")
                    continue
                summary = json.loads((run_dir / "summary.json").read_text())
                if summary.get("status") != "complete":
                    failures.append(
                        f"{level_dir.name}/{scenario}_rep{rep} "
                        f"status={summary.get('status')}"
                    )
                    continue
                if summary.get("correctness_status") != "pass":
                    failures.append(
                        f"{level_dir.name}/{scenario}_rep{rep} correctness fail"
                    )
                    continue
                values.append(_retention(run_dir, post))
            if values:
                entry[f"{arm}_median"] = round(statistics.median(values), 4)
                entry[f"{arm}_values"] = [round(v, 4) for v in values]
                entry["loss_pct"] = _loss_pct(
                    level_dir / f"{scenario}_rep01"
                )
        table.append(entry)

    ordered = sorted(
        (e for e in table if "loss_pct" in e),
        key=lambda e: (str(e["level"]).startswith("cb"), float(e["loss_pct"])),
    )
    print(f"{'level':10s} {'loss%':>6s} {'stay':>8s} {'switch':>8s}  raw")
    for entry in ordered:
        print(
            f"{entry['level']:10s} {entry['loss_pct']:>6.1f} "
            f"{entry.get('stay_median', float('nan')):>8.4f} "
            f"{entry.get('switch_median', float('nan')):>8.4f}  "
            f"stay={entry.get('stay_values')} switch={entry.get('switch_values')}"
        )
    if failures:
        print("\nFAILURES:")
        for failure in failures:
            print(" -", failure)
        return 1
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results-root", required=True, type=Path)
    return analyze(parser.parse_args().results_root)


if __name__ == "__main__":
    sys.exit(main())
