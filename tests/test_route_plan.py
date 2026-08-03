import unittest

from limer_v0.route_plan import RoutePlan


class RoutePlanTest(unittest.TestCase):
    def test_balanced_plan_uses_both_fabrics_each_step(self):
        plan = RoutePlan.balanced_active_active(world_size=4)

        self.assertEqual(plan.steps, 6)
        self.assertEqual(plan.routes[0], ("A", "B", "A", "B", "A", "B"))
        self.assertEqual(plan.routes[1], ("B", "A", "B", "A", "B", "A"))
        self.assertEqual(plan.routes[2], plan.routes[0])
        self.assertEqual(plan.routes[3], plan.routes[1])
        for step in range(plan.steps):
            self.assertEqual(
                {plan.route_for(rank, step) for rank in range(4)},
                {"A", "B"},
            )

    def test_localized_reroute_changes_only_faulty_sender_a_slots(self):
        baseline = RoutePlan.balanced_active_active(4)
        recovered = baseline.localized_reroute(2, "A", "B")

        self.assertEqual(recovered.policy, "localized_reroute")
        self.assertEqual(recovered.routes[2], ("B",) * 6)
        for rank in (0, 1, 3):
            self.assertEqual(recovered.routes[rank], baseline.routes[rank])
        self.assertEqual(
            baseline.changed_slots(recovered),
            [
                {
                    "sender_rank": 2,
                    "step_id": step,
                    "old_route": "A",
                    "new_route": "B",
                }
                for step in (0, 2, 4)
            ],
        )

    def test_single_and_global_plans_use_one_fabric(self):
        single = RoutePlan.single_fabric(4, "A")
        global_b = RoutePlan.global_fabric(4, "B")

        self.assertTrue(all(route == "A" for row in single.routes for route in row))
        self.assertTrue(
            all(route == "B" for row in global_b.routes for route in row)
        )
        self.assertEqual(len(single.changed_slots(global_b)), 24)

    def test_round_trip_and_fingerprint_are_stable(self):
        plan = RoutePlan.balanced_active_active(4)
        restored = RoutePlan.from_dict(plan.to_dict())

        self.assertEqual(restored, plan)
        self.assertEqual(restored.canonical_json(), plan.canonical_json())
        self.assertEqual(restored.fingerprint, plan.fingerprint)
        self.assertEqual(len(plan.fingerprint), 64)

    def test_fingerprint_changes_when_content_changes(self):
        baseline = RoutePlan.balanced_active_active(4)
        recovered = baseline.localized_reroute(2, "A", "B")

        self.assertNotEqual(baseline.fingerprint, recovered.fingerprint)

    def test_rejects_invalid_world_size_and_shape(self):
        with self.assertRaisesRegex(ValueError, "world_size"):
            RoutePlan.single_fabric(1, "A")
        with self.assertRaisesRegex(ValueError, "sender rows"):
            RoutePlan(2, "invalid", (("A", "B"),))
        with self.assertRaisesRegex(ValueError, "steps"):
            RoutePlan(2, "invalid", (("A",), ("B",)))

    def test_rejects_unsupported_fabric_and_invalid_lookup(self):
        with self.assertRaisesRegex(ValueError, "fabric"):
            RoutePlan.single_fabric(2, "C")
        plan = RoutePlan.single_fabric(2, "A")
        with self.assertRaisesRegex(IndexError, "sender_rank"):
            plan.route_for(2, 0)
        with self.assertRaisesRegex(IndexError, "step_id"):
            plan.route_for(0, 2)

    def test_rejects_invalid_or_noop_localized_reroute(self):
        plan = RoutePlan.balanced_active_active(4)
        with self.assertRaisesRegex(IndexError, "sender_rank"):
            plan.localized_reroute(4, "A", "B")
        with self.assertRaisesRegex(ValueError, "different"):
            plan.localized_reroute(2, "A", "A")
        with self.assertRaisesRegex(ValueError, "no slots"):
            RoutePlan.global_fabric(4, "B").localized_reroute(2, "A", "B")

    def test_from_dict_rejects_missing_and_extra_keys(self):
        value = RoutePlan.balanced_active_active(4).to_dict()
        missing = dict(value)
        missing.pop("policy")
        with self.assertRaisesRegex(ValueError, "keys"):
            RoutePlan.from_dict(missing)
        extra = dict(value, extra=True)
        with self.assertRaisesRegex(ValueError, "keys"):
            RoutePlan.from_dict(extra)

    def test_changed_slots_requires_matching_world_size(self):
        with self.assertRaisesRegex(ValueError, "world_size"):
            RoutePlan.single_fabric(2, "A").changed_slots(
                RoutePlan.single_fabric(4, "A")
            )


if __name__ == "__main__":
    unittest.main()
