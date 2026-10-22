"""Offline checks of packaged ledgers, detector traces and execution ownership."""
import argparse
import gzip
import hashlib
import json
from pathlib import Path
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / 'baselines/simai_runtime'))
from simulation.run_business_observation import aggregate, make_trials, replay, audit_observations, audit_probe_waves
from simulation.audit_dynamic_dag import audit_dynamic
from simulation.audit_closed_loop import audit_closed_loop
from dag_tools import verify_trace


def read(path):
    return json.loads(path.read_text())


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path)
    args = parser.parse_args()
    result = {'scope': 'Offline archive reconstruction, not new simulation efficacy evidence'}
    ledger_results = {}
    for campaign in ('adaptive_validation', 'coverage_validation', 'adaptive_high_controls'):
        folder = ROOT / 'artifacts/m13/runs' / ('m13_' + campaign + '_v1')
        registration = read(folder / 'registration.json')
        expected = read(folder / 'summary.json')
        # The constant-probe campaign predates the adaptive target field.
        # Its absent target means zero, as in the native CLI default.
        registered_trials = [dict(trial, probeTargetPps=trial.get('probeTargetPps', 0)) for trial in registration['trials']]
        if registered_trials != make_trials(campaign):
            raise ValueError('Current condition generator differs from frozen registration: ' + campaign)
        rows = [read(folder / trial['id'] / 'status.json') for trial in registration['trials']]
        actual = aggregate(registration, rows)
        if actual != expected:
            raise ValueError('Archived trial aggregation changed: ' + campaign)
        ledger_results[campaign] = {k:actual[k] for k in ('registered', 'primary_faults', 'timely_faults', 'verified_control_trials', 'per_condition_95_verdict')}
    result['M13_complete_ledgers'] = ledger_results
    trace_results = []
    samples = ROOT / 'artifacts/samples/m13'
    original = ROOT / 'artifacts/m13/runs/m13_adaptive_validation_v1'
    for trial in read(samples / 'index.json'):
        folder = samples / trial['id']
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'reports.jsonl'
            for compressed in folder.glob('*.gz'):
                (Path(directory)/compressed.name.removesuffix('.gz')).write_bytes(gzip.decompress(compressed.read_bytes()))
            (Path(directory)/'baseline_alarms.jsonl').write_bytes((original/trial['id']/'baseline_alarms.jsonl').read_bytes())
            truth = read(original / trial['id'] / 'truth.json')
            actual = replay(path, truth['observation_end_ns'])
            audit_observations(Path(directory), trial, truth, actual)
            audit_probe_waves(Path(directory), trial)
        status = read(original / trial['id'] / 'status.json')
        for field in ('alarms', 'baseline_alarms', 'input_rows'):
            if actual[field] != status[field]:
                raise ValueError('Report replay differs: ' + trial['id'] + '/' + field)
        native = [json.loads(line) for line in gzip.decompress((folder / 'alarms.jsonl.gz').read_bytes()).decode().splitlines()]
        if native != actual['alarms']:
            raise ValueError('Native and Python alarm differ: ' + trial['id'])
        trace_results.append(dict(condition=trial['condition'], id=trial['id'], reports=actual['input_rows'], alarms=len(actual['alarms'])))
    result['M13_observable_trace_samples'] = trace_results
    folder = ROOT / 'artifacts/server/runs/m9_execution_v1'
    execution = []
    for case in read(folder / 'registration.json')['cases']:
        if case['expected_exit']:
            status = read(folder / case['id'] / 'status.json')
            if status['exit_code'] != case['expected_exit']:
                raise ValueError('Expected invalid-version rejection changed')
            execution.append(dict(id=case['id'], expected_rejection=case['expected_exit']))
            continue
        graph = read(folder / case['id'] / 'graph.json')
        trace = [json.loads(line) for line in gzip.decompress((folder / case['id'] / 'trace.jsonl.gz').read_bytes()).decode().splitlines()]
        actual = audit_dynamic(graph, trace, case['requests'], case['model'])
        expected = read(folder / case['id'] / 'status.json')['audit']
        if actual != expected:
            raise ValueError('Execution ownership replay differs: ' + case['id'])
        execution.append(dict(id=case['id'], **actual))
    result['M9_execution_replay'] = execution
    folder = ROOT / 'artifacts/server/runs/m11_closed_loop_v1'
    registration = read(folder/'registration.json')
    closed = []
    for case in registration['cases']:
        d = folder/case['id']
        trace = [json.loads(line) for line in gzip.decompress((d/'trace.jsonl.gz').read_bytes()).decode().splitlines()]
        records = [json.loads(line) for line in gzip.decompress((d/'progress.jsonl.gz').read_bytes()).decode().splitlines()]
        releases = {int(line.split()[0]):int(line.split()[1]) for line in (d/'releases.txt').read_text().splitlines()[1:]}
        actual = audit_closed_loop(read(d/'graph.json'), trace, records, registration['model'], case['mode'], case['requests'], releases)
        status = read(d/'status.json')
        for field in ('observation','execution','policies','requests'):
            # JSON serializes integer map keys to strings.
            if json.loads(json.dumps(actual[field])) != status[field]:
                raise ValueError('M11 online audit differs: '+case['id']+'/'+field)
        closed.append(dict(id=case['id'], makespan_ns=actual['execution']['makespan_ns'], changed_flows=actual['execution']['changed_flows']))
    result['M11_closed_loop_replay'] = closed
    compared = []
    for row in read(ROOT / 'artifacts/server/logs/measurements_summary.json'):
        name = row['command'][row['command'].index('-w') + 1].split('/')[-1]
        folder = ROOT / 'artifacts/server/runs' / name
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / 'trace.jsonl'
            path.write_bytes(gzip.decompress((folder / 'trace.jsonl.gz').read_bytes()))
            actual = verify_trace(read(folder / 'graph.json'), path)
        if actual != row['trace_check']:
            raise ValueError('Ring/OptCC trace replay differs: ' + name)
        compared.append(dict(name=name, makespan_ns=actual['makespan_ns']))
    result['Ring_OptCC_30_network_replays'] = compared
    result['status'] = 'PASS'
    text = json.dumps(result, indent=2) + '\n'
    if args.output:
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(text)
    print(json.dumps(dict(status='PASS', complete_M13_campaigns=len(ledger_results), M13_sample_traces=len(trace_results), M9_cases=len(execution), M11_cases=len(closed), Ring_OptCC_traces=len(compared))))


if __name__ == '__main__':
    main()
