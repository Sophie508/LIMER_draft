"""Score phase performance and sustained NEW B-prime work from independent logs."""
import csv
import json
from collections import defaultdict
from pathlib import Path


def calculate(root):
    root = Path(root)
    status = json.loads((root / 'run_status.json').read_text())
    scene = json.loads((root / 'run_manifest.json').read_text())['scene']
    starts = {}
    with (root / 'phase_events.csv').open() as f:
        for r in csv.DictReader(f):
            starts[int(r['phase'])] = int(r['timestamp_ns'])
    end = status['job_done_ns'] or status['horizon_ns']
    activation = {}
    with (root / 'control_events.csv').open() as f:
        for r in csv.DictReader(f):
            if r['event'] == 'ACTIVATE':
                activation.setdefault(int(r['rank']), int(r['arrival_ns']))
    alarms = {}
    with (root / 'detector_events.csv').open() as f:
        for r in csv.DictReader(f):
            key = int(r['path_id'])
            src = key // 48
            dst = src + 4 if src < 12 else (src + 1) % 4
            if src < 16 and key == (src * 16 + dst) * 3 + 1:
                alarms[src] = int(r['timestamp_ns'])
    migrated, allocated, route_type, progress = set(), {}, {}, defaultdict(int)
    proxy_routes, logical_completion = {}, {}
    totals = defaultdict(lambda: defaultdict(int))
    bins = defaultdict(lambda: defaultdict(int))
    bin_ns = 10000000
    fault_ns = scene['fault_ns'] if scene['family'] != 'healthy' else None
    nodes = set(range(4)) if scene['family'] == 'no_idle_helpers' else {scene['node']}
    affected = {s for s in range(16) if s in nodes or (s+4 if s < 12 else (s+1) % 4) in nodes}
    allocation_windows = defaultdict(lambda: defaultdict(int))
    with (root / 'logical_events.csv').open() as f:
        for r in csv.DictReader(f):
            c, p, s, t = (int(r[k]) for k in ['chunk_id', 'phase', 'src', 'timestamp_ns'])
            if r['event'] == 'ALLOC':
                allocated[c] = (t, p, s, int(r['lane']))
                if fault_ns is not None and s in affected:
                    region = ('before_fault' if t < fault_ns else
                              'after_replacement' if s in activation and t >= activation[s] else
                              'before_diagnosis' if s not in alarms or t < alarms[s] else 'preparing')
                    lane = 'Bprime' if int(r['epoch']) else 'A' if r['lane'] == '0' else 'B'
                    allocation_windows[region][lane + '_new_bytes'] += 65536
            elif r['event'] == 'MIGRATE':
                migrated.add(c)
            elif r['event'] in ['DIRECT_LAUNCH', 'PROXY_LAUNCH']:
                route_type[c] = 'Bprime' if r['event'] == 'PROXY_LAUNCH' else ('A' if r['lane'] == '0' else 'B')
                if route_type[c] == 'Bprime':
                    proxy_routes[int(r['route'])] = c
                    totals[p]['rescued_launches' if c in migrated else 'new_Bprime_launches'] += 1
            elif r['event'] == 'ACK_PROGRESS':
                amount = int(r['acked']) - progress[c]
                progress[c] = int(r['acked'])
                lane = route_type[c]
                totals[p][lane + '_unique_bytes'] += amount
                bins[t // bin_ns][lane + '_unique_bytes'] += amount
                bins[t // bin_ns][f'src{s}_unique_bytes'] += amount
                bins[t // bin_ns][f'src{s}_{lane}_unique_bytes'] += amount
            elif r['event'] == 'DONE':
                logical_completion[int(r['route'])] = t
                totals[p]['done_chunks'] += 1
                totals[p]['end_ns'] = max(totals[p]['end_ns'], t)
                if c not in migrated and route_type[c] == 'Bprime':
                    totals[p]['new_Bprime_done'] += 1
    rows = []
    last_activation = max(activation.values(), default=None)
    for p, start in sorted(starts.items()):
        x = totals[p]
        complete = x.get('done_chunks', 0) == 16 * status['chunks_per_phase']
        stop = x.get('end_ns', start) if complete else end
        duration = stop - start
        row = dict(phase=p, start_ns=start, end_ns=stop, complete=complete, duration_ns=duration,
                   **{k: v for k, v in x.items() if k != 'end_ns'})
        row['region'] = ('healthy' if fault_ns is None else 'before_fault' if stop <= fault_ns else
                         'after_replacement' if last_activation and start > last_activation else 'fault_or_diagnosis')
        row['aggregate_unique_gbps'] = sum(x.get(k + '_unique_bytes', 0) for k in ['A', 'B', 'Bprime']) * 8 / max(1, duration)
        rows.append(row)
    with (root / 'phase_metrics.csv').open('w', newline='') as f:
        columns = ['phase', 'start_ns', 'end_ns', 'complete', 'duration_ns', 'region', 'aggregate_unique_gbps',
                   'A_unique_bytes', 'B_unique_bytes', 'Bprime_unique_bytes', 'new_Bprime_launches',
                   'new_Bprime_done', 'rescued_launches', 'done_chunks']
        w = csv.DictWriter(f, fieldnames=columns)
        w.writeheader()
        w.writerows(rows)
    binned = [dict(start_ns=b * bin_ns, end_ns=(b + 1) * bin_ns, **v) for b, v in sorted(bins.items())]
    (root / 'throughput_10ms.json').write_text(json.dumps(binned, indent=2) + '\n')
    steady = [r for r in rows if r['complete'] and r['region'] == 'after_replacement']
    result = dict(task_completed=status['status'] == 'completed',
        communication_ms=(status['job_done_ns'] - 1000000) / 1e6 if status['job_done_ns'] else None,
        restricted_communication_ms=((status['job_done_ns'] or status['horizon_ns']) - 1000000) / 1e6,
        alarms_ns=alarms, first_activations_ns=activation,
        detector_delays_ms={s: (t - fault_ns) / 1e6 for s, t in alarms.items()} if fault_ns else {},
        alarm_to_activation_ms={s: (t - alarms[s]) / 1e6 for s, t in activation.items() if s in alarms},
        new_Bprime_launches=sum(r.get('new_Bprime_launches', 0) for r in rows),
        new_Bprime_completions=sum(r.get('new_Bprime_done', 0) for r in rows),
        new_Bprime_phases=sum(r.get('new_Bprime_done', 0) > 0 for r in rows),
        post_replacement_complete_phases=len(steady),
        post_replacement_mean_phase_ms=sum(r['duration_ns'] for r in steady) / len(steady) / 1e6 if steady else None,
        unique_payload_bytes=sum(progress.values()),
        recovery_observed=bool(activation) and status['status'] == 'completed',
        sustained_new_proxy_observed=sum(r.get('new_Bprime_done', 0) > 0 for r in rows) >= 2)
    result['scored_affected_sources'] = sorted(affected) if fault_ns is not None else []
    result['affected_source_new_allocations_by_region'] = dict(allocation_windows)
    result['healthy_alarm_observed'] = scene['family'] == 'healthy' and any(t <= end for t in alarms.values())
    result['healthy_proxy_observed'] = scene['family'] == 'healthy' and bool(status['proxy_chunks'])
    result['alarms_before_injected_fault'] = {s: t for s, t in alarms.items() if fault_ns is not None and t < fault_ns}
    # Explain whether copying, the network leg or the completion notification limits fresh B-prime.
    leg_start, leg_duration, final_target_at = {}, defaultdict(dict), {}
    with (root / 'leg_events.csv').open() as f:
        for r in csv.DictReader(f):
            rid, index, t = int(r['route']), int(r['index']), int(r['timestamp_ns'])
            if rid not in proxy_routes: continue
            if r['event'] == 'LEG_START': leg_start[rid, index] = t
            elif r['event'] == 'LEG_DONE':
                leg_duration[rid][index] = t - leg_start[rid, index]
                if index == 2: final_target_at[rid] = t
    fresh_routes = [rid for rid, c in proxy_routes.items() if c not in migrated and
                    rid in logical_completion and len(leg_duration[rid]) == 3]
    result['fresh_proxy_costs'] = dict(completed_routes=len(fresh_routes))
    if fresh_routes:
        costs = result['fresh_proxy_costs']
        for index, name in enumerate(['source_local_leg_ms', 'network_leg_ms', 'destination_local_leg_ms']):
            costs[name] = sum(leg_duration[rid][index] for rid in fresh_routes) / len(fresh_routes) / 1e6
        costs['final_notification_ms'] = sum(logical_completion[rid] - final_target_at[rid] for rid in fresh_routes) / len(fresh_routes) / 1e6
        costs['route_to_logical_done_ms'] = sum(logical_completion[rid] - leg_start[rid, 0] for rid in fresh_routes) / len(fresh_routes) / 1e6
    (root / 'performance.json').write_text(json.dumps(result, indent=2) + '\n')
    return result


if __name__ == '__main__':
    import sys
    print(json.dumps(calculate(sys.argv[1])))
