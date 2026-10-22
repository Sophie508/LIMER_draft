import unittest

from limer_v0.ack_progress import AckProgressRule


def report(sample, ack, busy=True, lag=1_000_000, path=0):
    return dict(path=path, acked_bytes=ack, sample_ns=sample,
                arrival_ns=sample+lag, full_busy=busy)


class AckProgressTests(unittest.TestCase):
    def calibrated(self):
        rule = AckProgressRule()
        for i in range(5):
            self.assertIsNone(rule.observe(report(i*2_000_000, i*200_000)))
        return rule

    def test_alarm_uses_arrival_time_after_three_busy_windows(self):
        rule = self.calibrated()
        self.assertIsNone(rule.observe(report(10_000_000, 820_000)))
        self.assertIsNone(rule.observe(report(12_000_000, 840_000)))
        self.assertEqual(rule.observe(report(14_000_000, 860_000)),
                         dict(path=0, decision_ns=15_000_000))
        self.assertIsNone(rule.observe(report(16_000_000, 880_000)))

    def test_idle_interrupts_evidence(self):
        rule = self.calibrated()
        rule.observe(report(10_000_000, 820_000))
        rule.observe(report(12_000_000, 820_000, busy=False))
        self.assertIsNone(rule.observe(report(14_000_000, 840_000)))
        self.assertIsNone(rule.observe(report(16_000_000, 860_000)))

    def test_short_slowdown_clears_on_recovery(self):
        rule = self.calibrated()
        rule.observe(report(10_000_000, 820_000))
        rule.observe(report(12_000_000, 1_020_000))
        self.assertIsNone(rule.observe(report(14_000_000, 1_040_000)))

    def test_startup_without_positive_reference_does_not_alarm(self):
        rule = AckProgressRule()
        for i in range(10):
            self.assertIsNone(rule.observe(report(i*2_000_000, 0)))

    def test_report_latency_changes_decision_time(self):
        rule = self.calibrated()
        for i in range(3):
            alarm = rule.observe(report(10_000_000+i*2_000_000, 820_000+i*20_000,
                                        lag=120_000_000))
        self.assertEqual(alarm['decision_ns'], 134_000_000)

    def test_counter_decrease_rejected(self):
        rule = self.calibrated()
        with self.assertRaisesRegex(ValueError, 'counter'):
            rule.observe(report(10_000_000, 1))

    def test_out_of_order_sample_rejected(self):
        rule = self.calibrated()
        with self.assertRaisesRegex(ValueError, 'sample'):
            rule.observe(report(8_000_000, 800_000))

    def test_observer_schema_rejects_hidden_injection_fields(self):
        rule = AckProgressRule()
        row = report(0, 0)
        row['fault_ns'] = 0
        with self.assertRaisesRegex(ValueError, 'schema'):
            rule.observe(row)


if __name__ == '__main__':
    unittest.main()
