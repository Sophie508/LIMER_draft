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
        alternate_path_probe: Mapping[str, Any],
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
        if not bool(alternate_path_probe.get("healthy", False)):
            return RefinerDecision(
                "defer",
                ["The alternate fabric health probe failed, so reroute is unsafe."],
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
                "The alternate fabric health probe passed.",
            ],
        )


class StepGateRefiner:
    """Confirm from in-round step evidence instead of a completed round.

    A step counts as slow when its duration exceeds slowdown_factor times the
    fault-free per-step p95, and it is confirmable only if the switch-side
    burst symptom is still active when the step completes: that persistence
    requirement is what separates a lasting impairment from a transient whose
    switch symptom has already cleared, because both inflate a similar number
    of steps inside the impacted round.
    """

    def __init__(
        self, slowdown_factor: float = 1.5, min_slow_steps: int = 2
    ) -> None:
        if slowdown_factor <= 1:
            raise ValueError("slowdown_factor must be greater than one")
        if min_slow_steps <= 0:
            raise ValueError("min_slow_steps must be positive")
        self.slowdown_factor = slowdown_factor
        self.min_slow_steps = min_slow_steps

    def is_slow(self, duration_s: float, baseline_step_p95_s: float) -> bool:
        if baseline_step_p95_s <= 0:
            raise ValueError("baseline_step_p95_s must be positive")
        if duration_s <= 0:
            raise ValueError("step duration must be positive")
        return duration_s > self.slowdown_factor * baseline_step_p95_s

    def evaluate(
        self,
        switch_event: Optional[Mapping[str, Any]],
        confirmable_slow_steps: List[Mapping[str, Any]],
        baseline_step_p95_s: float,
        alternate_path_probe: Mapping[str, Any],
    ) -> RefinerDecision:
        if baseline_step_p95_s <= 0:
            raise ValueError("baseline_step_p95_s must be positive")
        if switch_event is None:
            return RefinerDecision(
                "defer", ["No switch-side suspicion was available for host refinement."]
            )
        if len(confirmable_slow_steps) < self.min_slow_steps:
            return RefinerDecision(
                "defer",
                [
                    f"Only {len(confirmable_slow_steps)} slow steps completed while "
                    "the switch-side burst symptom was active; "
                    f"{self.min_slow_steps} are required.",
                ],
            )
        if not bool(alternate_path_probe.get("healthy", False)):
            return RefinerDecision(
                "defer",
                ["The alternate fabric health probe failed, so reroute is unsafe."],
            )
        described = ", ".join(
            f"rank {step['rank']} round {step['round_id']} step {step['step_id']} "
            f"({float(step['duration_s']):.3f}s)"
            for step in confirmable_slow_steps[: self.min_slow_steps]
        )
        return RefinerDecision(
            "confirm",
            [
                "Switch-side burst-rate degradation was active at each slow step.",
                f"{len(confirmable_slow_steps)} steps exceeded "
                f"{self.slowdown_factor:.1f}x the fault-free step p95 "
                f"({baseline_step_p95_s:.6f}s): {described}.",
                "The alternate fabric health probe passed.",
            ],
        )

    def suppression(
        self, slow_step_count: int, confirmable_count: int
    ) -> RefinerDecision:
        return RefinerDecision(
            "suppress",
            [
                "Step-level impact did not persist: "
                f"{slow_step_count} slow steps were observed but only "
                f"{confirmable_count} completed while the switch-side burst "
                f"symptom was active (fewer than {self.min_slow_steps}).",
            ],
        )
