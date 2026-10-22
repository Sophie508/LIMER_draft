"""Gate frozen coverage development, then independently seeded validation."""
import json
from pathlib import Path
import shutil
import subprocess
import sys

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
STATE=ROOT/'logs/m13_coverage_pipeline_state.json'


def write(value): STATE.write_text(json.dumps(value,indent=2)+'\n')


def command(args,log):
    with (ROOT/'logs'/log).open('w') as handle:
        result=subprocess.run(args,stdout=handle,stderr=subprocess.STDOUT)
    if result.returncode:raise RuntimeError(f'{log} exited {result.returncode}')


def stage(source,campaign):
    write(dict(stage=campaign,status='RUNNING',source=source))
    command([sys.executable,str(ROOT/source/'simulation/run_business_observation.py'),
             '--root',str(ROOT),'--campaign',campaign,'--tag','v1','--workers','8'],f'm13_{campaign}_v1.log')
    terminal=json.loads((ROOT/'runs'/f'm13_{campaign}_v1/terminal.json').read_text())
    if not terminal['complete'] or set(terminal['statuses'])!={'PASS'}:raise RuntimeError('Incomplete/engineering-failed ledger')
    command([sys.executable,str(ROOT/'audit_m13_parallel.py'),'--root',str(ROOT),
             '--frozen',source,'--campaign',f'm13_{campaign}_v1'],f'm13_{campaign}_v1_final_audit.log')
    audit=json.loads((ROOT/'logs'/f'm13_{campaign}_v1_final_audit.json').read_text())
    if not audit['passed']:raise RuntimeError('Final independent audit failed')
    return terminal['summary']


def main():
    source='m13_source_frozen_coverage_dev_v1'
    d=ROOT/source;binary=ROOT/'m13d_backend/simulation/build/scratch/ns3.36.1-LimerBusinessObservation-debug'
    (d/'native_binary').mkdir(exist_ok=True);shutil.copy2(binary,d/'native_binary'/binary.name)
    try:
        development=stage(source,'coverage_development')
        if development['per_condition_95_verdict']!='PASS':
            write(dict(status='COMPLETE',stage='development_failed_scientifically',summary=development,
                       validation_launched=False));return
        validation_source='m13_source_frozen_coverage_validation_v1'
        shutil.copytree(d,ROOT/validation_source)
        validation=stage(validation_source,'coverage_validation')
        write(dict(status='COMPLETE',stage='validation_audited',development=development,
                   summary=validation,validation_launched=True))
    except Exception as error:
        write(dict(status='FAILED',reason=str(error)));raise


if __name__=='__main__':main()
