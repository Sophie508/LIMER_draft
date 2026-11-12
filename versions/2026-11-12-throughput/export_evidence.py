"""Export compact receipts and recheck every retained raw archive hash."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil


def sha(p):
    h=hashlib.sha256()
    with p.open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):h.update(b)
    return h.hexdigest()


def export(base,out):
    mapping={'pilot-v1':(base,'source-v1','project-v1'),
             'pilot-v2':(base/'iteration-v2','source-v2','project'),
             'policy-pilot-v2':(base/'iteration-v2','source-v2','project'),
             'full-v2':(base/'iteration-v2','source-v2','project')}
    out.mkdir(parents=True,exist_ok=False)
    archives=[]
    for group,(root,source,local_project) in mapping.items():
        origin=root/'results'/group;dest=out/group
        reg=json.loads((origin/'registration.json').read_text())
        assert all((origin/'attempts'/(c['name']+'.json')).exists() for c in reg['cases']),group+' incomplete'
        shutil.copytree(origin/'attempts',dest/'attempts')
        shutil.copy2(origin/'registration.json',dest/'registration.json')
        shutil.copy2(root/'build-v7/build.json',dest/'native-build.json')
        for c in reg['cases']:
            run=origin/'runs'/c['name'];target=dest/'runs'/c['name'];target.mkdir(parents=True)
            for name in ('run_status.json','run_manifest.json','result.json','audit.json','observation_audit.json',
                         'performance.json','archive_manifest.json','detector_events.csv','service_alarms.csv',
                         'phase_events.csv','phase_metrics.csv','control_events.csv','policy_decisions.jsonl',
                         'runner_error.json','simulator.log','audit.log','replay.log'):
                if (run/name).exists():shutil.copy2(run/name,target/name)
            for name in ('inputs','truth'):
                if (run/name).exists():shutil.copytree(run/name,target/name)
            if (run/'archive_manifest.json').exists():
                receipt=json.loads((run/'archive_manifest.json').read_text())
                archive=origin/'archives'/(c['name']+'.tar.gz')
                digest=sha(archive);assert digest==receipt['sha256'],str(archive)
                archives.append(dict(group=group,name=c['name'],path=str(archive),sha256=digest,
                                     bytes=archive.stat().st_size,all_member_hashes_verified=receipt['all_content_hashes_verified']))
        (dest/'source-location.json').write_text(json.dumps(dict(local_project=local_project,server_source=str(root/source)),indent=2)+'\n')
    (out/'archive-integrity.json').write_text(json.dumps(dict(archives=archives,all_archive_hashes_rechecked=True),indent=2)+'\n')
    files={p.relative_to(out).as_posix():sha(p) for p in sorted(out.rglob('*')) if p.is_file()}
    (out/'COMPACT_MANIFEST.json').write_text(json.dumps(dict(files=files,raw_archives_included=False),indent=2)+'\n')
    print(json.dumps(dict(groups=len(mapping),archives=len(archives),compact_files=len(files))))


if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('base',type=Path);p.add_argument('out',type=Path)
    a=p.parse_args();export(a.base,a.out)
