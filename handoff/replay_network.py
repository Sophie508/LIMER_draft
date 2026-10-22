"""Rerun the registered Ring/OptCC network inputs without a DAG generator."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / 'baselines/simai_runtime'))
from dag_tools import verify_trace


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--tag', required=True)
    parser.add_argument('--docker-host', default='')
    parser.add_argument('--image', default='limer-simai-cpu:2026-10-10')
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    campaign = root / 'runs' / ('paper_network_' + args.tag)
    campaign.mkdir(parents=True, exist_ok=False)
    sources = REPO / 'artifacts/server/runs'
    rows = json.loads((REPO / 'artifacts/server/logs/measurements_summary.json').read_text())
    names = [row['command'][row['command'].index('-w') + 1].split('/')[-1] for row in rows]
    binary_rel = Path('baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation/build/scratch/ns3.36.1-LimerDagReplay-debug')
    registration = dict(scope='Reproduction of frozen network-only schedules; not integrated LIMER versus OptCC',
        cases=names, binary_sha256=hashlib.sha256((root / binary_rel).read_bytes()).hexdigest(),
        source_input_sha256={name:{p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in (sources/name).iterdir() if p.name in ('graph.json','graph.txt','topology.txt','SimAI.conf')} for name in names})
    (campaign / 'registration.json').write_text(json.dumps(registration, indent=2) + '\n')
    results = []
    docker = ['docker'] + (['--host', args.docker_host] if args.docker_host else [])
    for name in names:
        out = campaign / name
        out.mkdir()
        for p in (sources / name).iterdir():
            if p.name in ('graph.json','graph.txt','topology.txt','flow.txt','trace_nodes.txt','SimAI.conf'):
                data = p.read_text()
                if p.name == 'SimAI.conf':
                    data = data.replace('/work/runs/' + name, '/work/' + str(out.relative_to(root)))
                (out / p.name).write_text(data)
        command = docker + ['run','--rm','--cpus=2','--memory=4g','-e','AS_SEND_LAT=3','-e','AS_PXN_ENABLE=0','-e','AS_NVLS_ENABLE=0',
            '-v',str(root)+':/work','-w','/work/'+str(out.relative_to(root)),args.image,'/work/'+str(binary_rel),
            'topology.txt','SimAI.conf','graph.txt','trace.jsonl']
        record = dict(name=name, command=command, status='UNVERIFIED')
        try:
            with (out / 'stdout.log').open('w') as handle:
                process = subprocess.run(command, stdout=handle, stderr=subprocess.STDOUT, timeout=180)
            record['exit_code'] = process.returncode
            if process.returncode:
                raise RuntimeError('Native process failed')
            record['trace_check'] = verify_trace(json.loads((out/'graph.json').read_text()), out/'trace.jsonl')
            if 'drain=1' not in (out/'stdout.log').read_text():
                raise ValueError('Transport did not drain')
            record['status'] = 'PASS'
        except (ValueError, RuntimeError, OSError, subprocess.TimeoutExpired) as error:
            record['failure'] = str(error)
        (out / 'status.json').write_text(json.dumps(record, indent=2) + '\n')
        results.append(record)
        (campaign/'summary.json').write_text(json.dumps(dict(registered=len(names), results=results), indent=2)+'\n')
        print(name, record['status'], flush=True)
        if record['status'] != 'PASS':
            raise SystemExit('Stopped with failed attempt preserved. Remaining attempts are unrun.')


if __name__ == '__main__':
    main()
