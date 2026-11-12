"""Check compact evidence, frozen source provenance, and table re-derivation."""
import hashlib
import csv
import json
from pathlib import Path
import subprocess
import sys
import tempfile

ROOT = Path(__file__).resolve().parent

def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()

def read(path):
    return json.loads(path.read_text())


def check_lending(run, disjoint):
    controls = list(csv.DictReader((run / 'control_events.csv').open()))
    alarms = {}
    for row in csv.DictReader((run / 'detector_events.csv').open()):
        key = int(row['path_id'])
        src = key//48
        dst = src+4 if src<12 else (src+1)%4
        if key == (src*16+dst)*3+1:
            alarms.setdefault(src, int(row['timestamp_ns']))
    transactions, used = 0, {}
    for active in controls:
        if active['event'] != 'LEND_ACTIVE':
            continue
        requests = [row for row in controls if row['phase']==active['phase']
                    and row['version']==active['version']
                    and row['event'] in ('LEND_TX', 'LEND_RX')]
        assert len(requests)==2 and {row['event'] for row in requests}=={'LEND_TX','LEND_RX'}
        alarm = alarms[int(active['rank'])]
        assert all(int(row['sent_ns'])>=alarm for row in requests)
        assert int(active['arrival_ns'])==max(int(row['arrival_ns']) for row in requests)
        helpers = {int(row['rank']) for row in requests}
        assert len(helpers)==2
        if disjoint:
            previous = used.setdefault(active['phase'], set())
            assert not previous & helpers, 'Concurrent lending reuses one helper'
            previous.update(helpers)
        transactions += 1
    return transactions


def verify():
    constraints = read(ROOT / 'verification/unchanged-constraints.json')
    for name, digest in constraints['identical_files'].items():
        assert sha(ROOT / 'project' / name) == digest, name
        assert sha(ROOT.parent / '2026-10-28-rdma/project' / name) == digest, name
    evidence = ROOT / 'evidence'
    manifest = read(evidence / 'COMPACT_MANIFEST.json')
    current = {p.relative_to(evidence).as_posix(): sha(p)
               for p in evidence.rglob('*') if p.is_file() and p.name != 'COMPACT_MANIFEST.json'}
    assert current == manifest['files'], 'Compact evidence changed'
    archives = read(evidence / 'archive-integrity.json')
    assert archives['all_archive_hashes_rechecked']
    archive_map = {(a['group'], a['name']): a for a in archives['archives']}
    reports, provenance, lending_transactions = [], {}, 0
    with tempfile.TemporaryDirectory() as tmp:
        for group in ('pilot-v1', 'pilot-v2', 'policy-pilot-v2', 'full-v2'):
            root = evidence / group
            project = ROOT / read(root / 'source-location.json')['local_project']
            registration = read(root / 'registration.json')
            build = read(root / 'native-build.json')
            assert sha(root / 'native-build.json') == registration['build_sha256']
            assert build['binary_sha256'] == registration['binary_sha256']
            for name, digest in build['source_hashes'].items():
                assert sha(project / name) == digest, name
            for folder, hashes in registration['source_hashes'].items():
                current = {p.relative_to(project / folder).as_posix(): sha(p)
                           for p in (project / folder).rglob('*')
                           if p.is_file() and '__pycache__' not in p.parts}
                assert current == hashes, group + ': ' + folder
            names = {c['name'] for c in registration['cases']}
            assert {p.stem for p in (root / 'attempts').glob('*.json')} == names
            for case in registration['cases']:
                run = root / 'runs' / case['name']
                attempt = read(root / 'attempts' / (case['name'] + '.json'))
                if not attempt['valid']:
                    continue
                r = attempt['result']
                assert r['scene'] == case['scene']
                assert r['audit']['pass'] and r['observation_audit']['pass']
                lending_transactions += check_lending(run, group != 'pilot-v1')
                for key, file in (('audit','audit.json'), ('observation_audit','observation_audit.json'),
                                  ('status','run_status.json'), ('performance','performance.json')):
                    assert r[key] == read(run / file), (group, case['name'], key)
                run_manifest = read(run / 'run_manifest.json')
                assert run_manifest['binary_sha256'] == registration['binary_sha256']
                for name, digest in run_manifest['input_hashes'].items():
                    assert sha(run / name) == digest, name
                archive = read(run / 'archive_manifest.json')
                receipt = archive_map[group, case['name']]
                assert archive['sha256'] == receipt['sha256']
                assert archive['bytes'] == receipt['bytes']
                assert archive['all_content_hashes_verified'] and receipt['all_member_hashes_verified']
                for name, digest in archive['files'].items():
                    if (run / name).is_file():
                        assert sha(run / name) == digest, name
            out = Path(tmp) / group
            subprocess.run([sys.executable, str(ROOT / 'summarize.py'), str(root),
                            '--scorer', str(project / 'tools/research_campaign.py'),
                            '--out', str(out)], check=True, stdout=subprocess.DEVNULL)
            report = read(out / 'report.json')
            assert report == read(ROOT / 'results' / group / 'report.json'), group
            assert (out / 'trials.csv').read_bytes() == (ROOT / 'results' / group / 'trials.csv').read_bytes()
            reports.append(report)
            provenance[group] = dict(binary_sha256=build['binary_sha256'],
                                     source_files=len(build['source_hashes']))
    rows = [row for report in reports for row in report['rows']]
    diagnosis = read(ROOT / 'diagnostics/completion-original-seed.json')
    original = next(row for row in reports[-1]['rows']
                    if row['family']=='blackhole' and row['helper_mode']=='shared'
                    and row['seed']==111210016)
    assert abs(diagnosis['mean_phase_completion_ms']-original['phase3_onward_mean_ms']) < 1e-9
    assert sum(rank['critical_phase_count'] for rank in diagnosis['per_rank'].values()) == 27
    counterexample = read(ROOT / 'diagnostics/gate-counterexample.json')
    policy_log = evidence / counterexample['group'] / 'runs' / counterexample['run'] / 'policy_decisions.jsonl'
    assert sha(policy_log) == counterexample['policy_log_sha256']
    decisions = [json.loads(line) for line in policy_log.read_text().splitlines()]
    for pair in counterexample['pairs']:
        before, after = pair['initial'], pair['followup']
        assert before in decisions and after in decisions
        assert before['phase']==after['phase'] and before['src']==after['src']
        assert all(row['input']['pending_bytes']==row['input']['a_bytes']==0 for row in (before,after))
        assert before['input']['b_bytes']==after['input']['b_bytes']>0
        assert before['should_switch']==0 and after['should_switch']==1
        assert before['stay_ns'] < 1000
        assert (after['timestamp_ns']-before['timestamp_ns'])/1e6==pair['elapsed_ms']
    primary = [row for row in reports[-1]['rows'] if row['helper_mode']=='shared'
               and row['family'] in ('blackhole','weak_loss')]
    healthy = [row for row in reports[-1]['rows'] if row['family']=='healthy']
    receipt = dict(compact_files_verified=len(manifest['files']), native_builds=provenance,
        registered_attempts=len(rows), execution_valid=sum(row['valid'] for row in rows),
        completed=sum(row['status']=='completed' for row in rows),
        invalid=sum(row['status']=='invalid_attempt' for row in rows),
        unfinished=sum(row['valid'] and row['status']!='completed' for row in rows),
        not_run=sum(row['status']=='not_run' for row in rows),
        retained_raw_archive_hashes_rechecked=len(archive_map),
        local_source_matches_registrations=True, regenerated_tables_match=True,
        protected_constraint_files_unchanged=len(constraints['identical_files']),
        timing_diagnosis_matches_phase_metrics=True,
        lending_transactions_checked_at_both_ends=lending_transactions,
        v2_helper_roles_are_disjoint=True,
        recorded_gate_tail_counterexamples_verified=len(counterexample['pairs']),
        healthy_reference_unchanged=all(row['communication_ms']==480.178448 for row in healthy),
        full_shared_fault_cases=len(primary),
        full_shared_fault_cases_at_least_70_percent=sum(
            row['valid'] and row['status']=='completed' and row['healthy_normalized_percent']>=70
            for row in primary),
        scope='Local compact integrity and table re-derivation; raw packet replay and archive hashes verified on otakotak, not repeated on this laptop.')
    (ROOT / 'verification/final-check.json').write_text(json.dumps(receipt, indent=2)+'\n')
    print(json.dumps(receipt, indent=2))


if __name__ == '__main__':
    verify()
