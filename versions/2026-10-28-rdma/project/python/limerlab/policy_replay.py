"""Independent replay of observable benefit decisions, without fault inputs.

Cross-file logs lack a total ordering for equal timestamps. For logical events
we accept a matching causal prefix at that timestamp, rather than applying a
subsequent MIGRATE/ACK before its decision. FIFO enqueue prefixes are handled
the same way. Other execution audits check transaction and helper correctness.
"""
import csv
from collections import defaultdict, deque
import itertools
import json
import math
from pathlib import Path

from .benefit_policy import BenefitInput, RelaySample, ServiceSample, evaluate_benefit


def _rows(path):
    with path.open() as stream:
        yield from csv.DictReader(stream)


def _close(a, b):
    if a is None or b is None:
        return (a is None and (b is None or math.isinf(b))) or (b is None and math.isinf(a))
    return math.isclose(float(a), float(b), rel_tol=1e-10, abs_tol=1e-6)


def replay_policy(root):
    root = Path(root)
    errors = []
    def check(ok, message):
        if not ok and len(errors) < 100:
            errors.append(message)
    required = ('policy_decisions.jsonl', 'logical_events.csv', 'peer_events.csv',
                'leg_events.csv', 'control_events.csv', 'run_status.json')
    missing = [name for name in required if not (root/name).exists()]
    if missing:
        return {'pass': False, 'errors': ['missing policy evidence: '+', '.join(missing)],
                'decisions_checked': 0, 'truth_accessed': False}
    try:
        status = json.loads((root/'run_status.json').read_text())
        decisions = [json.loads(line) for line in (root/'policy_decisions.jsonl').read_text().splitlines() if line.strip()]
        check(all(int(a['timestamp_ns']) <= int(b['timestamp_ns']) for a, b in zip(decisions, decisions[1:])),
              'policy decisions are not time ordered')
        chunks_per_phase = int(status['chunks_per_phase'])
        chunk_bytes = 65536
        total = chunks_per_phase*chunk_bytes
        adaptive = status['method'] in ('G10', 'G11')

        # Only route/resource/ACK evidence is read. No manifest scene,
        # injection file, fault trace, or future recovery time is consulted.
        probe_routes = {}
        for r in _rows(root/'peer_events.csv'):
            if r['event'] == 'RESERVE' and int(r['relay']) and int(r['probe']):
                probe_routes[int(r['route'])] = r
        starts, completed = {}, defaultdict(dict)
        for r in _rows(root/'leg_events.csv'):
            route, index = int(r['route']), int(r['index'])
            if route not in probe_routes:
                continue
            if r['event'] == 'LEG_START':
                starts[route, index] = r
            elif r['event'] == 'LEG_DONE':
                start = starts.get((route, index))
                check(start is not None, 'health-probe leg completion lacks start')
                if start:
                    completed[route][index] = (int(r['timestamp_ns'])-int(start['timestamp_ns']), int(r['length']), int(r['timestamp_ns']))
        probes = {}
        for route, legs in completed.items():
            if set(legs) != {0, 1, 2}:
                continue
            r = probe_routes[route]
            probes[int(r['src']), int(r['phase']), legs[2][2]] = (r, legs)

        controls = list(_rows(root/'control_events.csv'))
        health_reports = defaultdict(list)
        for r in controls:
            if r['event'] == 'HEALTH_REPORT':
                health_reports[int(r['version'])].append(r)
        require_health_report = status.get('detector_mode') == 'service' or bool(health_reports)
        fifo_before = {}
        free = 0
        # Store prefix boundaries at enqueue timestamps; actual propagation
        # arrivals independently validate the physical control FIFO cost.
        for r in controls:
            if not int(r['wire_bytes']):
                continue
            sent = int(r['sent_ns'])
            fifo_before.setdefault(sent, [free]).append(
                max(sent, free)+(int(r['wire_bytes'])*8000000000+100000000-1)//100000000)
            free = fifo_before[sent][-1]
            check(int(r['arrival_ns']) == free+1_000_000,
                  'control FIFO serialization/propagation differs')
        fifo_times = sorted(fifo_before)

        # Physical canary completion timestamps provide the fallback service
        # estimate when a lane has no owned work and no recent direct ACKs.
        canary_complete = []
        if (root/'service_events.csv').exists():
            submitted = {}
            for r in _rows(root/'service_events.csv'):
                token, t = int(r['token']), int(r['timestamp_ns'])
                if r['event'] == 'SUBMIT':
                    submitted[token] = (t, int(r['bytes']))
                elif r['event'] == 'COMPLETE':
                    begin = submitted.pop(token, None)
                    if begin:
                        canary_complete.append((t, int(r['path_id']), t-begin[0], begin[1]))
        canary_complete.sort()
        canaries = {}
        ci = 0
        outstanding = defaultdict(int)
        offered = defaultdict(int)
        chunks = {}
        samples = defaultdict(deque)

        def apply(r):
            t, ident = int(r['timestamp_ns']), int(r['chunk_id'])
            source, phase, lane = int(r['src']), int(r['phase']), int(r['lane'])
            key = source, phase, lane
            event, ack = r['event'], int(r['acked'])
            if event == 'ALLOC':
                length = int(r['length'])
                check(ident not in chunks, 'duplicate allocation in policy evidence')
                chunks[ident] = (ack, key, length)
                outstanding[key] += length-ack
                offered[key] += length
            elif event == 'ACK_PROGRESS':
                previous = chunks.get(ident)
                check(previous is not None, 'ACK without logical allocation')
                if previous:
                    delta = ack-previous[0]
                    check(delta >= 0, 'logical ACK regressed')
                    outstanding[key] -= delta
                    chunks[ident] = (ack, key, previous[2])
                    if int(r['epoch']) == 0 and delta > 0:
                        samples[source, lane].append((t, delta))
            elif event == 'DONE':
                previous = chunks.pop(ident, None)
                if previous:
                    outstanding[key] -= previous[2]-previous[0]

        def snapshot(source, phase, t):
            owned = [outstanding[source, phase, lane] for lane in (0, 1)]
            offer = [offered[source, phase, lane] for lane in (0, 1)]
            if adaptive:
                pending = total-sum(offer)
            else:
                pending = 0
                owned = [owned[lane]+total//2-offer[lane] for lane in (0, 1)]
            rates = []
            for lane in (0, 1):
                q = samples[source, lane]
                while q and q[0][0]+10_000_000 < t:
                    q.popleft()
                amount = sum(value for _, value in q)
                rate = amount/10_000_000.
                if not amount and not owned[lane]:
                    dest = source+4 if source < 12 else (source+1)%4
                    canary = canaries.get((source*16+dest)*3+lane)
                    if canary and canary[0]+20_000_000 >= t:
                        rate = min(1.25, canary[2]/max(1, canary[1]))
                rates.append(rate)
            return owned, pending, rates

        logical = iter(_rows(root/'logical_events.csv'))
        following = next(logical, None)
        fifo_index, fifo_free = 0, 0
        for t, group in itertools.groupby(decisions, key=lambda d: int(d['timestamp_ns'])):
            group = list(group)
            while ci < len(canary_complete) and canary_complete[ci][0] <= t:
                ct, path, duration, size = canary_complete[ci]
                canaries[path] = (ct, duration, size)
                ci += 1
            while following is not None and int(following['timestamp_ns']) < t:
                apply(following)
                following = next(logical, None)
            possible = [[] for _ in group]
            for i, decision in enumerate(group):
                possible[i].append(snapshot(int(decision['src']), int(decision['phase']), t))
            while following is not None and int(following['timestamp_ns']) == t:
                apply(following)
                for i, decision in enumerate(group):
                    possible[i].append(snapshot(int(decision['src']), int(decision['phase']), t))
                following = next(logical, None)
            while fifo_index < len(fifo_times) and fifo_times[fifo_index] < t:
                fifo_free = fifo_before[fifo_times[fifo_index]][-1]
                fifo_index += 1
            queue_options = [max(0, value-t) for value in fifo_before.get(t, [fifo_free])]

            for i, decision in enumerate(group):
                label = 'policy src={} phase={} t={}: '.format(decision['src'], decision['phase'], t)
                raw = dict(decision['input'])
                a, b, relay = raw.pop('service_a'), raw.pop('service_b'), raw.pop('relay')
                for obj in (a, b, relay):
                    obj['known'] = bool(obj['known'])
                raw['helper_ready'] = bool(raw['helper_ready'])
                x = BenefitInput(service_a=ServiceSample(**a), service_b=ServiceSample(**b),
                                 relay=RelaySample(**relay), **raw)
                predicted = evaluate_benefit(x)
                for name in ('should_switch', 'reason', 'stay_ns', 'switch_ns', 'gain_ns'):
                    equal = (decision[name] == predicted[name] if name in ('should_switch', 'reason')
                             else _close(decision[name], predicted[name]))
                    check(equal, label+'native/Python policy differs: '+name)
                check(decision['stage'] in ('probe_complete', 'commit'), label+'unknown policy stage')
                matches = [s for s in possible[i] if s[0] == [x.a_bytes, x.b_bytes] and s[1] == x.pending_bytes
                           and all(_close(s[2][lane], (x.service_a, x.service_b)[lane].bytes_per_ns) for lane in (0, 1))]
                check(bool(matches), label+'remaining bytes/direct ACK service differ from logical causal prefixes')
                check(x.service_a.age_ns == x.service_b.age_ns == 0
                      and x.service_a.known == x.service_b.known == (t >= 20_000_000),
                      label+'direct service known/age metadata differs')
                health = t-x.relay.age_ns
                evidence = probes.get((int(decision['src']), int(decision['phase']), health))
                check(evidence is not None, label+'candidate lacks completed three-leg physical probe')
                if evidence:
                    reservation, legs = evidence
                    check(x.relay.known and x.relay.sample_bytes == int(reservation['length'])
                          and all(legs[j][1] == x.relay.sample_bytes for j in range(3)),
                          label+'candidate probe byte count differs')
                    check(all(_close(x.relay.leg_ns[j], legs[j][0]) for j in range(3)),
                          label+'candidate probe leg duration differs')
                    if require_health_report:
                        route = int(reservation['route'])
                        reports = health_reports.get(route, [])
                        check(any(int(r['rank']) == int(decision['src'])
                                  and int(r['phase']) == int(decision['phase'])
                                  and int(r['sent_ns']) >= health
                                  and int(r['arrival_ns']) <= t
                                  and int(r['wire_bytes']) == 96 for r in reports),
                              label+'candidate probe lacks delivered charged HEALTH_REPORT')
                check(x.relay.parallel_chunks == 4, label+'relay credit count differs')
                waiting = x.relay.final_ack_ns-1_007_680
                check(any(_close(waiting, value) for value in queue_options),
                      label+'final ACK estimate omits actual control queue or serialization')
                setup = 0 if decision['stage'] == 'commit' else waiting+4_092_160
                check(_close(x.setup_ns, setup), label+'coordination setup estimate differs')

        activated = set()
        for r in controls:
            if r['event'] != 'ACTIVATE':
                continue
            source, phase, at = int(r['rank']), int(r['phase']), int(r['sent_ns'])
            if source in activated:
                continue
            activated.add(source)
            commits = [d for d in decisions if int(d['src']) == source and int(d['phase']) == phase
                       and d['stage'] == 'commit' and int(d['timestamp_ns']) <= at]
            check(bool(commits) and bool(commits[-1]['should_switch']),
                  'first ACTIVATE lacks approved benefit commit: src={} phase={}'.format(source, phase))
        return {'pass': not errors, 'errors': errors, 'decisions_checked': len(decisions),
                'initial_activations_checked': len(activated), 'truth_accessed': False,
                'same_timestamp_order': 'matching causal prefix; logs have no cross-file sequence',
                'checks': ['pure policy', 'logical remaining bytes', 'direct ACK service',
                           'physical candidate probes', 'charged delivered health reports' if require_health_report else 'legacy health-report compatibility',
                           'control FIFO/current cost estimate', 'initial commit authorization']}
    except (OSError, ValueError, KeyError, TypeError, OverflowError) as exc:
        errors.append('invalid policy evidence: '+str(exc))
        return {'pass': False, 'errors': errors[:100], 'decisions_checked': 0, 'truth_accessed': False}
