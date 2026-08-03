import json
import unittest
from pathlib import Path

from limer_v0.qdisc import PortSample
from limer_v0.sentinel import BurstAwareSentinelRule


ROOT = Path(__file__).resolve().parents[1]
PRESERVED_RESULTS = ROOT / "results_active_active"


def sample(t_ns, byte_count, drops=0, overlimits=0):
    return PortSample(
        interface="sA-eth3",
        t_ns=t_ns,
        kind="netem",
        bytes=byte_count,
        packets=0,
        drops=drops,
        overlimits=overlimits,
        requeues=0,
        backlog_bytes=0,
        qlen=0,
        rx_bytes=byte_count,
        rx_dropped=drops,
    )


def mbit_per_20ms(mbit):
    return int(mbit * 1e6 * 0.020 / 8)


class BurstAwareSentinelRuleTest(unittest.TestCase):
    def calibrated_rule(self, **kwargs):
        rule = BurstAwareSentinelRule(interface="sA-eth3", **kwargs)
        byte_count = 0
        t_ns = 0
        # Healthy pattern: 100 Mbit bursts separated by two ACK-level gap
        # windows, mirroring the preserved bimodal switch traces.
        for _ in range(6):
            byte_count += mbit_per_20ms(100)
            t_ns += 20_000_000
            rule.observe(sample(t_ns, byte_count))
            for _ in range(2):
                byte_count += mbit_per_20ms(0.3)
                t_ns += 20_000_000
                rule.observe(sample(t_ns, byte_count))
        baseline = rule.freeze_baseline()
        self.assertAlmostEqual(baseline, 100_000_000.0, delta=2_000_000.0)
        return rule, byte_count, t_ns

    def test_baseline_uses_burst_mode_only(self):
        rule, _byte_count, _t_ns = self.calibrated_rule()
        # The idle-mode windows must not drag the median to the ACK level.
        self.assertGreater(rule.baseline_median_bps, 50_000_000.0)
        # The first burst window only establishes the previous counter value.
        self.assertEqual(rule.calibration_sample_count, 5)

    def test_capped_but_flowing_burst_triggers_in_two_windows(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        event = None
        for _ in range(2):
            byte_count += mbit_per_20ms(17.5)
            t_ns += 20_000_000
            event = rule.observe(sample(t_ns, byte_count))
        self.assertIsNotNone(event)
        self.assertEqual(event["event"], "SWITCH_SUSPECT")
        self.assertEqual(event["signals"]["mode"], "burst")
        self.assertEqual(event["signals"]["injector_state_read"], False)
        self.assertTrue(rule.rate_degraded_burst_active())

    def test_single_edge_window_does_not_activate_symptom(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        # One intermediate-rate window (a burst straddling a poll boundary)
        # followed by gaps: the state must stay clear.
        byte_count += mbit_per_20ms(40)
        t_ns += 20_000_000
        self.assertIsNone(rule.observe(sample(t_ns, byte_count)))
        self.assertFalse(rule.rate_degraded_burst_active())
        for _ in range(3):
            byte_count += mbit_per_20ms(0.3)
            t_ns += 20_000_000
            rule.observe(sample(t_ns, byte_count))
        self.assertFalse(rule.rate_degraded_burst_active())

    def test_healthy_burst_clears_degraded_state(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        for _ in range(2):
            byte_count += mbit_per_20ms(17.5)
            t_ns += 20_000_000
            rule.observe(sample(t_ns, byte_count))
        self.assertTrue(rule.rate_degraded_burst_active())
        byte_count += mbit_per_20ms(100)
        t_ns += 20_000_000
        rule.observe(sample(t_ns, byte_count))
        self.assertFalse(rule.rate_degraded_burst_active())

    def test_gap_windows_preserve_degraded_state(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        for _ in range(2):
            byte_count += mbit_per_20ms(17.5)
            t_ns += 20_000_000
            rule.observe(sample(t_ns, byte_count))
        for _ in range(4):
            byte_count += mbit_per_20ms(0.3)
            t_ns += 20_000_000
            rule.observe(sample(t_ns, byte_count))
        self.assertTrue(rule.rate_degraded_burst_active())

    def test_extended_silence_triggers_suspect(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        event = None
        # Calibrated max gap run is 2, so the silence threshold is
        # max(min_silence_samples, 3 * 2) = 6 gap windows.
        for _ in range(6):
            t_ns += 20_000_000
            event = rule.observe(sample(t_ns, byte_count))
        self.assertIsNotNone(event)
        self.assertEqual(event["signals"]["mode"], "silence")

    def test_operstate_down_does_not_produce_burst_evidence(self):
        rule, byte_count, t_ns = self.calibrated_rule()
        for _ in range(3):
            byte_count += mbit_per_20ms(17.5)
            t_ns += 20_000_000
            event = rule.observe(sample(t_ns, byte_count), operstate="down")
            self.assertIsNone(event)

    def test_freeze_requires_three_burst_samples(self):
        rule = BurstAwareSentinelRule(interface="sA-eth3")
        byte_count = 0
        for index in range(1, 6):
            byte_count += mbit_per_20ms(0.3)
            rule.observe(sample(index * 20_000_000, byte_count))
        with self.assertRaises(ValueError):
            rule.freeze_baseline()


@unittest.skipUnless(
    PRESERVED_RESULTS.is_dir(),
    "preserved results_active_active evidence is not present",
)
class BurstRuleReplayOnPreservedEvidenceTest(unittest.TestCase):
    """Replay the burst rule against the archived formal runs.

    These fixtures are the actual switch counter traces from the 21 formal
    runs; the rule must detect every persistent or transient fault quickly
    and never trigger before the fault or on healthy traffic.
    """

    @classmethod
    def setUpClass(cls):
        import sys

        sys.path.insert(0, str(ROOT / "scripts"))
        from replay_sentinel import replay_rule, replay_step_gate

        cls.replay_rule = staticmethod(replay_rule)
        cls.replay_step_gate = staticmethod(replay_step_gate)

    def run_ids(self, prefix):
        return sorted(
            path
            for path in PRESERVED_RESULTS.iterdir()
            if path.is_dir() and path.name.startswith(prefix)
            and not path.name.endswith("smoke")
        )

    def test_fault_runs_trigger_within_100ms(self):
        for prefix in ("aa2_detect", "aa3_local", "aa3_global", "aa5_transient"):
            for run_dir in self.run_ids(prefix):
                replay = self.replay_rule(run_dir, "burst")
                trigger_ms = replay.trigger_ms_after_fault()
                self.assertIsNotNone(trigger_ms, run_dir.name)
                self.assertLess(trigger_ms, 100.0, run_dir.name)
                self.assertFalse(replay.pre_fault_trigger, run_dir.name)

    def test_no_trigger_on_healthy_or_undetected_runs(self):
        for prefix in ("aa0_healthy", "aa1_fault", "aa4_oracle"):
            for run_dir in self.run_ids(prefix):
                replay = self.replay_rule(run_dir, "burst")
                self.assertIsNone(replay.trigger_t_ns, run_dir.name)

    def test_step_gate_confirms_persistent_and_rejects_transient(self):
        for prefix, expected in (
            ("aa3_local", "confirm"),
            ("aa3_global", "confirm"),
            ("aa2_detect", "confirm"),
            ("aa5_transient", "no-confirm"),
        ):
            for run_dir in self.run_ids(prefix):
                replay = self.replay_rule(run_dir, "burst")
                gate = self.replay_step_gate(run_dir, replay)
                self.assertEqual(gate["decision"], expected, run_dir.name)
                if expected == "confirm":
                    self.assertLess(
                        gate["confirm_ms_after_fault"], 1500.0, run_dir.name
                    )


if __name__ == "__main__":
    unittest.main()
