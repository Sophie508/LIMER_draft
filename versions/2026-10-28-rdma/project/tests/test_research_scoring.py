"""Meaningful acceptance checks: censoring, localization, and paired inputs."""
import importlib.util
from contextlib import redirect_stderr, redirect_stdout
import io
import json
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace
import unittest
from unittest import mock

_SCRIPT = Path(__file__).resolve().parents[1] / 'tools/research_campaign.py'
_SPEC = importlib.util.spec_from_file_location('research_campaign', _SCRIPT)
research = importlib.util.module_from_spec(_SPEC)
_SPEC.loader.exec_module(research)


def scene(family='blackhole'):
    return dict(family=family, fault_ns=40_000_000, horizon_ns=800_000_000,
                node=0, detector='service')


def alarm(t, key):
    return dict(timestamp_ns=t, path_id=key, signal='deadline')


class ResearchScoringTests(unittest.TestCase):
    def test_all_affected_directions_must_pass_strict_deadline(self):
        s = scene()
        self.assertEqual(research.affected_paths(s), {13, 721})
        result = research.score_alarm_rows(s, [alarm(90_000_000, 13), alarm(140_000_000, 721)])
        self.assertTrue(result['first_incident_timely_success'])
        self.assertFalse(result['all_paths_timely_success'])
        self.assertEqual(result['classification'], 'late')
        self.assertEqual(result['all_paths_delay_ms'], 100.0)

    def test_missing_second_path_is_miss_not_successful_only_latency(self):
        result = research.score_alarm_rows(scene(), [alarm(90_000_000, 13)])
        self.assertEqual(result['classification'], 'miss')
        self.assertIsNone(result['all_paths_delay_ms'])
        self.assertTrue(result['first_incident_timely_success'])

    def test_wrong_path_or_prefault_alarm_invalidates_otherwise_timely_trial(self):
        good = [alarm(90_000_000, 13), alarm(91_000_000, 721)]
        wrong = research.score_alarm_rows(scene(), good + [alarm(92_000_000, 12)])
        early = research.score_alarm_rows(scene(), good + [alarm(30_000_000, 13)])
        self.assertEqual(wrong['classification'], 'mislocalized')
        self.assertEqual(early['classification'], 'pre_fault_alarm')
        self.assertFalse(wrong['all_paths_timely_success'])
        self.assertFalse(early['first_incident_timely_success'])

    def test_no_helper_fault_requires_all_eight_paths(self):
        s = scene('no_idle_helpers')
        affected = research.affected_paths(s)
        self.assertEqual(len(affected), 8)
        rows = [alarm(90_000_000, key) for key in affected]
        self.assertTrue(research.score_alarm_rows(s, rows)['all_paths_timely_success'])
        self.assertFalse(research.score_alarm_rows(s, rows[:-1])['all_paths_timely_success'])

    def test_mislocalization_cannot_enter_p95_as_successful_latency(self):
        result=research.score_alarm_rows(scene(),[alarm(90000000,13),alarm(91000000,721),alarm(92000000,64)])
        self.assertEqual(result['classification'],'mislocalized')
        self.assertEqual(result['observed_all_paths_delay_ms'],51)
        self.assertIsNone(result['all_paths_delay_ms'])
        self.assertIsNone(research.percentile95([50]*18+[result['all_paths_delay_ms']]*2))

    def test_healthy_alarms_and_exposure_are_separate_from_detection_recall(self):
        result = research.score_alarm_rows(scene('healthy'), [alarm(700_000_000, 13)])
        self.assertTrue(result['healthy_false_alarm'])
        self.assertFalse(result['all_paths_timely_success'])
        self.assertEqual(result['healthy_exposure_ms'], 800)

    def test_error_never_passes_even_if_alarms_were_timely(self):
        result = research.score_alarm_rows(scene(), [alarm(90_000_000, 13), alarm(91_000_000, 721)], valid=False)
        self.assertEqual(result['classification'], 'error')
        self.assertFalse(result['all_paths_timely_success'])

    def test_job_completion_does_not_substitute_for_full_monitoring_exposure(self):
        case = dict(scene=scene())
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'service_alarms.csv').write_text('timestamp_ns,path_id,signal\n90000000,13,deadline\n91000000,721,deadline\n')
            (root / 'policy_decisions.jsonl').write_text('{"decision":"stay"}\n')
            result = dict(audit={'pass': True}, observation_audit={'pass': True},
                          status=dict(status='completed', monitor_end_ns=200_000_000))
            research.write_json(root / 'result.json', result)
            truncated = research.score_run(root, case)
            self.assertFalse(truncated['monitoring_complete'])
            self.assertFalse(truncated['all_paths_timely_success'])
            self.assertEqual(truncated['classification'], 'error')
            result['status']['monitor_end_ns'] = 800_000_000
            research.write_json(root / 'result.json', result)
            full = research.score_run(root, case)
            self.assertTrue(full['all_paths_timely_success'])
            self.assertEqual(full['policy_decision_counts'], {'stay': 1})

    def test_percentile_keeps_missing_and_late_trials_in_denominator(self):
        self.assertIsNone(research.percentile95([50] * 18 + [None] * 2))
        self.assertEqual(research.percentile95([50] * 18 + [150, None]), 150)
        self.assertIsNone(research.percentile95([]))

    def test_confidence_is_separate_from_empirical_rate(self):
        self.assertAlmostEqual(research.exact_lower_bound(60, 60), .05 ** (1 / 60))
        self.assertGreater(research.exact_lower_bound(60, 60), .95)
        self.assertLess(research.exact_lower_bound(57, 60), .95)
        self.assertEqual(research.exact_lower_bound(0, 60), 0)
        self.assertIsNone(research.exact_lower_bound(0, 0))

    def test_validation_has_450_cases_and_disjoint_development_seeds(self):
        plan = research.make_plan('validation')
        development = research.make_plan('development')
        self.assertEqual(len(plan['cases']), 450)
        self.assertEqual(len(development['cases']), 42)
        seeds = {case['scene']['seed'] for case in plan['cases']}
        dev_seeds = {case['scene']['seed'] for case in development['cases']}
        self.assertFalse(seeds & dev_seeds)
        for condition in research.PRIMARY:
            cases = [c for c in plan['cases'] if c['condition'] == condition and c['arm'] == 'benefit']
            self.assertEqual(len(cases), 60)
            self.assertEqual(len({c['scene']['seed'] for c in cases}), 60)

    def test_optional_delay_and_slow_quarter_are_registered_explicitly(self):
        plan = research.make_plan('validation', include_delay=True, include_slow_quarter=True)
        development = research.make_plan('development', development_trials=1,
                                         include_delay=True, include_slow_quarter=True)
        self.assertEqual(len(plan['cases']), 580)
        self.assertEqual(len(development['cases']), 27)
        self.assertEqual(plan['scoring']['primary_conditions'], ['blackhole', 'quarter', 'weak_loss', 'delay'])
        delayed = [c for c in plan['cases'] if c['condition'] == 'delay']
        slow = [c for c in plan['cases'] if c['condition'] == 'slow_proxy_quarter']
        self.assertEqual(len(delayed), 100)
        self.assertEqual(len(slow), 30)
        self.assertTrue(all(c['scene']['family'] == 'delay' for c in delayed))
        for case in slow:
            self.assertEqual(case['scene']['family'], 'quarter')
            self.assertEqual(case['scene']['local_gbps'], 1)
            self.assertEqual(case['scene']['rounds'], 1)
            self.assertEqual(case['scene']['chunks_per_phase'], 256)
            self.assertGreaterEqual(case['scene']['horizon_ns'], 800000000)
            self.assertEqual(case['scene']['fault_duration_ns'], 0)

    def test_explicit_seed_base_is_recorded_disjoint_and_pair_preserving(self):
        old = research.make_plan('validation', include_delay=True, include_slow_quarter=True)
        new = research.make_plan('validation', include_delay=True, include_slow_quarter=True,
                                 seed_base=102990000)
        self.assertEqual(new['scoring']['seed_base'], 102990000)
        self.assertEqual(len(new['cases']), len(old['cases']))
        self.assertFalse({c['scene']['seed'] for c in old['cases']} & {c['scene']['seed'] for c in new['cases']})
        for before, after in zip(old['cases'], new['cases']):
            self.assertEqual(before['condition'], after['condition'])
            self.assertEqual(before['arm'], after['arm'])
            self.assertEqual(after['scene']['seed'] - before['scene']['seed'], 100000)
        pairs = {}
        for case in new['cases']:
            physical = {k: v for k, v in case['scene'].items() if k != 'policy'}
            if case['pair_id'] in pairs:
                self.assertEqual(pairs[case['pair_id']], physical)
            pairs[case['pair_id']] = physical

    def test_seed_base_defaults_remain_compatible_and_invalid_values_fail(self):
        self.assertEqual(research.make_plan('development')['scoring']['seed_base'], 102800000)
        self.assertEqual(research.make_plan('validation')['scoring']['seed_base'], 102890000)
        self.assertEqual(research.make_plan('development', seed_base=0)['scoring']['seed_base'], 0)
        for invalid in (-1, 1.5, True, '102990000'):
            with self.subTest(seed_base=invalid), self.assertRaises(ValueError):
                research.make_plan('validation', seed_base=invalid)

    def test_default_stride_keeps_derived_loss_streams_unique_across_trials_and_sides(self):
        plan = research.make_plan('validation', seed_base=103100000)
        weak = [c for c in plan['cases'] if c['condition'] == 'weak_loss' and c['arm'] == 'benefit']
        self.assertEqual(plan['scoring']['seed_stride'], 32)
        self.assertEqual(len(weak), 60)
        bases = [c['scene']['seed'] + c['scene']['node'] for c in weak]
        streams = [2 * base + side for base in bases for side in (0, 1)]
        self.assertEqual(len(set(bases)), 60)
        self.assertEqual(len(set(streams)), 120)
        self.assertTrue(all(b['scene']['seed'] - a['scene']['seed'] == 32 for a, b in zip(weak, weak[1:])))
        # Policy variants intentionally share the same physical loss stream;
        # different trial/condition blocks must never reuse one.
        streams_by_trial = {}
        for case in plan['cases']:
            key = (case['condition'], case['trial'])
            nodes = range(4) if case['scene']['family'] == 'no_idle_helpers' else [case['scene']['node']]
            actual = {2 * (case['scene']['seed'] + node) + side for node in nodes for side in (0, 1)}
            if key in streams_by_trial:
                self.assertEqual(streams_by_trial[key], actual)
            streams_by_trial[key] = actual
        seen = set()
        for actual in streams_by_trial.values():
            self.assertFalse(seen & actual)
            seen.update(actual)

    def test_stride_validation_and_condition_range_guards(self):
        self.assertEqual(research.make_plan('validation', seed_stride=16)['scoring']['seed_stride'], 16)
        self.assertEqual(research.make_plan('development', seed_stride=1)['scoring']['seed_stride'], 1)
        for phase, stride in [('validation', 15), ('validation', 1), ('development', 0),
                              ('validation', -1), ('development', 1.5), ('validation', True),
                              ('validation', 167), ('development', 5000)]:
            with self.subTest(phase=phase, stride=stride), self.assertRaises(ValueError):
                research.make_plan(phase, seed_stride=stride)

    def test_registered_delay_cannot_be_ignored_when_three_original_conditions_pass(self):
        plan = research.make_plan('validation', include_delay=True)
        plan['cases'] = [c for c in plan['cases'] if c['arm'] == 'benefit' and c['condition'] in plan['scoring']['primary_conditions']]
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('tooling', 'cases', 'attempts', 'runs'):
                (root / directory).mkdir()
            research.write_json(root / 'registration.json', dict(plan=plan, plan_sha256=research.digest_json(plan), tooling_hashes={}))
            for case in plan['cases']:
                name = case['name']
                research.write_json(root / 'cases' / (name + '.json'), case)
                if case['condition'] == 'delay':
                    continue
                destination = root / 'runs' / name
                destination.mkdir()
                rows = ['timestamp_ns,path_id,signal'] + [f"{case['scene']['fault_ns'] + 50_000_000},{key},deadline"
                                                         for key in research.affected_paths(case['scene'])]
                (destination / 'service_alarms.csv').write_text('\n'.join(rows) + '\n')
                result = dict(audit={'pass': True}, observation_audit={'pass': True},
                              status=dict(status='completed', monitor_end_ns=case['scene']['horizon_ns']),
                              performance=dict(communication_ms=100, restricted_communication_ms=100))
                research.write_json(destination / 'result.json', result)
                research.write_json(root / 'attempts' / (name + '.json'), dict(valid=True))
            summary = research.summarize(root)
            self.assertFalse(summary['primary_empirical_95_percent_under_100ms_met'])
            for group in summary['groups']:
                self.assertEqual(group['empirical_target_met'], group['condition'] != 'delay')

    def test_policy_pairs_receive_identical_physical_inputs(self):
        plan = research.make_plan('validation')
        groups = {}
        for case in plan['cases']:
            groups.setdefault(case['pair_id'], []).append(case)
        paired = [cases for cases in groups.values() if len(cases) == 3]
        self.assertEqual(len(paired), 90)
        for cases in paired:
            physical = [{k: v for k, v in c['scene'].items() if k != 'policy'} for c in cases]
            self.assertEqual(physical[0], physical[1])
            self.assertEqual(physical[1], physical[2])

    def test_validation_cannot_be_relabelled_small_development_sample(self):
        with self.assertRaises(ValueError):
            research.make_plan('validation', trials=3, paired_trials=3)

    def test_summary_retains_unrun_attempts_in_registered_denominator(self):
        plan = research.make_plan('development', development_trials=1)
        selected = [c for c in plan['cases'] if c['condition'] == 'blackhole']
        plan['cases'] = selected
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('tooling', 'cases', 'attempts', 'runs'):
                (root / directory).mkdir()
            research.write_json(root / 'registration.json', dict(plan=plan, plan_sha256=research.digest_json(plan), tooling_hashes={}))
            for case in selected:
                research.write_json(root / 'cases' / (case['name'] + '.json'), case)
            summary = research.summarize(root)
            self.assertEqual(summary['registered'], 3)
            self.assertEqual(summary['attempted'], 0)
            self.assertFalse(summary['complete'])
            self.assertFalse(summary['primary_empirical_95_percent_under_100ms_met'])
            for group in summary['groups']:
                self.assertEqual(group['registered'], 1)
                self.assertEqual(group['verified'], 0)
                self.assertEqual(group['empirical_timely_rate'], 0)
                self.assertEqual(group['classifications'], {'not_run': 1})

    def test_staged_submission_preserves_all_580_and_never_retries_failed_attempt(self):
        plan = research.make_plan('validation', include_delay=True, include_slow_quarter=True)
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            for directory in ('tooling', 'cases', 'attempts', 'runs', 'logs', 'archives'):
                (root / directory).mkdir()
            registration = dict(plan=plan, plan_sha256=research.digest_json(plan),
                                tooling_hashes={}, build_directory=str(root / 'build'))
            research.write_json(root / 'registration.json', registration)
            for case in plan['cases']:
                research.write_json(root / 'cases' / (case['name'] + '.json'), case)
            original_registration = (root / 'registration.json').read_bytes()
            original_cases = {p.name: p.read_bytes() for p in (root / 'cases').glob('*.json')}
            failed_name = plan['cases'][0]['name']
            failed_attempt = dict(name=failed_name, valid=False, status='runner_error', error='Retained simulated failure')
            research.write_json(root / 'attempts' / (failed_name + '.json'), failed_attempt)
            submitted = []

            def mock_runner(command, **kwargs):
                destination = Path(command[command.index('--out') + 1])
                case = research.read_json(command[command.index('--case') + 1])
                submitted.append(case['name'])
                destination.mkdir()
                archive = Path(command[command.index('--archive-to') + 1])
                archive.write_bytes(('Mock archive bytes for ' + case['name']).encode())
                status = dict(status='completed', monitor_end_ns=case['scene']['horizon_ns'])
                result = dict(status=status, audit={'pass': True}, observation_audit={'pass': True},
                              performance=dict(communication_ms=100, restricted_communication_ms=100),
                              archive=dict(sha256=research.sha(archive)))
                research.write_json(destination / 'result.json', result)
                rows = ['timestamp_ns,path_id,signal'] + [f"{case['scene']['fault_ns'] + 50_000_000},{key},canary_service"
                                                         for key in research.affected_paths(case['scene'])]
                (destination / 'service_alarms.csv').write_text('\n'.join(rows) + '\n')
                return SimpleNamespace(returncode=0)

            with mock.patch.object(research, 'validate_registration', return_value=registration), \
                    mock.patch.object(research.subprocess, 'run', side_effect=mock_runner), redirect_stdout(io.StringIO()):
                research.execute(root, workers=2, resume=True, exclude_conditions=['slow_proxy_quarter'])
                first_state = research.read_json(root / 'campaign_state.json')
                first_summary = research.read_json(root / 'research_summary.json')
                self.assertEqual(first_state['status'], 'partial_registered_cases_remaining')
                self.assertEqual(first_state['registered_cases_remaining'], 30)
                self.assertEqual(first_summary['registered'], 580)
                self.assertEqual(first_summary['attempted'], 550)
                self.assertFalse(first_summary['complete'])
                slow_groups = [g for g in first_summary['groups'] if g['condition'] == 'slow_proxy_quarter']
                self.assertEqual(sum(g['registered'] for g in slow_groups), 30)
                self.assertTrue(all(g['classifications'] == {'not_run': 10} for g in slow_groups))
                self.assertEqual(len(submitted), 549)  # The existing failed attempt is retained.
                self.assertNotIn(failed_name, submitted)
                before_second_stage = set(submitted)
                research.execute(root, workers=2, resume=True, only_conditions=['slow_proxy_quarter'])
                second_state = research.read_json(root / 'campaign_state.json')
                second_summary = research.read_json(root / 'research_summary.json')
                self.assertEqual(second_state['status'], 'complete_with_retained_errors')
                self.assertEqual(second_state['registered_cases_remaining'], 0)
                self.assertEqual(second_summary['registered'], 580)
                self.assertEqual(second_summary['attempted'], 580)
                self.assertEqual(second_summary['verified'], 579)
                self.assertTrue(second_summary['complete'])
                new_submissions = submitted[549:]
                self.assertEqual(len(new_submissions), 30)
                self.assertTrue(all('slow_proxy_quarter' in name for name in new_submissions))
                self.assertFalse(before_second_stage & set(new_submissions))
            self.assertEqual(research.read_json(root / 'attempts' / (failed_name + '.json')), failed_attempt)
            self.assertEqual((root / 'registration.json').read_bytes(), original_registration)
            self.assertEqual({p.name: p.read_bytes() for p in (root / 'cases').glob('*.json')}, original_cases)

    def test_unknown_or_mutually_exclusive_condition_selection_is_rejected(self):
        plan = research.make_plan('development')
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            research.write_json(root / 'registration.json', dict(plan=plan, build_directory=str(root / 'build')))
            selections = [dict(only_conditions=['unregistered']), dict(exclude_conditions=['unregistered']),
                          dict(only_conditions=['blackhole'], exclude_conditions=['quarter'])]
            with mock.patch.object(research, 'validate_registration') as validation:
                for options in selections:
                    with self.subTest(options=options), self.assertRaises(ValueError):
                        research.execute(root, **options)
                validation.assert_not_called()
            self.assertFalse((root / 'campaign_state.json').exists())

    def test_condition_cli_is_repeatable_and_mutually_exclusive(self):
        with mock.patch.object(sys, 'argv', ['research_campaign.py', 'execute', '/tmp/unused',
                                             '--only-condition', 'blackhole', '--only-condition', 'quarter']), \
                mock.patch.object(research, 'execute') as execution:
            research.main()
            self.assertEqual(execution.call_args.args[-2:], (None, ['blackhole', 'quarter']))
        with mock.patch.object(sys, 'argv', ['research_campaign.py', 'execute', '/tmp/unused',
                                             '--only-condition', 'blackhole', '--exclude-condition', 'quarter']), \
                mock.patch.object(research, 'execute') as execution, redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as error:
                research.main()
            self.assertEqual(error.exception.code, 2)
            execution.assert_not_called()


if __name__ == '__main__':
    unittest.main()
