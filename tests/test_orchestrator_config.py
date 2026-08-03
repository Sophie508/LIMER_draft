import json
from pathlib import Path
import unittest

from limer_v0.orchestrator import (
    _assess_alternate_path_probe,
    _initial_route_plan,
    _recovery_route_plan,
    aggregate_round_events,
    validate_config,
)
from limer_v0.route_plan import RoutePlan


ROOT = Path(__file__).resolve().parents[1]


def valid_config():
    return {
        "condition": "C1",
        "topology": "single",
        "chunk_bytes": 2097152,
        "warmup_rounds": 1,
        "baseline_rounds": 2,
        "post_fault_rounds": 3,
        "fault_rate_mbit": 20.0,
        "fault_loss_pct": 0.0,
        "detector": False,
        "recovery": False,
        "oracle": False,
        "transient_ms": 0,
        "what_changes": "Rate-cap only w2 egress while the link stays up.",
        "expected": "Post-fault throughput remains below the baseline.",
    }


def valid_active_active_config():
    config = valid_config()
    config.update(
        {
            "condition": "C3",
            "topology": "dual",
            "detector": True,
            "recovery": True,
            "experiment_family": "active_active_v1",
            "scenario_id": "AA3_LOCAL",
            "routing_policy": "balanced_active_active",
            "recovery_policy": "localized",
            "fault_scope": {"rank": 2, "fabric": "A", "direction": "egress"},
        }
    )
    return config


class ConfigValidationTest(unittest.TestCase):
    def test_active_active_matrix(self):
        config_dir = ROOT / "configs" / "active_active_v1"
        paths = sorted(config_dir.glob("*.json"))
        self.assertEqual(len(paths), 7)
        scenario_ids = set()
        for path in paths:
            with self.subTest(path=path.name):
                with path.open(encoding="utf-8") as handle:
                    config = validate_config(json.load(handle))
                self.assertEqual(config["experiment_family"], "active_active_v1")
                self.assertEqual(config["topology"], "dual")
                self.assertEqual(
                    config["routing_policy"], "balanced_active_active"
                )
                self.assertEqual(
                    config["fault_scope"],
                    {"rank": 2, "fabric": "A", "direction": "egress"},
                )
                self.assertNotIn(config["scenario_id"], scenario_ids)
                scenario_ids.add(config["scenario_id"])
                self.assertTrue(config["what_changes"])
                self.assertTrue(config["expected"])
        self.assertEqual(
            scenario_ids,
            {
                "AA0_HEALTHY",
                "AA1_FAULT",
                "AA2_DETECT",
                "AA3_LOCAL",
                "AA3_GLOBAL",
                "AA4_ORACLE",
                "AA5_TRANSIENT",
            },
        )

    def test_accepts_complete_legacy_config_with_explicit_defaults(self):
        result = validate_config(valid_config())

        self.assertEqual(result["condition"], "C1")
        self.assertEqual(result["experiment_family"], "legacy_v0")
        self.assertEqual(result["scenario_id"], "C1")
        self.assertEqual(result["routing_policy"], "single_fabric")
        self.assertEqual(result["recovery_policy"], "none")
        self.assertEqual(
            result["fault_scope"],
            {"rank": 2, "fabric": "A", "direction": "egress"},
        )

    def test_accepts_strict_active_active_config(self):
        result = validate_config(valid_active_active_config())

        self.assertEqual(result["experiment_family"], "active_active_v1")
        self.assertEqual(result["scenario_id"], "AA3_LOCAL")
        self.assertEqual(result["routing_policy"], "balanced_active_active")
        self.assertEqual(result["recovery_policy"], "localized")

    def test_v1_requires_all_explicit_extension_fields(self):
        for field in (
            "scenario_id",
            "routing_policy",
            "recovery_policy",
            "fault_scope",
        ):
            config = valid_active_active_config()
            config.pop(field)
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, field
            ):
                validate_config(config)

    def test_rejects_blank_experiment_intent_and_scenario(self):
        for field in ("what_changes", "expected"):
            config = valid_config()
            config[field] = "   "
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_config(config)
        config = valid_active_active_config()
        config["scenario_id"] = "  "
        with self.assertRaisesRegex(ValueError, "scenario_id"):
            validate_config(config)

    def test_rejects_recovery_on_single_topology(self):
        config = valid_config()
        config["recovery"] = True
        with self.assertRaisesRegex(ValueError, "dual"):
            validate_config(config)

    def test_rejects_active_active_on_single_topology(self):
        config = valid_active_active_config()
        config["topology"] = "single"
        with self.assertRaisesRegex(ValueError, "active-active.*dual"):
            validate_config(config)

    def test_rejects_unknown_condition_family_or_policy(self):
        config = valid_config()
        config["condition"] = "C99"
        with self.assertRaisesRegex(ValueError, "condition"):
            validate_config(config)

        for field, value in (
            ("experiment_family", "future_v9"),
            ("routing_policy", "random"),
            ("recovery_policy", "silent_fallback"),
        ):
            config = valid_active_active_config()
            config[field] = value
            with self.subTest(field=field), self.assertRaisesRegex(ValueError, field):
                validate_config(config)

    def test_rejects_wrong_v1_fault_scope(self):
        for field, value in (
            ("rank", 1),
            ("fabric", "B"),
            ("direction", "bidirectional"),
        ):
            config = valid_active_active_config()
            config["fault_scope"] = dict(config["fault_scope"], **{field: value})
            with self.subTest(field=field), self.assertRaisesRegex(
                ValueError, "fault_scope"
            ):
                validate_config(config)

    def test_recovery_policy_matches_recovery_toggle(self):
        config = valid_active_active_config()
        config["recovery"] = False
        config["recovery_policy"] = "localized"
        with self.assertRaisesRegex(ValueError, "recovery_policy"):
            validate_config(config)

    def test_v1_scenario_id_cannot_mislabel_policy_or_condition(self):
        config = valid_active_active_config()
        config["scenario_id"] = "AA3_GLOBAL"
        with self.assertRaisesRegex(ValueError, "semantics mismatch"):
            validate_config(config)

        config = valid_active_active_config()
        config["scenario_id"] = "AA9_UNKNOWN"
        with self.assertRaisesRegex(ValueError, "scenario_id"):
            validate_config(config)

        config = valid_active_active_config()
        config["recovery_policy"] = "none"
        with self.assertRaisesRegex(ValueError, "recovery_policy"):
            validate_config(config)

    def test_c2_requires_detector(self):
        config = valid_config()
        config["condition"] = "C2"
        config["detector"] = False
        with self.assertRaisesRegex(ValueError, "detector"):
            validate_config(config)

    def test_c3_requires_full_non_oracle_path(self):
        config = valid_config()
        config.update(
            {
                "condition": "C3",
                "topology": "dual",
                "detector": True,
                "recovery": True,
            }
        )
        self.assertEqual(validate_config(config)["condition"], "C3")
        config["oracle"] = True
        with self.assertRaisesRegex(ValueError, "C3"):
            validate_config(config)

    def test_c5_requires_positive_transient(self):
        config = valid_config()
        config.update(
            {
                "condition": "C5",
                "topology": "dual",
                "detector": True,
                "recovery": True,
                "transient_ms": 0,
            }
        )
        with self.assertRaisesRegex(ValueError, "transient"):
            validate_config(config)


class RoundAggregationTest(unittest.TestCase):
    def _events(self):
        plan = RoutePlan.balanced_active_active(4)
        events = []
        for rank in range(4):
            send_routes = list(plan.routes[rank])
            predecessor = (rank - 1) % 4
            receive_routes = list(plan.routes[predecessor])
            events.append(
                {
                    "event": "ROUND_DONE",
                    "rank": rank,
                    "round_id": 3,
                    "version": 0,
                    "route_plan_fingerprint": plan.fingerprint,
                    "routing_policy": plan.policy,
                    "send_routes": send_routes,
                    "receive_routes": receive_routes,
                    "send_steps_by_fabric": {"A": 3, "B": 3},
                    "receive_steps_by_fabric": {"A": 3, "B": 3},
                    "bytes_sent_by_fabric": {"A": 3000, "B": 3000},
                    "bytes_received_by_fabric": {"A": 3000, "B": 3000},
                    "duration_ns": 1_000_000_000 + rank,
                    "bytes_sent": 6000,
                    "bytes_received": 6000,
                    "frame_count": 6,
                    "checksum_errors": 0,
                    "version_errors": 0,
                }
            )
        return events

    def test_aggregates_collective_round_by_slowest_rank_and_fabric(self):
        result = aggregate_round_events(self._events(), "baseline", world_size=4)

        self.assertEqual(result["round_id"], 3)
        self.assertEqual(result["period"], "baseline")
        self.assertEqual(result["version"], 0)
        self.assertEqual(result["bytes_completed"], 24_000)
        self.assertEqual(result["duration_ns"], 1_000_000_003)
        self.assertAlmostEqual(result["duration_s"], 1.000000003)
        self.assertEqual(result["fabric_steps_sent"], {"A": 12, "B": 12})
        self.assertEqual(result["fabric_steps_received"], {"A": 12, "B": 12})
        self.assertEqual(result["fabric_bytes_sent"], {"A": 12_000, "B": 12_000})
        self.assertEqual(
            result["fabric_bytes_received"], {"A": 12_000, "B": 12_000}
        )
        self.assertEqual(result["checksum_errors"], 0)
        self.assertEqual(result["version_errors"], 0)

    def test_rejects_missing_rank(self):
        with self.assertRaisesRegex(ValueError, "ranks"):
            aggregate_round_events(self._events()[:-1], "baseline", world_size=4)

    def test_rejects_fingerprint_or_version_split_brain(self):
        events = self._events()
        events[-1]["route_plan_fingerprint"] = "0" * 64
        with self.assertRaisesRegex(ValueError, "fingerprint"):
            aggregate_round_events(events, "post_fault", world_size=4)

        events = self._events()
        events[-1]["version"] = 1
        with self.assertRaisesRegex(ValueError, "version"):
            aggregate_round_events(events, "post_fault", world_size=4)

    def test_rejects_per_fabric_totals_that_do_not_match_bytes(self):
        events = self._events()
        events[0]["bytes_sent_by_fabric"]["A"] = 2999
        with self.assertRaisesRegex(ValueError, "bytes_sent"):
            aggregate_round_events(events, "baseline", world_size=4)


class RoutePlanSelectionTest(unittest.TestCase):
    def test_v1_localized_target_changes_only_rank_two_a_slots(self):
        config = validate_config(valid_active_active_config())
        baseline = _initial_route_plan(config)
        target = _recovery_route_plan(baseline, config)

        self.assertEqual(baseline.policy, "balanced_active_active")
        self.assertEqual(target.policy, "localized_reroute")
        self.assertEqual(len(baseline.changed_slots(target)), 3)
        for rank in (0, 1, 3):
            self.assertEqual(baseline.routes[rank], target.routes[rank])

    def test_global_baseline_changes_every_non_b_slot(self):
        config = valid_active_active_config()
        config["scenario_id"] = "AA3_GLOBAL"
        config["recovery_policy"] = "global_failover"
        config = validate_config(config)
        baseline = _initial_route_plan(config)
        target = _recovery_route_plan(baseline, config)

        self.assertEqual(target.policy, "global_fabric_B")
        self.assertEqual(len(baseline.changed_slots(target)), 12)


class StepGateConfigTest(unittest.TestCase):
    def test_defaults_are_legacy_round(self):
        config = validate_config(valid_active_active_config())
        self.assertEqual(config["detector_rule"], "legacy")
        self.assertEqual(config["host_gate"], "round")

    def test_aa6_requires_burst_rule_and_step_gate(self):
        config = valid_active_active_config()
        config["scenario_id"] = "AA6_STEPDETECT"
        with self.assertRaises(ValueError):
            validate_config(config)
        config["detector_rule"] = "burst"
        config["host_gate"] = "step"
        validated = validate_config(config)
        self.assertEqual(validated["scenario_id"], "AA6_STEPDETECT")

    def test_step_gate_requires_burst_rule(self):
        config = valid_active_active_config()
        config["host_gate"] = "step"
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_step_gate_requires_detector_and_recovery(self):
        config = valid_active_active_config()
        config.update(
            {
                "scenario_id": "AA1_FAULT",
                "condition": "C1",
                "detector": False,
                "recovery": False,
                "recovery_policy": "none",
                "host_gate": "step",
                "detector_rule": "legacy",
            }
        )
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_burst_rule_requires_detector(self):
        config = valid_active_active_config()
        config.update(
            {
                "scenario_id": "AA1_FAULT",
                "condition": "C1",
                "detector": False,
                "recovery": False,
                "recovery_policy": "none",
                "detector_rule": "burst",
            }
        )
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_unknown_values_are_rejected(self):
        config = valid_active_active_config()
        config["detector_rule"] = "psychic"
        with self.assertRaises(ValueError):
            validate_config(config)
        config = valid_active_active_config()
        config["host_gate"] = "vibes"
        with self.assertRaises(ValueError):
            validate_config(config)

    def test_transient_scenario_accepts_step_stack(self):
        config = valid_active_active_config()
        config.update(
            {
                "scenario_id": "AA5_TRANSIENT",
                "condition": "C5",
                "transient_ms": 100,
                "detector_rule": "burst",
                "host_gate": "step",
            }
        )
        validated = validate_config(config)
        self.assertEqual(validated["host_gate"], "step")


class AlternatePathProbeAssessmentTest(unittest.TestCase):
    BASELINE = {"max_latency_ms": 2.05}

    def test_quiet_assessment_rejects_queueing_latency(self):
        assessed = _assess_alternate_path_probe(
            {"healthy": True, "max_latency_ms": 103.0}, self.BASELINE
        )
        self.assertFalse(assessed["healthy"])
        self.assertEqual(assessed["probe_context"], "quiet-network")

    def test_loaded_assessment_tolerates_queueing_latency(self):
        assessed = _assess_alternate_path_probe(
            {"healthy": True, "max_latency_ms": 103.0}, self.BASELINE, loaded=True
        )
        self.assertTrue(assessed["healthy"])
        self.assertEqual(assessed["probe_context"], "loaded-mid-round")

    def test_loaded_assessment_still_rejects_extreme_latency(self):
        assessed = _assess_alternate_path_probe(
            {"healthy": True, "max_latency_ms": 400.0}, self.BASELINE, loaded=True
        )
        self.assertFalse(assessed["healthy"])

    def test_loaded_assessment_requires_ping_success(self):
        assessed = _assess_alternate_path_probe(
            {"healthy": False, "max_latency_ms": 10.0}, self.BASELINE, loaded=True
        )
        self.assertFalse(assessed["healthy"])


if __name__ == "__main__":
    unittest.main()
