import unittest

from limer_v0.orchestrator import _correctness_report
from limer_v0.route_plan import RoutePlan


def active_config(recovery_policy="localized"):
    return {
        "experiment_family": "active_active_v1",
        "routing_policy": "balanced_active_active",
        "recovery_policy": recovery_policy,
        "fault_scope": {"rank": 2, "fabric": "A", "direction": "egress"},
        "warmup_rounds": 0,
        "baseline_rounds": 1,
        "post_fault_rounds": 1,
    }


def worker_rows(baseline, recovered):
    rows = []
    for period, round_id, version, plan in (
        ("baseline", 0, 0, baseline),
        ("post_fault", 1, 1, recovered),
    ):
        for rank in range(4):
            predecessor = (rank - 1) % 4
            rows.append(
                {
                    "rank": rank,
                    "round_id": round_id,
                    "period": period,
                    "version": version,
                    "route_plan_fingerprint": plan.fingerprint,
                    "routing_policy": plan.policy,
                    "send_routes": list(plan.routes[rank]),
                    "receive_routes": list(plan.routes[predecessor]),
                    "bytes_sent_by_fabric": {
                        "A": plan.routes[rank].count("A") * 100,
                        "B": plan.routes[rank].count("B") * 100,
                    },
                    "checksum_errors": 0,
                    "version_errors": 0,
                }
            )
    return rows


def aggregate_rows(baseline, recovered):
    return [
        {
            "round_id": 0,
            "period": "baseline",
            "version": 0,
            "route_plan_fingerprint": baseline.fingerprint,
            "rank_count": 4,
        },
        {
            "round_id": 1,
            "period": "post_fault",
            "version": 1,
            "route_plan_fingerprint": recovered.fingerprint,
            "rank_count": 4,
        },
    ]


class CorrectnessReportTest(unittest.TestCase):
    def setUp(self):
        self.baseline = RoutePlan.balanced_active_active(4)
        self.recovered = self.baseline.localized_reroute(2, "A", "B")

    def test_passes_active_active_and_locality_gates(self):
        result = _correctness_report(
            active_config(),
            worker_rows(self.baseline, self.recovered),
            aggregate_rows(self.baseline, self.recovered),
            [{"event": "RECOVERY_COMMIT"}],
        )

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["plan_consistency"]["passed"])
        self.assertTrue(result["active_active_use"]["passed"])
        self.assertEqual(
            result["active_active_use"]["baseline_send_steps"],
            {"A": 12, "B": 12},
        )
        self.assertTrue(result["locality"]["passed"])
        self.assertEqual(result["locality"]["changed_slot_count"], 3)
        self.assertEqual(result["locality"]["changed_sender_ranks"], [2])
        self.assertEqual(result["locality"]["unchanged_sender_ranks"], [0, 1, 3])

    def test_fails_when_an_unaffected_sender_schedule_changes(self):
        rows = worker_rows(self.baseline, self.recovered)
        recovered_rank_zero = next(
            row
            for row in rows
            if row["period"] == "post_fault" and row["rank"] == 0
        )
        recovered_rank_zero["send_routes"] = ["B"] * 6

        result = _correctness_report(
            active_config(),
            rows,
            aggregate_rows(self.baseline, self.recovered),
            [{"event": "RECOVERY_COMMIT"}],
        )

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["locality"]["passed"])
        self.assertIn(0, result["locality"]["changed_sender_ranks"])

    def test_fails_when_healthy_baseline_does_not_use_both_fabrics(self):
        rows = worker_rows(self.baseline, self.recovered)
        for row in rows:
            if row["period"] == "baseline":
                row["send_routes"] = ["A"] * 6
                row["bytes_sent_by_fabric"] = {"A": 600, "B": 0}

        result = _correctness_report(
            active_config(),
            rows,
            aggregate_rows(self.baseline, self.recovered),
            [{"event": "RECOVERY_COMMIT"}],
        )

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["active_active_use"]["passed"])

    def test_fails_when_one_rank_has_a_different_fingerprint(self):
        rows = worker_rows(self.baseline, self.recovered)
        rows[-1]["route_plan_fingerprint"] = "0" * 64

        result = _correctness_report(
            active_config(),
            rows,
            aggregate_rows(self.baseline, self.recovered),
            [{"event": "RECOVERY_COMMIT"}],
        )

        self.assertEqual(result["status"], "fail")
        self.assertFalse(result["plan_consistency"]["passed"])

    def test_fails_when_consistent_fingerprint_hides_wrong_schedule(self):
        rows = worker_rows(self.baseline, self.baseline)
        for row in rows:
            row["version"] = 0
            row["route_plan_fingerprint"] = self.baseline.fingerprint
            row["routing_policy"] = self.baseline.policy
            rank = int(row["rank"])
            predecessor = (rank - 1) % 4
            row["send_routes"] = [
                "B" if route == "A" else "A"
                for route in self.baseline.routes[rank]
            ]
            row["receive_routes"] = [
                "B" if route == "A" else "A"
                for route in self.baseline.routes[predecessor]
            ]
        aggregates = aggregate_rows(self.baseline, self.baseline)
        aggregates[1]["version"] = 0
        aggregates[1]["route_plan_fingerprint"] = self.baseline.fingerprint

        result = _correctness_report(active_config(), rows, aggregates, [])

        self.assertEqual(result["status"], "fail")
        self.assertTrue(result["plan_consistency"]["passed"])
        self.assertTrue(result["active_active_use"]["passed"])
        self.assertFalse(result["schedule_conformance"]["passed"])
        self.assertGreater(result["schedule_conformance"]["failure_count"], 0)

    def test_transient_without_commit_does_not_require_locality_transition(self):
        rows = worker_rows(self.baseline, self.baseline)
        for row in rows:
            row["version"] = 0
            row["route_plan_fingerprint"] = self.baseline.fingerprint
        aggregates = aggregate_rows(self.baseline, self.baseline)
        aggregates[1]["version"] = 0
        aggregates[1]["route_plan_fingerprint"] = self.baseline.fingerprint

        result = _correctness_report(
            active_config(),
            rows,
            aggregates,
            [],
        )

        self.assertEqual(result["status"], "pass")
        self.assertFalse(result["locality"]["required"])
        self.assertIsNone(result["locality"]["passed"])

    def test_global_policy_requires_every_recovered_slot_on_b(self):
        global_b = RoutePlan.global_fabric(4, "B")
        result = _correctness_report(
            active_config("global_failover"),
            worker_rows(self.baseline, global_b),
            aggregate_rows(self.baseline, global_b),
            [{"event": "RECOVERY_COMMIT"}],
        )

        self.assertEqual(result["status"], "pass")
        self.assertTrue(result["locality"]["passed"])
        self.assertEqual(result["locality"]["mode"], "global_failover")
        self.assertEqual(result["locality"]["changed_slot_count"], 12)


if __name__ == "__main__":
    unittest.main()
