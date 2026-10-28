"""Synthetic reporting fixtures: never native experiment evidence."""
import csv
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import unittest
from unittest import mock

SPEC = importlib.util.spec_from_file_location('research_report', Path(__file__).resolve().parents[1]/'tools/research_report.py')
reporter = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reporter)


def write_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))


def write_csv(path, rows):
    with path.open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=list(rows[0]))
        writer.writeheader(); writer.writerows(rows)


def fixture(root, supplemental=False):
    root.mkdir()
    rows, cases = [], []
    choices = [(i, 'benefit', 'weak_loss') for i in range(60)]
    if not supplemental:
        choices += [(0, 'always', 'weak_loss'), (0, 'no_proxy', 'weak_loss'), (0, 'benefit', 'healthy')]
    for i, arm, condition in choices:
        seed = 100000+i*32 if supplemental else i
        node = 0 if supplemental else i%2
        name = f'{condition}-{i}-{arm}'
        rows.append(dict(name=name, condition=condition, arm=arm, detector='service',
            pair_id=f'{condition}-{i}', seed=seed, node=node, fault_ns=40000000,
            horizon_ms=400, valid='True', all_paths_delay_ms=20, all_paths_timely='True',
            completed='True', capped_ms=200))
        cases.append(dict(trial=i, condition=condition, arm=arm, detector='service',
                          scene=dict(seed=seed, node=node, fault_ns=40000000, rounds=2)))
        write_json(root/'runs'/name/'result.json', dict(status=dict(rescued_chunks=0),
            performance=dict(first_activations_ns=[], new_Bprime_completions=0,
                             sustained_new_proxy_observed=False)))
        write_json(root/'attempts'/(name+'.json'), dict(score=dict(policy_decision_counts={})))
        if condition=='healthy':
            write_json(root/'runs'/name/'run_status.json',
                       dict(health_probe_routes=0, probe_wire_bytes=0, monitor_end_ns=400000000))
    group = dict(condition='weak_loss', detector='service', arm='benefit', registered=60,
        timely_trials=60, classifications=dict(timely=60), p95_all_trials_ms=20,
        exact_one_sided_95_lower=.05**(1/60), invalid_or_missing=0)
    summary = dict(complete=True, attempted=len(rows), registered=len(rows), verified=len(rows),
        primary_conditions=['weak_loss'], groups=[group], healthy_false_alarm_trials=0)
    hashes = {'python/limerlab/'+name:'same' for name in
              ('detector/service_detector.py','service_replay.py','benefit_policy.py','policy_replay.py','audit.py')}
    reg = dict(binary_sha256='same-binary', source_hashes={'native':'same'}, tooling_hashes=hashes,
        plan_sha256='supplement' if supplemental else 'reference',
        plan=dict(cases=cases, scoring=dict(detector_parameters={'same':1})))
    if supplemental:
        reg['plan']['supplement']=dict(reference_plan_sha256='reference')
    write_json(root/'registration.json', reg)
    write_json(root/'research_summary.json', summary)
    write_csv(root/'research_trials.csv', rows)
    if not supplemental:
        write_csv(root/'research_pairs.csv', [dict(pair_id='weak_loss-0', condition='weak_loss',
            valid='True', benefit_minus_always_capped_ms=0, benefit_minus_no_proxy_capped_ms=0)])


class AggregateReplayTests(unittest.TestCase):
    def test_only_sub_picosecond_mean_rounding_is_allowed(self):
        expected = {'groups': [{'mean_capped_ms': 216.53439113333334,
                                'registered': 60, 'timely_trials': 60}]}
        rounded = json.loads(json.dumps(expected))
        rounded['groups'][0]['mean_capped_ms'] = 216.5343911333334
        self.assertTrue(reporter.summary_matches(expected, rounded))
        self.assertIn('mean_capped_ms', expected['groups'][0])
        rounded['groups'][0]['mean_capped_ms'] += .000001
        self.assertFalse(reporter.summary_matches(expected, rounded))

    def test_mean_rounding_tolerance_cannot_hide_count_or_latency_changes(self):
        expected = {'groups': [{'mean_capped_ms': 200., 'registered': 60,
                                'p95_all_trials_ms': 43.115947}]}
        changed = json.loads(json.dumps(expected))
        changed['groups'][0]['mean_capped_ms'] += 1e-12
        changed['groups'][0]['registered'] = 59
        self.assertFalse(reporter.summary_matches(expected, changed))
        changed['groups'][0]['registered'] = 60
        changed['groups'][0]['p95_all_trials_ms'] += 1e-12
        self.assertFalse(reporter.summary_matches(expected, changed))

    def test_guard_rejects_stale_tables_and_never_overwrites_them(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)/'synthetic';fixture(root)
            tools=root/'tooling'/'tools';tools.mkdir(parents=True)
            golden=root/'tooling'/'golden';golden.mkdir()
            names=('research_summary.json','research_trials.csv','research_pairs.csv')
            for name in names:
                shutil.copyfile(root/name,golden/name)
            # A synthetic frozen scorer isolates the replay guard from native
            # scoring; the real frozen scorer is exercised on native QA data.
            (tools/'research_campaign.py').write_text(
                'from pathlib import Path\nimport shutil\n'
                'def summarize(out):\n'
                '    for source in (Path(out)/"tooling"/"golden").iterdir():\n'
                '        shutil.copyfile(source,Path(out)/source.name)\n')
            reporter.verify_aggregates(root)
            for name in names:
                original=(root/name).read_bytes()
                if name.endswith('.json'):
                    record=json.loads(original);record['primary_conditions']=['quarter']
                    (root/name).write_text(json.dumps(record))
                else:
                    (root/name).write_bytes(original+b'wrong,extra,row\n')
                corrupted=(root/name).read_bytes()
                with self.assertRaisesRegex(ValueError,'frozen aggregate replay'):
                    reporter.verify_aggregates(root)
                self.assertEqual((root/name).read_bytes(),corrupted)
                (root/name).write_bytes(original)


class ResearchReportTests(unittest.TestCase):
    def setUp(self):
        # Selection fixtures deliberately have no native/frozen campaign. The
        # aggregate guard itself is checked separately and on native results.
        patch = mock.patch.object(reporter, 'verify_aggregates')
        patch.start()
        self.addCleanup(patch.stop)

    def test_reused_loss_streams_do_not_get_independent_confidence_bound(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); fixture(root/'main')
            result=reporter.report(root/'main', root/'report')
            row=result['primary_detection'][0]
            self.assertEqual(row['registered'],60)
            self.assertEqual(row['unique_derived_loss_stream_pairs'],31)
            self.assertIsNone(row['exact_one_sided_95_lower'])

    def test_separate_confirmation_replaces_detection_row_without_pooling(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); fixture(root/'main'); fixture(root/'confirmation', True)
            result=reporter.report(root/'main', root/'report', independent_loss_campaign=root/'confirmation')
            row=result['primary_detection'][0]
            self.assertEqual(result['registered'],123)
            self.assertEqual(row['registered'],60)
            self.assertEqual(row['timely'],60)
            self.assertEqual(row['campaign'],'confirmation')
            self.assertGreater(row['exact_one_sided_95_lower'],.95)
            self.assertEqual(result['paired_policy'][0]['pairs'],1)
            reg=json.loads((root/'confirmation'/'registration.json').read_text())
            reg['plan']['cases'][0]['scene']['rounds']=3
            write_json(root/'confirmation'/'registration.json',reg)
            with self.assertRaisesRegex(ValueError,'workload'):
                reporter.report(root/'main',root/'must-not-write',independent_loss_campaign=root/'confirmation')
