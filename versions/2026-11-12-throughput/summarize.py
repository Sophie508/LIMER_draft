"""Summarize every registered throughput attempt, including failures."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
from statistics import mean


def summarize(campaign,scorer):
    campaign=Path(campaign)
    spec=importlib.util.spec_from_file_location('detector_scoring',scorer)
    score=importlib.util.module_from_spec(spec);spec.loader.exec_module(score)
    registration=json.loads((campaign/'registration.json').read_text())
    result=[]
    for case in registration['cases']:
        scene=case['scene'];path=campaign/'runs'/case['name']
        row=dict(name=case['name'],family=scene['family'],method=case['method'],seed=scene['seed'],
            phases=scene['phases_per_round'],relay_completion=scene['relay_completion'],
            helper_mode=scene['helper_mode'],policy=scene['policy'],valid=False,status='not_run',
            communication_ms=None,healthy_normalized_percent=None,old_healthy_normalized_percent=None)
        ap=campaign/'attempts'/(case['name']+'.json')
        if ap.exists():
            attempt=json.loads(ap.read_text());row['status']='invalid_attempt'
            if not attempt['valid']:row['error']=attempt.get('error')
            else:
                r=attempt['result'];p=r['performance'];s=r['status']
                manifest=json.loads((path/'run_manifest.json').read_text())
                assert manifest['scene']==scene and manifest['binary_sha256']==registration['binary_sha256']
                assert r['audit']['pass'] and r['observation_audit']['pass']
                alarms=list(csv.DictReader((path/'detector_events.csv').open()))
                detection=score.score_alarm_rows(scene,alarms,True)
                phases=list(csv.DictReader((path/'phase_metrics.csv').open()))
                row.update(valid=True,status=s['status'],communication_ms=p['communication_ms'],
                    detector_classification=detection['classification'],detection_ms=detection['all_paths_delay_ms'],
                    detection_below_100ms=detection['all_paths_timely_success'],
                    unique_payload_bytes=p['unique_payload_bytes'],fresh_Bprime_chunks=p['new_Bprime_completions'],
                    fresh_Bprime_phases=p['new_Bprime_phases'],rescued_chunks=s['rescued_chunks'],
                    health_probes=s['health_probe_routes'],control_wire_bytes=s['control_wire_bytes'],
                    max_logical_outstanding=r['audit']['max_logical_source_credit'],
                    max_physical_nic_credit=r['audit']['max_physical_nic_credit'],
                    max_helper_buffers=r['audit']['max_helper_buffers'],
                    phase3_onward_mean_ms=mean(int(x['duration_ns'])/1e6 for x in phases[3:]) if len(phases)>3 else None)
        result.append(row)
    healthy={(r['seed'],r['relay_completion'],r['helper_mode'],r['policy']):r['communication_ms']
             for r in result if r['family']=='healthy' and r['valid'] and r['status']=='completed'}
    for r in result:
        if r['communication_ms'] is None: continue
        h=healthy.get((r['seed'],r['relay_completion'],r['helper_mode'],r['policy']))
        if h:r['healthy_normalized_percent']=100*h/r['communication_ms']
        if r['phases']==30:r['old_healthy_normalized_percent']=100*480.178448/r['communication_ms']
    return dict(registered=len(result),valid=sum(r['valid'] for r in result),
                completed=sum(r['status']=='completed' for r in result),
                invalid=sum(r['status']=='invalid_attempt' for r in result),
                not_run=sum(r['status']=='not_run' for r in result),
                scope=registration['role'],rows=result)


if __name__=='__main__':
    a=argparse.ArgumentParser(description=__doc__);a.add_argument('campaign',type=Path)
    a.add_argument('--scorer',type=Path,required=True);a.add_argument('--out',type=Path,required=True)
    args=a.parse_args();result=summarize(args.campaign,args.scorer)
    args.out.mkdir(parents=True,exist_ok=False)
    (args.out/'report.json').write_text(json.dumps(result,indent=2)+'\n')
    fields=list(dict.fromkeys(k for r in result['rows'] for k in r))
    with (args.out/'trials.csv').open('w') as f:
        w=csv.DictWriter(f,fieldnames=fields);w.writeheader();w.writerows(result['rows'])
    print(json.dumps({k:v for k,v in result.items() if k!='rows'}))
