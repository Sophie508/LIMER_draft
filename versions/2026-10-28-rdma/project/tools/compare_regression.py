"""Compare a fresh qualification against original physical/logical trace hashes."""
import argparse
import hashlib
import json
from pathlib import Path
import zipfile

TRACES = ['logical_events.csv', 'packet_events.csv', 'wire_events.csv', 'observations.jsonl',
          'peer_events.csv', 'leg_events.csv', 'control_events.csv', 'phase_events.csv',
          'detector_events.csv', 'm13_alarms.jsonl', 'm13_baseline.jsonl', 'fault_events.csv']


def sha(p):
    h = hashlib.sha256()
    with p.open('rb') as f:
        for block in iter(lambda: f.read(1048576), b''): h.update(block)
    return h.hexdigest()


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('campaign', type=Path)
    parser.add_argument('--out', type=Path, required=True)
    parser.add_argument('--allow-partial', action='store_true')
    a = parser.parse_args()
    project = Path(__file__).resolve().parents[1]
    index = json.loads((project / 'reference/index.json').read_text())
    bundle = project / 'reference' / index['archive']
    if sha(bundle) != index['sha256']: raise ValueError('Reference bundle changed')
    with zipfile.ZipFile(bundle) as z:
        original = json.loads(z.read(index['root'] + '/evidence/smoke_results.json'))
    expected = {r['name']: r for r in original}
    results = json.loads((a.campaign / 'results.json').read_text()) if (a.campaign / 'results.json').exists() else []
    cases = []
    for result in results:
        old = expected[result['name']]
        comparison = dict(name=result['name'], status_identical=result['status'] == old['status'],
                          method_and_scene_identical=result['method'] == old['method'] and result['scene'] == old['scene'],
                          independent_checks_passed=result['audit']['pass'] and result['observation_audit']['pass'],
                          communication_ms=result['performance']['communication_ms'],
                          traces={name: result['archive']['files'].get(name) == old['archive']['files'].get(name)
                                  and name in result['archive']['files'] and name in old['archive']['files'] for name in TRACES})
        comparison['passed'] = (comparison['status_identical'] and comparison['method_and_scene_identical'] and
                                comparison['independent_checks_passed'] and all(comparison['traces'].values()))
        cases.append(comparison)
    record = dict(schema='limer-migration-regression-v1', reference_bundle_sha256=index['sha256'],
                  expected=7, compared=len(cases), complete=len(cases) == 7,
                  all_available_cases_identical=all(c['passed'] for c in cases), cases=cases,
                  claim='Original and refactored logical, packet, wire, observation, control and fault traces are byte-identical for these exact cases')
    a.out.parent.mkdir(parents=True, exist_ok=True)
    a.out.write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(dict(compared=len(cases), expected=7, identical=record['all_available_cases_identical'],
                          complete=record['complete'], mismatches=[c['name'] for c in cases if not c['passed']])))
    raise SystemExit(not record['all_available_cases_identical'] or (not a.allow_partial and not record['complete']))
