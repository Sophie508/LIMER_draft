import unittest

from limer_v0.state import RouteState


class RouteStateTest(unittest.TestCase):
    def test_starts_on_fabric_a_version_zero(self):
        state = RouteState()
        self.assertEqual(state.route_for(0), ("A", 0))

    def test_committed_route_activates_only_at_effective_round(self):
        state = RouteState()
        state.prepare(version=1, route="B", effective_round=5)
        state.commit(version=1)
        self.assertEqual(state.route_for(4), ("A", 0))
        self.assertEqual(state.route_for(5), ("B", 1))
        self.assertEqual(state.route_for(6), ("B", 1))

    def test_commit_without_prepare_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "prepared"):
            RouteState().commit(version=1)

    def test_stale_or_future_prepare_is_rejected(self):
        state = RouteState()
        with self.assertRaisesRegex(ValueError, "next version"):
            state.prepare(version=2, route="B", effective_round=3)

    def test_abort_preserves_active_route(self):
        state = RouteState()
        state.prepare(version=1, route="B", effective_round=2)
        state.abort(version=1)
        self.assertEqual(state.route_for(10), ("A", 0))

    def test_abort_can_rollback_commit_before_effective_round(self):
        state = RouteState()
        state.prepare(version=1, route="B", effective_round=5)
        state.commit(version=1)
        self.assertEqual(state.route_for(4), ("A", 0))
        state.abort(version=1)
        self.assertEqual(state.route_for(5), ("A", 0))


if __name__ == "__main__":
    unittest.main()
