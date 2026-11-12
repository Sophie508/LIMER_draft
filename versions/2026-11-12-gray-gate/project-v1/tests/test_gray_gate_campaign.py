"""Guard policy matching, preregistration and adverse-outcome denominators."""
from copy import deepcopy
import importlib.util
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'tools'))
spec = importlib.util.spec_from_file_location('gray_gate_campaign', ROOT / 'tools/gray_gate_campaign.py')
campaign = importlib.util.module_from_spec(spec)
spec.loader.exec_module(campaign)


class GrayGateCampaignTests(unittest.TestCase):
    def test_frozen_presets_are_bounded_and_use_disjoint_seeds(self):
        pilot, confirmation = (campaign.make_plan(p) for p in ('pilot', 'confirmation'))
        self.assertEqual(len(pilot['cases']), 20)
        self.assertEqual(len(confirmation['cases']), 30)
        self.assertEqual(pilot, campaign.make_plan('pilot'))
        self.assertTrue({c['scene']['seed'] for c in pilot['cases']}.isdisjoint(
            {c['scene']['seed'] for c in confirmation['cases']}))
        self.assertTrue(all(c['scene']['fault_ns'] >= 21_000_000 for c in pilot['cases']))
        self.assertTrue(all(c['scene']['horizon_ns'] == 250_000_000 for c in pilot['cases']))
        self.assertEqual(pilot['lifecycle_revision']['probe_timeout_ns'], 20_000_000)
        self.assertEqual(pilot['lifecycle_revision']['policy'], 'benefit_v2')

    def test_primary_arms_differ_only_in_method_and_policy(self):
        plan = campaign.make_plan()
        for condition in campaign.PRIMARY:
            members = [c for c in plan['cases'] if c['condition'] == condition]
            self.assertEqual({c['arm'] for c in members}, set(campaign.ARMS))
            reference = deepcopy(members[0]['scene']); reference.pop('policy')
            for case in members:
                scene = deepcopy(case['scene']); scene.pop('policy')
                self.assertEqual(reference, scene)
        changed = deepcopy(plan)
        changed['cases'][5]['scene']['chunks_per_phase'] = 1024
        with self.assertRaisesRegex(ValueError, 'Matched arms differ'):
            campaign.validate_plan(changed)

    def test_quarter_stays_25_percent_and_confirmation_explicitly_sweeps(self):
        plan = campaign.make_plan('confirmation')
        half = [c for c in plan['cases'] if c['condition'] == 'sustained_50_early']
        self.assertEqual(len(half), 4)
        self.assertTrue(all(c['scene']['family'] == 'slowdown' and
                            c['scene']['slowdown_fraction'] == .5 for c in half))
        self.assertTrue(all(c['scene']['slowdown_fraction'] == .25 for c in plan['cases']
                            if c['scene']['family'] == 'quarter'))
        self.assertTrue(all(c['scene']['fault_duration_ns'] == 20_000_000 for c in plan['cases']
                            if c['condition'] == 'transient_25_20ms'))

    def test_missing_matched_healthy_and_early_fault_are_rejected(self):
        plan = campaign.make_plan('confirmation')
        plan['cases'] = [c for c in plan['cases'] if c['condition'] != 'healthy_local_1gbps']
        with self.assertRaisesRegex(ValueError, 'No matched healthy reference'):
            campaign.validate_plan(plan)
        plan = campaign.make_plan()
        plan['cases'][4]['scene']['fault_ns'] = 4_000_000
        with self.assertRaisesRegex(ValueError, 'calibration'):
            campaign.validate_plan(plan)

    def test_result_summary_retains_pending_invalid_and_unfinished(self):
        plan = campaign.make_plan()
        registration = dict(plan=plan, plan_sha256='test-plan')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'attempts').mkdir(); (root / 'runs').mkdir()
            healthy = next(c for c in plan['cases'] if c['condition'] == 'healthy' and c['arm'] == 'candidate_gate')
            fault = next(c for c in plan['cases'] if c['condition'] == 'sustained_25_early' and c['arm'] == 'candidate_gate')
            invalid = next(c for c in plan['cases'] if c['condition'] == 'sustained_25_early' and c['arm'] == 'direct')
            unfinished = next(c for c in plan['cases'] if c['condition'] == 'blackhole' and c['arm'] == 'candidate_gate')
            finished_pair = next(c for c in plan['cases'] if c['condition'] == 'blackhole' and c['arm'] == 'direct')
            for case in (healthy, fault, invalid, unfinished, finished_pair):
                run = root / 'runs' / case['name']; run.mkdir()
                result = dict(method=case['method'], scene=case['scene'],
                              status=dict(status='unfinished' if case == unfinished else 'completed'),
                              performance=dict(communication_ms=None if case == unfinished else 40 if case == healthy else 50))
                (run / 'result.json').write_text(json.dumps(result))
                (root / 'attempts' / (case['name'] + '.json')).write_text(json.dumps(
                    dict(valid=case != invalid, error='retained audit failure')))
            score = dict(valid=True, classification='timely', all_paths_timely_success=True,
                         all_paths_delay_ms=10, healthy_false_alarm=False)
            with patch.object(campaign.research, 'validate_registration', return_value=registration), \
                 patch.object(campaign.research, 'score_run', return_value=score):
                report = campaign.summarize(root)
            rows = {r['name']: r for r in report['rows']}
            self.assertEqual(report['registered'], 20)
            self.assertEqual(report['attempted'], 5)
            self.assertEqual(report['completed'], 3)
            self.assertEqual(report['valid'], 4)
            self.assertFalse(report['complete'])
            self.assertAlmostEqual(rows[fault['name']]['healthy_ratio'], .8)
            self.assertIsNone(rows[invalid['name']]['communication_ms'])
            self.assertIsNone(rows[invalid['name']]['capped_ms'])
            self.assertIsNone(rows[unfinished['name']]['communication_ms'])
            self.assertEqual(rows[unfinished['name']]['capped_ms'], 249)
            self.assertEqual(sum(r['classification'] == 'not_run' for r in report['rows']), 15)
            self.assertTrue(all(r['capped_ms'] is None for r in report['rows'] if not r['attempted']))
            invalid_pair = next(p for p in report['pairs'] if p['pair_id'] == fault['pair_id'] and p['comparator'] == 'direct')
            self.assertFalse(invalid_pair['both_valid'])
            self.assertIsNone(invalid_pair['candidate_minus_baseline_capped_ms'])
            self.assertIsNone(invalid_pair['candidate_minus_baseline_ms'])
            capped_pair = next(p for p in report['pairs'] if p['pair_id'] == unfinished['pair_id'])
            self.assertTrue(capped_pair['both_valid'])
            self.assertFalse(capped_pair['both_completed'])
            self.assertEqual(capped_pair['candidate_minus_baseline_capped_ms'], 199)
            self.assertIsNone(capped_pair['candidate_minus_baseline_ms'])

    def test_runner_keeps_failed_attempts_and_bounds_workers(self):
        for workers in (0, 3):
            with self.assertRaisesRegex(ValueError, 'one or two workers'):
                campaign.execute(Path('/unused'), workers=workers)
        registration = dict(plan=campaign.make_plan())
        with patch.object(campaign.research, 'validate_registration', return_value=registration), \
             patch.object(campaign.research, 'execute') as run, \
             patch.object(campaign, 'summarize', return_value={'registered': 20}):
            campaign.execute(Path('/unused'), resume=True, only_conditions=['weak_loss'])
        run.assert_called_once_with(Path('/unused'), workers=1, resume=True,
                                    only_conditions=['weak_loss'])

    def test_malformed_attempt_remains_visible_in_partial_summary(self):
        plan = campaign.make_plan()
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp); (root / 'attempts').mkdir()
            (root / 'attempts' / (plan['cases'][0]['name'] + '.json')).write_text('{broken')
            with patch.object(campaign.research, 'validate_registration', return_value=dict(plan=plan, plan_sha256='test')):
                result = campaign.summarize(root)
            self.assertEqual(result['registered'], 20)
            self.assertEqual(result['attempted'], 1)
            self.assertEqual(result['valid'], 0)
            self.assertEqual(result['rows'][0]['classification'], 'error')

    def test_control_costs_count_wire_bytes_and_do_not_infer_counterfactual_harm(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'control_events.csv').write_text(
                'sent_ns,arrival_ns,event,rank,phase,version,wire_bytes\n'
                '1,2,LEND_TX,1,0,2,96\n'
                '2,2,LEND_ACTIVE,0,0,2,0\n'
                '3,4,RELEASE_TX,1,0,2,96\n'
                '4,4,ACTIVATE,0,0,2,0\n')
            cost = campaign.cost_summary(root, dict(performance={'fresh_Bprime_payload_bytes': 0}))
            self.assertEqual(cost['control_wire_bytes'], 192)
            self.assertEqual(cost['activations'], 1)
            self.assertTrue(cost['no_fresh_payload_activation'])
            self.assertNotIn('harmful_switch', cost)


if __name__ == '__main__':
    unittest.main()
