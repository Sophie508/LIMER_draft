"""Score every registered attempt, including failures and missing detections."""
from pathlib import Path
from collections import Counter
import json
import math

ROOT = Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')


def order_statistic_p95(values):
    """Nearest-rank p95; None means no detection, not an omitted observation."""
    if not values:
        return {'value_ms': None, 'status': 'no_registered_faults'}
    ordered = sorted(math.inf if x is None else x for x in values)
    value = ordered[math.ceil(.95 * len(ordered)) - 1]
    return {'value_ms': value if math.isfinite(value) else None,
            'status': 'finite' if math.isfinite(value) else 'infinite_due_to_misses',
            'definition': 'nearest-rank ceil(0.95*N), nondetections=infinity'}


def wilson(successes, n):
    if not n:
        return None
    z = 1.959963984540054
    p = successes / n
    center = (p + z*z/(2*n)) / (1 + z*z/n)
    width = z * math.sqrt(p*(1-p)/n + z*z/(4*n*n)) / (1+z*z/n)
    return [max(0, center-width), min(1, center+width)]


def score(registration_name='m7_validation_v3', output_name=None):
    registered = json.loads((ROOT/'logs'/f'{registration_name}_registration.json').read_text())
    analysis = {r['name']: r for r in json.loads((ROOT/'logs/m7_tcp_analysis.json').read_text())}
    rows = []
    for name, config_path in registered:
        cfg = json.loads((ROOT/'limer_source_m7_tcp_v3'/config_path).read_text())
        status_path = ROOT/'logs'/f'{name}.status.json'
        status = json.loads(status_path.read_text()) if status_path.exists() else {}
        row = dict(name=name, configured_loss_pct=cfg['fault_loss_pct'],
                   control=cfg['m7_control'], launched=bool(status),
                   terminal='exit_code' in status,
                   complete=status.get('exit_code') == 0 and
                            status.get('summary', {}).get('status') == 'complete',
                   correctness=status.get('correctness', {}).get('status'),
                   confirmation_ms=None, within100ms=False,
                   false_alarm_count=None, observed=False)
        if name in analysis:
            row.update(analysis[name], observed=True)
        # A scientific detection does not erase an infrastructure failure.
        row['within100ms_and_complete'] = bool(row['within100ms'] and row['complete']
                                              and row['correctness'] == 'pass')
        row['input_hashes'] = status.get('hashes')
        row['wrapper_sha256'] = status.get('wrapper_sha256')
        row['image_id'] = status.get('image_id')
        folder = ROOT/'mininet_results'/name
        qdiscs = []
        for filename in ['all_switch_final_qdiscs.json', 'all_ingress_final_qdiscs.json']:
            path = folder/filename
            if path.exists():
                for interface, records in json.loads(path.read_text()).items():
                    for record in records:
                        if record.get('kind') == 'netem':
                            qdiscs.append(dict(interface=interface, drops=record.get('drops')))
        row['final_netem_drops'] = qdiscs
        rows.append(row)
    faults = [r for r in rows if r['configured_loss_pct'] > 0]
    controls = [r for r in rows if r['configured_loss_pct'] == 0]
    groups = {}
    for loss in sorted({r['configured_loss_pct'] for r in faults}):
        group = [r for r in faults if r['configured_loss_pct'] == loss]
        n = len(group)
        successes = sum(r['within100ms_and_complete'] for r in group)
        times = [r['confirmation_ms'] for r in group]
        finite = [t for t in times if t is not None]
        groups[str(loss)] = dict(registered=n, timely_complete=successes,
                                rate=successes/n, wilson95=wilson(successes, n),
                                detected=len(finite), missed=n-len(finite),
                                late=sum(t >= 100 for t in finite),
                                p95=order_statistic_p95(times),
                                finite_min_ms=min(finite, default=None),
                                finite_max_ms=max(finite, default=None),
                                false_alarms=sum(r['false_alarm_count'] or 0 for r in group))
    control_groups = {}
    for kind in sorted({r['control'] for r in controls}):
        group = [r for r in controls if r['control'] == kind]
        control_groups[kind] = dict(registered=len(group),
                                    observed=sum(r['observed'] for r in group),
                                    false_alarm_runs=sum(bool(r['false_alarm_count']) for r in group),
                                    false_alarm_events=sum(r['false_alarm_count'] or 0 for r in group),
                                    observed_seconds=sum(r.get('observation_seconds', 0) for r in group),
                                    connection_seconds=sum(r.get('connection_seconds', 0) for r in group),
                                    netem_drop_total=sum(q['drops'] or 0 for r in group for q in r['final_netem_drops']))
    verified_controls = all(r['observed'] and r['complete'] and r['correctness'] == 'pass'
                            and r['false_alarm_count'] == 0 for r in controls)
    strict = bool(faults and controls and all(r['within100ms_and_complete'] and
                  r['false_alarm_count'] == 0 for r in faults) and verified_controls)
    hash_fields = ['limer_v0/worker.py', 'limer_v0/orchestrator.py', 'limer_v0/tcp_loss.py']
    source_hashes = {k: sorted({r['input_hashes'][k] for r in rows if r['input_hashes']})
                     for k in hash_fields}
    output = dict(registration=registration_name, registered=len(rows),
                  launched=sum(r['launched'] for r in rows), terminal=sum(r['terminal'] for r in rows),
                  completed_correct=sum(r['complete'] and r['correctness'] == 'pass' for r in rows),
                  faults=groups, controls=control_groups,
                  timely_faults=sum(r['within100ms_and_complete'] for r in faults),
                  registered_faults=len(faults),
                  pooled_p95=order_statistic_p95([r['confirmation_ms'] for r in faults]),
                  all_fault_false_alarm_events=sum(r['false_alarm_count'] or 0 for r in faults),
                  all_control_false_alarm_events=sum(r['false_alarm_count'] or 0 for r in controls),
                  all_control_false_alarm_runs=sum(bool(r['false_alarm_count']) for r in controls),
                  control_false_alarm_run_rate_wilson95=wilson(sum(bool(r['false_alarm_count']) for r in controls), len(controls)),
                  strict_all_run_gate='pass' if strict else ('incomplete' if not all(r['terminal'] for r in rows) else 'fail'),
                  source_hashes=source_hashes,
                  source_frozen=all(len(v) == 1 for v in source_hashes.values()),
                  image_ids=sorted({r['image_id'] for r in rows if r['image_id']}),
                  wrapper_hashes=sorted({r['wrapper_sha256'] for r in rows if r['wrapper_sha256']}),
                  rule_versions=dict(Counter(r.get('rule_version', 'unobserved') for r in rows)),
                  rows=rows)
    path = ROOT/'logs'/f'{output_name or registration_name}_metrics.json'
    path.write_text(json.dumps(output, indent=2, allow_nan=False)+'\n')
    print(json.dumps({k:v for k,v in output.items() if k != 'rows'}, indent=2, allow_nan=False))
    return output


if __name__ == '__main__':
    import sys
    assert order_statistic_p95([1]*95+[None]*5)['value_ms'] == 1
    assert order_statistic_p95([1]*94+[None]*6)['status'] == 'infinite_due_to_misses'
    assert order_statistic_p95([1, 101])['value_ms'] == 101
    score(sys.argv[1] if len(sys.argv) > 1 else 'm7_validation_v3')
