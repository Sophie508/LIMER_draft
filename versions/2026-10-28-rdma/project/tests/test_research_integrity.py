"""Tamper and missing-artifact counterexamples for frozen research evidence."""
import importlib.util
import json
from pathlib import Path
import shutil
import sys
import tarfile
import tempfile
import types
import unittest

ROOT = Path(__file__).resolve().parents[1]


def load(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


integrity = load('research_integrity_for_tests', ROOT / 'tools/verify_research.py')
research = load('research_campaign_for_integrity_tests', ROOT / 'tools/research_campaign.py')


def write(path, value):
    Path(path).write_text(json.dumps(value, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')


def fixture(root):
    """A tiny real archive and linked metadata; no native executable is run."""
    root = Path(root)
    for directory in ('tooling/tools', 'cases', 'attempts', 'runs', 'archives', 'native/lib'):
        (root / directory).mkdir(parents=True)
    shutil.copyfile(ROOT / 'tools/research_campaign.py', root / 'tooling/tools/research_campaign.py')
    shutil.copytree(ROOT / 'python', root / 'tooling/python', ignore=shutil.ignore_patterns('__pycache__'))
    binary = root / 'native/binary'
    binary.write_bytes(b'An integrity fixture, never an executed native binary.\n')
    build = dict(schema='limer-build-v1', binary_relative='binary', libraries_relative='lib',
                 binary_sha256=integrity.sha(binary), library_hashes={}, source_hashes={})
    write(root / 'native/build.json', build)
    shutil.copyfile(root / 'native/build.json', root / 'build.json')
    plan = research.make_plan('development', development_trials=1)
    case = next(c for c in plan['cases'] if c['condition'] == 'blackhole' and c['arm'] == 'benefit')
    plan['cases'] = [case]
    write(root / 'cases' / (case['name'] + '.json'), case)
    registration = dict(schema='limer-research-registration-v1', plan=plan,
                        plan_sha256=research.digest_json(plan), tooling_hashes=integrity.frozen_hashes(root / 'tooling'),
                        build_directory=str(root / 'native'), build_sha256=integrity.sha(root / 'build.json'),
                        binary_sha256=build['binary_sha256'], source_hashes={})
    write(root / 'registration.json', registration)
    run = root / 'runs' / case['name']
    (run / 'inputs').mkdir(parents=True)
    (run / 'truth').mkdir()
    (run / 'inputs/topology.txt').write_text('Fixture topology\n')
    (run / 'truth/injection.txt').write_text('Fixture injection, not read by an algorithm\n')
    scene = case['scene']
    status = dict(status='completed', monitor_end_ns=scene['horizon_ns'])
    audit, observations = {'pass': True}, {'pass': True}
    performance = dict(communication_ms=100, restricted_communication_ms=100)
    manifest = dict(scene=scene, method=case['method'], binary_sha256=registration['binary_sha256'],
                    build_sha256=registration['build_sha256'],
                    input_hashes={relative: integrity.sha(run / relative)
                                  for relative in ['inputs/topology.txt', 'truth/injection.txt']})
    for filename, value in [('run_status.json', status), ('audit.json', audit),
                            ('observation_audit.json', observations), ('performance.json', performance),
                            ('run_manifest.json', manifest)]:
        write(run / filename, value)
    rows = ['timestamp_ns,path_id,signal'] + [f"{scene['fault_ns'] + 50_000_000},{key},canary_service"
                                             for key in research.affected_paths(scene)]
    (run / 'service_alarms.csv').write_text('\n'.join(rows) + '\n')
    (run / 'service_events.csv').write_text('timestamp_ns,event,path_id,token,bytes,last_progress_ns\n')
    (run / 'service_decisions.jsonl').write_text('')
    (run / 'policy_decisions.jsonl').write_text('{"decision":"stay"}\n')
    hashes = {p.relative_to(run).as_posix(): integrity.sha(p) for p in run.rglob('*') if p.is_file()}
    archive_path = root / 'archives' / (case['name'] + '.tar.gz')
    with tarfile.open(archive_path, 'w:gz') as archive:
        for relative in sorted(hashes):
            archive.add(run / relative, arcname=relative, recursive=False)
    record = dict(name=case['name'], method=case['method'], family=case['family'], scene=scene,
                  status=status, audit=audit, observation_audit=observations, performance=performance,
                  archive=dict(archive=str(archive_path), sha256=integrity.sha(archive_path),
                               bytes=archive_path.stat().st_size, files=hashes, all_content_hashes_verified=True))
    write(run / 'result.json', record)
    score = research.score_run(run, case)
    write(root / 'attempts' / (case['name'] + '.json'), dict(name=case['name'], valid=True,
          status='completed', archive_sha256=record['archive']['sha256'], score=score))
    return case, run, archive_path


class ResearchIntegrityTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.case, self.run, self.archive = fixture(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_intact_archive_compact_metadata_and_frozen_score_pass(self):
        result = integrity.verify(self.root)
        self.assertTrue(result['passed'], result['errors'])
        self.assertEqual(result['verified_runs'], 1)
        self.assertEqual(result['archive_digests_verified'], 1)
        self.assertTrue(result['native_binary_verified'])

    def test_archive_tamper_is_detected_and_attempt_is_retained(self):
        self.archive.write_bytes(self.archive.read_bytes() + b'tampered')
        result = integrity.verify(self.root)
        self.assertFalse(result['passed'])
        self.assertTrue(any('archive SHA-256' in e for e in result['errors']))
        self.assertEqual(result['registered'], 1)
        self.assertEqual(result['attempts_present'], 1)

    def test_missing_server_archives_require_explicit_compact_only_scope(self):
        self.archive.unlink()
        full = integrity.verify(self.root)
        self.assertFalse(full['passed'])
        self.assertTrue(any('server raw artifacts' in e for e in full['errors']))
        compact = integrity.verify(self.root, skip_archives=True)
        self.assertTrue(compact['passed'], compact['errors'])
        self.assertEqual(compact['scope'], 'compact-only')
        self.assertEqual(compact['archive_digests_verified'], 0)
        self.assertTrue(any('compact-only' in w for w in compact['warnings']))

    def test_changed_alarm_file_fails_even_when_attempt_claims_success(self):
        (self.run / 'service_alarms.csv').write_text('timestamp_ns,path_id,signal\n')
        result = integrity.verify(self.root)
        self.assertFalse(result['passed'])
        self.assertTrue(any('service_alarms.csv' in e for e in result['errors']))

    def test_changed_retained_score_is_recomputed_from_frozen_code(self):
        path = self.root / 'attempts' / (self.case['name'] + '.json')
        attempt = integrity.read_json(path)
        attempt['score']['all_paths_timely_success'] = False
        write(path, attempt)
        result = integrity.verify(self.root)
        self.assertFalse(result['passed'])
        self.assertTrue(any('frozen score' in e for e in result['errors']))

    def test_changed_case_and_frozen_toolchain_are_rejected_before_replay(self):
        path = self.root / 'cases' / (self.case['name'] + '.json')
        case = integrity.read_json(path)
        case['scene']['seed'] += 1
        write(path, case)
        changed_case = integrity.verify(self.root)
        self.assertFalse(changed_case['passed'])
        self.assertTrue(any('Registered case changed' in e for e in changed_case['errors']))
        scorer = self.root / 'tooling/tools/research_campaign.py'
        scorer.write_text(scorer.read_text() + '\nraise RuntimeError("must not execute altered frozen code")\n')
        changed_tool = integrity.verify(self.root)
        self.assertFalse(changed_tool['passed'])
        self.assertTrue(any('Frozen toolchain' in e for e in changed_tool['errors']))
        self.assertFalse(any('must not execute' in e for e in changed_tool['errors']))

    def test_missing_or_failed_attempt_is_not_dropped(self):
        path = self.root / 'attempts' / (self.case['name'] + '.json')
        attempt = integrity.read_json(path)
        attempt.update(valid=False, error='Native failed')
        write(path, attempt)
        failed = integrity.verify(self.root)
        self.assertFalse(failed['passed'])
        self.assertEqual(failed['registered'], 1)
        path.unlink()
        missing = integrity.verify(self.root)
        self.assertFalse(missing['passed'])
        self.assertEqual(missing['registered'], 1)
        self.assertEqual(missing['attempts_present'], 0)

    def test_build_binary_tamper_and_descriptor_tamper_are_detected(self):
        binary = self.root / 'native/binary'
        binary.write_bytes(b'Changed native bytes')
        native = integrity.verify(self.root)
        self.assertFalse(native['passed'])
        self.assertTrue(any('Binary differs' in e for e in native['errors']))
        (self.root / 'build.json').write_text('{}\n')
        descriptor = integrity.verify(self.root)
        self.assertFalse(descriptor['passed'])
        self.assertTrue(any('Copied build descriptor' in e for e in descriptor['errors']))

    def test_unavailable_native_build_is_explicitly_descriptor_only(self):
        shutil.rmtree(self.root / 'native')
        result = integrity.verify(self.root)
        self.assertTrue(result['passed'], result['errors'])
        self.assertFalse(result['native_binary_verified'])
        self.assertEqual(result['build_scope'], 'copied-descriptor-and-run-links-only')

    def test_current_checkout_module_cache_cannot_override_frozen_runner(self):
        fake = types.ModuleType('limerlab.runner')
        def poisoned_resolve(*args):
            raise RuntimeError('Current checkout must not resolve the frozen build')
        fake.resolve_build = poisoned_resolve
        previous = sys.modules.get('limerlab.runner')
        sys.modules['limerlab.runner'] = fake
        try:
            result = integrity.verify(self.root)
            self.assertTrue(result['passed'], result['errors'])
            self.assertIs(sys.modules.get('limerlab.runner'), fake)
        finally:
            if previous is None:
                sys.modules.pop('limerlab.runner', None)
            else:
                sys.modules['limerlab.runner'] = previous


if __name__ == '__main__':
    unittest.main()
