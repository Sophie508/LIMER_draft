"""The project's single public command-line interface."""
import argparse
import json
from pathlib import Path
import subprocess
import sys
from .paths import ROOT, read_json, write_json


def main():
    parser = argparse.ArgumentParser(prog='limer', description='Dual-plane adaptive splitting and M13-driven GPU relay recovery')
    commands = parser.add_subparsers(dest='command', required=True)
    build = commands.add_parser('build', help='Compile the owned simulator from vendored source')
    build.add_argument('--out', type=Path, required=True)
    build.add_argument('--jobs', type=int, default=2)
    run = commands.add_parser('run', help='Run and independently audit one immutable case')
    run.add_argument('--build', type=Path, required=True)
    run.add_argument('--out', type=Path, required=True)
    run.add_argument('--method', choices=['G00', 'G10', 'G01', 'G11'], default='G11')
    run.add_argument('--scenario', default='healthy')
    run.add_argument('--rounds', type=int, default=2)
    run.add_argument('--chunks', type=int, default=64)
    run.add_argument('--horizon-ms', type=float, default=2500)
    run.add_argument('--fault-ms', type=float, default=20)
    run.add_argument('--node', type=int, default=0)
    run.add_argument('--seed', type=int, default=100001)
    run.add_argument('--local-gbps', type=int, default=2400)
    run.add_argument('--detector', choices=['legacy','service'], default='legacy')
    run.add_argument('--policy', choices=['always','benefit'], default='always')
    run.add_argument('--fault-duration-ms', type=float, default=0)
    run.add_argument('--canary-period-ns', type=int, default=2000000)
    run.add_argument('--case', type=Path, help='Exact preregistered case JSON; overrides scalar scenario arguments')
    run.add_argument('--archive-to', type=Path)
    run.add_argument('--prune-raw', action='store_true')
    for name in ['audit', 'replay', 'metrics']:
        p = commands.add_parser(name, help='Run the independent ' + name + ' stage')
        p.add_argument('directory', type=Path)
    check = commands.add_parser('check', help='Run project unit tests')
    check.add_argument('--verbose', action='store_true')
    commands.add_parser('verify', help='Verify delivery checksums, validated source and regression evidence')
    campaign = commands.add_parser('campaign', help='Freeze and execute a paired experiment preset')
    campaign.add_argument('--build', type=Path, required=True)
    campaign.add_argument('--out', type=Path, required=True)
    campaign.add_argument('--preset', type=Path, default=ROOT / 'experiments/qualification.json')
    campaign.add_argument('--workers', type=int, default=2)
    campaign.add_argument('--resume', action='store_true')
    report = commands.add_parser('report', help='Summarize every registered case, including unfinished tasks')
    report.add_argument('directory', type=Path)
    reference = commands.add_parser('verify-reference', help='Verify the immutable published reference evidence')
    reference.add_argument('--extract', type=Path)
    a = parser.parse_args()
    if a.command == 'build':
        if a.jobs < 1: parser.error('--jobs must be positive')
        raise SystemExit(subprocess.call([sys.executable, str(ROOT / 'build_backend.py'), '--out', str(a.out), '--jobs', str(a.jobs)]))
    if a.command == 'run':
        from .config import Scenario
        from .runner import run_case
        if a.case:
            case = read_json(a.case)
            method, scene = case['method'], Scenario(**case['scene'])
        else:
            method = a.method
            scene = Scenario(a.scenario, a.rounds, a.chunks, round(a.horizon_ms*1000000),
                             round(a.fault_ms*1000000), a.node, a.seed, a.local_gbps,
                             detector=a.detector,policy=a.policy,fault_duration_ns=round(a.fault_duration_ms*1000000),
                             canary_period_ns=a.canary_period_ns)
        result = run_case(a.build, a.out, method, scene, a.archive_to, not a.prune_raw)
        print(json.dumps(dict(name=result['name'], status=result['status']['status'],
                              communication_ms=result['performance']['communication_ms'],
                              fresh_proxy=result['status']['new_proxy_chunks'], checks_passed=True)))
    elif a.command == 'audit':
        from .audit import audit
        result = audit(a.directory)
        result['pass'] = result.pop('pass_')
        write_json(a.directory / 'audit.json', result)
        print(json.dumps(result)); raise SystemExit(not result['pass'])
    elif a.command == 'replay':
        from .replay import replay
        result = replay(a.directory)
        write_json(a.directory / 'observation_audit.json', result)
        print(json.dumps(result)); raise SystemExit(not result['pass'])
    elif a.command == 'metrics':
        from .metrics import calculate
        print(json.dumps(calculate(a.directory)))
    elif a.command == 'check':
        cmd = [sys.executable, '-m', 'unittest', 'discover', '-s', str(ROOT / 'tests'), '-p', 'test_*.py']
        if a.verbose: cmd.append('-v')
        raise SystemExit(subprocess.call(cmd))
    elif a.command == 'campaign':
        from .campaign import execute
        execute(a.build, a.out, a.preset, a.workers, a.resume)
    elif a.command == 'report':
        from .report import report
        print(json.dumps(report(a.directory)))
    elif a.command == 'verify-reference':
        from .reference import verify
        print(json.dumps(verify(a.extract)))
    elif a.command == 'verify':
        from .verify import verify
        result = verify()
        print(json.dumps(result)); raise SystemExit(not result['passed'])
