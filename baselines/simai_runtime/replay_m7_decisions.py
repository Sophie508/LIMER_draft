"""Verify archived worker decisions using only archived TCP sample inputs."""
from pathlib import Path
import hashlib
import json
import sys

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
SOURCE=ROOT/'limer_source_m7_tcp_v3'
sys.path.insert(0,str(SOURCE))
from limer_v0.tcp_loss import TcpLossDetector

checks=[]
for campaign in ['m7_validation_v3','m7_stress_v3']:
    tasks=json.loads((ROOT/'logs'/f'{campaign}_registration.json').read_text())
    for name,config in tasks:
        status=json.loads((ROOT/'logs'/f'{name}.status.json').read_text())
        assert 'exit_code' in status
        detectors={};expected=[];observed=[];count=0
        with (ROOT/'mininet_results'/name/'events.jsonl').open() as stream:
            for line in stream:
                e=json.loads(line)
                if e['event']=='HOST_TCP_SAMPLE':
                    count+=1
                    key=(e['rank'],e['fabric'])
                    detector=detectors.setdefault(key,TcpLossDetector())
                    decision=detector.observe(e)
                    if decision is not None:
                        expected.append((e['rank'],e['fabric'],e['sample_t_monotonic_ns']))
                if e['event']=='HOST_TCP_LOSS_CONFIRM':
                    observed.append((e['rank'],e['fabric'],e['evidence_sample_t_ns']))
        matched=sorted(expected)==sorted(observed)
        checks.append(dict(name=name,samples=count,replayed=len(expected),logged=len(observed),matched=matched))
        assert matched,name
out=dict(registered=len(checks),matched=sum(c['matched'] for c in checks),
         samples=sum(c['samples'] for c in checks),
         source_sha256=hashlib.sha256((SOURCE/'limer_v0/tcp_loss.py').read_bytes()).hexdigest(),
         boundary='Replay checks consistency of actual worker decisions with archived observations; it does not independently prove physical fault accuracy.',checks=checks)
(ROOT/'logs/m7_decision_replay.json').write_text(json.dumps(out,indent=2)+'\n')
print(json.dumps({k:v for k,v in out.items() if k!='checks'}))
