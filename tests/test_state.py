import unittest

from limer_v0.route_plan import RoutePlan
from limer_v0.state import RouteState


class RouteStateTest(unittest.TestCase):
    def setUp(self):
        self.baseline = RoutePlan.balanced_active_active(4)
        self.recovered = self.baseline.localized_reroute(2, "A", "B")

    def test_starts_on_initial_plan_version_zero(self):
        state = RouteState(self.baseline)
        self.assertEqual(state.plan_for(0), (self.baseline, 0))

    def test_committed_plan_activates_only_at_effective_round(self):
        state = RouteState(self.baseline)
        state.prepare(version=1, plan=self.recovered, effective_round=5)
        state.commit(version=1)

        self.assertEqual(state.plan_for(4), (self.baseline, 0))
        self.assertEqual(state.plan_for(5), (self.recovered, 1))
        self.assertEqual(state.plan_for(6), (self.recovered, 1))

    def test_commit_without_prepare_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "prepared"):
            RouteState(self.baseline).commit(version=1)

    def test_stale_or_future_prepare_is_rejected(self):
        state = RouteState(self.baseline)
        with self.assertRaisesRegex(ValueError, "next version"):
            state.prepare(version=2, plan=self.recovered, effective_round=3)

    def test_duplicate_prepare_is_rejected(self):
        state = RouteState(self.baseline)
        state.prepare(version=1, plan=self.recovered, effective_round=3)
        with self.assertRaisesRegex(ValueError, "already prepared"):
            state.prepare(version=1, plan=self.recovered, effective_round=3)

    def test_noop_and_world_size_mismatch_are_rejected(self):
        state = RouteState(self.baseline)
        with self.assertRaisesRegex(ValueError, "differ"):
            state.prepare(version=1, plan=self.baseline, effective_round=3)
        with self.assertRaisesRegex(ValueError, "world_size"):
            state.prepare(
                version=1,
                plan=RoutePlan.single_fabric(2, "B"),
                effective_round=3,
            )

    def test_negative_effective_round_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "non-negative"):
            RouteState(self.baseline).prepare(
                version=1,
                plan=self.recovered,
                effective_round=-1,
            )

    def test_abort_preserves_active_plan(self):
        state = RouteState(self.baseline)
        state.prepare(version=1, plan=self.recovered, effective_round=2)
        state.abort(version=1)
        self.assertEqual(state.plan_for(10), (self.baseline, 0))

    def test_abort_can_rollback_commit_before_effective_round(self):
        state = RouteState(self.baseline)
        state.prepare(version=1, plan=self.recovered, effective_round=5)
        state.commit(version=1)
        self.assertEqual(state.plan_for(4), (self.baseline, 0))
        state.abort(version=1)
        self.assertEqual(state.plan_for(5), (self.baseline, 0))

    def test_wrong_commit_and_abort_versions_are_rejected(self):
        state = RouteState(self.baseline)
        state.prepare(version=1, plan=self.recovered, effective_round=5)
        with self.assertRaisesRegex(ValueError, "does not match"):
            state.commit(version=2)
        with self.assertRaisesRegex(ValueError, "does not match"):
            state.abort(version=2)


if __name__ == "__main__":
    unittest.main()
