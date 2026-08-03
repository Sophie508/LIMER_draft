import json
from pathlib import Path
import tempfile
import xml.etree.ElementTree as ET
import unittest

from limer_v0.report import (
    evaluate_run,
    generate_report,
    render_throughput_svg,
    select_retention,
)


def summary(condition):
    return {
        "run_id": f"{condition.lower()}_rep01",
        "condition": condition,
        "status": "complete",
        "correctness_status": "pass",
        "fault_interface_operstate_after": "up",
        "detector_interface_operstate_after": "up",
        "fault_observation_isolation": {
            "same_interface": False,
            "detector_reads_injector_qdisc": False,
        },
        "fault_period_retention": 0.21,
        "post_recovery_retention": 0.97,
        "switch_detection": {"triggered": condition in {"C2", "C3", "C5"}},
        "host_refinement": {
            "action": "confirm" if condition == "C3" else "suppress"
        },
        "recovery": {"committed": condition in {"C3", "C4"}},
    }


def active_summary(scenario_id):
    value = summary("C3")
    value.update(
        {
            "run_id": f"{scenario_id.lower()}_rep01",
            "experiment_family": "active_active_v1",
            "scenario_id": scenario_id,
            "condition": {
                "AA0_HEALTHY": "C0",
                "AA1_FAULT": "C1",
                "AA2_DETECT": "C2",
                "AA3_LOCAL": "C3",
                "AA3_GLOBAL": "C3",
                "AA4_ORACLE": "C4",
                "AA5_TRANSIENT": "C5",
                "AA6_STEPDETECT": "C3",
            }[scenario_id],
            "routing": {
                "initial_policy": "balanced_active_active",
                "recovery_policy": (
                    "global_failover"
                    if scenario_id == "AA3_GLOBAL"
                    else "localized"
                    if scenario_id
                    in {"AA3_LOCAL", "AA4_ORACLE", "AA5_TRANSIENT", "AA6_STEPDETECT"}
                    else "none"
                ),
                "changed_slots": (
                    [{"sender_rank": 2, "step_id": step} for step in (0, 2, 4)]
                    if scenario_id
                    in {"AA3_LOCAL", "AA4_ORACLE", "AA6_STEPDETECT"}
                    else [
                        {"sender_rank": rank, "step_id": step}
                        for rank in range(4)
                        for step in range(6)
                        if (rank + step) % 2 == 0
                    ]
                    if scenario_id == "AA3_GLOBAL"
                    else []
                ),
            },
            "latency": {
                "l_switch_ms": 50.0,
                "l_host_ms": 5250.0,
                "l_detection_ms": 5300.0,
                "l_coordination_ms": 1.0,
                "l_fault_to_commit_ms": 5301.0,
                "l_commit_to_recovered_round_ms": 600.0,
                "l_fault_to_recovered_round_complete_ms": 5901.0,
                "latency_target": {
                    "numeric_target_ms": None,
                    "status": "not_formally_specified",
                },
            },
        }
    )
    condition = value["condition"]
    value["switch_detection"] = {
        "triggered": scenario_id in {
            "AA2_DETECT",
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA5_TRANSIENT",
            "AA6_STEPDETECT",
        }
    }
    value["host_refinement"] = {
        "action": (
            "confirm"
            if scenario_id in {"AA3_LOCAL", "AA3_GLOBAL", "AA6_STEPDETECT"}
            else "suppress"
            if scenario_id == "AA5_TRANSIENT"
            else None
        ),
        "gate_mode": (
            "step" if scenario_id == "AA6_STEPDETECT" else "round"
        ),
    }
    value["recovery"] = {
        "committed": scenario_id
        in {"AA3_LOCAL", "AA3_GLOBAL", "AA4_ORACLE", "AA6_STEPDETECT"}
    }
    if scenario_id == "AA6_STEPDETECT":
        value["latency"] = dict(
            value["latency"],
            l_switch_ms=50.0,
            l_host_ms=850.0,
            l_detection_ms=900.0,
            l_fault_to_commit_ms=2900.0,
            l_fault_to_recovered_round_complete_ms=4000.0,
        )
    if scenario_id == "AA0_HEALTHY":
        value["fault_period_retention"] = 1.0
        value["post_recovery_retention"] = None
    elif scenario_id in {"AA1_FAULT", "AA2_DETECT"}:
        value["fault_period_retention"] = 0.4
        value["post_recovery_retention"] = None
    elif scenario_id == "AA5_TRANSIENT":
        value["fault_period_retention"] = 0.95
        value["post_recovery_retention"] = None
    return value


def write_active_run(root: Path, scenario_id: str, repeat: int) -> None:
    run_id = f"{scenario_id.lower()}_rep{repeat:02d}"
    run_dir = root / run_id
    run_dir.mkdir()
    value = active_summary(scenario_id)
    value.update(
        {
            "run_id": run_id,
            "topology": "dual",
            "fault_interface": "w2-eth0",
            "detector_interface": "sA-eth3",
            "baseline": {"median_throughput_bps": 100_000_000.0},
            "post_fault": {"median_throughput_bps": 40_000_000.0},
            "post_recovery": (
                {"median_throughput_bps": 97_000_000.0}
                if scenario_id
                in {"AA3_LOCAL", "AA3_GLOBAL", "AA4_ORACLE", "AA6_STEPDETECT"}
                else None
            ),
        }
    )
    value["switch_detection"]["l_switch_ms"] = (
        50.0 if value["switch_detection"]["triggered"] else None
    )
    value["host_refinement"]["l_host_ms"] = (
        5250.0 if value["host_refinement"]["action"] else None
    )
    value["recovery"].update(
        {
            "l_coordination_ms": (
                1.0 if value["recovery"]["committed"] else None
            ),
            "l_fault_to_commit_ms": (
                5301.0 if value["recovery"]["committed"] else None
            ),
        }
    )
    (run_dir / "summary.json").write_text(
        json.dumps(value), encoding="utf-8"
    )
    correctness = {
        "checksum_errors": 0,
        "version_errors": 0,
        "active_active_use": {
            "passed": True,
            "baseline_send_bytes": {"A": 1, "B": 1},
        },
        "locality": {
            "passed": scenario_id
            in {"AA3_LOCAL", "AA3_GLOBAL", "AA4_ORACLE", "AA6_STEPDETECT"}
            or not value["recovery"]["committed"],
        },
    }
    (run_dir / "correctness.json").write_text(
        json.dumps(correctness), encoding="utf-8"
    )
    fault_ns = 1_000_000_000
    events = [
        {
            "event": "FAULT_APPLIED",
            "record": {"t_after_ns": fault_ns},
            "t_monotonic_ns": fault_ns,
        },
        {"event": "SWITCH_SUSPECT", "t_monotonic_ns": fault_ns + 50_000_000},
        {"event": "HOST_CONFIRM", "t_monotonic_ns": fault_ns + 5_300_000_000},
        {"event": "RECOVERY_COMMIT", "t_monotonic_ns": fault_ns + 5_301_000_000},
    ]
    (run_dir / "events.jsonl").write_text(
        "".join(json.dumps(event) + "\n" for event in events),
        encoding="utf-8",
    )
    (run_dir / "manifest.json").write_text("{}\n", encoding="utf-8")
    for name in (
        "switch_timeseries.csv",
        "worker_rounds.csv",
        "aggregate_rounds.csv",
        "version_commits.csv",
    ):
        (run_dir / name).write_text("header\n", encoding="utf-8")


class ReportGateTest(unittest.TestCase):
    def test_selects_recovery_retention_for_recovery_conditions(self):
        self.assertEqual(select_retention(summary("C3")), 0.97)
        self.assertEqual(select_retention(summary("C4")), 0.97)
        self.assertEqual(select_retention(summary("C1")), 0.21)

    def test_accepts_expected_c1_through_c5_outcomes(self):
        for condition in ("C1", "C2", "C3", "C4", "C5"):
            with self.subTest(condition=condition):
                self.assertEqual(evaluate_run(summary(condition)), [])

    def test_rejects_false_recovery_on_transient(self):
        value = summary("C5")
        value["recovery"]["committed"] = True
        failures = evaluate_run(value)
        self.assertTrue(any("must not commit" in failure for failure in failures))

    def test_rejects_tautological_injector_observation(self):
        value = summary("C2")
        value["fault_observation_isolation"]["same_interface"] = True
        failures = evaluate_run(value)
        self.assertTrue(any("must be distinct" in failure for failure in failures))

    def test_svg_is_parseable_and_labels_allreduce_like(self):
        svg = render_throughput_svg(
            {"C0": [1.0], "C1": [0.21], "C3": [0.97]}
        )
        ET.fromstring(svg)
        self.assertIn("AllReduce-like", svg)
        self.assertNotIn("NCCL AllReduce", svg)

    def test_selects_active_active_retention_by_scenario(self):
        self.assertEqual(select_retention(active_summary("AA3_LOCAL")), 0.97)
        self.assertEqual(select_retention(active_summary("AA3_GLOBAL")), 0.97)
        self.assertEqual(select_retention(active_summary("AA4_ORACLE")), 0.97)
        self.assertEqual(select_retention(active_summary("AA1_FAULT")), 0.4)

    def test_accepts_predeclared_active_active_scenario_semantics(self):
        for scenario in (
            "AA0_HEALTHY",
            "AA1_FAULT",
            "AA2_DETECT",
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA4_ORACLE",
            "AA5_TRANSIENT",
        ):
            with self.subTest(scenario=scenario):
                self.assertEqual(evaluate_run(active_summary(scenario)), [])

    def test_rejects_localized_summary_that_changes_an_unaffected_sender(self):
        value = active_summary("AA3_LOCAL")
        value["routing"]["changed_slots"].append(
            {"sender_rank": 0, "step_id": 0}
        )
        failures = evaluate_run(value)
        self.assertTrue(any("worker 2" in failure for failure in failures))

    def test_does_not_invent_a_numeric_latency_target(self):
        target = active_summary("AA3_LOCAL")["latency"]["latency_target"]
        self.assertIsNone(target["numeric_target_ms"])
        self.assertEqual(target["status"], "not_formally_specified")

    def test_generates_complete_active_active_matrix_report(self):
        scenarios = (
            "AA0_HEALTHY",
            "AA1_FAULT",
            "AA2_DETECT",
            "AA3_LOCAL",
            "AA3_GLOBAL",
            "AA4_ORACLE",
            "AA5_TRANSIENT",
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for scenario in scenarios:
                for repeat in range(1, 4):
                    write_active_run(root, scenario, repeat)

            aggregate = generate_report(root)

            self.assertEqual(aggregate["formal_run_count"], 21)
            self.assertTrue(aggregate["three_runs_per_scenario"])
            self.assertTrue(aggregate["overall_acceptance"])
            self.assertIsNone(
                aggregate["latency_target"]["numeric_target_ms"]
            )
            for output in (
                "summary.csv",
                "aggregate_summary.json",
                "throughput.svg",
                "timeline.svg",
                "README.md",
            ):
                self.assertTrue((root / output).is_file(), output)
            ET.parse(root / "throughput.svg")
            ET.parse(root / "timeline.svg")
            report_readme = (root / "README.md").read_text(encoding="utf-8")
            self.assertIn("Run-level experiment matrix: **PASS**", report_readme)
            self.assertIn("directed Fabric A egress", report_readme)


class StepDetectGateTest(unittest.TestCase):
    def aa6_summary(self):
        value = active_summary("AA6_STEPDETECT")
        value["post_recovery_retention"] = 0.94
        return value

    def test_accepts_fast_step_gated_recovery(self):
        self.assertEqual(evaluate_run(self.aa6_summary()), [])

    def test_rejects_slow_switch_suspicion(self):
        value = self.aa6_summary()
        value["latency"]["l_switch_ms"] = 2777.0
        failures = evaluate_run(value)
        self.assertTrue(any("switch suspicion" in f for f in failures))

    def test_rejects_slow_confirmation(self):
        value = self.aa6_summary()
        value["latency"]["l_detection_ms"] = 2868.0
        failures = evaluate_run(value)
        self.assertTrue(any("fault-to-confirm" in f for f in failures))

    def test_rejects_round_gate_mode(self):
        value = self.aa6_summary()
        value["host_refinement"]["gate_mode"] = "round"
        failures = evaluate_run(value)
        self.assertTrue(any("step mode" in f for f in failures))

    def test_rejects_non_localized_change_set(self):
        value = self.aa6_summary()
        value["routing"]["changed_slots"] = [
            {"sender_rank": rank, "step_id": 0} for rank in range(4)
        ]
        failures = evaluate_run(value)
        self.assertTrue(any("worker 2 route slots" in f for f in failures))

    def test_partial_campaign_keeps_honest_denominator(self):
        scenarios = ("AA6_STEPDETECT", "AA5_TRANSIENT", "AA3_LOCAL")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            for scenario in scenarios:
                for repeat in range(1, 4):
                    write_active_run(root, scenario, repeat)
            aggregate = generate_report(root)
        self.assertEqual(aggregate["formal_run_count"], 9)
        self.assertEqual(aggregate["expected_formal_run_count"], 9)
        self.assertEqual(
            sorted(aggregate["scenarios_present"]), sorted(scenarios)
        )
        self.assertIn("AA0_HEALTHY", aggregate["scenarios_absent"])
        self.assertTrue(aggregate["three_runs_per_scenario"])
        self.assertTrue(aggregate["overall_acceptance"])


if __name__ == "__main__":
    unittest.main()
