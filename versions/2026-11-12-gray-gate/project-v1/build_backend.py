"""Bootstrap a clean, source-only backend build for the independent delivery."""
import argparse
import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import time

PROJECT = Path(__file__).resolve().parent


def sha(p):
    return hashlib.sha256(p.read_bytes()).hexdigest()


def build(out, jobs, resume=False):
    out = Path(out).resolve()
    if out.exists() and not resume: raise FileExistsError('Build directory must be new: ' + str(out))
    if resume and not (out / 'backend/CMakeLists.txt').exists(): raise ValueError('Not a LIMER backend build')
    out.mkdir(parents=True, exist_ok=resume)
    backend = out / 'backend'
    shutil.copytree(PROJECT / 'third_party/ns3', backend, dirs_exist_ok=resume)
    shutil.copytree(PROJECT / 'src/simulator', backend / 'scratch/limer', dirs_exist_ok=resume)
    # Root scratch owns the executable; subdirectories only supply headers.
    shutil.copyfile(PROJECT / 'src/simulator/main.cc', backend / 'scratch/LimerSimulator.cc')
    (backend / 'scratch/limer/CMakeLists.txt').write_text('# Header-only application modules\n')
    (backend / 'ns3').chmod(0o755)
    commands = [
        ['./ns3', 'configure', '-d', 'debug', '--enable-mtp', '--enable-modules=applications;csma;point-to-point;mtp'],
        ['cmake', '-S', '.', '-B', 'cmake-cache', '-DCMAKE_CXX_FLAGS_DEBUG=-O2 -g'],
        ['cmake', '--build', 'cmake-cache', '--target', 'scratch_LimerSimulator', '--parallel', str(jobs)],
    ]
    started = time.monotonic()
    sources = {str(p.relative_to(PROJECT)): sha(p) for d in ['src', 'third_party']
               for p in sorted((PROJECT / d).rglob('*')) if p.is_file()}
    with (out / 'build.log').open('w') as log:
        for command in commands:
            log.write(json.dumps(command) + '\n'); log.flush()
            r = subprocess.run(command, cwd=backend, stdout=log, stderr=subprocess.STDOUT)
            if r.returncode:
                print((out / 'build.log').read_text()[-12000:])
                raise RuntimeError('Build failed; see ' + str(out / 'build.log'))
    binary = backend / 'build/scratch/ns3.36.1-LimerSimulator-debug'
    current = {str(p.relative_to(PROJECT)): sha(p) for d in ['src', 'third_party']
               for p in sorted((PROJECT / d).rglob('*')) if p.is_file()}
    if current != sources: raise RuntimeError('Source changed during compilation; make a new build')
    record = dict(schema='limer-build-v1', binary=str(binary), binary_sha256=sha(binary),
                  binary_relative='backend/build/scratch/ns3.36.1-LimerSimulator-debug',
                  libraries_relative='backend/build/lib',
                  libraries=str(backend / 'build/lib'), seconds=time.monotonic()-started,
                  source_hashes=sources,
                  library_hashes={p.name: sha(p) for p in (backend / 'build/lib').glob('*.so')},
                  compiler=subprocess.check_output(['c++', '--version'], text=True).splitlines()[0],
                  profile='O2 debug checks; standalone network backend; no AstraSim frontend')
    (out / 'build.json').write_text(json.dumps(record, indent=2) + '\n')
    print(json.dumps(dict(build='passed', binary=str(binary), sha256=record['binary_sha256'], seconds=record['seconds'])), flush=True)


if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--out', type=Path, required=True)
    p.add_argument('--jobs', type=int, default=2)
    p.add_argument('--resume', action='store_true', help='Reconfigure this new project build after a development fix')
    a = p.parse_args()
    build(a.out, a.jobs, a.resume)
