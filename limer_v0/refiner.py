"""Deterministic end-host confirmation gate for LIMER CPU v0."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Dict, List, Mapping, Optional


@dataclass(frozen=True)
class RefinerDecision:
    action: str
    reasons: List[str]
    confidence: Optional[float] = None
    calibration_version: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class HostRefiner:
    """Apply an explainable v0 gate without pretending a model is trained."""

    def __init__(self, slowdown_factor: float = 1.5) -> None:
        if slowdown_factor <= 1:
            raise ValueError("slowdown_factor must be greater than one")
        self.slowdown_factor = slowdown_factor

    def evaluate(
        self,
        switch_event: Optional[Mapping[str, Any]],
        degraded_round: Mapping[str, Any],
        baseline_p95_s: float,
        standby_probe: Mapping[str, Any],
    ) -> RefinerDecision:
        if baseline_p95_s <= 0:
            raise ValueError("baseline_p95_s must be positive")
        duration_s = float(degraded_round["duration_s"])
        if duration_s <= 0:
            raise ValueError("degraded round duration must be positive")
        if switch_event is None:
            return RefinerDecision(
                "defer", ["No switch-side suspicion was available for host refinement."]
            )
        if not bool(standby_probe.get("healthy", False)):
            return RefinerDecision(
                "defer",
                ["The standby fabric health probe failed, so reroute is unsafe."],
            )
        threshold_s = self.slowdown_factor * baseline_p95_s
        if duration_s <= threshold_s:
            return RefinerDecision(
                "suppress",
                [
                    "Collective impact is not persistent: round duration "
                    f"{duration_s:.6f}s did not exceed {self.slowdown_factor:.1f}x "
                    f"the fault-free p95 ({threshold_s:.6f}s)."
                ],
            )
        return RefinerDecision(
            "confirm",
            [
                "Switch-side direct symptoms persisted for the configured rule.",
                f"Round duration {duration_s:.6f}s exceeded {self.slowdown_factor:.1f}x "
                f"the fault-free p95 ({threshold_s:.6f}s).",
                "The standby fabric health probe passed.",
            ],
        )
