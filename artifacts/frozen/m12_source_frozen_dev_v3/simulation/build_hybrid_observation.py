"""Build only M12 in an isolated copy of the existing pinned CPU backend."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    args=parser.parse_args()
    root=args.root.resolve()
    rel=Path("baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation")
    isolated=root/"m12c_backend/simulation"
    if not isolated.exists():
        shutil.copytree(root/"m8_backend/simulation",isolated,symlinks=True)
    cpp=Path(__file__).resolve().parent/"LimerHybridObservation.cc"
    shutil.copy2(cpp,isolated/"scratch/LimerHybridObservation.cc")
    shutil.copy2(cpp.with_name("batch_deficit_observer.h"),isolated/"scratch/batch_deficit_observer.h")
    cmake=isolated/"scratch/CMakeLists.txt"
    content=cmake.read_text()
    before='  else()\n    target_link_libraries(\n      ${target_prefix}${scratch_name} "${ns3-libs}" "${ns3-contrib-libs}"\n      "${ns3-external-libs}"\n    )\n  endif()'
    after='  elseif(scratch_name STREQUAL "LimerHybridObservation")\n    target_sources(${target_prefix}${scratch_name} PRIVATE ${PROJECT_SOURCE_DIR}/src/applications/model/simple-seq-ts-header.cc)\n    target_link_libraries(${target_prefix}${scratch_name} ${libcore} ${libnetwork} ${libinternet} ${libpoint-to-point} ${libmtp})\n'+before
    if 'elseif(scratch_name STREQUAL "LimerHybridObservation")' not in content:
        if content.count(before)!=1:raise ValueError("unexpected pinned scratch build schema")
        cmake.with_name("CMakeLists.before_m12.txt").write_text(content)
        cmake.write_text(content.replace(before,after))
    command=["docker","--host","unix:///run/user/1005/limer-docker/docker.sock",
             "run","--rm","--name","limer-m12-build-script","--cpus=1","--memory=4g",
             "-v",str(root)+":/work","-v",str(isolated)+":/work/"+str(rel),
             "-w","/work/"+str(rel),"limer-simai-cpu:2026-10-10",
             "bash","-c","./ns3 build LimerHybridObservation -j 1"]
    log=root/"logs/m12_reproducible_build.log"
    with log.open("w") as handle:
        process=subprocess.run(command,stdout=handle,stderr=subprocess.STDOUT)
    status=dict(exit_code=process.returncode,command=command,
                cpp_sha256=hashlib.sha256(cpp.read_bytes()).hexdigest(),
                cmake_sha256=hashlib.sha256(cmake.read_bytes()).hexdigest())
    (root/"logs/m12_build_status.json").write_text(json.dumps(status,indent=2)+"\n")
    print(json.dumps(status))
    raise SystemExit(process.returncode)


if __name__=="__main__":main()
