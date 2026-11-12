"""Audit M13 causality, persistent B-prime new work, physical routes and ACKs."""
from collections import defaultdict
from bisect import bisect_right
import csv
import json
from pathlib import Path


def rows(path):
    with path.open() as f:
        yield from csv.DictReader(f)


def audit_helper_reports(root):
    """Independently reconstruct paid helper observations from logical ACKs."""
    root = Path(root)
    errors = []
    def check(ok, message):
        if not ok and len(errors) < 100: errors.append(message)
    path = root / 'helper_reports.jsonl'
    if not path.exists():
        return dict(pass_=False, **{'pass':False}, errors=['missing paid helper reports file'], delivered=0)
    reports = [json.loads(line) for line in path.read_text().splitlines() if line.strip()]
    status = json.loads((root/'run_status.json').read_text())
    phase_bytes = status['chunks_per_phase'] * 65536
    controls = list(rows(root/'control_events.csv'))
    index = defaultdict(list)
    for row in controls:
        index[row['event'],int(row['phase']),int(row['version'])].append(row)
    # Accumulate increments, not repeated prefixes; migration never re-ACKs a byte.
    old, phase_progress, own_progress = {}, defaultdict(list), defaultdict(list)
    own_event_phases = defaultdict(list)
    phase_sum, own_sum = defaultdict(int), defaultdict(int)
    for row in rows(root/'logical_events.csv'):
        c, src, p, t = (int(row[k]) for k in ('chunk_id','src','phase','timestamp_ns'))
        if row['event'] == 'ALLOC': old[c] = 0
        elif row['event'] == 'ACK_PROGRESS':
            ack = int(row['acked']);delta = ack-old.get(c,0);old[c] = ack
            phase_sum[p,src] += delta;own_sum[src] += delta
            phase_progress[p,src].append((t,phase_sum[p,src]))
            own_progress[src].append((t,own_sum[src]))
            own_event_phases[src].append(p)
    def cumulative(values,t,inclusive=True):
        at = bisect_right(values,(t,10**30 if inclusive else -1))-1
        return values[at][1] if at >= 0 else 0
    sent, delivered = {}, {}
    for row in reports:
        ident = row['report_id'];src=row['source'];p=row['phase'];slot=row['slot']
        check(slot in (0,1),'helper snapshot slot invalid')
        if slot not in (0,1): continue
        kind = 'RX' if slot else 'TX'
        if row['event'] == 'SENT':
            check(ident not in sent,'duplicate helper snapshot ID')
            sent[ident] = row
            check(row['timestamp_ns']==row['sampled_ns'],'helper snapshot was not sampled at send')
            query = index['HELPER_QUERY_'+kind,p,ident]
            response = index['HELPER_REPORT_'+kind,p,ident]
            check(len(query)==len(response)==1,'helper snapshot missing paid query/report')
            if len(query)==len(response)==1:
                query,response = query[0],response[0]
                check(int(query['rank'])==row['rank'] and int(query['arrival_ns'])==row['sampled_ns']
                      and int(query['wire_bytes'])==96 and int(query['arrival_ns'])>=int(query['sent_ns'])+1000000,
                      'helper snapshot sampled before matching paid query')
                check(int(response['rank'])==src and int(response['sent_ns'])==row['sampled_ns']
                      and int(response['arrival_ns'])==row['delivered_ns'] and int(response['wire_bytes'])==96
                      and row['delivered_ns']>=row['sampled_ns']+1000000,
                      'helper snapshot report cost/address missing')
            lease = index['LEND_ACTIVE',p,row['lease_id']]
            participant = index['LEND_'+kind,p,row['lease_id']]
            check(len(lease)==1 and int(lease[0]['rank'])==src
                  and int(lease[0]['arrival_ns'])<=row['sampled_ns']
                  and len(participant)==1 and int(participant[0]['rank'])==row['rank'],
                  'helper snapshot has no matching active lease')
            # Files lack a global event sequence. A query can run before an ACK
            # at the exact same nanosecond. Require ONE shared causal prefix for
            # remaining bytes and service, never independently mix two prefixes.
            rank,t=row['rank'],row['sampled_ns'];progress=own_progress[rank]
            first=bisect_right(progress,(t,-1));last=bisect_right(progress,(t,10**30))
            current=cumulative(phase_progress[p,rank],t,False)
            total=progress[first-1][1] if first else 0
            before_window=cumulative(progress,t-10000000,False)
            candidates=[(phase_bytes-current,(total-before_window)/10000000.)]
            for i in range(first,last):
                delta=progress[i][1]-total;total=progress[i][1]
                if own_event_phases[rank][i]==p: current+=delta
                candidates.append((phase_bytes-current,(total-before_window)/10000000.))
            check(any(row['own_remaining_bytes']==amount for amount,_ in candidates),
                  'helper snapshot remaining bytes differ from local ACKs')
            check(any(abs(row['own_bytes_per_ns']-rate)<=1e-12 for _,rate in candidates),
                  'helper snapshot service differs from local ACK window')
            check(any(row['own_remaining_bytes']==amount and abs(row['own_bytes_per_ns']-rate)<=1e-12
                      for amount,rate in candidates),'helper snapshot mixes incompatible causal ACK prefixes')
            check(bool(row['known']),'delivered local helper observation marked unknown')
            prepare=index['M13_REPLACEMENT_PREPARE',p,row['version']]
            check(len(prepare)==1 and int(prepare[0]['rank'])==src
                  and int(prepare[0]['sent_ns'])<=row['sampled_ns'],
                  'helper snapshot has no matching prepared binding')
        elif row['event'] in ('DELIVERED','STALE'):
            check(ident in sent and ident not in delivered,'helper snapshot delivery has no unique send')
            if ident not in sent: continue
            reference = sent[ident]
            check(all(row.get(k)==v for k,v in reference.items() if k not in ('event','timestamp_ns')),
                  'helper snapshot changed in transit')
            check(row['timestamp_ns']==row['delivered_ns'],'helper snapshot delivered at wrong time')
            delivered[ident] = row
            if row['event']=='DELIVERED':
                check(not any(x['event']=='RESET_TO_AB' and int(x['phase'])>p
                              and int(x['arrival_ns'])<=row['delivered_ns'] for x in controls),
                      'stale helper snapshot delivered after phase reset')
                check(not any(x['event']=='LEND_RELEASED' and int(x['phase'])==p
                              and int(x['rank'])==src and int(x['version'])==row['lease_id']
                              and int(x['arrival_ns'])<=row['delivered_ns'] for x in controls),
                      'released lease snapshot consumed')
                check(not any(x['event']=='M13_REPLACEMENT_PREPARE' and int(x['phase'])==p
                              and int(x['rank'])==src and int(x['version'])!=row['version']
                              and row['sampled_ns']<int(x['sent_ns'])<=row['delivered_ns'] for x in controls),
                      'superseded helper binding snapshot consumed')
        else: check(False,'unknown helper snapshot event')
    for ident,row in sent.items():
        check(ident in delivered or row['delivered_ns']>=status.get('monitor_end_ns',status['horizon_ns']),
              'helper snapshot disappeared before monitor end')
    return dict(pass_=not errors, **{'pass':not errors},errors=errors,delivered=sum(r['event']=='DELIVERED' for r in delivered.values()),
                stale=sum(r['event']=='STALE' for r in delivered.values()))


def audit_explicit_lease_drains(controls, reservations, releases):
    """Only actual lease release events require physical reservations to drain.

    A phase boundary resets admission eligibility, but does not release physical
    route credits. Those survive until their separately logged RELEASE event.
    The main resource replay checks the same physical counters across phases.
    """
    errors = []
    participants = defaultdict(dict)
    for row in controls:
        if row['event'] in ('LEND_TX', 'LEND_RX'):
            participants[int(row['phase']), int(row['version'])][row['event']] = int(row['rank'])
    for row in controls:
        if row['event'] != 'LEND_RELEASED': continue
        p, src, lease, at = (int(row[k]) for k in ('phase','rank','version','arrival_ns'))
        endpoints = participants.get((p,lease), {})
        if set(endpoints) != {'LEND_TX','LEND_RX'}:
            # The main transaction audit reports missing/invalid participants.
            continue
        hs,hd=endpoints['LEND_TX'],endpoints['LEND_RX']
        if any(r['relay'] and r['phase']==p and r['src']==src
               and (r['helper_src'],r['helper_dst'])==(hs,hd)
               and r['timestamp_ns'] < at < releases.get(rid,10**30)
               for rid,r in reservations.items()):
            errors.append('lease release erased live relay ownership')
    return errors


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
    pipelined = status.get('relay_completion', 'final_ack') == 'pipelined'
    shared_helpers = status.get('helper_mode', 'idle') == 'shared'
    source_window = 32 if pipelined else 8
    if 'source_window' in status: check(status['source_window'] == source_window, 'unregistered source window')
    phase_chunks = status['chunks_per_phase']
    phase_bytes = phase_chunks * 65536
    manifest_path = root / 'run_manifest.json'
    if manifest_path.exists():
        manifest = json.loads(manifest_path.read_text())
        check(manifest['scene']['chunks_per_phase'] == phase_chunks, 'registered chunk geometry changed')
        for name in ('replacement_lifetime', 'phases_per_round', 'relay_completion', 'helper_mode'):
            if name in manifest['scene']:
                check(status.get(name) == manifest['scene'][name], 'registered '+name+' changed')
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
    phase_scoped = status.get('replacement_lifetime', 'persistent') == 'phase'
    expected_scope=('service-driven persistent B-prime replacement v2' if status.get('detector_mode')=='service'
                    else 'M13-driven persistent B-prime replacement v1')
    if phase_scoped: expected_scope = 'phase-scoped B-prime replacement v3'
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
            if status['method'] == 'A_ONLY': check(r['lane'] == 0, 'A-only control used B business')
            check(r['acked'] == 0, 'new chunk starts acknowledged')
            intervals[r['phase'], r['src']].append(r['offset'])
            allocations[c] = dict(r)
            active[r['src']] += 1
            max_source = max(max_source, active[r['src']])
            check(active[r['src']] <= source_window, 'logical source credit exceeded')
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

    controls = list(rows(root / 'control_events.csv'))
    lending, loan_times = defaultdict(list), defaultdict(list)
    lease_records = {}
    v2 = status.get('policy_mode') == 'benefit_v2'
    reset_times = sorted({(int(x['phase']), int(x['arrival_ns'])) for x in controls
                          if x['event'] == 'RESET_TO_AB'})
    for record in controls:
        if record['event'] != 'LEND_ACTIVE': continue
        p, source, lease = int(record['phase']), int(record['rank']), int(record['version'])
        key = p, source
        requests = [x for x in controls if x['phase'] == record['phase']
                    and x['version'] == record['version'] and x['event'] in ('LEND_TX','LEND_RX')]
        check(shared_helpers and len(requests) == 2, 'invalid lending transaction')
        if len(requests) != 2: continue
        by_kind = {x['event']:x for x in requests}
        check(set(by_kind) == {'LEND_TX','LEND_RX'}, 'missing lending participant')
        if set(by_kind) != {'LEND_TX','LEND_RX'}: continue
        at = int(record['arrival_ns'])
        check(int(record['sent_ns']) == at and at == max(int(x['arrival_ns']) for x in requests),
              'lending applied before requests arrived')
        hs, hd = int(by_kind['LEND_TX']['rank']), int(by_kind['LEND_RX']['rank'])
        check(v2 or not lending[key], 'duplicate phase lending')
        release = [x for x in controls if x['event'] == 'LEND_RELEASED'
                   and int(x['phase']) == p and int(x['rank']) == source
                   and int(x['version']) == lease]
        check(len(release) <= 1, 'duplicate lease release')
        stop = min((t for phase_id,t in reset_times if phase_id > p), default=10**30)
        if release:
            check(v2, 'legacy policy released helper lending')
            record_release = release[0]
            released = int(record_release['arrival_ns'])
            release_requests = [x for x in controls if x['event'] in ('RELEASE_TX','RELEASE_RX')
                                and int(x['phase']) == p and int(x['version']) == lease]
            check(len(release_requests) == 2, 'lease release missing charged requests')
            check(int(record_release['sent_ns']) == released and released >= at,
                  'noncausal lease release')
            if len(release_requests) == 2:
                actual = {(x['event'],int(x['rank'])) for x in release_requests}
                check(actual == {('RELEASE_TX',hs),('RELEASE_RX',hd)}, 'wrong release participants')
                check(all(at <= int(x['sent_ns']) <= int(x['arrival_ns']) <= released
                          for x in release_requests), 'lease released before requests arrived')
            check(released < stop, 'stale release applied after phase reset')
            stop = min(stop,released)
        item = (at,stop,hs,hd,lease)
        lending[key].append(item)
        lease_records[p,source,lease] = item
        loan_times[p,hs,'tx'].append((at,stop))
        loan_times[p,hd,'rx'].append((at,stop))
    # Leases cannot overlap even when a helper changes between TX and RX roles.
    helper_intervals = defaultdict(list)
    for (p,source),items in lending.items():
        for at,stop,hs,hd,lease in items:
            for helper in (hs,hd): helper_intervals[p,helper].append((at,stop,lease))
    for intervals_for_helper in helper_intervals.values():
        intervals_for_helper.sort()
        check(all(old[1] <= new[0] for old,new in zip(intervals_for_helper,intervals_for_helper[1:])),
              'overlapping helper leases')
    for record in controls:
        if record['event'] != 'LEND_RELEASED': continue
        check((int(record['phase']),int(record['rank']),int(record['version'])) in lease_records,
              'release does not identify an active lease')
    reservations, releases = {}, {}
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
                if shared_helpers:
                    loans = lending.get((r['phase'], r['src']),[])
                    check(any(a <= t < z and (hs,hd) == (r['helper_src'],r['helper_dst']) for a,z,hs,hd,_ in loans), 'relay lacks delivered matching lending authorization')
                else:
                    check(idle_at(r['phase'], r['helper_src'], t) and idle_at(r['phase'], r['helper_dst'], t), 'helper has unfinished own phase traffic')
                if not r['probe']:
                    relay_count += 1
                    check(rid in final_routes, 'resource reservation without proxy launch')
        else:
            check(rid in reservations and rid not in releases, 'release without reservation or double release')
            releases[rid] = t
        for s, d, nic in edges:
            if shared_helpers and not r['relay'] and nic == 3 and delta == 1:
                if any(a <= t < z for a,z in loan_times.get((r['phase'],s,'tx'),[])):
                    check(tx[s,nic] < 3, 'own traffic consumed lent TX credit')
                if any(a <= t < z for a,z in loan_times.get((r['phase'],d,'rx'),[])):
                    check(rx[d,nic] < 3, 'own traffic consumed lent RX credit')
            tx[s, nic] += delta
            rx[d, nic] += delta
            check(0 <= tx[s, nic] <= 4 and 0 <= rx[d, nic] <= 4, 'physical NIC credit exceeded')
            max_nic = max(max_nic, tx[s, nic], rx[d, nic])
        if r['relay']:
            for g in [r['helper_src'], r['helper_dst']]:
                buffers[g] += delta
                check(0 <= buffers[g] <= 4, 'helper buffering exceeded')
                max_buffers = max(max_buffers, buffers[g])
    starts, completed, cancelled, cancel_times = {}, {}, set(), {}
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
            cancel_times[tag] = r['timestamp_ns']
    aborted = {}
    for record in controls:
        if record['event'] != 'PROBE_ABORT': continue
        rid,t = int(record['version']),int(record['sent_ns'])
        check(v2 and rid in reservations and rid not in aborted,'invalid or duplicate probe abort')
        if rid not in reservations: continue
        probe = reservations[rid];aborted[rid]=t
        check(probe['relay']==1 and probe['probe']==1,'probe timeout targeted logical payload')
        check(int(record['rank'])==probe['src'] and int(record['phase'])==probe['phase'],
              'probe abort identity differs from owned reservation')
        check(t==int(record['arrival_ns'])==probe['timestamp_ns']+20000000,
              'candidate probe deadline changed')
        check(releases.get(rid)==t,'probe abort failed to release exact reservation')
        for tag,leg in starts.items():
            if leg['route']!=rid: continue
            check(leg['timestamp_ns']<t,'probe leg launched after its deadline')
            if (rid,leg['index']) not in completed:
                check(cancel_times.get(tag)==t,'probe abort left a transport leg active')
            else:
                check(completed[rid,leg['index']]<=t,'aborted probe reported later completion')
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
    first_phase_activation = {}
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
            activation_key = (p, src) if phase_scoped else src
            if activation_key not in first_phase_activation:
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
            first_phase_activation.setdefault(activation_key, at)
        check(raw['event'] != 'PHASE_LAG_TRIGGER', 'unregistered tail fallback enabled')
        if raw['event'] == 'M13_REPLACEMENT_PREPARE':
            src = int(raw['rank'])
            check(enabled and alarms.get(src, 10**30) <= int(raw['sent_ns']), 'replacement preparation before diagnosis')
        if raw['event'] == 'FINAL_ACK':
            rid = int(raw['version'])
            check((rid, 2) in completed and int(raw['sent_ns']) >= completed[rid, 2], 'final ACK before final target received data')
            notifications[rid] = int(raw['arrival_ns'])
    for (p,src), loans in lending.items():
        for at,stop,hs,hd,lease in loans:
            check(alarms.get(src,10**30) <= at, 'lending before diagnosis')
            check(any(r['event']=='LEND_TX' and r['rank']==str(hs) and r['phase']==str(p) and int(r['version'])==lease and int(r['sent_ns'])>=alarms.get(src,10**30) for r in controls), 'lending request before diagnosis')
    for error in audit_explicit_lease_drains(controls,reservations,releases): check(False,error)
    if v2:
        helper_result = audit_helper_reports(root)
        for error in helper_result['errors']: check(False,error)
        decisions_path = root / 'policy_decisions.jsonl'
        decisions = [json.loads(line) for line in decisions_path.read_text().splitlines()] if decisions_path.exists() else []
        for decision in decisions:
            if decision.get('should_switch') or not shared_helpers: continue
            p,src,at = decision['phase'],decision['src'],decision['timestamp_ns']
            matches = [x for x in lending.get((p,src),[]) if x[0] <= at < x[1]]
            for loan in matches:
                lease = loan[4]
                sent = [r for r in controls if r['event'] in ('RELEASE_TX','RELEASE_RX')
                        and int(r['phase'])==p and int(r['version'])==lease]
                check(len(sent)==2 and all(int(r['sent_ns'])==at for r in sent),
                      'rejected v2 gate retained helper lease without paid release')
                arrival = max((int(r['arrival_ns']) for r in sent),default=10**30)
                stop = loan[1]
                check(stop <= arrival or arrival >= status.get('monitor_end_ns',status['horizon_ns'])
                      or any(r['relay'] and r['src']==src and r['phase']==p and r['timestamp_ns']<=arrival
                             and releases.get(rid,10**30)>arrival for rid,r in reservations.items()),
                      'rejected helper lease leaked after delivered release')
    if 'control_wire_bytes' in status:
        check(status['control_wire_bytes'] == control_bytes, 'unaccounted control traffic')
    # A retired direct B route can drain, but it can never accept a new chunk.
    for launch in direct_routes.values():
        key = (launch['phase'], launch['src']) if phase_scoped else launch['src']
        if launch['lane'] == 1 and key in first_phase_activation:
            check(launch['timestamp_ns'] < first_phase_activation[key], 'new work sent on retired B')
    if phase_scoped:
        phase_starts = list(rows(root / 'phase_events.csv'))
        check([int(r['phase']) for r in phase_starts] == list(range(len(phase_starts))), 'phase sequence changed')
        resets = defaultdict(list)
        for r in controls:
            if r['event'] == 'RESET_TO_AB': resets[int(r['phase'])].append(r)
        for row in phase_starts:
            p, at = int(row['phase']), int(row['timestamp_ns'])
            group = resets[p]
            check(len(group) == 16 and {int(r['rank']) for r in group} == set(range(16)), 'missing phase binding reset')
            check(all(int(r['sent_ns']) == int(r['arrival_ns']) == at and int(r['wire_bytes']) == 0 for r in group), 'noncausal phase binding reset')
            if p:
                previous = [r for r in done.values() if r['phase'] == p-1]
                check(len(previous) == 16*phase_chunks and max((r['timestamp_ns'] for r in previous), default=at) < at, 'next phase started before previous completion')
    for r in reservations.values():
        if r['relay']:
            check(alarms.get(r['src'], 10**30) <= r['timestamp_ns'], 'proxy probe/data before M13 diagnosis')
    health_index = defaultdict(list)
    health_reports={int(r['version']):r for r in controls if r['event']=='HEALTH_REPORT'}
    require_health_report=(status.get('detector_mode')=='service' or
                           status.get('policy_mode') in ('benefit','benefit_v2'))
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
        if pipelined and (rid,2) in completed:
            check(releases.get(rid) == completed[rid,2], 'pipelined release differs from final target delivery')
        elif pipelined:
            check(rid not in releases, 'pipelined resource release before final target delivery')
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
                dual_plane_verified=True, helper_phase_idle_verified=not shared_helpers,
                helper_shared_capacity_verified=shared_helpers, pipelined_release_verified=pipelined,
                helper_snapshot_causality_verified=v2, helper_lease_release_verified=v2,
                final_target_completion_verified=True,
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
