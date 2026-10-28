"""Honest summaries: unfinished tasks stay in the denominator and at the cap."""
import csv
from pathlib import Path
from .paths import read_json, write_json


def report(directory):
    root = Path(directory)
    registration = read_json(root / 'registration.json')
    results = read_json(root / 'results.json') if (root / 'results.json').exists() else []
    by_name = {r['name']: r for r in results}
    rows = []
    for case in registration['cases']:
        r = by_name.get(case['name'])
        if not r:
            rows.append(dict(name=case['name'], method=case['method'], family=case['family'], status='not_verified'))
            continue
        p, s = r['performance'], r['status']
        rows.append(dict(name=case['name'], method=case['method'], family=case['family'], status=s['status'],
                         communication_ms=p['communication_ms'], restricted_ms=p['restricted_communication_ms'],
                         fresh_proxy_chunks=s['new_proxy_chunks'], rescued_chunks=s['rescued_chunks'],
                         fresh_proxy_phases=p['new_Bprime_phases'],
                         post_replacement_phase_ms=p['post_replacement_mean_phase_ms']))
    columns = ['name', 'method', 'family', 'status', 'communication_ms', 'restricted_ms', 'fresh_proxy_chunks',
               'rescued_chunks', 'fresh_proxy_phases', 'post_replacement_phase_ms']
    with (root / 'summary.csv').open('w', newline='') as stream:
        writer = csv.DictWriter(stream, fieldnames=columns); writer.writeheader(); writer.writerows(rows)
    summary = dict(expected=len(rows), verified=len(results),
                   completed=sum(r['status']['status'] == 'completed' for r in results),
                   observation_limit=sum(r['status']['status'] == 'task_unfinished' for r in results),
                   complete=len(results) == len(rows),
                   all_verified_checks_passed=all(r['audit']['pass'] and r['observation_audit']['pass'] for r in results))
    write_json(root / 'summary.json', summary)
    text = ['# LIMER experiment results', '',
            f"Verified {len(results)}/{len(rows)} cases. Completed tasks: {summary['completed']}; observation limit: {summary['observation_limit']}.", '',
            'Times below are simulated communication times, not CPU wall time. Observation limits are not successful completions.', '',
            '| Case | Method | Status | Communication ms | New B-prime chunks | Post-replacement phase ms |',
            '| --- | --- | --- | ---: | ---: | ---: |']
    for r in rows:
        value = r.get('communication_ms')
        t = 'unfinished' if r['status'] == 'task_unfinished' else 'pending' if value is None else f'{value:.6f}'
        phase = r.get('post_replacement_phase_ms')
        text.append(f"| {r['name']} | {r['method']} | {r['status']} | {t} | {r.get('fresh_proxy_chunks', '')} | " +
                    (f'{phase:.6f}' if phase is not None else '') + ' |')
    text += ['', 'M13 does not contain a dedicated sustained-capacity-degradation branch. '
             'GPU computation/CUDA kernels and HBM contention are not modeled. '
             'Task completion and restoration of healthy throughput are distinct outcomes.', '']
    (root / 'report.md').write_text('\n'.join(text), encoding='utf-8')
    return summary
