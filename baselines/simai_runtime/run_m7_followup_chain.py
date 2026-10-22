"""Wait for the frozen matrix, then run predeclared stress/cost references."""
from pathlib import Path
import json
import subprocess
import time

ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
ledger=ROOT/'logs/m7_validation_v3_summary.json'
while not ledger.exists():
    time.sleep(5)
rows=json.loads(ledger.read_text())
assert len(rows)==100 and all('exit_code' in r for r in rows)
assert all(r['exit_code']==0 for r in rows), 'Infrastructure/execution failure: inspect before new launches'
print('All100validationattemptsterminal; starting separately registered stress.', flush=True)
for stage in ['stress','sensor_off']:
    path=ROOT/'baselines/simai_runtime'/f'run_m7_{stage}_v3.py'
    with (ROOT/'logs'/f'm7_{stage}_v3_driver.log').open('w') as log:
        result=subprocess.run(['python3',str(path)],stdout=log,stderr=subprocess.STDOUT)
    assert result.returncode==0, f'{stage} driver failed; preserve ledger and inspect'
    print(stage,'driverterminal',flush=True)
subprocess.run(['python3',str(ROOT/'baselines/simai_runtime/collect_m7_reference_cost.py')],check=True)
