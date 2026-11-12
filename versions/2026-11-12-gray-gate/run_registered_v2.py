"""Run one frozen v2 stage after root checks native validity and storage."""
import argparse
import json
from pathlib import Path
import subprocess
import sys


def read(path):
    return json.loads(path.read_text())


def check_attempts(directory, expected):
    attempts = [read(p) for p in sorted((directory / 'attempts').glob('*.json'))]
    if len(attempts) != expected or not all(a['valid'] for a in attempts):
        raise RuntimeError('Retained invalid or absent attempt; investigate before extending: ' + str(directory))
    return attempts


def run(base, stage):
    pilot, confirmation = (base / 'results' / n for n in ('pilot-v2', 'confirmation-v2'))
    budget = read(base / 'concurrency-decision.json')
    if not budget['decision'] or budget['allowed_workers'] != 2:
        raise RuntimeError('Measured two-worker storage decision is missing')
    if stage == 'pilot':
        first = check_attempts(pilot, 2)
        if {a['name'] for a in first} != {'blackhole-direct-s111213001', 'blackhole-candidate_gate-s111213001'}:
            raise RuntimeError('Initial validated native pair differs')
        directory, resume, expected = pilot, True, 20
    else:
        check_attempts(pilot, 20)
        # Root writes this only after rechecking quota and measured pilot storage.
        fresh_budget = read(base / 'confirmation-storage-decision.json')
        if not fresh_budget['decision']:
            raise RuntimeError('Confirmation storage budget is not sufficient')
        directory, resume, expected = confirmation, False, 30
    tool = directory / 'tooling/tools/gray_gate_campaign.py'
    command = [sys.executable, str(tool), 'execute', '--out', str(directory), '--workers', '2']
    if resume:
        command.append('--resume')
    print(json.dumps(dict(stage=directory.name, action='starting_frozen_cases')), flush=True)
    subprocess.run(command, check=True)
    attempts = check_attempts(directory, expected)
    print(json.dumps(dict(stage=directory.name, action='validated', attempted=len(attempts),
                          completed=sum(a['status'] == 'completed' for a in attempts))), flush=True)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('base', type=Path)
    parser.add_argument('--stage', choices=('pilot', 'confirmation'), required=True)
    args = parser.parse_args()
    run(args.base.resolve(), args.stage)
