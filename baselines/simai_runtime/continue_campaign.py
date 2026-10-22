"""Gate-driven registered follow-up with two isolated Mininet lifecycles max."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
D=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock']
IMAGE='limer-mininet:2026-10-10-py312'
SOURCE='limer_source_guarded_v1'


def run(task):
    name,config,source,wrapper=task
    source_root=ROOT/source
    args=['python3','/runtime/signal_control_wrapper.py'] if wrapper else ['python3','-m','limer_v0.orchestrator']
    command=D+['run','--rm','--name','limer-'+name,'--privileged','--cpus=4','--memory=4g',
       '-v',str(source_root)+':/work','-v',str(ROOT/'baselines/simai_runtime')+':/runtime',
       '-v',str(ROOT/'mininet_results')+':/results',IMAGE,'bash','/runtime/mininet_entry.sh']+args+[
       '--config',config,'--results-dir','/results','--workdir','/work','--run-id',name]
    status={'name':name,'config':config,'source_snapshot':source,'command':command,
        'start_unix':time.time(),'image_id':subprocess.check_output(D+['image','inspect',IMAGE,'--format','{{.Id}}'],text=True).strip(),
        'hashes':{f:hashlib.sha256((source_root/f).read_bytes()).hexdigest() for f in
                  [config,'limer_v0/orchestrator.py','limer_v0/worker.py','limer_v0/tcp_retrans.py']}}
    if wrapper:
        status['wrapper_hashes']={f:hashlib.sha256((ROOT/'baselines/simai_runtime'/f).read_bytes()).hexdigest()
                                 for f in ['signal_control_wrapper.py','udp_control.py']}
    output=ROOT/'logs'/f'{name}.status.json'
    output.write_text(json.dumps(status,indent=2)+'\n')
    with (ROOT/'logs'/f'{name}.log').open('w') as log:
        try:status['exit_code']=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800).returncode
        except subprocess.TimeoutExpired:
            status.update(exit_code=None,timeout=True)
            subprocess.run(D+['rm','-f','limer-'+name],capture_output=True)
    status['wall_seconds']=time.time()-status['start_unix']
    folder=ROOT/'mininet_results'/name
    for filename in ('summary.json','correctness.json'):
        if (folder/filename).exists():status[filename.removesuffix('.json')]=json.loads((folder/filename).read_text())
    status['completion_pass']=(status['exit_code']==0 and status.get('summary',{}).get('status')=='complete'
                               and status.get('correctness',{}).get('status')=='pass')
    if (folder/'events.jsonl').exists():
        events=[json.loads(x) for x in (folder/'events.jsonl').read_text().splitlines()]
        decisions=[e for e in events if e['event']=='POLICY_DECISION']
        status['policy_decisions']=decisions
        status['event_counts']={key:sum(e['event']==key for e in events) for key in
                               ['HOST_CONFIRM','PLAN_COMMIT','RECOVERY_SUPPRESSED','WORKER_ERROR','TCP_RETRANS_SAMPLE']}
        if name.startswith('m5_guarded_'):
            expected='switch' if 'switch' in name else 'stay'
            status['expected_branch']=expected
            status['branch_gate_pass']=len(decisions)==1 and decisions[0]['verdict']==expected
    output.write_text(json.dumps(status,indent=2)+'\n')
    print(name,'completion',status['completion_pass'],'branch',status.get('branch_gate_pass'),
          round(status['wall_seconds'],2),flush=True)
    return status


def prepare():
    source=ROOT/SOURCE
    configs=source/'configs/m5_guarded';configs.mkdir(exist_ok=False)
    for arm in ('switch','stay'):
        original=json.loads((source/f'configs/m4b_policy/aa12_policy_{arm}.json').read_text())
        original.update(policy_headroom_mode='baseline_guarded',
            what_changes='Opt-in stationary-capacity guarded spare reference; original loss scene unchanged.',
            expected=f'Correct completion and branch {arm}; baseline unknown must not manufacture spare.')
        (configs/f'{arm}.json').write_text(json.dumps(original,indent=2)+'\n')
    controls=source/'configs/m5_pilot_controls';controls.mkdir(exist_ok=False)
    for kind in ('nominal','congestion','burst_pause','reorder'):
        config=json.loads((source/'configs/m5_retrans_observation/l1.json').read_text())
        config.update(fault_loss_pct=0,pilot_control_kind=kind,
            what_changes=f'Observation-only matched no-drop pilot control: {kind}; no telemetry trigger.',
            expected='Record retransmission availability/deltas and existing counter detector outcomes; no no-alarm guarantee.')
        if kind=='reorder':config['fault_delay_ms']=10
        (controls/f'{kind}.json').write_text(json.dumps(config,indent=2)+'\n')
    tasks=[(f'm5_guarded_{arm}_pilot',f'configs/m5_guarded/{arm}.json',SOURCE,False)
           for arm in ('switch','stay')]
    for scene,config in [('hard','aa7_hard.json'),('grayfast','aa8_grayfast.json'),('transient','aa5_transient_stepcutover.json')]:
        tasks += [(f'm5_original_v3_{scene}_r{i:02}',f'configs/active_active_v3/{config}','limer_source',False) for i in range(1,4)]
    for config in ('healthy','l0p5','l1','l2','l5','l10','l25'):
        tasks += [(f'm5_signal_{config}_r{i:02}',f'configs/m5_retrans_observation/{config}.json',SOURCE,False) for i in range(1,4)]
    for kind in ('nominal','congestion','burst_pause','reorder'):
        tasks += [(f'm5_signal_control_{kind}_r{i:02}',f'configs/m5_pilot_controls/{kind}.json',SOURCE,True) for i in range(1,4)]
    (ROOT/'logs/continuation_registration.json').write_text(json.dumps(tasks,indent=2)+'\n')
    return tasks


def main():
    tasks=prepare()
    with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,tasks))
    (ROOT/'logs/continuation_summary.json').write_text(json.dumps(results,indent=2)+'\n')
    guarded=results[:2]
    if all(r['completion_pass'] and r.get('branch_gate_pass') for r in guarded):
        extra=[(f'm5_guarded_{arm}_r{i:02}',f'configs/m5_guarded/{arm}.json',SOURCE,False)
               for i in range(2,11) for arm in ('switch','stay')]
        (ROOT/'logs/guarded_expansion_registration.json').write_text(json.dumps(extra,indent=2)+'\n')
        with ThreadPoolExecutor(max_workers=2) as pool:expanded=list(pool.map(run,extra))
        (ROOT/'logs/guarded_expansion_summary.json').write_text(json.dumps(expanded,indent=2)+'\n')
    else:
        (ROOT/'logs/guarded_expansion_blocked.json').write_text(json.dumps({'reason':'guarded pilot branch/completion gate failed','pilots':guarded},indent=2)+'\n')


if __name__=='__main__':main()
