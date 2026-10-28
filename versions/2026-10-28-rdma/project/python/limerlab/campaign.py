"""Preregistered paired execution with a self-contained frozen Python toolchain."""
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import json
from pathlib import Path
import shutil
import subprocess
import sys
import threading
from .config import METHODS, Scenario
from .paths import ROOT, read_json, sha, tree_hashes, write_json
from .runner import resolve_build


def execute(build, out, preset, workers=2, resume=False):
    build, out, preset = Path(build).resolve(), Path(out).resolve(), Path(preset).resolve()
    if workers < 1: raise ValueError('workers must be positive')
    plan = read_json(preset)
    cases = plan['cases']
    names = [c['name'] for c in cases]
    if len(names) != len(set(names)) or any(Path(n).name != n for n in names):
        raise ValueError('Case names must be unique simple filenames')
    for c in cases:
        Scenario(**c['scene'])
        if c['method'] not in METHODS: raise ValueError('Unknown method')
    build_record, _, _ = resolve_build(build)
    registration_path = out / 'registration.json'
    if out.exists():
        if not resume: raise FileExistsError(out)
        registration = read_json(registration_path)
        if (registration['cases'] != cases or registration['build_sha256'] != sha(build / 'build.json') or
                registration['preset_sha256'] != sha(preset)):
            raise ValueError('Registered inputs or build changed')
        if tree_hashes(out / 'tooling') != registration['tooling_hashes']:
            raise ValueError('Frozen Python/configuration sources changed')
    else:
        out.mkdir(parents=True)
        snapshot = out / 'tooling'
        for name in ['python', 'configs', 'experiments', 'tests']:
            shutil.copytree(ROOT / name, snapshot / name, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copyfile(ROOT / 'limer.py', snapshot / 'limer.py')
        registration = dict(schema='limer-registration-v1', created_utc=datetime.now(timezone.utc).isoformat(),
            name=plan['name'], cases=cases, workers=workers, build_sha256=sha(build / 'build.json'),
            binary_sha256=build_record['binary_sha256'], preset_sha256=sha(preset),
            tooling_hashes=tree_hashes(snapshot), policy='M13-only diagnosis; persistent B-prime; fixed versus adaptive splitting')
        write_json(registration_path, registration)
        shutil.copyfile(build / 'build.json', out / 'build.json')
        for name in ['runs', 'cases', 'logs', 'archives']: (out / name).mkdir()
        for c in cases: write_json(out / 'cases' / (c['name'] + '.json'), c)
    results_path = out / 'results.json'
    results = read_json(results_path) if results_path.exists() else []
    for r in results:
        if not r['audit']['pass'] or not r['observation_audit']['pass']:
            raise ValueError('Cannot reuse failed evidence')
        archive = out / 'archives' / (r['name'] + '.tar.gz')
        if sha(archive) != r['archive']['sha256']: raise ValueError('Retained archive changed')
    lock = threading.Lock()

    def state(status, **values):
        write_json(out / 'campaign_state.json', dict(status=status, verified=len(results), expected=len(cases),
            updated_utc=datetime.now(timezone.utc).isoformat(), **values))

    def run(case):
        destination = out / 'runs' / case['name']
        if destination.exists(): raise ValueError('Incomplete attempt retained; use a new campaign directory: ' + str(destination))
        command = [sys.executable, str(out / 'tooling/limer.py'), 'run', '--build', str(build),
                   '--out', str(destination), '--case', str(out / 'cases' / (case['name'] + '.json')),
                   '--archive-to', str(out / 'archives' / (case['name'] + '.tar.gz')), '--prune-raw']
        with (out / 'logs' / (case['name'] + '.log')).open('w') as log:
            process = subprocess.run(command, stdout=log, stderr=subprocess.STDOUT)
        if process.returncode: raise RuntimeError('Case failed: ' + case['name'] + '; inspect logs')
        result = read_json(destination / 'result.json')
        with lock:
            results.append(result)
            temporary = results_path.with_suffix('.tmp')
            write_json(temporary, results); temporary.replace(results_path)
            state('running')
        print(json.dumps(dict(name=case['name'], status=result['status']['status'],
                              communication_ms=result['performance']['communication_ms'], checked=True)), flush=True)
    state('running')
    try:
        retained = {r['name'] for r in results}
        for group in [[c for c in cases if c['family'] == 'healthy'], [c for c in cases if c['family'] != 'healthy']]:
            with ThreadPoolExecutor(max_workers=workers) as pool:
                futures = [pool.submit(run, c) for c in group if c['name'] not in retained]
                try:
                    for f in as_completed(futures): f.result()
                except Exception:
                    for f in futures: f.cancel()
                    raise
        state('complete')
    except Exception as error:
        state('stopped_on_error', error=str(error))
        raise
    finally:
        from .report import report
        report(out)
