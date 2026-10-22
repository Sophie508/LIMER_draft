"""Registered fresh lifecycles; isolated containers and complete failure ledger."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
from pathlib import Path
import subprocess
import time

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
DOCKER=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock']
IMAGE='limer-mininet:2026-10-10-py312'


def run(config,name):
    command=DOCKER+['run','--rm','--name','limer-'+name,'--privileged','--cpus=4',
                   '--memory=4g','-v',str(ROOT/'limer_source')+':/work',
                   '-v',str(ROOT/'baselines/simai_runtime')+':/runtime',
                   '-v',str(ROOT/'mininet_results')+':/results',IMAGE,'bash',
                   '/runtime/mininet_entry.sh','python3','-m','limer_v0.orchestrator',
                   '--config',config,'--results-dir','/results','--workdir','/work',
                   '--run-id',name]
    status={'name':name,'config':config,'command':command,'start_unix':time.time(),
            'config_sha256':hashlib.sha256((ROOT/'limer_source'/config).read_bytes()).hexdigest()}
    with (ROOT/'logs'/f'{name}.log').open('w') as log:
        try:
            result=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=1800)
            status['exit_code']=result.returncode
        except subprocess.TimeoutExpired:
            status.update(exit_code=None,timeout=True)
            subprocess.run(DOCKER+['rm','-f','limer-'+name],capture_output=True)
    status['wall_seconds']=time.time()-status['start_unix']
    folder=ROOT/'mininet_results'/name
    for filename in ('summary.json','correctness.json'):
        if (folder/filename).exists():
            status[filename.removesuffix('.json')]=json.loads((folder/filename).read_text())
    status['completion_pass']=(status['exit_code']==0 and
        status.get('summary',{}).get('status')=='complete' and
        status.get('correctness',{}).get('status')=='pass')
    (ROOT/'logs'/f'{name}.status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(name,'PASS' if status['completion_pass'] else 'FAILED',
          round(status['wall_seconds'],2),flush=True)
    return status


def main():
    registrations=[]
    for repeat in range(1,11):
        for arm in ('switch','stay'):
            registrations.append((f'configs/m4b_policy/aa12_policy_{arm}.json',
                                  f'm5_aa12_{arm}_r{repeat:02d}'))
    for scene,filename in [('hard','aa7_hard.json'),('grayfast','aa8_grayfast.json'),
                           ('transient','aa5_transient_stepcutover.json')]:
        for repeat in range(1,4):
            registrations.append(('configs/active_active_v3/'+filename,
                                  f'm5_{scene}_r{repeat:02d}'))
    (ROOT/'logs/mininet_campaign_registration.json').write_text(json.dumps(registrations,indent=2)+'\n')
    with ThreadPoolExecutor(max_workers=2) as executor:
        results=list(executor.map(lambda args:run(*args),registrations))
    (ROOT/'logs/mininet_campaign_summary.json').write_text(json.dumps(results,indent=2)+'\n')


if __name__=='__main__':
    main()
