"""Independent parallel final replay of frozen M13 source and all registered trials."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys
from multiprocessing import get_context

MODULE=None
DIRECTORY=None


def audit_trial(trial):
    module=MODULE;d=DIRECTORY/trial['id']
    status=json.loads((d/'status.json').read_text())
    if status['status']!='PASS' or status['exit_code']!=0:raise ValueError('engineering failure')
    truth=json.loads((d/'truth.json').read_text());module.audit(truth)
    observed=module.replay(d/'reports.jsonl',truth['observation_end_ns'])
    audited=module.audit_observations(d,trial,truth,observed)
    for key,value in dict(module.score(trial,truth,observed),**audited).items():
        if status[key]!=value:raise ValueError(f"replay differs {trial['id']}/{key}")
    if module.digest(d/'reports.jsonl')!=status['input_sha256'] or module.digest(d/'truth.json')!=status['truth_sha256']:
        raise ValueError('recorded inputs changed')
    files={p.name:module.digest(p) for p in list(d.glob('*.jsonl'))+list(d.glob('*.csv'))}
    return dict(id=trial['id'],status=status,artifacts=files,report_rows=observed['input_rows'],
                probes=sum(p['probe_sent'] for p in truth['paths']),wire=sum(p['wire_bytes'] for p in truth['paths']))


def main():
    parser=argparse.ArgumentParser();parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--campaign',default='m13_development_v2');parser.add_argument('--frozen',default='m13_source_frozen_dev_v2');args=parser.parse_args()
    root=args.root;frozen=root/args.frozen;sys.path.insert(0,str(frozen))
    spec=importlib.util.spec_from_file_location('frozen_business',frozen/'simulation/run_business_observation.py')
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    global MODULE,DIRECTORY
    MODULE=module;DIRECTORY=root/'runs'/args.campaign
    reg=json.loads((DIRECTORY/'registration.json').read_text());terminal=json.loads((DIRECTORY/'terminal.json').read_text())
    if not terminal['complete']:raise ValueError('incomplete ledger')
    files=dict(detector='limer_v0/business_delivery.py',runner='simulation/run_business_observation.py',
        cpp='simulation/LimerBusinessObservation.cc',header='simulation/business_observer.h',
        native_base='simulation/m13_batch_deficit_observer.h',hybrid_base='limer_v0/hybrid_delivery.py',
        early_detector='limer_v0/early_delivery.py',base_detector='limer_v0/batch_loss.py')
    if 'probe_budget_header' in reg['hashes']:files['probe_budget_header']='simulation/probe_budget.h'
    for key,path in files.items():
        if module.digest(frozen/path)!=reg['hashes'][key]:raise ValueError(f'changed source {key}')
    binary=root/module.BINARY_REL
    if module.digest(binary)!=reg['hashes']['binary'] or module.digest(frozen/'native_binary'/binary.name)!=reg['hashes']['binary']:
        raise ValueError('native executable changed')
    for name,sha in reg['library_hashes'].items():
        if module.digest(binary.parent.parent/'lib'/name)!=sha:raise ValueError('dependency changed')
    if module.digest(binary.parent.parent.parent/'scratch/CMakeLists.txt')!=reg['cmake_sha256']:raise ValueError('build wiring changed')
    with get_context('fork').Pool(8) as pool:results=pool.map(audit_trial,reg['trials'])
    summary=module.aggregate(reg,[r['status'] for r in results])
    if summary!=terminal['summary'] or summary!=json.loads((DIRECTORY/'summary.json').read_text()):raise ValueError('aggregate differs')
    out=dict(passed=True,campaign=args.campaign,source=frozen.name,registrations=len(results),
        report_rows=sum(r['report_rows'] for r in results),probe_packets=sum(r['probes'] for r in results),
        wire_bytes=sum(r['wire'] for r in results),source_hashes=reg['hashes'],
        artifacts={r['id']:r['artifacts'] for r in results},summary=summary,
        claim='Exact native/Python replay, serialized payloads, actual packet observations and accounting; not physical deployment')
    module.write(root/'logs'/f'{args.campaign}_final_audit.json',out)
    print(json.dumps({k:out[k] for k in ('passed','campaign','registrations','report_rows','probe_packets')}))


if __name__=='__main__':main()
