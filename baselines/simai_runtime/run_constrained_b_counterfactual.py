from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path
import time
from continue_campaign import run, ROOT, SOURCE

# Wait on the registered current campaign rather than exceeding two lifecycles.
while not (ROOT/'logs/continuation_summary.json').exists():time.sleep(2)
while not ((ROOT/'logs/guarded_expansion_blocked.json').exists() or (ROOT/'logs/guarded_expansion_summary.json').exists()):time.sleep(2)
folder=ROOT/SOURCE/'configs/m5_constrained_counterfactual'
folder.mkdir(exist_ok=False)
base=json.loads((ROOT/SOURCE/'configs/m4b_policy/aa12_policy_stay.json').read_text())
base.pop('host_gate',None)
base.pop('detector_rule',None)
for arm in ('stay','switch'):
    config=dict(base)
    config.update(condition='C1' if arm=='stay' else 'C4',detector=False,
        recovery=arm=='switch',oracle=arm=='switch',recovery_policy='none' if arm=='stay' else 'localized',
        scenario_id='AA9_STAY' if arm=='stay' else 'AA10_SWITCH',
        what_changes=f'Fixed {arm} under25% loss and10Mbit alternate access; no adaptive decision.',
        expected='Measure episode completion with failures retained; branch optimality is a hypothesis.')
    (folder/f'{arm}.json').write_text(json.dumps(config,indent=2)+'\n')
tasks=[(f'm5_b10_fixed_{arm}_r{i:02}',f'configs/m5_constrained_counterfactual/{arm}.json',SOURCE,False)
       for i in range(1,4) for arm in ('stay','switch')]
(ROOT/'logs/b10_counterfactual_registration.json').write_text(json.dumps(tasks,indent=2)+'\n')
with ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(run,tasks))
(ROOT/'logs/b10_counterfactual_summary.json').write_text(json.dumps(results,indent=2)+'\n')
