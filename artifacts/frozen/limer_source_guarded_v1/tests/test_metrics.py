import unittest

from limer_v0.metrics import summarize_interval, summarize_rounds


class MetricsTest(unittest.TestCase):
    def test_summarizes_throughput_and_retention(self):
        rows = [
            {"bytes_completed": 1000, "duration_s": 2.0},
            {"bytes_completed": 1000, "duration_s": 4.0},
            {"bytes_completed": 1000, "duration_s": 2.0},
        ]
        result = summarize_rounds(rows, baseline_median_bps=1000.0)
        self.assertEqual(result["round_count"], 3)
        self.assertEqual(result["median_throughput_bps"], 4000.0)
        self.assertEqual(result["fault_period_retention"], 4.0)
        self.assertEqual(result["baseline_median_bps"], 1000.0)

    def test_rejects_zero_baseline(self):
        with self.assertRaisesRegex(ValueError, "baseline"):
            summarize_rounds([{"bytes_completed": 1, "duration_s": 1}], 0)

    def test_rejects_non_positive_duration(self):
        with self.assertRaisesRegex(ValueError, "duration"):
            summarize_rounds([{"bytes_completed": 1, "duration_s": 0}], 1)

    def test_rejects_empty_rows(self):
        with self.assertRaisesRegex(ValueError, "round"):
            summarize_rounds([], 1)

    def test_summarizes_time_weighted_interval(self):
        rows = [
            {"bytes_completed": 1000, "duration_s": 2.0},
            {"bytes_completed": 3000, "duration_s": 6.0},
        ]

        result = summarize_interval(rows, baseline_median_bps=8000.0)

        self.assertEqual(result["round_count"], 2)
        self.assertEqual(result["total_bytes_completed"], 4000)
        self.assertEqual(result["total_duration_s"], 8.0)
        self.assertEqual(result["interval_throughput_bps"], 4000.0)
        self.assertEqual(result["interval_retention"], 0.5)

    def test_interval_rejects_invalid_inputs(self):
        with self.assertRaisesRegex(ValueError, "at least one"):
            summarize_interval([], 1.0)
        with self.assertRaisesRegex(ValueError, "baseline"):
            summarize_interval([{"bytes_completed": 1, "duration_s": 1}], 0)
        with self.assertRaisesRegex(ValueError, "duration"):
            summarize_interval([{"bytes_completed": 1, "duration_s": 0}], 1)
        with self.assertRaisesRegex(ValueError, "non-negative"):
            summarize_interval([{"bytes_completed": -1, "duration_s": 1}], 1)


if __name__ == "__main__":
    unittest.main()
