"""Register full-ring weak-loss integration checks without replacing short runs."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
import time

base=Path(sys.argv[1]);out=Path(sys.argv[2])
p=json.loads((base/'registration.json').read_text())
cases=[]
for policy in ('always','benefit'):
    case=deepcopy(next(c for c in p['cases'] if c['name']=='full-ring-blackhole-G11-'+policy))
    case['name']='full-ring-weak_loss-G11-'+policy
    case['scene']['family']='weak_loss'
    cases.append(case)
p.update(cases=cases,run_count=2,registered_unix=time.time(),
    role='Separate preregistered weak-loss integration follow-up, not pooled independent acceptance',
    rationale='The four-phase weak-loss runs finish shortly after diagnosis and show no new B-prime work. Test the unchanged per-phase workload over the default full 30 phases, keeping all original short outcomes.',
    parent_registration_sha256=hashlib.sha256((base/'registration.json').read_bytes()).hexdigest())
out.mkdir(parents=True,exist_ok=False)
(out/'registration.json').write_text(json.dumps(p,indent=2)+'\n')
print(json.dumps(dict(registered=[c['name'] for c in cases],role=p['role'])))
