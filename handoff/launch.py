"""Run archived campaigns after explicit infrastructure-only path adaptation."""
import argparse
import hashlib
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys

REPO = Path(__file__).resolve().parents[1]
OLD_ROOT = '/home/suliu/scratch/LIMER_WORK_2026-10-10'
OLD_SOCKET = 'unix:///run/user/1005/limer-docker/docker.sock'
ENTRIES = {
    'm8': 'simulation/run_batch_observation.py',
    'm9': 'simulation/run_dynamic_dag_gates.py',
    'm10': 'simulation/run_progress_development.py',
    'm11': 'simulation/run_closed_loop.py',
    'm12': 'simulation/run_hybrid_observation.py',
    'm13': 'simulation/run_business_observation.py',
    'optcc': 'baselines/simai_runtime/run_gates_and_measurements.py',
    'static': 'baselines/simai_runtime/run_dual_calibration_ecn_v1.py',
    'static-extra': 'baselines/simai_runtime/run_dual_calibration_extra.py',
}


def stage(root, socket, image):
    manifest = {}
    for directory in ('limer_v0', 'simulation', 'configs', 'baselines/simai_runtime', 'baselines/optcc_checks'):
        for path in (REPO / directory).rglob('*'):
            if not path.is_file() or '__pycache__' in path.parts:
                continue
            relative = path.relative_to(REPO)
            destination = root / relative
            destination.parent.mkdir(parents=True, exist_ok=True)
            original = path.read_bytes()
            data = original
            # Never change C++ implementations or Python detector modules.
            if path.suffix in ('.py', '.sh') and directory in ('simulation', 'baselines/simai_runtime'):
                data = original.decode().replace(OLD_ROOT, str(root)).replace(OLD_SOCKET, socket).replace('limer-simai-cpu:2026-10-10', image).encode()
            if destination.exists() and destination.read_bytes() != data:
                raise FileExistsError('Source staging would change a previous workspace. Use a new root: ' + str(destination))
            destination.write_bytes(data)
            manifest[str(relative)] = dict(original_sha256=hashlib.sha256(original).hexdigest(),
                                           staged_sha256=hashlib.sha256(data).hexdigest(), adapted=data != original)
    for directory in ('limer_source_guarded_v1', 'limer_source_m7_tcp_v3'):
        source = REPO / 'artifacts/frozen' / directory
        target = root / directory
        if source.exists() and not target.exists():
            shutil.copytree(source, target)
    (root / 'logs').mkdir(exist_ok=True)
    (root / 'runs').mkdir(exist_ok=True)
    (root / 'mininet_results').mkdir(exist_ok=True)
    record = root / 'logs/handoff_source_adaptations.json'
    record.write_text(json.dumps(dict(changes='Root path, Docker socket and image strings only in staged infrastructure scripts', files=manifest), indent=2) + '\n')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('stage', choices=ENTRIES)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--docker-host', default=os.environ.get('DOCKER_HOST', 'unix:///var/run/docker.sock'))
    parser.add_argument('--image', default='limer-simai-cpu:2026-10-10')
    args, extra = parser.parse_known_args()
    if extra and extra[0] == '--':
        extra = extra[1:]
    root = args.root.expanduser().resolve()
    if root == REPO or root.is_relative_to(REPO):
        parser.error('Use a separate scratch root outside this source repository')
    root.mkdir(parents=True, exist_ok=True)
    stage(root, args.docker_host, args.image)
    entry = root / ENTRIES[args.stage]
    command = [sys.executable, str(entry)]
    if args.stage in ('m8', 'm9', 'm10', 'm11', 'm12', 'm13'):
        command += ['--root', str(root)]
    environment = dict(os.environ)
    environment['PYTHONPATH'] = str(root) + os.pathsep + str(root / 'baselines/simai_runtime')
    subprocess.run(command + extra, cwd=root, env=environment, check=True)


if __name__ == '__main__':
    main()
