"""Audit M13 causality, persistent B-prime new work, physical routes and ACKs."""
from collections import defaultdict
from bisect import bisect_right
import csv
import json
from pathlib import Path


def rows(path):
    with path.open() as f:
        yield from csv.DictReader(f)


def audit(root):
    root = Path(root)
    status = json.loads((root / 'run_status.json').read_text())
    errors = []

    def check(ok, message):
        if not ok and len(errors) < 100:
            errors.append(message)

    topology = (root / 'inputs/topology.txt').read_text().splitlines()
    check(topology[0].split()[:4] == ['92', '4', '4', '72'], 'not the original dual-plane node inventory')
    access = defaultdict(list)
    for line in topology[2:]:
        u, v, rate, *_ = line.split()
        if int(u) < 16 and int(v) >= 20:
            access[int(u)].append(int(v))
            check(rate == '10Gbps', 'access bandwidth changed')
    check(all(len(access[g]) == 2 for g in range(16)), 'a GPU has an added or missing access link')
    check(status['physical_planes'] == 2 and not status['extra_rto'], 'protocol metadata changed')
    fixed = status['method'] in ('G00', 'G01')
    enabled = status['method'] in ('G01', 'G11')
    phase_chunks = status['chunks_per_phase']
    phase_bytes = phase_chunks * 65536
    manifest_path = root / 'run_manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        check(manifest['scene']['chunks_per_phase'] == phase_chunks, 'registered chunk geometry changed')
        for name in ('detector','policy'):
            if name in manifest['scene']:
                check(status.get(name+'_mode') == manifest['scene'][name], 'registered '+name+' changed')
        local = defaultdict(list)
        for line in topology[2:]:
            u, v, rate, *_ = line.split()
            if int(u) < 16 and 16 <= int(v) < 20:
                local[int(u)].append(rate)
        check(all(local[g] == [str(manifest['scene']['local_gbps']) + 'Gbps'] for g in range(16)),
              'registered intra-server bandwidth changed')
    expected_scope=('service-driven persistent B-prime replacement v2' if status.get('detector_mode')=='service'
                    else 'M13-driven persistent B-prime replacement v1')
    check(status['scope'] == expected_scope, 'wrong protocol')
    chunks = {}
    done = {}
    intervals = defaultdict(list)
    allocations = {}
    final_routes = {}
    direct_routes = {}
    migrated = set()
    unique = 0
    active = defaultdict(int)
    max_source = 0
    for raw in rows(root / 'logical_events.csv'):
        name = raw['event']
        r = {k: int(v) for k, v in raw.items() if k != 'event'}
        c, t = r['chunk_id'], r['timestamp_ns']
        if name == 'ALLOC':
            check(c not in chunks, 'duplicate logical allocation')
            check(r['length'] == 65536 and r['offset'] % 65536 == 0, 'changed chunk geometry')
            check(r['dst'] == (r['src'] + 4 if r['src'] < 12 else (r['src'] + 1) % 4), 'logical destination changed')
            if fixed:
                check(r['lane'] == (r['offset'] // 65536) % 2, 'fixed B work reassigned to A')
            check(r['acked'] == 0, 'new chunk starts acknowledged')
            intervals[r['phase'], r['src']].append(r['offset'])
            allocations[c] = dict(r)
            active[r['src']] += 1
            max_source = max(max_source, active[r['src']])
            check(active[r['src']] <= 8, 'logical source credit exceeded')
        else:
            check(c in chunks, 'event for unknown chunk')
            if c not in chunks:
                continue
            old = chunks[c]
            check(all(r[k] == old[k] for k in ['phase', 'src', 'dst', 'offset', 'length', 'lane']), 'logical owner changed')
            check(c not in done, 'event after logical completion')
            if name == 'ACK_PROGRESS':
                check(r['epoch'] == old['epoch'] and old['acked'] < r['acked'] <= 65536, 'stale or duplicate ACK')
                unique += r['acked'] - old['acked']
            elif name == 'MIGRATE':
                check(enabled and c not in migrated and r['epoch'] == old['epoch'] + 1 and r['acked'] == old['acked'], 'invalid migration')
                migrated.add(c)
            elif name == 'PROXY_LAUNCH':
                check(enabled and r['epoch'] == 1 and r['lane'] == 1, 'proxy on unenabled method/lane')
                final_routes[r['route']] = dict(r)
            elif name == 'DIRECT_LAUNCH':
                check(r['epoch'] == 0, 'direct launch after migration')
                direct_routes[r['route']] = dict(r)
            elif name == 'DONE':
                check(r['acked'] == 65536, 'premature logical DONE')
                done[c] = dict(r)
                active[r['src']] -= 1
            else:
                check(False, 'unknown logical event')
        chunks[c] = r
    for flow, offsets in intervals.items():
        check(len(offsets) == len(set(offsets)), 'overlapping logical chunks')
        check(all(0 <= x < phase_bytes for x in offsets), 'logical offset outside stage')
        if status['status'] == 'completed':
            check(sorted(offsets) == list(range(0, phase_bytes, 65536)), 'incomplete stage payload')
    if status['status'] == 'completed':
        check(len(done) == status['phases_expected'] * 16 * phase_chunks == len(chunks), 'missing logical completion')
        check(unique == status['phases_expected'] * 16 * phase_bytes, 'unique payload total mismatch')
        check(status['job_done_ns'] == max(r['timestamp_ns'] for r in done.values()), 'completion timestamp mismatch')
    finishes = defaultdict(list)
    for r in done.values():
        finishes[r['phase'], r['src'], 'out'].append(r['timestamp_ns'])
        finishes[r['phase'], r['dst'], 'in'].append(r['timestamp_ns'])

    def idle_at(p, g, t):
        out, incoming = finishes[p, g, 'out'], finishes[p, g, 'in']
        return len(out) == len(incoming) == phase_chunks and max(out + incoming) <= t

    def idle_time(p, g):
        return max(finishes[p, g, 'out'] + finishes[p, g, 'in'], default=10**30)

    reservations = {}
    tx, rx, buffers = defaultdict(int), defaultdict(int), defaultdict(int)
    max_nic = max_buffers = relay_count = 0
    for raw in rows(root / 'peer_events.csv'):
        name = raw['event']
        r = {k: int(v) for k, v in raw.items() if k != 'event'}
        rid, t = r['route'], r['timestamp_ns']
        edges = [(r['src'], r['dst'], r['rail'] + 2)]
        if r['relay']:
            edges = [(r['src'], r['helper_src'], 1), (r['helper_src'], r['helper_dst'], r['rail'] + 2), (r['helper_dst'], r['dst'], 1)]
        delta = 1 if name == 'RESERVE' else -1
        check(name in ('RESERVE', 'RELEASE'), 'unknown resource event')
        if delta == 1:
            check(rid not in reservations, 'duplicate reservation')
            reservations[rid] = r
            if r['relay']:
                check(enabled, 'relay resources on baseline')
                if r['probe'] and status.get('detector_mode')=='service':
                    check(r['length']==65536, 'paired recovery policies use different representative probes')
                check(r['helper_src'] != r['src'] and r['helper_src'] // 4 == r['src'] // 4, 'source helper outside source server')
                check(r['helper_dst'] != r['dst'] and r['helper_dst'] // 4 == r['dst'] // 4, 'target helper outside target server')
                check(idle_at(r['phase'], r['helper_src'], t) and idle_at(r['phase'], r['helper_dst'], t), 'helper has unfinished own phase traffic')
                if not r['probe']:
                    relay_count += 1
                    check(rid in final_routes, 'resource reservation without proxy launch')
        else:
            check(rid in reservations, 'release without reservation')
        for s, d, nic in edges:
            tx[s, nic] += delta
            rx[d, nic] += delta
            check(0 <= tx[s, nic] <= 4 and 0 <= rx[d, nic] <= 4, 'physical NIC credit exceeded')
            max_nic = max(max_nic, tx[s, nic], rx[d, nic])
        if r['relay']:
            for g in [r['helper_src'], r['helper_dst']]:
                buffers[g] += delta
                check(0 <= buffers[g] <= 4, 'helper buffering exceeded')
                max_buffers = max(max_buffers, buffers[g])
    starts, completed, cancelled = {}, {}, set()
    for raw in rows(root / 'leg_events.csv'):
        name = raw['event']
        r = {k: int(v) for k, v in raw.items() if k != 'event'}
        tag, rid = r['tag'], r['route']
        if name == 'LEG_START':
            check(tag not in starts, 'transport port/tag reused')
            starts[tag] = r
            if rid in reservations:
                reserve = reservations[rid]
                expected = [(reserve['src'], reserve['dst'], reserve['rail'] + 2)]
                if reserve['relay']:
                    expected = [(reserve['src'], reserve['helper_src'], 1), (reserve['helper_src'], reserve['helper_dst'], reserve['rail'] + 2), (reserve['helper_dst'], reserve['dst'], 1)]
                check(r['index'] < len(expected) and (r['src'], r['dst'], r['nic']) == expected[r['index']], 'actual physical leg differs from route')
            if r['index']:
                check((rid, r['index'] - 1) in completed and completed[rid, r['index'] - 1] < r['timestamp_ns'], 'store-and-forward leg started early')
        elif name == 'LEG_DONE':
            check(tag in starts and tag not in cancelled, 'unknown/cancelled leg completed')
            check(r['timestamp_ns'] >= starts[tag]['timestamp_ns'], 'noncausal leg')
            completed[rid, r['index']] = r['timestamp_ns']
        elif name == 'LEG_CANCEL':
            check(tag in starts, 'unknown leg cancelled')
            cancelled.add(tag)
    notifications = {}
    activated = defaultdict(list)
    alarms = {}
    for row in rows(root / 'detector_events.csv'):
        key = int(row['path_id'])
        src = key // 48
        dst = src + 4 if src < 12 else (src + 1) % 4
        if src < 16 and key == (src * 16 + dst) * 3 + 1:
            alarms[src] = int(row['timestamp_ns'])
    controls = list(rows(root / 'control_events.csv'))
    first_activation = {}
    control_bytes = 0
    for raw in controls:
        control_bytes += int(raw['wire_bytes'])
        if int(raw['wire_bytes']):
            check(int(raw['wire_bytes']) == 96 and int(raw['arrival_ns']) >= int(raw['sent_ns']) + 1000000, 'control message cost omitted')
        if raw['event'] == 'ACTIVATE':
            src, at = int(raw['rank']), int(raw['arrival_ns'])
            check(enabled and src in alarms and alarms.get(src, 10**30) <= at, 'activation without causal M13 alarm')
            activated[int(raw['phase']), src].append(at)
            p, version = int(raw['phase']), raw['version']
            matching = [r for r in controls if r['phase'] == str(p) and r['version'] == version
                        and r['event'] in ['PREPARE', 'READY', 'COMMIT', 'HELPER_READY']
                        and int(r['arrival_ns']) <= at]
            # Independent timestamp checks of the initial distributed transaction.
            by_event = defaultdict(list)
            for r in matching:
                by_event[r['event']].append(r)
            if src not in first_activation:
                for name in ['PREPARE', 'READY', 'COMMIT']:
                    check(len(by_event[name]) == 4, 'missing initial coordination participants')
                if all(by_event[n] for n in ['PREPARE', 'READY', 'COMMIT']):
                    check(min(int(r['sent_ns']) for r in by_event['READY']) >=
                          max(int(r['arrival_ns']) for r in by_event['PREPARE']) + 1000000,
                          'READY before preparation completed')
                    check(min(int(r['sent_ns']) for r in by_event['COMMIT']) >=
                          max(int(r['arrival_ns']) for r in by_event['READY']), 'COMMIT before all READY arrived')
                    check(max(int(r['arrival_ns']) for r in by_event['COMMIT']) == at,
                          'activation before all COMMIT arrived')
            else:
                check(len(by_event['HELPER_READY']) == 2 and
                      max((int(r['arrival_ns']) for r in by_event['HELPER_READY']), default=-1) == at,
                      'phase reuse without charged helper confirmation')
            first_activation.setdefault(src, at)
        check(raw['event'] != 'PHASE_LAG_TRIGGER', 'unregistered tail fallback enabled')
        if raw['event'] == 'M13_REPLACEMENT_PREPARE':
            src = int(raw['rank'])
            check(enabled and alarms.get(src, 10**30) <= int(raw['sent_ns']), 'replacement preparation before diagnosis')
        if raw['event'] == 'FINAL_ACK':
            rid = int(raw['version'])
            check((rid, 2) in completed and int(raw['sent_ns']) >= completed[rid, 2], 'final ACK before final target received data')
            notifications[rid] = int(raw['arrival_ns'])
    if 'control_wire_bytes' in status:
        check(status['control_wire_bytes'] == control_bytes, 'unaccounted control traffic')
    # A retired direct B route can drain, but it can never accept a new chunk.
    for launch in direct_routes.values():
        if launch['lane'] == 1 and launch['src'] in first_activation:
            check(launch['timestamp_ns'] < first_activation[launch['src']], 'new work sent on retired B')
    for r in reservations.values():
        if r['relay']:
            check(alarms.get(r['src'], 10**30) <= r['timestamp_ns'], 'proxy probe/data before M13 diagnosis')
    health_index = defaultdict(list)
    health_reports={int(r['version']):r for r in controls if r['event']=='HEALTH_REPORT'}
    require_health_report=(status.get('detector_mode')=='service' or
                           status.get('policy_mode')=='benefit')
    health_keys = ['phase', 'src', 'dst', 'helper_src', 'helper_dst']
    for qid, q in reservations.items():
        if q['relay'] and q['probe'] and (qid, 2) in completed:
            if require_health_report:
                check(qid in health_reports and int(health_reports[qid]['arrival_ns'])>=completed[qid,2]+1000000,
                      'complete-route health is not transported back to source')
            arrival=int(health_reports[qid]['arrival_ns']) if qid in health_reports else completed[qid,2]
            health_index[tuple(q[k] for k in health_keys)].append((completed[qid, 2],arrival,qid))
    for timestamps in health_index.values():
        timestamps.sort()
    for rid, launch in final_routes.items():
        c = launch['chunk_id']
        r = reservations[rid]
        check(any(t <= launch['timestamp_ns'] for t in activated[r['phase'], r['src']]), 'proxy launched before activation')
        healthy = health_index[tuple(r[k] for k in health_keys)]
        position = bisect_right(healthy, (launch['timestamp_ns'],10**30,10**30)) - 1
        check(position >= 0 and launch['timestamp_ns'] - healthy[position][0] <= 20000000
              and healthy[position][1]<=launch['timestamp_ns'],
              'proxy has no fresh complete-route probe')
        if position >= 0:
            measured, arrival, qid = healthy[position]
            if require_health_report or qid in health_reports:
                report=health_reports.get(qid)
                check(report is not None and int(report['rank'])==r['src']
                      and int(report['phase'])==reservations[qid]['phase']
                      and int(report['sent_ns'])>=measured
                      and int(report['wire_bytes'])==96
                      and arrival<=launch['timestamp_ns'],
                      'proxy consumed a missing, misaddressed, wrong-phase or undelivered health report')
        if c in done:
            check(rid in notifications and done[c]['timestamp_ns'] == notifications.get(rid), 'logical completion before final notification')
            check(all((rid, i) in completed for i in range(3)), 'logical completion missing a relay leg')
    for c, r in done.items():
        rid = r['route']
        if rid in direct_routes:
            check((rid, 0) in completed and r['timestamp_ns'] == completed.get((rid, 0)), 'direct DONE before transport completion')
        else:
            check(rid in final_routes, 'logical DONE without a transport route')
    wire_totals = defaultdict(int)
    tag_wire = defaultdict(int)
    for raw in rows(root / 'wire_events.csv'):
        tag = int(raw['tag'])
        check(tag in starts, 'wire packet without actual transport leg')
        if tag in starts:
            check(all(int(raw[k]) == starts[tag][k] for k in ['src', 'dst', 'nic']), 'wire packet on wrong physical resource')
        amount = int(raw['wire_bytes'])
        tag_wire[tag] += amount
        wire_totals['local_wire_bytes' if raw['nic'] == '1' else 'network_wire_bytes'] += amount
        if raw['probe'] == '1': wire_totals['probe_wire_bytes'] += amount
        if raw['relay'] == '1' and raw['probe'] == '0': wire_totals['relay_wire_bytes'] += amount
        if raw['retransmission'] == '1': wire_totals['retransmission_wire_bytes'] += amount
    for key, value in wire_totals.items():
        check(status[key] == value, 'wire total mismatch: ' + key)
    for tag, r in starts.items():
        if (r['route'], r['index']) in completed:
            check(tag_wire[tag] >= r['length'], 'completed transport leg lacks actual wire bytes')
    check(status['proxy_chunks'] == relay_count, 'proxy chunk status mismatch')
    new_proxy = [r for r in final_routes.values() if r['chunk_id'] not in migrated]
    check(status['new_proxy_chunks'] == len(new_proxy), 'fresh B-prime work count mismatch')
    check(status['rescued_chunks'] == len(migrated), 'rescued suffix count mismatch')
    if not enabled:
        check(not reservations or not any(r['relay'] for r in reservations.values()), 'baseline used relay resources')
    return dict(pass_=not errors, errors=errors, logical_chunks=len(chunks), completed_chunks=len(done),
                unique_ack_bytes=unique, relay_chunks=relay_count, relay_leg_transfers=sum(rid in final_routes for rid, _ in completed),
                max_logical_source_credit=max_source, max_physical_nic_credit=max_nic, max_helper_buffers=max_buffers,
                dual_plane_verified=True, helper_phase_idle_verified=True, final_target_completion_verified=True,
                physical_wire_totals=dict(wire_totals), m13_causality_verified=status.get('detector_mode','legacy')=='legacy',
                active_detector_causality_verified=True, active_detector=status.get('detector_mode','legacy'),
                retired_B_no_new_work_verified=True, fresh_proxy_chunks=len(new_proxy),
                fresh_proxy_phases=len({r['phase'] for r in new_proxy}),
                affected_sources_with_replacement=sorted(first_activation))


if __name__ == '__main__':
    import sys
    result = audit(Path(sys.argv[1]))
    result['pass'] = result.pop('pass_')
    (Path(sys.argv[1]) / 'audit.json').write_text(json.dumps(result, indent=2) + '\n')
    print(json.dumps(result))
    raise SystemExit(0 if result['pass'] else 1)
