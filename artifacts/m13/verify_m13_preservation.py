import hashlib,json,importlib.util
from pathlib import Path
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
digest=lambda p:hashlib.sha256(p.read_bytes()).hexdigest()
frozen=ROOT/'m13_source_frozen_adaptive_dev_v1';current=ROOT/'m13_source_frozen_adaptive_controls_v1'
science=['limer_v0/business_delivery.py','limer_v0/hybrid_delivery.py','limer_v0/early_delivery.py','limer_v0/batch_loss.py','simulation/LimerBusinessObservation.cc','simulation/business_observer.h','simulation/m13_batch_deficit_observer.h','simulation/probe_budget.h']
for rel in science:assert digest(frozen/rel)==digest(current/rel),rel
import sys
sys.path.insert(0,str(frozen))
def load(p,n):
 spec=importlib.util.spec_from_file_location(n,p);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m);return m
old=load(frozen/'simulation/run_business_observation.py','old_runner');new=load(current/'simulation/run_business_observation.py','new_runner')
for c in ['adaptive_development','adaptive_validation','adaptive_smoke']:
 assert old.make_trials(c)==new.make_trials(c),c
# Native M12 and frozen M12 science remain untouched by all M13 builds.
m12=ROOT/'m12_source_frozen_validation_v2'
assert m12.exists()
reg=json.loads((ROOT/'runs/m12_validation_v2/registration.json').read_text())
paths=dict(detector='limer_v0/hybrid_delivery.py',runner='simulation/run_hybrid_observation.py',cpp='simulation/LimerHybridObservation.cc',header='simulation/batch_deficit_observer.h',early_detector='limer_v0/early_delivery.py',base_detector='limer_v0/batch_loss.py')
for key,rel in paths.items():assert digest(m12/rel)==reg['hashes'][key],rel
binary=ROOT/'m12e_backend/simulation/build/scratch/ns3.36.1-LimerHybridObservation-debug'
assert digest(binary)==reg['hashes']['binary']
for name,sha in reg['library_hashes'].items():assert digest(binary.parent.parent/'lib'/name)==sha
print(json.dumps(dict(science_identical=True,primary_trials_identical=True,m12_source_binary_dependencies_preserved=True,science_hashes={rel:digest(frozen/rel) for rel in science},m12_science_hashes={rel:digest(m12/rel) for rel in paths.values()})))
