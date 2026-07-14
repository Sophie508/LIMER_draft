"""KPI calculations for raw worker round records."""

from __future__ import annotations

import statistics
from typing import Any, Dict, Iterable, List, Mapping


def _iqr(values: List[float]) -> float:
    ordered = sorted(values)
    if len(ordered) < 2:
        return 0.0
    quartiles = statistics.quantiles(ordered, n=4, method="inclusive")
    return quartiles[2] - quartiles[0]


def summarize_rounds(
    rows: Iterable[Mapping[str, Any]], baseline_median_bps: float
) -> Dict[str, Any]:
    if baseline_median_bps <= 0:
        raise ValueError("baseline_median_bps must be positive")
    throughputs: List[float] = []
    byte_counts: List[int] = []
    durations: List[float] = []
    for row in rows:
        duration = float(row["duration_s"])
        byte_count = int(row["bytes_completed"])
        if duration <= 0:
            raise ValueError("round duration must be positive")
        if byte_count < 0:
            raise ValueError("bytes_completed must be non-negative")
        durations.append(duration)
        byte_counts.append(byte_count)
        throughputs.append(byte_count * 8.0 / duration)
    if not throughputs:
        raise ValueError("at least one round is required")
    median_bps = statistics.median(throughputs)
    retention = median_bps / float(baseline_median_bps)
    return {
        "round_count": len(throughputs),
        "median_throughput_bps": median_bps,
        "iqr_throughput_bps": _iqr(throughputs),
        "fault_period_retention": retention,
        "post_recovery_retention": retention,
        "baseline_median_bps": float(baseline_median_bps),
        "throughput_bps": throughputs,
        "bytes_completed": byte_counts,
        "duration_s": durations,
    }
