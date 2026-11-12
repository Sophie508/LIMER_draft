"""Export compact campaign evidence without discarding invalid or pending cases."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def read(path):
    return json.loads(path.read_text())


def export(base, out, groups, local_project='project'):
    if Path(local_project).name != local_project:
        raise ValueError('Local project must be a sibling directory name')
    out.mkdir(parents=True, exist_ok=False)
    receipts, failed_raw = [], []
    inventory = {}
    for group in groups:
        if Path(group).name != group:
            raise ValueError('Campaign must be a simple directory name')
        origin, dest = base / 'results' / group, out / group
        registration = read(origin / 'registration.json')
        dest.mkdir()
        for name in ('registration.json', 'build.json', 'campaign_state.json',
                     'gray_gate_summary.json'):
            if (origin / name).exists():
                shutil.copy2(origin / name, dest / name)
        for name in ('attempts', 'cases', 'logs'):
            shutil.copytree(origin / name, dest / name)
        inventory[group] = dict(registered=len(registration['plan']['cases']),
                                attempted=0, valid=0, archives=0)
        for case in registration['plan']['cases']:
            name = case['name']
            attempt_file = origin / 'attempts' / (name + '.json')
            if attempt_file.exists():
                attempt = read(attempt_file)
                inventory[group]['attempted'] += 1
                inventory[group]['valid'] += bool(attempt['valid'])
            run, target = origin / 'runs' / name, dest / 'runs' / name
            if not run.exists():
                continue
            if attempt_file.exists() and not read(attempt_file)['valid']:
                failed_raw.append(dict(group=group, name=name, server_path=str(run),
                    files={p.relative_to(run).as_posix(): sha(p)
                           for p in sorted(run.rglob('*')) if p.is_file()}))
            target.mkdir(parents=True)
            for filename in ('run_status.json', 'run_manifest.json', 'result.json',
                             'audit.json', 'observation_audit.json', 'performance.json',
                             'archive_manifest.json', 'detector_events.csv',
                             'service_alarms.csv', 'phase_events.csv', 'phase_metrics.csv',
                             'control_events.csv', 'policy_decisions.jsonl',
                             'helper_reports.jsonl', 'runner_error.json',
                             'simulator.log', 'audit.log', 'replay.log', 'metrics.log'):
                if (run / filename).exists():
                    shutil.copy2(run / filename, target / filename)
            for folder in ('inputs', 'truth'):
                if (run / folder).exists():
                    shutil.copytree(run / folder, target / folder)
            if (run / 'archive_manifest.json').exists():
                manifest = read(run / 'archive_manifest.json')
                archive = origin / 'archives' / (name + '.tar.gz')
                digest = sha(archive)
                assert digest == manifest['sha256'], str(archive)
                assert archive.stat().st_size == manifest['bytes']
                assert manifest['all_content_hashes_verified']
                receipts.append(dict(group=group, name=name, path=str(archive),
                                     sha256=digest, bytes=archive.stat().st_size,
                                     all_member_hashes_verified=True))
                inventory[group]['archives'] += 1
        (dest / 'source-location.json').write_text(json.dumps(dict(
            local_project=local_project, server_base=str(base),
            source_hashes=registration['source_hashes'],
            scope='Compact receipts; large raw logs and archives remain on otakotak.'
        ), indent=2) + '\n')
    (out / 'archive-integrity.json').write_text(json.dumps(dict(
        archives=receipts, all_archive_hashes_rechecked=True,
        failed_raw_inventories=failed_raw,
        campaign_inventory=inventory), indent=2) + '\n')
    files = {p.relative_to(out).as_posix(): sha(p)
             for p in sorted(out.rglob('*')) if p.is_file()}
    (out / 'COMPACT_MANIFEST.json').write_text(json.dumps(dict(
        files=files, raw_archives_included=False), indent=2) + '\n')
    print(json.dumps(inventory))


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('out', type=Path)
    parser.add_argument('--campaign', action='append', required=True)
    parser.add_argument('--local-project', default='project')
    args = parser.parse_args()
    export(args.base, args.out, args.campaign, args.local_project)
