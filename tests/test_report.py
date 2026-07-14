import xml.etree.ElementTree as ET
import unittest

from limer_v0.report import evaluate_run, render_throughput_svg, select_retention


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


if __name__ == "__main__":
    unittest.main()
