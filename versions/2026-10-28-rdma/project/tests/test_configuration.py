"""Configuration boundaries and portable input generation for a fresh checkout."""
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from limerlab.config import Scenario
from limerlab.inputs import generate


class ConfigurationTests(unittest.TestCase):
    def test_invalid_workload_geometry_rejected(self):
        for n in [0, 15, 17]:
            with self.assertRaises(ValueError): Scenario(chunks_per_phase=n)

    def test_invalid_fault_window_rejected(self):
        with self.assertRaises(ValueError): Scenario(fault_ns=100000000, horizon_ns=100000000)

    def test_inputs_live_under_the_requested_run_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'new-run'
            generate(path, Scenario())
            text = (path / 'config.txt').read_text()
            self.assertIn(path.resolve().as_posix() + '/flow.txt', text)
            self.assertNotIn('${', text)
            for line in text.splitlines():
                fields = line.split()
                if fields and fields[0].endswith('_FILE'):
                    self.assertEqual(Path(fields[1]).parent, path.resolve())

    def test_two_planes_and_requested_local_bandwidth_preserved(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'new-run'
            generate(path, Scenario(local_gbps=100))
            rows = (path / 'topology.txt').read_text().splitlines()
            for gpu in range(16):
                edges = [r.split() for r in rows[2:] if r.split()[0] == str(gpu)]
                self.assertEqual(len([r for r in edges if int(r[1]) >= 20]), 2)
                self.assertEqual([r[2] for r in edges if 16 <= int(r[1]) < 20], ['100Gbps'])


if __name__ == '__main__':
    unittest.main()
