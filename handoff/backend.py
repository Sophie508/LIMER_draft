"""Prepare an isolated pinned SimAI backend and build authored replay targets."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import tarfile
import urllib.request

REPO = Path(__file__).resolve().parents[1]
SIMAI = 'f5efb5a93ea9be7db25a8843f9f7ff54044f6062'
NS3 = '7e3cb5b88c99abcb582c5abc3919484a4805111b'
REL = Path('baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation')
TARGETS = {
    'm8': ('LimerBatchObservation', 'm8_backend'),
    'm9': ('LimerDynamicDagReplay', 'm9_backend'),
    'm10': ('LimerProgressDagReplay', 'm10_backend'),
    'm11': ('LimerClosedLoopReplay', 'm11_backend'),
    'm12': ('LimerHybridObservation', 'm12e_backend'),
    'm13': ('LimerBusinessObservation', 'm13e_backend'),
    'optcc': ('LimerDagReplay', str(REL.parent)),
    'static': ('LimerDualPlaneReplay', str(REL.parent)),
}


def docker(host):
    return ['docker'] + (['--host', host] if host else [])


def download_archive(project, commit, cache):
    archive = cache / (project + '-' + commit + '.tar.gz')
    if not archive.exists():
        temporary = archive.with_suffix('.part')
        url = f'https://codeload.github.com/aliyun/{project}/tar.gz/{commit}'
        with urllib.request.urlopen(url, timeout=120) as response, temporary.open('wb') as handle:
            shutil.copyfileobj(response, handle)
        temporary.rename(archive)
    return archive


def extract(archive, destination):
    if destination.exists() and any(destination.iterdir()):
        raise FileExistsError('Refusing to replace upstream sources: ' + str(destination))
    destination.mkdir(parents=True, exist_ok=True)
    with tarfile.open(archive) as source:
        members = source.getmembers()
        prefix = members[0].name.split('/')[0] + '/'
        for member in members:
            if not member.name.startswith(prefix):
                continue
            member.name = member.name[len(prefix):]
            if not member.name:
                continue
            target = (destination / member.name).resolve()
            if not target.is_relative_to(destination.resolve()) or member.issym() or member.islnk():
                raise ValueError('Unsafe upstream archive member: ' + member.name)
            source.extract(member, destination, filter='data')


def prepare(root):
    base = root / 'baselines/SimAI-official'
    marker = root / 'logs/handoff_backend_prepared.json'
    if marker.exists():
        print('Using already prepared isolated backend:', root)
        return
    if base.exists():
        raise FileExistsError('Refusing to modify an unregistered backend: ' + str(base))
    cache = root / 'downloads'
    cache.mkdir(parents=True, exist_ok=True)
    (root / 'logs').mkdir(exist_ok=True)
    archives = [download_archive('SimAI', SIMAI, cache), download_archive('ns-3-alibabacloud', NS3, cache)]
    expected = json.loads((REPO / 'handoff/upstream.lock.json').read_text())['archives']
    for archive in archives:
        if hashlib.sha256(archive.read_bytes()).hexdigest() != expected[archive.name]:
            raise ValueError('Pinned upstream archive hash mismatch: ' + archive.name)
    extract(archives[0], base)
    extract(archives[1], base / 'ns-3-alibabacloud')
    astra = base / 'astra-sim-alibabacloud'
    backend = root / REL
    shutil.copytree(base / 'ns-3-alibabacloud', backend.parent, dirs_exist_ok=True)
    shutil.copytree(astra / 'astra-sim', backend / 'src/applications/astra-sim')
    frontend = astra / 'astra-sim/network_frontend/ns3'
    for path in [frontend / 'AstraSimNetwork.cc', *frontend.glob('*.h')]:
        shutil.copy2(path, backend / 'scratch' / path.name)
    # Same published transport correction, in a fresh copy only.
    patch = REPO / 'baselines/simai_runtime/transport_repair.diff'
    subprocess.run(['patch', '--batch', '--forward', '-p1', '-i', str(patch)], cwd=backend, check=True)
    header = backend / 'src/applications/astra-sim/system/RecvPacketEventHadndlerData.hh'
    text = header.read_text()
    anchor = '  RecvPacketEventHadndlerData(\n'
    if text.count(anchor) != 1:
        raise ValueError('Unexpected pinned callback header')
    text = text.replace(anchor, '''  // Direct-network callback data; no BaseStream or Sys clock is required.
  RecvPacketEventHadndlerData(EventType event, AstraSim::ncclFlowTag tag)
      : BasicEventHandlerData(nullptr, event), owner(nullptr), vnet(0),
        stream_num(0), message_end(true), ready_time(0), flow_id(-1),
        channel_id(tag.channel_id), child_flow_id(-1), flowTag(tag) {}
''' + anchor)
    header.write_text(text)
    entry = (frontend / 'entry.h').read_text()
    if entry.count('AstraSim::Sys::boostedTick()') != 4:
        raise ValueError('Unexpected pinned entry clock calls')
    (backend / 'scratch/replay_entry.h').write_text(entry.replace('AstraSim::Sys::boostedTick()', 'Simulator::Now().GetNanoSeconds()'))
    marker.write_text(json.dumps(dict(SimAI=SIMAI, ns3=NS3,
        archives={p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in archives},
        transport_patch_sha256=hashlib.sha256(patch.read_bytes()).hexdigest()), indent=2) + '\n')


def build(root, stage, host, image, jobs):
    name, directory = TARGETS[stage]
    base = root / REL
    isolated = root / directory / 'simulation'
    if isolated != base and not isolated.exists():
        shutil.copytree(base, isolated, ignore=shutil.ignore_patterns('build', 'cmake-cache', '__pycache__'))
    source = REPO / ('baselines/simai_runtime' if stage in ('optcc', 'static') else 'simulation')
    for path in source.iterdir():
        if path.suffix in ('.cc', '.h'):
            shutil.copy2(path, isolated / 'scratch' / path.name)
    # Retain the pinned scratch generator and add only target-specific links.
    cmake = isolated / 'scratch/CMakeLists.txt'
    content = cmake.read_text()
    marker = '  else()\n    target_link_libraries(\n      ${target_prefix}${scratch_name} "${ns3-libs}" "${ns3-contrib-libs}"\n      "${ns3-external-libs}"\n    )\n  endif()'
    branch = f'  elseif(scratch_name STREQUAL "{name}")\n'
    if stage in ('m8', 'm12', 'm13'):
        branch += '    target_sources(${target_prefix}${scratch_name} PRIVATE ${PROJECT_SOURCE_DIR}/src/applications/model/simple-seq-ts-header.cc)\n'
        branch += '    target_link_libraries(${target_prefix}${scratch_name} ${libcore} ${libnetwork} ${libinternet} ${libpoint-to-point} ${libmtp})\n'
    else:
        branch += '    target_link_libraries(${target_prefix}${scratch_name} ${libapplications} ${libinternet} ${libpoint-to-point} ${libcore} ${libnetwork} ${libstats} ${libmtp} "${ns3-external-libs}")\n'
    if f'elseif(scratch_name STREQUAL "{name}")' not in content:
        if content.count(marker) != 1:
            raise ValueError('Unexpected pinned CMake schema')
        cmake.write_text(content.replace(marker, branch + marker))
    mount = ['-v', str(root) + ':/work', '-v', str(isolated) + ':/work/' + str(REL), '-w', '/work/' + str(REL)]
    for command in (['./ns3', 'configure', '-d', 'debug', '--enable-mtp'], ['./ns3', 'build', name, '-j', str(jobs)]):
        subprocess.run(docker(host) + ['run', '--rm', '--cpus', str(jobs), '--memory', '4g'] + mount + [image] + command, check=True)
    binary = isolated / 'build/scratch' / ('ns3.36.1-' + name + '-debug')
    record = dict(stage=stage, binary=str(binary), sha256=hashlib.sha256(binary.read_bytes()).hexdigest(),
                  source_sha256=hashlib.sha256((source / (name + '.cc')).read_bytes()).hexdigest())
    (root / 'logs' / ('handoff_build_' + stage + '.json')).write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(record))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('action', choices=('prepare', 'image', 'build'))
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--stage', choices=TARGETS, default='m13')
    parser.add_argument('--docker-host', default='')
    parser.add_argument('--image', default='limer-simai-cpu:2026-10-10')
    parser.add_argument('--jobs', type=int, default=2, choices=range(1, 9))
    args = parser.parse_args()
    root = args.root.expanduser().resolve()
    if root == REPO or root.is_relative_to(REPO):
        parser.error('Use a separate scratch directory outside the source repository')
    root.mkdir(parents=True, exist_ok=True)
    if args.action == 'image':
        subprocess.run(docker(args.docker_host) + ['build', '-t', args.image, '-f', str(REPO / 'baselines/simai_runtime/Dockerfile'), str(REPO / 'baselines/simai_runtime')], check=True)
    elif args.action == 'prepare':
        prepare(root)
    else:
        if not (root / 'logs/handoff_backend_prepared.json').exists():
            parser.error('Run prepare first in this isolated workspace')
        build(root, args.stage, args.docker_host, args.image, args.jobs)


if __name__ == '__main__':
    main()
