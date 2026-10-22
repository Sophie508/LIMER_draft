"""Independent reconstruction of pending-flow route ownership and control cost."""
import math


def audit_dynamic(graph, records, requests, control_model):
    p=graph['p']; flows={f['id']:f for f in graph['flows']}
    if len(flows)!=len(graph['flows']):raise ValueError('duplicate flow identity')
    request_index={r['version']:r for r in requests}
    if len(request_index)!=len(requests):raise ValueError('duplicate requested version')
    events={}; transactions={}; current_version=0; overrides={}; changed=0
    prior=(-1,-1); channel_free=0; control_bytes=0
    offered={}; delivered=set()
    duration=math.ceil(512*1_000_000_000/control_model['capacity_bps'])
    propagation=control_model['propagation_ns']
    def tx(version):
        if version not in transactions:raise ValueError('unknown control transaction')
        return transactions[version]
    for e in records:
        stamp=(e['ns'],e['order'])
        if stamp<=prior:raise ValueError('nonchronological event order')
        prior=stamp
        event=e['event']
        if 'id' in e:
            fid=e['id']
            if fid not in flows:raise ValueError('unexpected flow identity')
            key=(fid,event)
            if event not in ('start','send','recv') or key in events:
                raise ValueError('duplicate or invalid flow event')
            f=flows[fid]
            owner=tuple(e[k] for k in ('plane','port_src','port_dst','version'))
            if event=='start':
                plane=overrides.get(f['src'],f['plane']) if f['plane']==0 else f['plane']
                expected=(plane,f['src']+p*plane,f['dst']+p*plane,current_version)
                if owner!=expected:raise ValueError('route/version differs from committed plan')
                changed+=plane!=f['plane']
                for parent_id in f['deps']:
                    parent=flows[parent_id]
                    parent_event='send' if f['src']==parent['src'] else 'recv'
                    if f['src'] not in (parent['src'],parent['dst']):
                        raise ValueError('remote dependency requires notification')
                    if (parent_id,parent_event) not in events:
                        raise ValueError('premature endpoint dependency release')
            else:
                if (fid,'start') not in events:raise ValueError('completion before launch')
                start=events[fid,'start']
                if owner!=tuple(start[k] for k in ('plane','port_src','port_dst','version')):
                    raise ValueError('transfer ownership changed after launch')
                if event=='recv' and (fid,'send') not in events:
                    raise ValueError('receive before source serialization completion')
            events[key]=e
            continue
        version=e['version']
        if event=='request':
            if version not in request_index or version in transactions:
                raise ValueError('unexpected or duplicate request')
            r=request_index[version]
            if e['ns']!=r['request_ns'] or e['rank']!=r['affected_rank']:
                raise ValueError('request differs from registered input')
            if version!=current_version+1 or any(not t['terminal'] for t in transactions.values()):
                raise ValueError('nonconsecutive or overlapping plan')
            transactions[version]=dict(request=r,prepare=set(),ready=set(),commit_delivery=set(),
                                       terminal=False,activated=False)
        elif event=='control_offer':
            t=tx(version); kind=e['kind']; rank=e['rank']
            if kind not in ('prepare','ready','commit_delivery') or not 0<=rank<p:
                raise ValueError('invalid modeled control message')
            if kind=='ready' and rank not in t['prepare']:raise ValueError('readiness before prepare')
            if kind=='commit_delivery' and t['ready']!=set(range(p)):
                raise ValueError('commit offered without complete readiness')
            key=(version,kind,rank)
            if key in offered:raise ValueError('duplicate control message')
            start=max(e['ns'],channel_free);end=start+duration
            if (e['start_ns'],e['end_ns'],e['bytes'])!=(start,end,64):
                raise ValueError('incorrect control serialization budget')
            offered[key]=end+propagation;channel_free=end;control_bytes+=64
        elif event in ('prepare','ready','commit_delivery'):
            t=tx(version);rank=e['rank']; key=(version,event,rank)
            if key in delivered or key not in offered or e['ns']!=offered[key]:
                raise ValueError('missing or incorrect serialized control delivery')
            if event=='ready' and rank==t['request']['unavailable_rank']:
                raise ValueError('unavailable rank supplies readiness')
            delivered.add(key);t[event].add(rank)
        elif event=='activate':
            t=tx(version)
            if t['terminal'] or t['ready']!=set(range(p)):
                raise ValueError('activation lacks readiness')
            if t['commit_delivery']!=set(range(p)):
                raise ValueError('activation precedes commit delivery')
            latest=max(offered[version,'commit_delivery',rank] for rank in range(p))
            if e['ns']<=latest:raise ValueError('activation must follow all commits')
            if e['rank']!=t['request']['affected_rank']:raise ValueError('wrong affected sender')
            current_version=version;overrides[e['rank']]=1
            t.update(terminal=True,activated=True)
        elif event=='timeout':
            t=tx(version)
            if t['terminal'] or e['ns']!=t['request']['request_ns']+control_model['timeout_ns']:
                raise ValueError('invalid transaction timeout')
            if t['ready']==set(range(p)):raise ValueError('ready transaction unexpectedly times out')
            t['terminal']=True
        else:raise ValueError('unexpected control event')
    expected={(fid,ev) for fid in flows for ev in ('start','send','recv')}
    if set(events)!=expected:raise ValueError('incomplete graph lifecycle')
    if set(transactions)!=set(request_index) or any(not t['terminal'] for t in transactions.values()):
        raise ValueError('incomplete control lifecycle')
    if set(offered)!=delivered:raise ValueError('undelivered control message')
    return dict(flows=len(flows),dependency_edges=sum(len(f['deps']) for f in flows.values()),
                changed_flows=changed,activated_versions=sum(t['activated'] for t in transactions.values()),
                control_bytes=control_bytes,makespan_ns=max(e['ns'] for e in events.values()))
