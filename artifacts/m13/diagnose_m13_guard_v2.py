"""Retrospective guard sensitivity; unchanged source artifacts, no validation claim."""
import argparse
from collections import defaultdict
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True);args=parser.parse_args()
    root=args.root;frozen=root/'m13_source_frozen_dev_v2';sys.path.insert(0,str(frozen))
    spec=importlib.util.spec_from_file_location('frozen',frozen/'simulation/run_business_observation.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    d=root/'runs/m13_development_v2';reg=json.loads((d/'registration.json').read_text())
    if not json.loads((d/'terminal.json').read_text())['complete']:raise ValueError('incomplete ledger')
    groups={};records=[]
    for trial in reg['trials']:
        path=d/trial['id'];status=json.loads((path/'status.json').read_text());truth=json.loads((path/'truth.json').read_text())
        if status['status']!='PASS' or module.digest(path/'reports.jsonl')!=status['input_sha256']:raise ValueError('unverified report')
        rows=[json.loads(s) for s in (path/'reports.jsonl').read_text().splitlines()]
        group=groups.setdefault(trial['condition'],dict(n=0,kind=trial['kind'],candidate_timely=0,
                baseline_timely=0,damaged_runs=0,guards={str(g):dict(timely=0,false_runs=0) for g in (0,10,20,30,40)}))
        group['n']+=1;group['candidate_timely']+=int(status['timely'])
        base=module.score(trial,truth,dict(alarms=status['baseline_alarms']));group['baseline_timely']+=int(base['timely'])
        target=next(p for p in truth['paths'] if p['path']==truth['fault_path'])
        group['damaged_runs']+=int(bool(target['sent']>target['received'] or target['deferred'] or target['application_deferred']))
        record=dict(id=trial['id'],condition=trial['condition'],candidate_delay_ms=status['delay_ms'],baseline_delay_ms=base['delay_ms'],guards={})
        # Lower guards add earlier gap alarms without changing counter-lane state.
        # First alarm times equal the minimum of original first alarms and the new
        # gap-qualified reports on each path. This is a time-only counterfactual.
        for guard in (0,10,20,30,40):
            first={a['path']:dict(a) for a in status['alarms']}
            for r in rows:
                if r['side']!='rx' or r['arrival_t_ns']>(r['batch']+1)*10_000_000+200_000_000:continue
                if not any(r[k+'_gaps'] and r[k+'_gap_age_ns']>=guard*1_000_000 for k in ('data','probe')):continue
                if r['path'] not in first or r['arrival_t_ns']<first[r['path']]['decision_t_ns']:
                    first[r['path']]=dict(path=r['path'],decision_t_ns=r['arrival_t_ns'])
            scored=module.score(trial,truth,dict(alarms=list(first.values())))
            group['guards'][str(guard)]['timely']+=int(scored['timely'])
            group['guards'][str(guard)]['false_runs']+=int(scored['false_alarm_events']>0)
            record['guards'][str(guard)]=dict(delay_ms=scored['delay_ms'],false_events=scored['false_alarm_events'])
            if guard==40 and (scored['timely']!=status['timely'] or scored['false_alarm_events']!=status['false_alarm_events']):
                raise ValueError('original guard replay differs')
        records.append(record)
    module.write(root/'logs/m13_guard_sensitivity_v2.json',dict(groups=groups,records=records,
        claim='Retrospective first-alarm-time sensitivity on development only; no new native or held-out result'))
    print(json.dumps(groups))


if __name__=='__main__':main()
