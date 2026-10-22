import importlib.util
import json
from pathlib import Path
import tempfile
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
        self.assertTrue(all(run["mode"] == "legacy_global" for run in runs))
        active_runs = self.payload["active_active_runs"]
        self.assertEqual(
            [run["id"] for run in active_runs],
            ["aa3_local_rep01", "aa3_local_rep02", "aa3_local_rep03"],
        )
        self.assertTrue(
            all(run["mode"] == "active_active_local" for run in active_runs)
        )
        self.assertEqual(self.payload["replay_runs"], runs + active_runs)
        self.assertEqual(self.payload["active_active_status"], "measured")

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

    def _write_active_fixture(self, root, changed_slots=None):
        run_dir = root / "results_active_active" / "aa3_local_rep01"
        run_dir.mkdir(parents=True)
        if changed_slots is None:
            changed_slots = [
                {
                    "sender_rank": 2,
                    "step_id": step,
                    "old_route": "A",
                    "new_route": "B",
                }
                for step in (0, 2, 4)
            ]
        summary = {
            "run_id": "aa3_local_rep01",
            "status": "complete",
            "experiment_family": "active_active_v1",
            "scenario_id": "AA3_LOCAL",
            "fault_period_retention": 0.41,
            "post_recovery_retention": 0.96,
            "routing": {
                "initial_plan_fingerprint": "a" * 64,
                "recovered_plan_fingerprint": "b" * 64,
                "changed_slots": changed_slots,
            },
            "latency": {
                "l_switch_ms": 42.0,
                "l_host_ms": 5100.0,
                "l_coordination_ms": 0.8,
                "l_fault_to_recovered_round_complete_ms": 5800.0,
            },
        }
        correctness = {
            "status": "pass",
            "checksum_errors": 0,
            "version_errors": 0,
            "active_active_use": {
                "passed": True,
                "baseline_send_bytes": {"A": 1000, "B": 1000},
            },
            "locality": {
                "passed": True,
                "changed_slot_count": len(changed_slots),
                "changed_sender_ranks": sorted(
                    {change["sender_rank"] for change in changed_slots}
                ),
            },
        }
        events = [
            {"event": name, "t_monotonic_ns": index + 1}
            for index, name in enumerate(MODULE.EVENT_NAMES)
        ]
        (run_dir / "summary.json").write_text(
            json.dumps(summary), encoding="utf-8"
        )
        (run_dir / "correctness.json").write_text(
            json.dumps(correctness), encoding="utf-8"
        )
        (run_dir / "events.jsonl").write_text(
            "".join(json.dumps(event) + "\n" for event in events),
            encoding="utf-8",
        )
        return run_dir

    def test_active_run_is_built_only_from_complete_valid_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_active_fixture(root)

            run = MODULE.build_active_run(root, "aa3_local_rep01")

            self.assertEqual(run["mode"], "active_active_local")
            self.assertEqual(run["family_label"], "Active-active v1")
            self.assertEqual(run["changed_slot_count"], 3)
            self.assertEqual(run["changed_sender_ranks"], [2])
            self.assertEqual(run["baseline_fabric_bytes"], {"A": 1000, "B": 1000})
            self.assertEqual(run["switch_detection_ms"], 42.0)
            self.assertEqual(run["post_recovery_retention"], 0.96)
            self.assertEqual(
                run["source_summary"],
                "results_active_active/aa3_local_rep01/summary.json",
            )

    def test_active_run_rejects_partial_or_nonlocal_evidence(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            run_dir = self._write_active_fixture(root)
            (run_dir / "correctness.json").unlink()
            with self.assertRaisesRegex(ValueError, "missing"):
                MODULE.build_active_run(root, "aa3_local_rep01")

        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self._write_active_fixture(
                root,
                changed_slots=[
                    {
                        "sender_rank": 0,
                        "step_id": 0,
                        "old_route": "A",
                        "new_route": "B",
                    }
                ],
            )
            with self.assertRaisesRegex(ValueError, "three worker-2"):
                MODULE.build_active_run(root, "aa3_local_rep01")


if __name__ == "__main__":
    unittest.main()
