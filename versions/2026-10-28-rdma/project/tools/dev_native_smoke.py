"""Registered development diagnostics, never relabelled as frozen validation."""
import json
from pathlib import Path
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'python'))
from limerlab.config import Scenario
from limerlab.runner import run_case

ROOT=Path('/work/results/smoke-dev1')
ROOT.mkdir(exist_ok=False)
cases=[dict(name=family,family=family,method='G11',scene=Scenario(family=family,rounds=8,
    chunks_per_phase=16,horizon_ns=250000000,fault_ns=55000000,node=6,seed=710001,
    detector='service',policy='always').dictionary()) for family in ('healthy','quarter','weak_loss','blackhole')]
(ROOT/'registration.json').write_text(json.dumps(dict(phase='development',
    changed='Costed 64KiB/2ms real RDMA canaries; learned service detector; always replacement baseline',
    expected='Healthy clear; quarter and blackhole alarms; weak-loss tail checked without promise',cases=cases),indent=2))
def run(case):
    try:
        result=run_case('/work/build-dev', ROOT/case['name'],case['method'],Scenario(**case['scene']))
        print(json.dumps(dict(name=case['name'],status='checked',result=result)),flush=True)
    except Exception as exc:
        print(json.dumps(dict(name=case['name'],status='error',error=repr(exc))),flush=True)
with ThreadPoolExecutor(max_workers=4) as pool:
    for result in as_completed([pool.submit(run,case) for case in cases]): result.result()
