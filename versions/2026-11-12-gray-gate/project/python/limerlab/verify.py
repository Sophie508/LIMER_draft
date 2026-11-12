"""Verify delivery bytes, validated native sources and regression evidence."""
from .paths import ROOT, read_json, sha


def verify():
    checks = {}
    manifest = ROOT / 'DELIVERY_MANIFEST.json'
    if manifest.exists():
        files = read_json(manifest)['files']
        checks['delivery_file_hashes'] = all(sha(ROOT / name) == digest for name, digest in files.items())
    validation = ROOT / 'validation'
    files = read_json(validation / 'files.sha256.json')
    checks['validation_file_hashes'] = all(sha(validation / name) == digest for name, digest in files.items())
    build = read_json(validation / 'build.json')
    checks['native_source_matches_validated_build'] = all(sha(ROOT / name) == digest for name, digest in build['source_hashes'].items())
    regression = read_json(validation / 'regression.json')
    checks['seven_case_trace_equivalence'] = (regression['complete'] and regression['compared'] == 7 and
        regression['all_available_cases_identical'] and all(c['passed'] and all(c['traces'].values()) for c in regression['cases']))
    registration = read_json(validation / 'registration.json')
    checks['frozen_tools'] = all(sha(validation / 'tooling' / name) == digest for name, digest in registration['tooling_hashes'].items())
    results = read_json(validation / 'results.json')
    checks['all_independent_checks_passed'] = len(results) == 7 and all(r['audit']['pass'] and r['observation_audit']['pass'] for r in results)
    for result in results:
        folder = validation / 'runs' / result['name']
        inputs = read_json(folder / 'run_manifest.json')['input_hashes']
        checks['inputs:' + result['name']] = all(sha(folder / name) == digest for name, digest in inputs.items())
    index = read_json(ROOT / 'reference/index.json')
    checks['reference_archive_hash'] = sha(ROOT / 'reference' / index['archive']) == index['sha256']
    return dict(passed=all(checks.values()), checks=checks, validation_files=len(files),
                validated_native_source_files=len(build['source_hashes']), regression_cases=len(results))
