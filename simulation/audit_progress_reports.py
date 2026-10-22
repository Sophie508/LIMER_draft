"""Independent delivery FIFO, ACK bounds and actual-online-decision auditing."""
import math

from limer_v0.ack_progress import AckProgressRule


def audit_progress(graph, trace, records, model):
    events = {(e['id'], e['event']): e for e in trace if 'id' in e}
    offers = {}
    delivered = set()
    final = {}
    channel_free = 0
    rule = AckProgressRule()
    replay = []
    actual = []
    duration = math.ceil(512*1_000_000_000/model['capacity_bps'])
    for record in records:
        kind = record['kind']
        if kind == 'offer':
            key = record['path'], record['sample_ns']
            if key in offers:
                raise ValueError('duplicate progress offer')
            start = max(record['sample_ns'], channel_free)
            end = start+duration
            if (record['start_ns'], record['end_ns'], record['bytes']) != (start,end,64):
                raise ValueError('incorrect progress serialization')
            offers[key] = end+model['propagation_ns']
            channel_free = end
        elif kind == 'report':
            report = {key: value for key,value in record.items() if key != 'kind'}
            key = report['path'], report['sample_ns']
            if key in delivered or offers.get(key) != report['arrival_ns']:
                raise ValueError('incorrect or duplicate progress delivery')
            delivered.add(key)
            sample = report['sample_ns']
            path = report['path']
            lower = upper = 0
            full_busy = False
            for flow in graph['flows']:
                launched = events[flow['id'],'start']
                if launched['port_src'] != path:
                    continue
                created = launched['ns']+model['launch_delay_ns']
                completed = events[flow['id'],'recv']['ns']
                if created <= sample:
                    upper += flow['bytes']
                if completed < sample:
                    lower += flow['bytes']
                if created <= sample-model['period_ns'] and completed > sample:
                    full_busy = True
            if not lower <= report['acked_bytes'] <= upper:
                raise ValueError('ACK count outside launched/completed volume')
            if report['full_busy'] != full_busy:
                raise ValueError('busy evidence disagrees with queue-pair lifecycle')
            final[path] = report['acked_bytes']
            alarm = rule.observe(report)
            if alarm:
                replay.append(alarm)
        elif kind == 'alarm':
            actual.append({key:value for key,value in record.items() if key != 'kind'})
        else:
            raise ValueError('unexpected progress event')
    if delivered != set(offers) or actual != replay:
        raise ValueError('incomplete delivery or online/replay decision mismatch')
    expected = {path:0 for path in range(2*graph['p'])}
    for flow in graph['flows']:
        expected[events[flow['id'],'start']['port_src']] += flow['bytes']
    if final != expected:
        raise ValueError('final ACK byte conservation mismatch')
    return dict(reports=len(delivered), modeled_report_bytes=64*len(delivered),
                alarms=actual, acked_bytes=sum(final.values()), final_path_bytes=final)
