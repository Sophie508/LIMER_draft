import unittest

from limer_v0.qdisc import PortSample
from limer_v0.sentinel import SentinelRule


def sample(t_ns, byte_count, backlog=0, drops=0, overlimits=0):
    return PortSample(
        interface="sA-eth3",
        t_ns=t_ns,
        kind="netem",
        bytes=byte_count,
        packets=0,
        drops=drops,
        overlimits=overlimits,
        requeues=0,
        backlog_bytes=backlog,
        qlen=0,
        rx_bytes=byte_count,
        rx_dropped=drops,
    )


class SentinelRuleTest(unittest.TestCase):
    def calibrated_rule(self):
        rule = SentinelRule(interface="sA-eth3", consecutive_required=3)
        byte_count = 0
        for index in range(8):
            byte_count += 250_000  # 100 Mbit/s over a 20 ms interval
            rule.observe(sample(index * 20_000_000, byte_count))
        baseline = rule.freeze_baseline()
        self.assertAlmostEqual(baseline, 100_000_000.0)
        return rule, byte_count

    def test_persistent_rate_degradation_triggers_after_three_samples(self):
        rule, byte_count = self.calibrated_rule()
        event = None
        for offset in range(1, 4):
            byte_count += 50_000  # 20 Mbit/s over a 20 ms interval
            event = rule.observe(
                sample((7 + offset) * 20_000_000, byte_count, backlog=70_000)
            )
            if offset < 3:
                self.assertIsNone(event)
        self.assertEqual(event["event"], "SWITCH_SUSPECT")
        self.assertEqual(event["rule_version"], "l1-v0.2-isolated-rx-rate")
        self.assertEqual(event["interface"], "sA-eth3")
        self.assertEqual(len(event["evidence_samples"]), 3)
        self.assertLess(event["signals"]["observed_bps"], 0.6 * 100_000_000.0)
        self.assertEqual(event["signals"]["observed_counter"], "switch_port_rx_bytes")
        self.assertFalse(event["signals"]["injector_state_read"])
        self.assertNotIn("round_id", event)
        self.assertNotIn("worker", event)

    def test_single_transient_sample_does_not_trigger(self):
        rule, byte_count = self.calibrated_rule()
        byte_count += 50_000
        self.assertIsNone(
            rule.observe(sample(160_000_000, byte_count, backlog=70_000))
        )
        byte_count += 250_000
        self.assertIsNone(rule.observe(sample(180_000_000, byte_count, backlog=0)))
        for index in range(3):
            byte_count += 250_000
            self.assertIsNone(
                rule.observe(sample(200_000_000 + index * 20_000_000, byte_count))
            )

    def test_counter_reset_is_ignored(self):
        rule, _byte_count = self.calibrated_rule()
        self.assertIsNone(rule.observe(sample(160_000_000, 10, backlog=70_000)))
        self.assertEqual(rule.consecutive_evidence, 0)


if __name__ == "__main__":
    unittest.main()
