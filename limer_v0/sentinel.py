"""Switch-counter high-recall proxy rule for the LIMER CPU v0 prototype."""

from __future__ import annotations

import statistics
from collections import deque
from typing import Any, Deque, Dict, List, Optional

from .qdisc import PortSample


class SentinelRule:
    """Derive suspicion from a switch-facing port, never from injector state."""

    def __init__(
        self,
        interface: str,
        threshold_fraction: float = 0.60,
        consecutive_required: int = 3,
        rule_version: str = "l1-v0.2-isolated-rx-rate",
    ) -> None:
        if not 0 < threshold_fraction < 1:
            raise ValueError("threshold_fraction must be between zero and one")
        if consecutive_required <= 0:
            raise ValueError("consecutive_required must be positive")
        self.interface = interface
        self.threshold_fraction = threshold_fraction
        self.consecutive_required = consecutive_required
        self.rule_version = rule_version
        self._previous: Optional[PortSample] = None
        self._calibration_rates: List[float] = []
        self.baseline_median_bps: Optional[float] = None
        self.consecutive_evidence = 0
        self._evidence: Deque[Dict[str, Any]] = deque(maxlen=consecutive_required)
        self._triggered = False

    @property
    def calibration_sample_count(self) -> int:
        return len(self._calibration_rates)

    def freeze_baseline(self) -> float:
        if len(self._calibration_rates) < 3:
            raise ValueError(
                "at least three positive-rate switch samples are required for baseline"
            )
        self.baseline_median_bps = statistics.median(self._calibration_rates)
        return self.baseline_median_bps

    def _reset_evidence(self) -> None:
        self.consecutive_evidence = 0
        self._evidence.clear()

    def observe(
        self, sample: PortSample, operstate: str = "unknown"
    ) -> Optional[Dict[str, Any]]:
        if sample.interface != self.interface:
            raise ValueError(
                f"sample interface {sample.interface!r} does not match {self.interface!r}"
            )
        previous = self._previous
        self._previous = sample
        if previous is None:
            return None
        elapsed_ns = sample.t_ns - previous.t_ns
        byte_delta = sample.rx_bytes - previous.rx_bytes
        if elapsed_ns <= 0 or byte_delta < 0:
            self._reset_evidence()
            return None
        observed_bps = byte_delta * 8_000_000_000.0 / elapsed_ns
        drop_delta = max(0, sample.rx_dropped - previous.rx_dropped)
        overlimit_delta = max(0, sample.overlimits - previous.overlimits)
        if self.baseline_median_bps is None:
            if observed_bps > 0:
                self._calibration_rates.append(observed_bps)
            return None
        if self._triggered:
            return None

        rate_degraded = (
            observed_bps < self.threshold_fraction * self.baseline_median_bps
        )
        evidence = {
            "t_monotonic_ns": sample.t_ns,
            "observed_bps": observed_bps,
            "baseline_median_bps": self.baseline_median_bps,
            "threshold_bps": self.threshold_fraction * self.baseline_median_bps,
            "backlog_bytes": sample.backlog_bytes,
            "drop_delta": drop_delta,
            "overlimit_delta": overlimit_delta,
            "operstate": operstate,
            "observed_counter": "switch_port_rx_bytes",
            "injector_state_read": False,
        }
        if rate_degraded and operstate not in {"down", "lowerlayerdown"}:
            self.consecutive_evidence += 1
            self._evidence.append(evidence)
        else:
            self._reset_evidence()
            return None

        if self.consecutive_evidence < self.consecutive_required:
            return None
        self._triggered = True
        return {
            "event": "SWITCH_SUSPECT",
            "source": "switch_counter_management_proxy",
            "interface": self.interface,
            "t_monotonic_ns": sample.t_ns,
            "rule_version": self.rule_version,
            "signals": evidence,
            "evidence_samples": list(self._evidence),
        }
