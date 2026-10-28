"""Check stream separation and preservation of the registered workload."""
from copy import deepcopy
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
from register_independent_loss import confirmation_plan
from research_campaign import make_plan


class IndependentLossPlanTests(unittest.TestCase):
    def reference(self):
        # Reconstruct the old stride-1 schedule for this sampler regression only.
        plan = make_plan('development', development_trials=60, seed_stride=1,
                         horizon_ms=400, rounds=2, chunks=64,
                         include_delay=True, include_slow_quarter=True,
                         seed_base=102990000)
        plan['phase'] = 'validation'
        return dict(plan=plan, plan_sha256='reference-test-only')

    def test_confirmation_separates_streams_without_changing_workload(self):
        reference = self.reference()
        untouched = deepcopy(reference)
        plan = confirmation_plan(reference)
        self.assertEqual(reference, untouched)
        self.assertEqual(len(plan['cases']), 60)
        self.assertEqual(plan['scoring']['primary_conditions'], ['weak_loss'])
        old_cases = {c['name']: c for c in reference['plan']['cases']}
        old_streams = {c['scene']['seed']+c['scene']['node'] for c in reference['plan']['cases']}
        streams = set()
        for case in plan['cases']:
            old = deepcopy(old_cases[case['name']])
            for name in ('seed', 'node', 'fault_ns'):
                old['scene'][name] = case['scene'][name]
            self.assertEqual(old, case)
            base = case['scene']['seed']+case['scene']['node']
            for side in (0, 1):
                self.assertNotIn(2*base+side, streams)
                streams.add(2*base+side)
            self.assertNotIn(base, old_streams)
        self.assertEqual(len(streams), 120)

    def test_rejects_overlapping_or_invalid_confirmation(self):
        reference = self.reference()
        with self.assertRaises(ValueError):
            confirmation_plan(reference, seed_stride=1)
        first = next(c for c in reference['plan']['cases']
                     if c['condition']=='weak_loss' and c['arm']=='benefit')
        with self.assertRaises(ValueError):
            confirmation_plan(reference, seed_base=first['scene']['seed'])
        reference['plan']['cases'].remove(first)
        with self.assertRaises(ValueError):
            confirmation_plan(reference)
