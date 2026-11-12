"""Lossless degradation inputs and policy-mode registration boundaries."""
from pathlib import Path
import sys
import tempfile
import unittest
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'python'))
from limerlab.config import Scenario
from limerlab.inputs import inject


class GrayConfigurationTests(unittest.TestCase):
    def test_lossless_slowdown_and_recovery_are_explicit_injector_inputs(self):
        scene = Scenario(family='slowdown', slowdown_fraction=.5,
                         fault_ns=24_000_000, fault_duration_ns=20_000_000,
                         policy='benefit_v2', detector='service',
                         relay_completion='pipelined', helper_mode='shared')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'truth'
            inject(path, scene)
            fields = (path / 'injection.txt').read_text().split()
        self.assertEqual(fields[:5], ['24000000', '44000000', '0', '0.5', '0'])
        self.assertEqual(scene.dictionary()['policy'], 'benefit_v2')

    def test_previous_quarter_definition_stays_fixed(self):
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'truth'
            inject(path, Scenario(family='quarter'))
            self.assertEqual((path / 'injection.txt').read_text().split()[3:5], ['0.25', '0'])
        with self.assertRaises(ValueError):
            Scenario(family='quarter', slowdown_fraction=.5)

    def test_v2_requires_the_registered_observation_and_resource_modes(self):
        valid = dict(policy='benefit_v2', detector='service',
                     replacement_lifetime='phase', relay_completion='pipelined',
                     helper_mode='shared')
        Scenario(**valid)
        for name, value in (('detector', 'legacy'), ('replacement_lifetime', 'persistent'),
                            ('relay_completion', 'final_ack'), ('helper_mode', 'idle')):
            with self.subTest(name=name), self.assertRaises(ValueError):
                Scenario(**dict(valid, **{name: value}))

    def test_invalid_capacity_and_policy_are_rejected(self):
        for value in (0, -1, 1.01, float('nan'), float('inf'), True, '0.5'):
            with self.subTest(value=value), self.assertRaises(ValueError):
                Scenario(family='slowdown', slowdown_fraction=value)
        with self.assertRaises(ValueError):
            Scenario(policy='oracle')


if __name__ == '__main__':
    unittest.main()
