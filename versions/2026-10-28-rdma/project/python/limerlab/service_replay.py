"""Replay endpoint service observations and verify their physical/logged causes."""
import csv
import json
from .detector.service_detector import ServiceDetector


def rows(path):
    with path.open() as f:
        return list(csv.DictReader(f))


def _spacing_from_packets(root, horizon, packet_starts, valid_paths, check):
    """Reconstruct fixed-window endpoint spacing from accepted payloads.

    Only first accepted source identities are retained until their receiver
    acceptance. This keeps normal successful traffic from accumulating a
    full-run packet dictionary. Lost/cancelled packets remain as evidence.
    """
    summaries = {}
    window_end = 21_000_000
    gaps = {path: [] for path in valid_paths}
    previous = {}
    identities = {}
    accepted_packets = source_packets = 0
    previous_time = -1

    def flush():
        nonlocal window_end
        for path in valid_paths:
            samples = gaps[path]
            size = len(samples)
            # Nearest-rank P10: ceil(.1*n)-1, with the empty summary fixed 0.
            p10 = sorted(samples)[(size+9)//10-1] if size else 0
            summaries[path, window_end] = (p10, size)
            samples.clear()
        window_end += 10_000_000

    path = root/'packet_events.csv'
    if not path.exists():
        check(False, 'missing raw packet evidence for spacing summaries')
        return summaries, source_packets, accepted_packets
    with path.open() as stream:
        reader = csv.DictReader(stream)
        check('payload_bytes' in (reader.fieldnames or []), 'raw packet payload_bytes column missing')
        if 'payload_bytes' not in (reader.fieldnames or []):
            return summaries, source_packets, accepted_packets
        for r in reader:
            t = int(r['timestamp_ns'])
            check(t >= previous_time, 'raw packet events are not time ordered')
            previous_time = t
            while window_end <= t and window_end < horizon:
                flush()
            event = r['event']
            if event not in ('source_accept', 'network_rx'):
                continue
            path_id, payload = int(r['path_id']), int(r['payload_bytes'])
            identity = (path_id, int(r['probe']), int(r['batch']), int(r['sequence']))
            if event == 'source_accept':
                source_packets += 1
                leg = packet_starts.get(int(r['attempt_or_port']))
                offset = int(r['offset'])
                check(leg is not None, 'source packet lacks physical leg/tag')
                if leg:
                    length, physical_path = leg
                    check(0 <= offset < length and payload == min(976, length-offset),
                          'source payload differs from physical leg length/offset')
                    check(path_id == physical_path, 'source payload takes different physical path')
                check(identity not in identities, 'duplicate active source packet identity')
                identities[identity] = payload
            elif r['accepted'] == '1':
                accepted_packets += 1
                submitted = identities.pop(identity, None)
                check(submitted is not None and payload == submitted,
                      'accepted RX payload differs from source acceptance')
                if path_id not in valid_paths:
                    continue
                old = previous.get(path_id)
                if old and old[1] and payload == 976 and t > old[0]:
                    gaps[path_id].append(t-old[0])
                previous[path_id] = (t, payload == 976)
    while window_end < horizon:
        flush()
    return summaries, source_packets, accepted_packets


def replay_service(root):
    errors = []
    def check(ok, message):
        if not ok and len(errors) < 100:
            errors.append(message)
    manifest = json.loads((root / 'run_manifest.json').read_text())
    scene = manifest['scene']
    status = json.loads((root / 'run_status.json').read_text())
    detector = ServiceDetector()
    starts, done, packet_starts = {}, {}, {}
    for r in rows(root / 'leg_events.csv'):
        route = int(r['route'])
        if r['event'] == 'LEG_START':
            nic = int(r['nic'])
            physical_path = (int(r['src'])*16+int(r['dst']))*3+(2 if nic == 1 else nic-2)
            packet_starts[int(r['tag'])] = (int(r['length']), physical_path)
        if r['event'] == 'LEG_START' and r['index'] == '0': starts[route] = r
        elif r['event'] == 'LEG_DONE' and r['index'] == '0': done[route] = r
    valid_paths={(s*16+(s+4 if s<12 else (s+1)%4))*3+r for s in range(16) for r in (0,1)}
    spacing_enabled = hasattr(detector, 'spacing')
    spacing_summaries, source_packets, accepted_packets = ({}, 0, 0)
    if spacing_enabled:
        spacing_summaries, source_packets, accepted_packets = _spacing_from_packets(
            root, scene['horizon_ns'], packet_starts, valid_paths, check)
    spacing_records = set()
    retransmissions = set()
    with (root/'wire_events.csv').open() as stream:
        for r in csv.DictReader(stream):
            if r['retransmission'] == '1':
                retransmissions.add((int(r['timestamp_ns']),int(r['route']),int(r['wire_bytes'])))
    submitted, complete, recorded_retransmissions = {}, set(), set()
    schedule=set()
    logical_stream=(root/'logical_events.csv').open()
    logical=iter(csv.DictReader(logical_stream))
    next_logical=next(logical,None)
    active={}
    for r in rows(root / 'service_events.csv'):
        t, path, token, size = [int(r[k]) for k in ('timestamp_ns', 'path_id', 'token', 'bytes')]
        while next_logical is not None and int(next_logical['timestamp_ns'])<=t:
            q=next_logical;ident=int(q['chunk_id']);qt=int(q['timestamp_ns'])
            if q['event']=='ALLOC':active[ident]=dict(path=(int(q['src'])*16+int(q['dst']))*3+int(q['lane']),progress=qt,remaining=int(q['length']),epoch=0)
            elif ident in active:
                if q['event']=='ACK_PROGRESS':active[ident].update(progress=qt,remaining=int(q['length'])-int(q['acked']))
                elif q['event']=='MIGRATE':active[ident]['epoch']=int(q['epoch'])
                elif q['event']=='DONE':del active[ident]
            next_logical=next(logical,None)
        if r['event'] == 'ADVANCE': detector.advance(t)
        elif r['event'] == 'SPACING':
            key=(path,token)
            check(key not in spacing_records, 'duplicate spacing window summary')
            spacing_records.add(key)
            p10, count = int(r['spacing_ns']), int(r['sample_count'])
            check(path in valid_paths and t == token and size == 0
                  and int(r.get('last_progress_ns') or 0) == 0,
                  'spacing summary path/window metadata changed')
            check(spacing_summaries.get(key) == (p10,count),
                  'spacing P10/count differs from raw accepted full-payload RX gaps')
            check(spacing_enabled, 'spacing summary unsupported by frozen detector')
            if spacing_enabled:
                try:
                    detector.spacing(path,token,p10,count)
                except ValueError as exc:
                    check(False,'invalid spacing detector input: '+str(exc))
        elif r['event'] == 'SUBMIT':
            check(token not in submitted, 'duplicate canary route')
            submitted[token] = r
            leg = starts.get(token, {})
            check(bool(leg) and int(leg['timestamp_ns']) == t and int(leg['length']) == size,
                  'canary submission lacks physical QP start')
            if leg:
                actual_path = (int(leg['src'])*16+int(leg['dst']))*3+int(leg['nic'])-2
                check(actual_path == path, 'canary takes a different physical path')
            check(size == scene.get('canary_bytes', 65536), 'registered canary size changed')
            period = scene.get('canary_period_ns', 2000000)
            check(t >= 1000000 and (t-1000000) % period == 0, 'canary schedule changed')
            check((path,t) not in schedule, 'duplicate canary on the same path/tick')
            schedule.add((path,t))
            detector.submit(path, token, t, size)
        elif r['event'] == 'STALL':
            progress=int(r['last_progress_ns']);observed=active.get(token,{})
            check(observed==dict(path=path,progress=progress,remaining=size,epoch=0),
                  'business stall differs from actual unacknowledged progress')
            detector.stall(path,token,t,progress,size)
        elif r['event'] == 'RETRANSMIT':
            check((t,token,size) in retransmissions, 'service retransmission lacks repeated wire attempt')
            recorded_retransmissions.add((t,token,size))
            detector.retransmit(path,token,t)
        elif r['event'] == 'COMPLETE':
            check(token in submitted and token not in complete, 'unknown/duplicate canary completion')
            complete.add(token)
            leg = done.get(token, {})
            check(bool(leg) and int(leg['timestamp_ns']) == t, 'canary completion lacks physical ACK completion')
            detector.complete(path, token, t)
        else: check(False, 'unknown service observation event')
    logical_stream.close()
    period = scene.get('canary_period_ns', 2000000)
    expected = 32 * ((scene['horizon_ns']-1000001)//period+1)
    check(len(submitted) == expected, 'missing scheduled canary submissions')
    check({path for path,t in schedule} == valid_paths, 'canary path inventory changed')
    if spacing_enabled:
        check(spacing_records == set(spacing_summaries), 'missing/extra scheduled spacing summaries')
    check(recorded_retransmissions == {r for r in retransmissions if r[1] in submitted},
          'canary retransmission observation missing from actual wire evidence')
    check(status.get('monitor_end_ns', 0) >= scene['horizon_ns'], 'monitoring ended early')
    native = [json.loads(line) for line in (root/'service_decisions.jsonl').read_text().splitlines()]
    predicted = detector.alarms
    check(len(native) == len(predicted), 'native/Python service alarm count differs')
    for actual, wanted in zip(native, predicted):
        check(actual.get('rule_version') == detector.RULE_VERSION, 'native service rule version changed')
        for name in ('path', 'decision_t_ns', 'baseline_ns', 'deadline_ns','signal'):
            check(actual[name] == wanted[name], 'native/Python service evidence differs: '+name)
        check(actual['tokens'] == wanted['evidence_tokens'], 'service evidence tokens differ')
    controls = rows(root/'control_events.csv')
    free = 0
    for r in controls:
        if not int(r['wire_bytes']): continue
        free = max(free, int(r['sent_ns'])) + (int(r['wire_bytes'])*8000000000+100000000-1)//100000000
        check(int(r['arrival_ns']) == free+1000000, 'control FIFO serialization/propagation differs')
    messages = [r for r in controls if r['event'] == 'SERVICE_ALARM']
    check([(int(r['rank']),int(r['sent_ns'])) for r in messages] ==
          [(r['path'],r['decision_t_ns']) for r in predicted], 'service report sent without matching endpoint decision')
    actual = rows(root/'service_alarms.csv')
    delivered = [(int(r['path_id']), int(r['timestamp_ns']),r['signal']) for r in actual]
    expected_reports = [(int(r['rank']),int(r['arrival_ns']),a['signal']) for r,a in zip(messages,predicted)]
    # Reports still in flight at horizon have not reached the controller.
    expected_reports = [r for r in expected_reports if r[1] < scene['horizon_ns']]
    check(delivered == expected_reports, 'controller service alarms omit report transport cost')
    recorded = [(int(r['path_id']),int(r['timestamp_ns']),r['signal']) for r in rows(root/'detector_events.csv')]
    check(recorded == delivered, 'active detector and reported service alarms differ')
    return dict(pass_=not errors, errors=errors, reports_reconstructed=len(submitted),
                alarms=delivered, source=detector.RULE_VERSION+'; physical payload gaps/QP/retransmissions/business ACK stalls and charged reports',
                truth_accessed=False, completed_canaries=len(complete),
                spacing_summaries_reconstructed=len(spacing_summaries),
                source_packets_checked=source_packets, accepted_packets_checked=accepted_packets,
                canary_payload_bytes=len(submitted)*scene.get('canary_bytes',65536))
