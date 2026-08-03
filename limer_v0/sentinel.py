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


class BurstAwareSentinelRule:
    """Detect in-flight rate degradation on a bursty switch port.

    The legacy rule freezes one median over all positive-rate windows; on a
    port whose healthy traffic alternates line-rate bursts with near-idle
    ACK windows that median lands on the idle mode, so a capped-but-flowing
    fault stays invisible until the port goes silent. This rule separates
    the two modes with a fixed noise floor and calibrates only on burst
    windows, so a burst that flows well below the healthy burst rate is
    itself evidence. A silence path (gap run far beyond anything seen in
    calibration) still covers hard failures. Reads the same switch-facing
    rx counters as the legacy rule; never touches injector state.
    """

    def __init__(
        self,
        interface: str,
        threshold_fraction: float = 0.60,
        consecutive_required: int = 2,
        burst_floor_bps: float = 1_000_000.0,
        silence_multiple: int = 3,
        min_silence_samples: int = 6,
        rule_version: str = "l1-v0.3-burst-aware-rx-rate",
    ) -> None:
        if not 0 < threshold_fraction < 1:
            raise ValueError("threshold_fraction must be between zero and one")
        if consecutive_required <= 0:
            raise ValueError("consecutive_required must be positive")
        if burst_floor_bps <= 0:
            raise ValueError("burst_floor_bps must be positive")
        if silence_multiple <= 0:
            raise ValueError("silence_multiple must be positive")
        if min_silence_samples <= 0:
            raise ValueError("min_silence_samples must be positive")
        self.interface = interface
        self.threshold_fraction = threshold_fraction
        self.consecutive_required = consecutive_required
        self.burst_floor_bps = burst_floor_bps
        self.silence_multiple = silence_multiple
        self.min_silence_samples = min_silence_samples
        self.rule_version = rule_version
        self._previous: Optional[PortSample] = None
        self._calibration_rates: List[float] = []
        self._calibration_gap_run = 0
        self._calibration_max_gap_run = 0
        self.baseline_median_bps: Optional[float] = None
        self.silence_threshold_samples: Optional[int] = None
        self.consecutive_evidence = 0
        self._evidence: Deque[Dict[str, Any]] = deque(maxlen=consecutive_required)
        self._gap_run = 0
        self._triggered = False

    @property
    def calibration_sample_count(self) -> int:
        return len(self._calibration_rates)

    def freeze_baseline(self) -> float:
        if len(self._calibration_rates) < 3:
            raise ValueError(
                "at least three burst-mode switch samples are required for baseline"
            )
        self.baseline_median_bps = statistics.median(self._calibration_rates)
        self.silence_threshold_samples = max(
            self.min_silence_samples,
            self.silence_multiple * max(1, self._calibration_max_gap_run),
        )
        return self.baseline_median_bps

    def rate_degraded_burst_active(self) -> bool:
        """True while at least consecutive_required burst windows ran degraded.

        A single sub-threshold window is not enough: burst-edge windows (a
        burst straddling a poll boundary) produce isolated intermediate rates
        even on a healthy port. Gap windows leave the state unchanged because
        bursts are naturally separated by idle windows; one healthy burst
        clears it. The step gate uses this to distinguish a persistent
        impairment from a transient whose switch-side symptom has cleared.
        """
        return self.consecutive_evidence >= self.consecutive_required

    def _reset_evidence(self) -> None:
        self.consecutive_evidence = 0
        self._evidence.clear()

    def _suspect(self, sample: PortSample, evidence: Dict[str, Any]) -> Dict[str, Any]:
        self._triggered = True
        return {
            "event": "SWITCH_SUSPECT",
            "source": "switch_counter_management_proxy",
            "interface": self.interface,
            "t_monotonic_ns": sample.t_ns,
            "rule_version": self.rule_version,
            "signals": evidence,
            "evidence_samples": list(self._evidence) or [evidence],
        }

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
            self._gap_run = 0
            return None
        observed_bps = byte_delta * 8_000_000_000.0 / elapsed_ns
        is_burst = observed_bps > self.burst_floor_bps
        if self.baseline_median_bps is None:
            if is_burst:
                self._calibration_rates.append(observed_bps)
                self._calibration_gap_run = 0
            else:
                self._calibration_gap_run += 1
                if self._calibration_gap_run > self._calibration_max_gap_run:
                    self._calibration_max_gap_run = self._calibration_gap_run
            return None

        drop_delta = max(0, sample.rx_dropped - previous.rx_dropped)
        overlimit_delta = max(0, sample.overlimits - previous.overlimits)
        threshold_bps = self.threshold_fraction * self.baseline_median_bps
        evidence = {
            "t_monotonic_ns": sample.t_ns,
            "observed_bps": observed_bps,
            "baseline_median_bps": self.baseline_median_bps,
            "threshold_bps": threshold_bps,
            "burst_floor_bps": self.burst_floor_bps,
            "mode": "burst" if is_burst else "gap",
            "gap_run": self._gap_run,
            "backlog_bytes": sample.backlog_bytes,
            "drop_delta": drop_delta,
            "overlimit_delta": overlimit_delta,
            "operstate": operstate,
            "observed_counter": "switch_port_rx_bytes",
            "injector_state_read": False,
        }
        link_reported_down = operstate in {"down", "lowerlayerdown"}

        if is_burst:
            self._gap_run = 0
            if observed_bps < threshold_bps and not link_reported_down:
                self.consecutive_evidence += 1
                self._evidence.append(evidence)
                if (
                    not self._triggered
                    and self.consecutive_evidence >= self.consecutive_required
                ):
                    return self._suspect(sample, evidence)
            else:
                self._reset_evidence()
            return None

        self._gap_run += 1
        evidence["gap_run"] = self._gap_run
        if (
            not self._triggered
            and not link_reported_down
            and self.silence_threshold_samples is not None
            and self._gap_run >= self.silence_threshold_samples
        ):
            evidence["mode"] = "silence"
            return self._suspect(sample, evidence)
        return None
