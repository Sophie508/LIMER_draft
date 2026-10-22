import unittest

from limer_v0.refiner import HostRefiner, StepGateRefiner


SWITCH_EVENT = {
    "event": "SWITCH_SUSPECT",
    "interface": "sA-eth3",
    "signals": {"egress_bps": 20_000_000, "backlog_bytes": 120_000},
}


class HostRefinerTest(unittest.TestCase):
    def test_confirms_persistent_impact_when_alternate_path_is_healthy(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 5.3, "round_id": 3},
            baseline_p95_s=1.2,
            alternate_path_probe={"healthy": True, "median_latency_ms": 4.4},
        )
        self.assertEqual(decision.action, "confirm")
        self.assertTrue(any("1.5" in reason for reason in decision.reasons))
        self.assertIsNone(decision.confidence)

    def test_suppresses_transient_without_persistent_collective_impact(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 1.25, "round_id": 3},
            baseline_p95_s=1.2,
            alternate_path_probe={"healthy": True, "median_latency_ms": 4.4},
        )
        self.assertEqual(decision.action, "suppress")
        self.assertTrue(any("not persistent" in reason for reason in decision.reasons))

    def test_defers_when_alternate_fabric_is_unhealthy(self):
        decision = HostRefiner().evaluate(
            SWITCH_EVENT,
            degraded_round={"duration_s": 5.3, "round_id": 3},
            baseline_p95_s=1.2,
            alternate_path_probe={"healthy": False, "median_latency_ms": None},
        )
        self.assertEqual(decision.action, "defer")
        self.assertTrue(any("alternate" in reason for reason in decision.reasons))


def slow_step(rank, round_id, step_id, duration_s):
    return {
        "rank": rank,
        "round_id": round_id,
        "step_id": step_id,
        "duration_s": duration_s,
        "t_monotonic_ns": 0,
    }


class StepGateRefinerTest(unittest.TestCase):
    def test_slow_classification_uses_step_p95_factor(self):
        refiner = StepGateRefiner(slowdown_factor=1.5)
        self.assertFalse(refiner.is_slow(0.20, 0.178))
        self.assertTrue(refiner.is_slow(0.28, 0.178))

    def test_confirms_with_two_confirmable_steps_and_healthy_probe(self):
        refiner = StepGateRefiner()
        decision = refiner.evaluate(
            SWITCH_EVENT,
            [slow_step(3, 3, 0, 0.882), slow_step(0, 3, 1, 0.870)],
            0.178,
            {"healthy": True},
        )
        self.assertEqual(decision.action, "confirm")
        self.assertTrue(any("burst-rate degradation" in r for r in decision.reasons))

    def test_defers_below_minimum_confirmable_steps(self):
        refiner = StepGateRefiner()
        decision = refiner.evaluate(
            SWITCH_EVENT, [slow_step(3, 3, 0, 0.882)], 0.178, {"healthy": True}
        )
        self.assertEqual(decision.action, "defer")

    def test_defers_without_switch_suspicion(self):
        refiner = StepGateRefiner()
        decision = refiner.evaluate(
            None,
            [slow_step(3, 3, 0, 0.882), slow_step(0, 3, 1, 0.870)],
            0.178,
            {"healthy": True},
        )
        self.assertEqual(decision.action, "defer")

    def test_defers_when_alternate_fabric_is_unhealthy(self):
        refiner = StepGateRefiner()
        decision = refiner.evaluate(
            SWITCH_EVENT,
            [slow_step(3, 3, 0, 0.882), slow_step(0, 3, 1, 0.870)],
            0.178,
            {"healthy": False},
        )
        self.assertEqual(decision.action, "defer")

    def test_suppression_reports_step_accounting(self):
        refiner = StepGateRefiner()
        decision = refiner.suppression(7, 0)
        self.assertEqual(decision.action, "suppress")
        self.assertIn("7 slow steps", decision.reasons[0])


if __name__ == "__main__":
    unittest.main()
