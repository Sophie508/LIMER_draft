"""One immutable simulation attempt and its independent validation stages."""
import os
from pathlib import Path
import subprocess
import time
from .archive import archive_run
from .config import METHODS
from .inputs import generate, inject
from .paths import ROOT, read_json, sha, write_json


def resolve_build(directory):
    directory = Path(directory).resolve()
    record = read_json(directory / 'build.json')
    if record.get('schema') != 'limer-build-v1': raise ValueError('Not a LIMER build descriptor')
    binary = directory / record.get('binary_relative', 'backend/build/scratch/ns3.36.1-LimerSimulator-debug')
    libraries = directory / record.get('libraries_relative', 'backend/build/lib')
    binary.resolve().relative_to(directory)
    libraries.resolve().relative_to(directory)
    if sha(binary) != record['binary_sha256']: raise ValueError('Binary differs from build record')
    for name, digest in record.get('library_hashes', {}).items():
        library = (libraries / name).resolve()
        library.relative_to(libraries.resolve())
        if sha(library) != digest: raise ValueError('Library differs from build record: ' + name)
    return record, binary, libraries


def run_case(build, out, method, scene, archive_to=None, keep_raw=True, timeout=5400):
    if method not in METHODS: raise ValueError('Unknown method: ' + method)
    out = Path(out).resolve()
    build_record, binary, libraries = resolve_build(build)
    out.mkdir(parents=True, exist_ok=False)
    generate(out / 'inputs', scene)
    inject(out / 'truth', scene)
    command = [str(binary), str(out / 'inputs/topology.txt'), str(out / 'inputs/config.txt'), str(out),
               method, str(scene.rounds), str(scene.horizon_ns), str(out / 'truth/injection.txt'), str(scene.chunks_per_phase),
               scene.detector, scene.policy, str(scene.canary_period_ns), str(scene.canary_bytes)]
    manifest = dict(schema='limer-run-v1', method=method, scene=scene.dictionary(), command=command,
        binary_sha256=build_record['binary_sha256'], build_sha256=sha(Path(build) / 'build.json'),
        input_hashes={p.relative_to(out).as_posix(): sha(p) for p in out.rglob('*') if p.is_file()})
    write_json(out / 'run_manifest.json', manifest)
    env = {k: v for k, v in os.environ.items() if not k.startswith('LIMER_')}
    env['LD_LIBRARY_PATH'] = str(libraries)
    started = time.monotonic()
    with (out / 'simulator.log').open('w') as log:
        result = subprocess.run(command, cwd=out, env=env, stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
    if result.returncode not in (0, 2):
        write_json(out / 'runner_error.json', dict(stage='simulation', exit_code=result.returncode))
        raise RuntimeError('Simulator failed: ' + str(out / 'simulator.log'))
    for stage in ['audit', 'replay', 'metrics']:
        with (out / (stage + '.log')).open('w') as log:
            r = subprocess.run([os.sys.executable, str(ROOT / 'limer.py'), stage, str(out)],
                               stdout=log, stderr=subprocess.STDOUT, timeout=timeout)
        if r.returncode:
            write_json(out / 'runner_error.json', dict(stage=stage, exit_code=r.returncode))
            raise RuntimeError('Validation failed: ' + str(out / (stage + '.log')))
    record = dict(name=out.name, method=method, family=scene.family, scene=scene.dictionary(),
                  status=read_json(out / 'run_status.json'), audit=read_json(out / 'audit.json'),
                  observation_audit=read_json(out / 'observation_audit.json'), performance=read_json(out / 'performance.json'))
    if archive_to:
        record['archive'] = archive_run(out, archive_to, prune=not keep_raw)
    record['wall_seconds'] = time.monotonic() - started
    write_json(out / 'result.json', record)
    return record
