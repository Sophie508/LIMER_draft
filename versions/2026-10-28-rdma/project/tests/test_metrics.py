"""Ensure rescue completion cannot masquerade as sustained fresh-route service."""
import csv
import json
from pathlib import Path
import tempfile
import unittest
from test_audit import fixture

from limerlab import metrics


def prepare(root):
    fixture(root)
    (root / 'phase_events.csv').write_text('timestamp_ns,event,phase\n1,PHASE,0\n')
    (root / 'run_manifest.json').write_text(json.dumps(dict(scene=dict(family='blackhole', fault_ns=1, node=0))))
    path = root / 'run_status.json'
    status = json.loads(path.read_text())
    status.update(horizon_ns=50000000, job_done_ns=0)
    path.write_text(json.dumps(status))


class MetricsTests(unittest.TestCase):
    def test_rescued_data_does_not_count_as_new_proxy_service(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepare(root)
            result = metrics.calculate(root)
            self.assertEqual(result['new_Bprime_completions'], 0)
            self.assertFalse(result['sustained_new_proxy_observed'])
            self.assertFalse(result['recovery_observed'])  # One rescued chunk is not the whole job.
            self.assertEqual(result['fresh_proxy_costs']['completed_routes'], 0)

    def test_fresh_data_and_end_to_end_notification_are_measured(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepare(root)
            path = root / 'logical_events.csv'
            with path.open() as f:
                reader = csv.DictReader(f); columns, data = reader.fieldnames, list(reader)
            launch = next(r for r in data if r['event'] == 'PROXY_LAUNCH')
            target = launch['chunk_id']
            kept = []
            for r in data:
                if r['chunk_id'] == target:
                    if r['event'] in ['DIRECT_LAUNCH', 'MIGRATE']: continue
                    if r['event'] == 'ALLOC':
                        r['timestamp_ns'], r['epoch'] = launch['timestamp_ns'], '1'
                kept.append(r)
            kept.sort(key=lambda r: int(r['timestamp_ns']))
            with path.open('w', newline='') as f:
                writer = csv.DictWriter(f, fieldnames=columns); writer.writeheader(); writer.writerows(kept)
            result = metrics.calculate(root)
            self.assertEqual(result['new_Bprime_completions'], 1)
            self.assertFalse(result['sustained_new_proxy_observed'])  # One phase is not sustained evidence.
            self.assertEqual(result['fresh_proxy_costs']['completed_routes'], 1)
            self.assertGreaterEqual(result['fresh_proxy_costs']['final_notification_ms'], 1)

    def test_incomplete_phase_does_not_enter_steady_performance(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); prepare(root)
            result = metrics.calculate(root)
            self.assertEqual(result['post_replacement_complete_phases'], 0)
            self.assertIsNone(result['post_replacement_mean_phase_ms'])


if __name__ == '__main__':
    unittest.main()
