import unittest

from limer_v0.refiner import HostRefiner


SWITCH_EVENT = {
    "event": "SWITCH_SUSPECT",
    "interface": "sA-eth3",
    "signals": {"egress_bps": 20_000_000, "backlog_bytes": 120_000},
}


class HostRefinerTest(unittest.TestCase):
    def test_confirms_persistent_impact_when_standby_is_healthy(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 5.3, "round_id": 3},
            baseline_p95_s=1.2,
            standby_probe={"healthy": True, "median_latency_ms": 4.4},
        )
        self.assertEqual(decision.action, "confirm")
        self.assertTrue(any("1.5" in reason for reason in decision.reasons))
        self.assertIsNone(decision.confidence)

    def test_suppresses_transient_without_persistent_collective_impact(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 1.25, "round_id": 3},
            baseline_p95_s=1.2,
            standby_probe={"healthy": True, "median_latency_ms": 4.4},
        )
        self.assertEqual(decision.action, "suppress")
        self.assertTrue(any("not persistent" in reason for reason in decision.reasons))

    def test_defers_when_standby_fabric_is_unhealthy(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 5.3, "round_id": 3},
            baseline_p95_s=1.2,
            standby_probe={"healthy": False, "median_latency_ms": None},
        )
        self.assertEqual(decision.action, "defer")
        self.assertTrue(any("standby" in reason for reason in decision.reasons))


if __name__ == "__main__":
    unittest.main()
