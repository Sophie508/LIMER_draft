"""Build a separate M10 target without modifying frozen M8 or baseline artifacts."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    args=parser.parse_args();root=args.root.resolve()
    rel=Path('baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation')
    isolated=root/'m10_backend/simulation'
    if not isolated.exists():shutil.copytree(root/rel,isolated,symlinks=True)
    cpp=Path(__file__).with_name('LimerProgressDagReplay.cc')
    shutil.copy2(cpp,isolated/'scratch/LimerProgressDagReplay.cc')
    shutil.copy2(cpp.with_name('ack_progress_observer.h'),isolated/'scratch/ack_progress_observer.h')
    cmake=isolated/'scratch/CMakeLists.txt'
    content=cmake.read_text()
    marker='  else()\n    target_link_libraries(\n      ${target_prefix}${scratch_name} "${ns3-libs}" "${ns3-contrib-libs}"\n      "${ns3-external-libs}"\n    )\n  endif()'
    branch='  elseif(scratch_name STREQUAL "LimerProgressDagReplay")\n    target_link_libraries(${target_prefix}${scratch_name} ${libapplications} ${libinternet} ${libpoint-to-point} ${libcore} ${libnetwork} ${libstats} ${libmtp} "${ns3-external-libs}")\n'
    if 'elseif(scratch_name STREQUAL "LimerProgressDagReplay")' not in content:
        if content.count(marker)!=1:raise ValueError('unexpected scratch CMake schema')
        cmake.with_name('CMakeLists.before_m10.txt').write_text(content)
        cmake.write_text(content.replace(marker,branch+marker))
    command=['docker','--host','unix:///run/user/1005/limer-docker/docker.sock',
             'run','--rm','--name','limer-m10-build','--cpus=4','--memory=4g',
             '-v',str(root)+':/work','-v',str(isolated)+':/work/'+str(rel),
             '-w','/work/'+str(rel),'limer-simai-cpu:2026-10-10',
             'bash','-c','./ns3 build LimerProgressDagReplay -j 4']
    with (root/'logs/m10_build.log').open('w') as log:
        process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT)
    status=dict(exit_code=process.returncode,command=command,
                source_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),
                observer_sha256=hashlib.sha256(cpp.with_name('ack_progress_observer.h').read_bytes()).hexdigest())
    (root/'logs/m10_build_status.json').write_text(json.dumps(status,indent=2)+'\n')
    print(json.dumps(status));raise SystemExit(process.returncode)


if __name__=='__main__':main()
