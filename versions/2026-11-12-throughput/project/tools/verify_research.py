"""Verify frozen research evidence without rerunning native simulation.

Full mode checks retained archive byte digests, compact evidence, build links,
and scores recomputed with that campaign's own frozen scorer. Compact-only mode
never claims to have checked remote raw archives. SHA-256 checks provide content
integrity relative to the registration, not a signed authenticity guarantee.
"""
import argparse
from contextlib import contextmanager
import hashlib
import importlib.util
import json
from pathlib import Path
import sys


def read_json(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def sha(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as stream:
        for block in iter(lambda: stream.read(1048576), b''):
            digest.update(block)
    return digest.hexdigest()


def canonical(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False)


def safe_child(root, relative):
    path = (Path(root) / relative).resolve()
    path.relative_to(Path(root).resolve())
    return path


def frozen_hashes(root):
    root = Path(root)
    return {p.relative_to(root).as_posix(): sha(p) for p in sorted(root.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


@contextmanager
def frozen_scorer(snapshot):
    """Prevent current checkout imports or bytecode writes contaminating replay."""
    snapshot = Path(snapshot)
    saved_path, saved_bytecode = list(sys.path), sys.dont_write_bytecode
    saved_modules = {name: module for name, module in list(sys.modules.items())
                     if name == 'limerlab' or name.startswith('limerlab.')}
    for name in saved_modules:
        del sys.modules[name]
    module_name = '_limer_integrity_frozen_research'
    previous = sys.modules.pop(module_name, None)
    try:
        sys.dont_write_bytecode = True
        sys.path.insert(0, str(snapshot / 'python'))
        spec = importlib.util.spec_from_file_location(module_name, snapshot / 'tools/research_campaign.py')
        if spec is None or spec.loader is None:
            raise ValueError('Cannot load frozen research scorer')
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        yield module
    finally:
        for name in list(sys.modules):
            if name == 'limerlab' or name.startswith('limerlab.'):
                del sys.modules[name]
        sys.modules.update(saved_modules)
        sys.modules.pop(module_name, None)
        if previous is not None:
            sys.modules[module_name] = previous
        sys.path[:] = saved_path
        sys.dont_write_bytecode = saved_bytecode


def verify(directory, skip_archives=False, archives_root=None, progress=False):
    root = Path(directory).resolve()
    archive_root = Path(archives_root).resolve() if archives_root else root / 'archives'
    scope = 'compact-only' if skip_archives else 'archive-digests-and-compact-evidence'
    result = dict(schema='limer-research-integrity-v1', passed=False, scope=scope,
                  registered=0, attempts_present=0, verified_runs=0,
                  archive_digests_verified=0, archive_bytes_hashed=0,
                  compact_files_verified=0, native_binary_verified=False,
                  build_scope='not_checked', errors=[], warnings=[],
                  checks=['Frozen toolchain and exact case registration',
                          'Copied build descriptor and native-binary provenance links',
                          'Retained compact evidence content hashes and result agreement',
                          'First-alarm score replay using the campaign frozen scorer'],
                  limitations=['This does not rerun native simulation or raw packet audit.',
                               'Archived member content is not decompressed again; full mode verifies each complete archive byte digest.',
                               'Content hashes are relative to the supplied registration and are not digital signatures.'])
    if skip_archives:
        result['warnings'].append('Raw archives were deliberately not checked. This is compact-only verification.')
    else:
        result['checks'].append('Streaming SHA-256 of every registered retained raw archive')

    def error(message, name=None):
        result['errors'].append((name + ': ' if name else '') + message)

    try:
        registration = read_json(root / 'registration.json')
        cases = registration['plan']['cases']
        result['registered'] = len(cases)
        names = [c['name'] for c in cases]
        if len(names) != len(set(names)) or any(Path(name).name != name or name in ('.', '..') for name in names):
            raise ValueError('Registered case names are not unique simple filenames')
        # Do not import code until all frozen bytes match the registration.
        if frozen_hashes(root / 'tooling') != registration['tooling_hashes']:
            raise ValueError('Frozen toolchain or configuration changed')
        if sha(root / 'build.json') != registration['build_sha256']:
            raise ValueError('Copied build descriptor differs from registration')
        copied_build = read_json(root / 'build.json')
        if copied_build['binary_sha256'] != registration['binary_sha256']:
            raise ValueError('Copied build binary hash differs from registration')
        if copied_build.get('source_hashes') != registration.get('source_hashes'):
            raise ValueError('Copied build source hashes differ from registration')
        build_path = Path(registration['build_directory'])
        if build_path.exists():
            build_to_validate = build_path
        else:
            build_to_validate = None
            result['warnings'].append('Original native build directory is unavailable; only its copied descriptor and run provenance links are verified.')
        expected_names = set(names)
        existing_attempts = {p.stem for p in (root / 'attempts').glob('*.json')}
        for extra in sorted(existing_attempts - expected_names):
            error('Unexpected unregistered attempt retained: ' + extra)
        result['attempts_present'] = len(existing_attempts & expected_names)
        with frozen_scorer(root / 'tooling') as scorer:
            scorer.validate_registration(root, build_to_validate)
            result['native_binary_verified'] = build_to_validate is not None
            result['build_scope'] = 'native-binary-and-libraries' if build_to_validate is not None else 'copied-descriptor-and-run-links-only'
            for index, case in enumerate(cases, 1):
                name = case['name']
                initial_errors = len(result['errors'])
                try:
                    attempt_path = root / 'attempts' / (name + '.json')
                    if not attempt_path.exists():
                        raise ValueError('Registered attempt is missing; it remains in the denominator')
                    attempt = read_json(attempt_path)
                    if attempt.get('name') != name:
                        raise ValueError('Attempt name differs from registered case')
                    if not attempt.get('valid') or attempt.get('error'):
                        raise ValueError('Registered attempt is invalid or failed: ' + str(attempt.get('error', attempt.get('status'))))
                    run = root / 'runs' / name
                    record = read_json(run / 'result.json')
                    if record.get('name') != name or record.get('method') != case['method'] or record.get('scene') != case['scene']:
                        raise ValueError('Run result identity, method or scene differs from registered case')
                    archive = record['archive']
                    if not archive.get('all_content_hashes_verified'):
                        raise ValueError('Original archive did not record verified member contents')
                    archive_digest = archive['sha256']
                    if archive_digest != attempt.get('archive_sha256'):
                        raise ValueError('Result and attempt archive hashes disagree')
                    if not skip_archives:
                        archive_path = archive_root / (name + '.tar.gz')
                        if not archive_path.is_file():
                            raise ValueError('Raw archive is missing; server raw artifacts are required for full verification. Use --skip-archives only for explicitly compact-only scope.')
                        if sha(archive_path) != archive_digest:
                            raise ValueError('Retained raw archive SHA-256 differs from result/attempt')
                        if archive_path.stat().st_size != archive['bytes']:
                            raise ValueError('Retained raw archive size differs from result')
                        result['archive_digests_verified'] += 1
                        result['archive_bytes_hashed'] += archive_path.stat().st_size

                    indexed = archive['files']
                    required = ['run_status.json', 'audit.json', 'observation_audit.json',
                                'performance.json', 'run_manifest.json']
                    if case['scene'].get('detector', 'legacy') == 'service':
                        required.extend(['service_alarms.csv', 'service_events.csv', 'service_decisions.jsonl'])
                    else:
                        required.append('detector_events.csv')
                    policy_name = 'policy_decisions.jsonl' if 'policy_decisions.jsonl' in indexed else 'policy_decisions.csv'
                    required.append(policy_name)
                    for relative in required:
                        if relative not in indexed or not safe_child(run, relative).is_file():
                            raise ValueError('Required compact evidence is missing: ' + relative)
                    # Hash all retained indexed files, including topology/input
                    # and truth files when exported, without requiring pruned raw logs.
                    for relative, expected_digest in indexed.items():
                        path = safe_child(run, relative)
                        if path.exists():
                            if not path.is_file() or sha(path) != expected_digest:
                                raise ValueError('Retained evidence hash changed: ' + relative)
                            result['compact_files_verified'] += 1
                    for filename, field in [('run_status.json', 'status'), ('audit.json', 'audit'),
                                            ('observation_audit.json', 'observation_audit'), ('performance.json', 'performance')]:
                        if read_json(run / filename) != record[field]:
                            raise ValueError('Compact evidence and result disagree: ' + filename)
                    if not record['audit']['pass'] or not record['observation_audit']['pass']:
                        raise ValueError('Independent audit or observation replay failed')
                    if record['status']['status'] != attempt.get('status'):
                        raise ValueError('Attempt and result completion statuses disagree')
                    manifest = read_json(run / 'run_manifest.json')
                    if manifest['binary_sha256'] != registration['binary_sha256'] or manifest['build_sha256'] != registration['build_sha256']:
                        raise ValueError('Native binary/build provenance differs from registration')
                    if manifest.get('scene') != case['scene'] or manifest.get('method') != case['method']:
                        raise ValueError('Native run manifest differs from registered scene/method')
                    if 'binary_sha256' in record and record['binary_sha256'] != registration['binary_sha256']:
                        raise ValueError('Result binary hash differs from registration')
                    for relative, expected_digest in manifest.get('input_hashes', {}).items():
                        path = safe_child(run, relative)
                        if not path.is_file() or sha(path) != expected_digest:
                            raise ValueError('Native input is missing or changed: ' + relative)
                        if indexed.get(relative) != expected_digest:
                            raise ValueError('Native input and archived input hashes disagree: ' + relative)
                    recomputed = scorer.score_run(run, case)
                    if not recomputed.get('valid'):
                        raise ValueError('Frozen score replay found invalid audits or incomplete monitoring')
                    if canonical(recomputed) != canonical(attempt.get('score')):
                        raise ValueError('Recomputed frozen score differs from retained attempt score')
                except Exception as exception:
                    error(str(exception), name)
                if len(result['errors']) == initial_errors:
                    result['verified_runs'] += 1
                if progress and (index % 10 == 0 or index == len(cases)):
                    print(f'Checked {index}/{len(cases)} registered runs; verified {result["verified_runs"]}; errors {len(result["errors"])}', file=sys.stderr, flush=True)
    except Exception as exception:
        error(str(exception))
    result['passed'] = not result['errors'] and result['registered'] > 0 and result['verified_runs'] == result['registered']
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('directory', type=Path)
    parser.add_argument('--skip-archives', action='store_true', help='Verify compact evidence only; do not claim raw archive verification')
    parser.add_argument('--archives-root', type=Path, help='Directory containing case-name.tar.gz files, e.g. mounted server raw artifacts')
    parser.add_argument('--progress', action='store_true', help='Write bounded progress every ten cases to stderr')
    args = parser.parse_args()
    result = verify(args.directory, args.skip_archives, args.archives_root, args.progress)
    print(json.dumps(result, ensure_ascii=False, allow_nan=False))
    raise SystemExit(0 if result['passed'] else 1)


if __name__ == '__main__':
    main()
