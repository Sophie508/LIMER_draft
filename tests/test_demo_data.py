import importlib.util
import json
from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_demo_data", ROOT / "scripts" / "build_demo_data.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = MODULE.build_payload(ROOT)

    def test_formal_denominator_and_gate_counts_are_exact(self):
        self.assertEqual(self.payload["meta"]["formal_run_count"], 18)
        self.assertEqual(self.payload["meta"]["gate_pass_count"], 16)
        self.assertFalse(self.payload["meta"]["overall_acceptance"])
        self.assertEqual(self.payload["conditions"]["C3"]["gate_pass_count"], 1)

    def test_c3_runs_preserve_all_repeats(self):
        runs = self.payload["c3_runs"]
        self.assertEqual(
            [run["id"] for run in runs],
            ["c3_rep01", "c3_rep02", "c3_rep03"],
        )
        self.assertEqual(
            [round(run["post_recovery_retention"], 3) for run in runs],
            [0.971, 0.853, 0.865],
        )
        self.assertEqual([run["gate"] for run in runs], ["PASS", "FAIL", "FAIL"])

    def test_c3_rep01_timing_and_fault_window_are_traceable(self):
        run = self.payload["c3_runs"][0]
        self.assertAlmostEqual(run["switch_detection_ms"], 39.905322)
        self.assertAlmostEqual(run["host_confirmation_ms"], 5283.694265)
        self.assertAlmostEqual(run["coordination_ms"], 0.625035)
        self.assertAlmostEqual(run["fault_retention"], 0.21297836608124676)
        self.assertEqual(run["source_summary"], "results/c3_rep01/summary.json")
        self.assertEqual(run["source_events"], "results/c3_rep01/events.jsonl")
        self.assertEqual(
            run["source_correctness"],
            "results/c3_rep01/correctness.json",
        )
        self.assertEqual(run["checksum_errors"], 0)
        self.assertEqual(run["version_errors"], 0)

    def test_render_is_stable_and_committed_payload_matches(self):
        rendered = MODULE.render_payload(self.payload)
        committed = (ROOT / "docs/assets/data/demo-data.json").read_text(
            encoding="utf-8"
        )
        self.assertEqual(committed, rendered)
        self.assertEqual(json.loads(rendered), self.payload)


if __name__ == "__main__":
    unittest.main()
