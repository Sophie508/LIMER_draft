"""Read every registered integration attempt without dropping failures."""
import argparse
import csv
import importlib.util
import json
from pathlib import Path
import sys


def summarize(campaign,scorer):
    spec=importlib.util.spec_from_file_location('registered_detection_scoring',scorer)
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    campaign=Path(campaign);registration=json.loads((campaign/'registration.json').read_text())
    result=[]
    for case in registration['cases']:
        p=campaign/'attempts'/(case['name']+'.json')
        row=dict(name=case['name'],method=case['method'],family=case['scene']['family'],
            policy=case['scene']['policy'],lifetime=case['scene']['replacement_lifetime'],
            chunks=case['scene']['chunks_per_phase'],phases=case['scene']['phases_per_round'],
            horizon_ms=case['scene']['horizon_ns']/1e6,valid=False,status='not_run',
            completion_ms=None,fresh_Bprime_done=None,fresh_Bprime_phases=None)
        if p.exists():
            attempt=json.loads(p.read_text());row['status']='invalid_attempt'
            if attempt['valid']:
                run=campaign/'runs'/case['name'];record=attempt['result']
                manifest=json.loads((run/'run_manifest.json').read_text())
                assert manifest['scene']==case['scene'] and manifest['method']==case['method']
                assert manifest['binary_sha256']==registration['binary_sha256']
                assert record['audit']['pass'] and record['observation_audit']['pass']
                with (run/'detector_events.csv').open() as stream:alarms=list(csv.DictReader(stream))
                score=module.score_alarm_rows(case['scene'],alarms,True)
                perf=record['performance']
                row.update(valid=True,status=record['status']['status'],completion_ms=perf['communication_ms'],
                    restricted_ms=perf['restricted_communication_ms'],fresh_Bprime_done=perf['new_Bprime_completions'],
                    fresh_Bprime_phases=perf['new_Bprime_phases'],fresh_Bprime_bytes=perf['fresh_Bprime_payload_bytes'],
                    alarm_classification=score['classification'],all_paths_delay_ms=score['all_paths_delay_ms'],
                    detected_below_100ms=score['all_paths_timely_success'],
                    phase_resets=perf['phase_binding_resets'],rescued_chunks=record['status']['rescued_chunks'],
                    binding_lifecycles=perf['phase_route_lifecycles'])
            else:row['error']=attempt.get('error')
        result.append(row)
    return dict(schema='limer-integration-development-summary-v1',registered=len(result),
        valid=sum(r['valid'] for r in result),not_run=sum(r['status']=='not_run' for r in result),
        invalid=sum(r['status']=='invalid_attempt' for r in result),
        role=registration['role'],rows=result)


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('campaign',type=Path)
    p.add_argument('--scorer',type=Path,required=True);p.add_argument('--out',type=Path,required=True);a=p.parse_args()
    r=summarize(a.campaign,a.scorer);a.out.mkdir(parents=True,exist_ok=False)
    (a.out/'report.json').write_text(json.dumps(r,indent=2)+'\n')
    columns=['name','method','family','policy','lifetime','chunks','phases','horizon_ms','valid','status','completion_ms','restricted_ms','fresh_Bprime_done','fresh_Bprime_phases','fresh_Bprime_bytes','rescued_chunks','alarm_classification','all_paths_delay_ms','detected_below_100ms','phase_resets','error']
    with (a.out/'trials.csv').open('w',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=columns,extrasaction='ignore');writer.writeheader();writer.writerows(r['rows'])
    print(json.dumps({k:v for k,v in r.items() if k!='rows'}))
