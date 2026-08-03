import unittest

from limer_v0.orchestrator import _latency_summary


class LatencySummaryTest(unittest.TestCase):
    def test_derives_all_closed_loop_stages(self):
        result = _latency_summary(
            fault_t_ns=1_000_000_000,
            suspect_t_ns=1_050_000_000,
            host_decision_t_ns=6_300_000_000,
            host_action="confirm",
            oracle_trigger_t_ns=None,
            commit_t_ns=6_301_000_000,
            recovered_round_end_t_ns=7_000_000_000,
        )

        self.assertEqual(result["l_switch_ms"], 50.0)
        self.assertEqual(result["l_host_ms"], 5250.0)
        self.assertEqual(result["l_detection_ms"], 5300.0)
        self.assertEqual(result["l_coordination_ms"], 1.0)
        self.assertEqual(result["l_fault_to_commit_ms"], 5301.0)
        self.assertEqual(result["l_commit_to_recovered_round_ms"], 699.0)
        self.assertEqual(
            result["l_fault_to_recovered_round_complete_ms"], 6000.0
        )
        self.assertEqual(
            result["latency_target"]["status"], "not_formally_specified"
        )
        self.assertIsNone(result["latency_target"]["numeric_target_ms"])

    def test_oracle_uses_oracle_trigger_and_leaves_host_fields_null(self):
        result = _latency_summary(
            fault_t_ns=1_000_000_000,
            suspect_t_ns=None,
            host_decision_t_ns=None,
            host_action=None,
            oracle_trigger_t_ns=1_001_000_000,
            commit_t_ns=1_002_000_000,
            recovered_round_end_t_ns=1_500_000_000,
        )

        self.assertIsNone(result["l_switch_ms"])
        self.assertIsNone(result["l_host_ms"])
        self.assertIsNone(result["l_detection_ms"])
        self.assertEqual(result["l_coordination_ms"], 1.0)
        self.assertEqual(result["l_fault_to_commit_ms"], 2.0)
        self.assertEqual(result["l_commit_to_recovered_round_ms"], 498.0)

    def test_suppression_is_a_host_decision_not_confirmed_detection(self):
        result = _latency_summary(
            fault_t_ns=1_000_000_000,
            suspect_t_ns=1_010_000_000,
            host_decision_t_ns=1_020_000_000,
            host_action="suppress",
            oracle_trigger_t_ns=None,
            commit_t_ns=None,
            recovered_round_end_t_ns=None,
        )

        self.assertEqual(result["l_switch_ms"], 10.0)
        self.assertEqual(result["l_host_ms"], 10.0)
        self.assertIsNone(result["l_detection_ms"])
        self.assertIsNone(result["l_coordination_ms"])

    def test_missing_timestamps_stay_null_and_negative_order_is_rejected(self):
        result = _latency_summary(
            fault_t_ns=None,
            suspect_t_ns=None,
            host_decision_t_ns=None,
            host_action=None,
            oracle_trigger_t_ns=None,
            commit_t_ns=None,
            recovered_round_end_t_ns=None,
        )
        for field in (
            "l_switch_ms",
            "l_host_ms",
            "l_detection_ms",
            "l_coordination_ms",
            "l_fault_to_commit_ms",
            "l_commit_to_recovered_round_ms",
            "l_fault_to_recovered_round_complete_ms",
        ):
            self.assertIsNone(result[field])

        with self.assertRaisesRegex(ValueError, "timestamp order"):
            _latency_summary(
                fault_t_ns=2,
                suspect_t_ns=1,
                host_decision_t_ns=None,
                host_action=None,
                oracle_trigger_t_ns=None,
                commit_t_ns=None,
                recovered_round_end_t_ns=None,
            )


if __name__ == "__main__":
    unittest.main()
