"""Retain every invalid-setup registration including undispatched attempts."""
import json
from pathlib import Path


def main():
    root=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10');d=root/'runs/m13_development_v1'
    reg=json.loads((d/'registration.json').read_text());rows=[]
    for t in reg['trials']:
        p=d/t['id']/'status.json'
        if p.exists():
            r=json.loads(p.read_text())
            if r['status']=='RUNNING':
                r=dict(id=t['id'],status='INTERRUPTED',prior_status=r,
                       reason='Invalid sparse-40 setup discovered; process interrupted; no validated exit status')
        else:r=dict(id=t['id'],status='UNRUN',reason='Stopped invalid setup before dispatch')
        rows.append(r)
    status={k:sum(r['status']==k for r in rows) for k in ('PASS','FAILED','INTERRUPTED','UNRUN')}
    out=dict(all_registrations_accounted=True,run_complete=False,scientific_verdict='FAIL',
             reason='sparse_reorder40 actually deferred 80 ms; not acceptance evidence',
             registered=len(rows),statuses=status,trials=rows)
    (d/'interruption_ledger.json').write_text(json.dumps(out,indent=2)+'\n')
    print(status)


if __name__=='__main__':main()
