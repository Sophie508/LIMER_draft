"""Register the matched full-ring lifetime control before its execution."""
from copy import deepcopy
import json
from pathlib import Path
import sys
import time

base=Path(sys.argv[1]);out=Path(sys.argv[2])
p=json.loads((base/'registration.json').read_text())
case=deepcopy(next(c for c in p['cases'] if c['name']=='full-ring-blackhole-G11-benefit'))
case['name']='full-ring-blackhole-G11-benefit-persistent'
case['scene']['replacement_lifetime']='persistent'
p.update(cases=[case],run_count=1,registered_unix=time.time(),
    role='Separate preregistered development follow-up; not pooled as independent trials',
    rationale='The short phase reset costs more time, while the longer four-phase pilot differs little. Isolate binding lifetime over a full 30-phase workload with identical physical inputs and detector costs.',
    parent_registration_sha256=__import__('hashlib').sha256((base/'registration.json').read_bytes()).hexdigest())
out.mkdir(parents=True,exist_ok=False)
(out/'registration.json').write_text(json.dumps(p,indent=2)+'\n')
print(json.dumps(dict(registered=case['name'],role=p['role'])))
