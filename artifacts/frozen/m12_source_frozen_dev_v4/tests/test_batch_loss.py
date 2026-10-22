import unittest

from limer_v0.batch_loss import BatchLossDetector


def report(batch, side, count, path="2/A", extra_ms=0):
    end = (batch + 1) * 10_000_000
    sample = end + (50_000_000 if side == "rx" else 0)
    return dict(path=path, batch=batch, side=side, count=count,
                sample_t_ns=sample, arrival_t_ns=sample + (5 + extra_ms) * 1_000_000)


class BatchLossTest(unittest.TestCase):
    def pair(self, d, batch, tx=100, rx=100, path="2/A"):
        a, b = report(batch, "tx", tx, path), report(batch, "rx", rx, path)
        # Previous RX arrival may be later than this TX's original arrival.
        a["arrival_t_ns"] = max(a["arrival_t_ns"], d.now_ns)
        b["arrival_t_ns"] = max(b["arrival_t_ns"], a["arrival_t_ns"])
        self.assertIsNone(d.observe(a))
        return d.observe(b)

    def test_guard_and_reporting_latency_are_in_the_decision(self):
        d = BatchLossDetector()
        self.assertIsNone(d.observe(report(0, "tx", 100)))
        decision = d.observe(report(0, "rx", 98, extra_ms=20))
        self.assertEqual(decision["decision_t_ns"], 85_000_000)
        self.assertEqual(decision["missing_packets"], 2)

    def test_out_of_order_reports_and_complete_reordered_data_do_not_alarm(self):
        d = BatchLossDetector()
        rx = report(0, "rx", 100)
        self.assertIsNone(d.observe(rx))
        tx = report(0, "tx", 100)
        tx["arrival_t_ns"] = rx["arrival_t_ns"] + 1
        self.assertIsNone(d.observe(tx))

    def test_missing_report_is_unknown_never_zero(self):
        d = BatchLossDetector()
        d.observe(report(0, "tx", 100))
        expired = d.advance(211_000_000)
        self.assertEqual(len(expired), 1)
        self.assertEqual(d.unavailable_batches, 1)
        self.assertEqual(d.confirmations, 0)
        late_rx = report(0, "rx", 0, extra_ms=200)
        self.assertIsNone(d.observe(late_rx))

    def test_two_missing_packets_can_accumulate_across_complete_batches(self):
        d = BatchLossDetector()
        self.assertIsNone(self.pair(d, 0, rx=99))
        self.assertIsNotNone(self.pair(d, 1, rx=99))

    def test_expired_evidence_cannot_bridge_later_loss(self):
        d = BatchLossDetector()
        self.pair(d, 0, rx=99)
        self.assertIsNone(self.pair(d, 20, rx=99))

    def test_independent_paths_never_pool_missing_packets(self):
        d = BatchLossDetector()
        self.assertIsNone(self.pair(d, 0, rx=99, path="0/A"))
        self.assertIsNone(self.pair(d, 0, rx=99, path="1/A"))

    def test_identical_duplicates_are_ignored_and_conflicts_rejected(self):
        d = BatchLossDetector()
        tx = report(0, "tx", 100)
        d.observe(tx)
        self.assertIsNone(d.observe(tx))
        with self.assertRaises(ValueError):
            d.observe(dict(tx, count=99))
        self.assertIsNone(d.observe(report(0, "rx", 99)))
        duplicate = dict(tx, arrival_t_ns=d.now_ns)
        self.assertIsNone(d.observe(duplicate))
        self.assertEqual(d.completed_batches, 1)

    def test_bad_counts_do_not_become_negative_loss_or_evidence(self):
        d = BatchLossDetector()
        self.assertIsNone(self.pair(d, 0, rx=99))
        self.assertIsNone(self.pair(d, 1, tx=100, rx=101))
        self.assertEqual(d.invalid_batches, 1)
        self.assertIsNone(self.pair(d, 2, rx=99))

    def test_complete_active_batches_rearm_but_idle_batches_do_not(self):
        d = BatchLossDetector()
        self.assertIsNotNone(self.pair(d, 0, rx=98))
        self.pair(d, 1, tx=0, rx=0)
        self.pair(d, 2, tx=0, rx=0)
        self.assertIsNone(self.pair(d, 3, rx=98))
        self.pair(d, 4)
        self.pair(d, 5)
        self.assertIsNotNone(self.pair(d, 6, rx=98))

    def test_report_schema_and_guard_cannot_accept_injector_metadata(self):
        for mutation in (dict(fault_time_ns=1), dict(count=-1),
                         dict(count=1.5), dict(batch=True),
                         dict(sample_t_ns=1), dict(side="drop")):
            d = BatchLossDetector()
            with self.assertRaises(ValueError):
                d.observe(dict(report(0, "rx", 100), **mutation))

    def test_regressing_arrival_time_is_rejected(self):
        d = BatchLossDetector()
        d.observe(report(0, "rx", 100))
        with self.assertRaises(ValueError):
            d.observe(report(0, "tx", 100))

    def test_late_old_clean_batches_do_not_rearm_a_current_loss_episode(self):
        d = BatchLossDetector()
        self.assertIsNotNone(self.pair(d, 2, rx=98))
        self.pair(d, 0)
        self.pair(d, 1)
        self.assertIsNone(self.pair(d, 3, rx=98))

    def test_pending_and_completed_storage_is_bounded_by_report_ttl(self):
        d = BatchLossDetector()
        for batch in range(200):
            self.pair(d, batch)
        d.advance(3_000_000_000)
        self.assertEqual(d.retained_batches, 0)


if __name__ == "__main__":
    unittest.main()
