#!/usr/bin/env python3
"""Reconstruct reports from packet events and replay the frozen Python M13 rule."""
import argparse
import csv
import json
from collections import defaultdict
from pathlib import Path
from .detector.business_delivery import BusinessDeliveryDetector

def replay(root):
    scene=json.loads((root/'run_manifest.json').read_text()).get('scene',{}) if (root/'run_manifest.json').exists() else {}
    if scene.get('detector')=='service':
        from .service_replay import replay_service
        result=replay_service(root);result['pass']=result.pop('pass_')
        if scene.get('policy')=='benefit':
            from .policy_replay import replay_policy
            policy=replay_policy(root)
            result['policy_replay']=policy
            result['pass']=result['pass'] and policy['pass']
            result['errors']+=policy.get('errors',[])
        return result
    tx=defaultdict(int);rx=defaultdict(int);totals=defaultdict(int)
    next_seq=defaultdict(int);next_tx=defaultdict(int);holes=defaultdict(dict);snapshots={};errors=[]
    with (root/'packet_events.csv').open() as stream:
        for r in csv.DictReader(stream):
            t=int(r['timestamp_ns']);p=r['path_id'];kind=int(r['probe']);b=int(r['batch']);seq=int(r['sequence'])
            key=(p,kind)
            if r['event']=='source_accept':
                if seq!=next_tx[key]: errors.append('duplicate/nonconsecutive source acceptance')
                next_tx[key]=seq+1;tx[p,kind,b]+=1;totals[p,kind,'tx']+=1
            elif r['event']=='network_rx' and r['accepted']=='1':
                rx[p,kind,b]+=1;totals[p,kind,'rx']+=1
                if seq>=next_seq[key]:
                    for missing in range(next_seq[key],seq): holes[key][missing]=t
                    next_seq[key]=seq+1
                else:
                    if seq not in holes[key]:errors.append('duplicate receiver acceptance')
                    holes[key].pop(seq,None)
            elif r['event']=='snapshot':
                side='rx' if kind else 'tx';guard=seq
                counts=rx if kind else tx
                data,probe=[totals[p,k,side] if guard==10000000 else counts[p,k,b] for k in (0,1)]
                report={'path':p,'batch':b,'side':side,'guard_ns':guard,'sample_t_ns':t,
                        'count':data+probe,'data_count':data,'probe_count':probe}
                for k,label in enumerate(('data','probe')):
                    gaps=holes[p,k] if kind else {}
                    report[label+'_gaps']=len(gaps);report[label+'_gap_age_ns']=t-min(gaps.values()) if gaps else 0
                snapshots[p,b,side,guard,t]=report
    detector=BusinessDeliveryDetector();predicted=[];reports=0
    with (root/'observations.jsonl').open() as stream:
        for line in stream:
            r=json.loads(line);reports+=1
            key=tuple(r[k] for k in ('path','batch','side','guard_ns','sample_t_ns'))
            expected=snapshots.get(key)
            if expected!={k:v for k,v in r.items() if k!='arrival_t_ns'}: errors.append('report differs from packet reconstruction: '+str(key))
            alarm=detector.observe(r)
            if alarm: predicted.append((alarm['path'],alarm['decision_t_ns'],alarm['signal']))
    with (root/'detector_events.csv').open() as stream:
        actual=[(r['path_id'],int(r['timestamp_ns']),r['signal']) for r in csv.DictReader(stream) if r['alarm_origin']=='M13-R']
    if predicted!=actual: errors.append('C++ / frozen Python first alarms differ')
    if not snapshots: errors.append('missing raw snapshot events')
    return {'pass':not errors,'errors':errors[:100],'reports_reconstructed':reports,'alarms':actual,
            'source':'frozen M13 Python implementation at 1447bc48689802662f0571feaf0d3e03cace1475',
            'truth_accessed':False}

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('run',type=Path);a=p.parse_args()
    result=replay(a.run);(a.run/'observation_audit.json').write_text(json.dumps(result,indent=2)+'\n')
    print(json.dumps(result));raise SystemExit(0 if result['pass'] else 1)
