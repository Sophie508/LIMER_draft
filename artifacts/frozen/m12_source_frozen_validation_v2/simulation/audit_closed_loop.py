"""Independent delivery FIFO, ACK bounds and actual-online-decision auditing."""
import math

from limer_v0.ack_progress import AckProgressRule
from limer_v0.pending_route_cost import pending_route_cost
from simulation.audit_dynamic_dag import audit_dynamic


def audit_closed_loop_reports(graph, trace, records, model):
    events = {(e['id'], e['event']): e for e in trace if 'id' in e}
    offers = {}
    delivered = set()
    final = {}
    channel_free = 0
    rule = AckProgressRule()
    replay = []
    actual = []
    duration = math.ceil(768*1_000_000_000/model['capacity_bps'])
    for record in records:
        kind = record['kind']
        if kind == 'offer':
            key = record['path'], record['sample_ns']
            if key in offers:
                raise ValueError('duplicate progress offer')
            start = max(record['sample_ns'], channel_free)
            end = start+duration
            if (record['start_ns'], record['end_ns'], record['bytes']) != (start,end,96):
                raise ValueError('incorrect progress serialization')
            offers[key] = end+model['propagation_ns']
            channel_free = end
        elif kind == 'report':
            report = {key: value for key,value in record.items() if key not in {'kind','pending_a','pending_b','inflight_a','inflight_b'}}
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
    return dict(reports=len(delivered), modeled_report_bytes=96*len(delivered),
                alarms=actual, acked_bytes=sum(final.values()), final_path_bytes=final)


def audit_closed_loop(graph, trace, records, model, mode, scripted_requests, releases):
    reports={(r['path'],r['sample_ns']):r for r in records if r['kind']=='report'}
    events={(e['id'],e['event']):e for e in trace if 'id' in e}
    queue_fields=('pending_a','pending_b','inflight_a','inflight_b')
    for report in reports.values():
        rank=report['path']%graph['p']; sample=report['sample_ns']
        pending=[0,0]; launched=[0,0]; completed=[0,0]
        for f in graph['flows']:
            if f['src']!=rank:continue
            start=events[f['id'],'start']; finish=events[f['id'],'recv']['ns']
            if start['ns']>sample:pending[f['plane']]+=f['bytes']
            elif finish<sample:completed[start['plane']]+=f['bytes']
            else:launched[start['plane']]+=f['bytes']
        inflight=[]
        for plane in range(2):
            ack=reports[rank+plane*graph['p'],sample]['acked_bytes']
            inflight.append(launched[plane]-(ack-completed[plane]))
        if [report[k] for k in queue_fields]!=[*pending,*inflight]:
            raise ValueError('reported queue work disagrees with causal flow/ACK ownership')
    data=[r for r in records if r['kind']!='policy']
    observation=audit_closed_loop_reports(graph,trace,data,model)
    rule=AckProgressRule(); last_service={}; expected_policies=[]
    for raw in records:
        if raw['kind']!='report':continue
        report={k:raw[k] for k in AckProgressRule.SCHEMA}
        previous=rule.paths.get(report['path'])
        previous=None if previous is None else previous.previous
        rate=None
        if previous is not None:
            rate=(report['acked_bytes']-previous['acked_bytes'])/(report['sample_ns']-previous['sample_ns'])
            if report['full_busy'] and rate>0:last_service[report['path']]=(report['sample_ns'],rate)
        alarm=rule.observe(report)
        if alarm and mode=='candidate' and report['path']<graph['p']:
            path=report['path']; alternate=path+graph['p']
            state=rule.paths.get(alternate)
            service=last_service.get(alternate)
            reference=None if state is None else state.reference
            spare=0 if service is None or reference is None else min(reference,service[1])
            age=-1 if service is None else report['arrival_ns']-service[0]
            cost=pending_route_cost(*(raw[k] for k in queue_fields),rate,spare,age)
            expected_policies.append(dict(path=path,decision_ns=report['arrival_ns'],
                **{k:raw[k] for k in queue_fields},rate_a=rate,rate_b=spare,b_age_ns=age,
                coordination_ns=10_000,**cost))
    actual=[{k:v for k,v in r.items() if k!='kind'} for r in records if r['kind']=='policy']
    if len(actual)!=len(expected_policies):raise ValueError('missing or unexpected online cost evaluation')
    for a,b in zip(actual,expected_policies):
        if set(a)!=set(b):raise ValueError('policy record schema mismatch')
        for key,value in b.items():
            if isinstance(value,float):
                if not math.isclose(a[key],value,rel_tol=1e-10,abs_tol=1e-6):
                    raise ValueError('observable policy arithmetic mismatch')
            elif a[key]!=value:raise ValueError('online policy decision mismatch')
    requests=list(scripted_requests)
    for decision in actual:
        if decision['switch']:
            requests.append(dict(version=len(requests)+1,request_ns=decision['decision_ns'],
                                 affected_rank=decision['path'],unavailable_rank=-1))
    execution=audit_dynamic(graph,trace,requests,dict(capacity_bps=1_000_000_000,
                                                    propagation_ns=1000,timeout_ns=1_000_000))
    for fid,at in releases.items():
        if events[fid,'start']['ns']<at:raise ValueError('premature prescribed workload release')
    for e in trace:
        if e['event']=='activate':
            request=next(r for r in requests if r['version']==e['version'])
            if e['ns']-request['request_ns']>10_000:raise ValueError('coordination exceeds policy budget')
    return dict(observation=observation,execution=execution,policies=actual,requests=requests)
