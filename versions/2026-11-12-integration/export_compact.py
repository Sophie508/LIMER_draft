"""Export all registered attempts; large raw archives remain at the server."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def export(base,out):
    names=('development-v1','lifetime-full-v1','gray-full-v1')
    for name in names:
        root=base/'results'/name
        plan=json.loads((root/'registration.json').read_text())
        assert all((root/'attempts'/(c['name']+'.json')).exists() for c in plan['cases']),name+' is incomplete'
    out.mkdir(parents=True,exist_ok=False)
    for name in names:
        root=base/'results'/name;dest=out/name
        shutil.copytree(root/'attempts',dest/'attempts')
        shutil.copy2(root/'registration.json',dest/'registration.json')
        for c in json.loads((root/'registration.json').read_text())['cases']:
            run=root/'runs'/c['name'];target=dest/'runs'/c['name'];target.mkdir(parents=True)
            for f in ('run_status.json','run_manifest.json','result.json','audit.json','observation_audit.json','performance.json','archive_manifest.json','detector_events.csv','service_alarms.csv','phase_events.csv','phase_metrics.csv','control_events.csv','policy_decisions.jsonl','runner_error.json','simulator.log'):
                if (run/f).exists():shutil.copy2(run/f,target/f)
            for d in ('inputs','truth'):
                if (run/d).exists():shutil.copytree(run/d,target/d)
    shutil.copy2(base/'build-v7/build.json',out/'native-build.json')
    files={p.relative_to(out).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in sorted(out.rglob('*')) if p.is_file()}
    receipt=dict(schema='limer-phase-integration-compact-v1',files=files,
        raw_archive_location=str(base/'results'),raw_archives_included=False,
        scope='Compact execution, replay, scoring and archive receipts. Raw packet replay requires the retained server archives; this export is not a new raw replay.')
    (out/'COMPACT_MANIFEST.json').write_text(json.dumps(receipt,indent=2)+'\n')
    print(json.dumps(dict(files=len(files),bytes=sum(p.stat().st_size for p in out.rglob('*') if p.is_file()))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('out',type=Path);a=p.parse_args();export(a.base,a.out)
