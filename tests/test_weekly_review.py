"""Keep the weekly explanation linked to the selected raw campaigns."""
from pathlib import Path
import json
import unittest

ROOT = Path(__file__).resolve().parents[1]


class WeeklyReviewTests(unittest.TestCase):
    def setUp(self):
        self.data = json.loads((ROOT / "docs/assets/weekly/evidence.json").read_text())

    def test_selected_campaign_counts_preserve_failure(self):
        records = self.data["records"]
        self.assertEqual(93, len(records))
        self.assertEqual(93, len({r["path"] for r in records}))
        self.assertEqual(92, sum(r["status"] == "complete" for r in records))
        self.assertEqual([9, 42, 18, 18, 6], [c["runs"] for c in self.data["campaigns"]])
        for record in records:
            raw = json.loads((ROOT / record["path"] / "summary.json").read_text())
            self.assertEqual(raw["status"], record["status"])
            self.assertEqual(raw.get("latency", {}).get("l_switch_ms"), record["detection_ms"])

    def test_loss_denominator_and_threshold(self):
        fast = [r for r in self.data["records"] if r["scenario"] == "AA13_LOSSFAST"]
        self.assertEqual(18, len(fast))
        self.assertEqual(18, sum(r["detected"] for r in fast))
        self.assertEqual(6, sum(r["detection_ms"] < 100 for r in fast))
        for loss in (0.5, 1, 2, 5, 10, 25):
            self.assertEqual(3, sum(r["loss"] == loss for r in fast))

    def test_demo_routes_and_sandbox_exist(self):
        page = (ROOT / "docs/weekly-demo.html").read_text()
        self.assertIn('sandbox="allow-scripts"', page)
        for relative in ("demos/normal-flow.html", "demos/recovery-flow.html"):
            demo = (ROOT / "docs" / relative).read_text()
            self.assertIn("Content-Security-Policy", demo)
            self.assertIn("sandbox=", demo)
            self.assertIn(relative, page)
        self.assertIn("weekly-demo.html", (ROOT / "docs/index.html").read_text())


if __name__ == "__main__":
    unittest.main()
