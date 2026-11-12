"""Verify compact provenance and independently regenerate the campaign summaries."""
import json
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
from export_evidence import read, sha

ROOT = Path(__file__).resolve().parent


def verify(evidence):
    evidence = evidence.resolve()
    manifest = read(evidence / 'COMPACT_MANIFEST.json')
    actual = {p.relative_to(evidence).as_posix(): sha(p)
              for p in evidence.rglob('*')
              if p.is_file() and p.name != 'COMPACT_MANIFEST.json'}
    assert actual == manifest['files'], 'Compact evidence changed'
    archive_receipts = read(evidence / 'archive-integrity.json')
    assert archive_receipts['all_archive_hashes_rechecked']
    archive_map = {(r['group'], r['name']): r for r in archive_receipts['archives']}
    counts = dict(registered=0, attempted=0, valid=0, completed=0,
                  unfinished=0, invalid=0, unrun=0, verified_archives=0)
    for group in archive_receipts['campaign_inventory']:
        directory = evidence / group
        project = ROOT / read(directory / 'source-location.json')['local_project']
        registration, build = read(directory / 'registration.json'), read(directory / 'build.json')
        assert sha(directory / 'build.json') == registration['build_sha256']
        assert build['binary_sha256'] == registration['binary_sha256']
        assert build['source_hashes'] == registration['source_hashes']
        for name, digest in registration['source_hashes'].items():
            assert sha(project / name) == digest, name
        for name, digest in registration['tooling_hashes'].items():
            assert sha(project / name) == digest, name
        cases = registration['plan']['cases']
        summary = read(directory / 'gray_gate_summary.json')
        summary_rows = {row['name']: row for row in summary['rows']}
        expected_names = {case['name'] for case in cases}
        assert set(summary_rows) == expected_names, 'Summary denominator differs'
        attempts = {p.stem for p in (directory / 'attempts').glob('*.json')}
        assert attempts <= expected_names, 'Unregistered attempt'
        for case in cases:
            name = case['name']
            assert read(directory / 'cases' / (name + '.json')) == case
            counts['registered'] += 1
            if name not in attempts:
                assert not summary_rows[name]['attempted']
                assert not summary_rows[name]['valid']
                assert summary_rows[name]['communication_ms'] is None
                assert summary_rows[name]['capped_ms'] is None
                counts['unrun'] += 1
                continue
            counts['attempted'] += 1
            attempt = read(directory / 'attempts' / (name + '.json'))
            row = summary_rows[name]
            assert row['attempted'] and row['valid'] == attempt['valid'], name
            if not attempt['valid']:
                assert row['communication_ms'] is None and row['capped_ms'] is None
                counts['invalid'] += 1
                continue
            counts['valid'] += 1
            run = directory / 'runs' / name
            result = read(run / 'result.json')
            assert result['scene'] == case['scene'] and result['method'] == case['method']
            assert result['audit']['pass'] and result['observation_audit']['pass']
            assert attempt['exit_code'] == 0 and attempt['score']['valid']
            assert result['status']['monitor_end_ns'] >= case['scene']['horizon_ns']
            assert result['status']['horizon_ns'] == case['scene']['horizon_ns']
            assert attempt['score']['monitoring_complete']
            complete = result['status']['status'] == 'completed'
            assert row['completed'] == complete
            assert row['classification'] == attempt['score']['classification']
            assert row['all_paths_timely'] == attempt['score']['all_paths_timely_success']
            assert row['all_paths_delay_ms'] == attempt['score']['all_paths_delay_ms']
            assert row['healthy_false_alarm'] == attempt['score']['healthy_false_alarm']
            if complete:
                expected_ms = (result['status']['job_done_ns'] - 1_000_000) / 1e6
                assert row['communication_ms'] == expected_ms
            else:
                assert row['communication_ms'] is None
                assert row['capped_ms'] == (case['scene']['horizon_ns'] - 1_000_000) / 1e6
            counts['completed' if complete else 'unfinished'] += 1
            for key, file in (('audit', 'audit.json'), ('observation_audit', 'observation_audit.json'),
                              ('status', 'run_status.json'), ('performance', 'performance.json')):
                assert result[key] == read(run / file), (name, key)
            run_manifest = read(run / 'run_manifest.json')
            assert run_manifest['scene'] == case['scene'] and run_manifest['method'] == case['method']
            assert run_manifest['binary_sha256'] == registration['binary_sha256']
            assert run_manifest['build_sha256'] == registration['build_sha256']
            scene, command = case['scene'], run_manifest['command']
            assert command[4:7] == [case['method'], str(scene['rounds']), str(scene['horizon_ns'])]
            assert command[8:] == [str(scene['chunks_per_phase']), scene['detector'], scene['policy'],
                                   str(scene['canary_period_ns']), str(scene['canary_bytes']),
                                   scene['replacement_lifetime'], str(scene['phases_per_round']),
                                   scene['relay_completion'], scene['helper_mode']]
            for path, digest in run_manifest['input_hashes'].items():
                assert sha(run / path) == digest
            archive = read(run / 'archive_manifest.json')
            assert result['archive'] == archive
            receipt = archive_map[group, name]
            assert archive['sha256'] == receipt['sha256'] == attempt['archive_sha256']
            assert archive['bytes'] == receipt['bytes']
            assert archive['all_content_hashes_verified'] and receipt['all_member_hashes_verified']
            for path, digest in archive['files'].items():
                if (run / path).is_file():
                    assert sha(run / path) == digest, (name, path)
            counts['verified_archives'] += 1
        # Recreate only the registered tooling inventory; avoid changing retained evidence.
        with tempfile.TemporaryDirectory() as temporary:
            temp = Path(temporary)
            shutil.copy2(directory / 'registration.json', temp / 'registration.json')
            for folder in ('cases', 'attempts', 'runs'):
                (temp / folder).symlink_to(directory / folder, target_is_directory=True)
            for name in registration['tooling_hashes']:
                target = temp / 'tooling' / name
                target.parent.mkdir(parents=True, exist_ok=True)
                target.symlink_to(project / name)
            subprocess.run([sys.executable, str(project / 'tools/gray_gate_campaign.py'),
                            'summarize', '--out', str(temp)], check=True,
                           stdout=subprocess.DEVNULL)
            assert read(temp / 'gray_gate_summary.json') == read(directory / 'gray_gate_summary.json'), group
    for failed in archive_receipts.get('failed_raw_inventories', []):
        run = evidence / failed['group'] / 'runs' / failed['name']
        for name, digest in failed['files'].items():
            if (run / name).is_file():
                assert sha(run / name) == digest, (failed['name'], name)
    counts.update(compact_files_verified=len(actual), source_matches_registration=True,
                  summaries_regenerated=True,
                  scope='Local compact verification; raw archive hashes were rechecked on otakotak during export.')
    print(json.dumps(counts, indent=2))
    return counts


if __name__ == '__main__':
    verify(Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'evidence')
