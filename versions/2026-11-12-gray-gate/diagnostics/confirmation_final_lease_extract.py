"""Read-only extraction for the retained final-phase lease failure; no simulation."""
import csv
import hashlib
import json
from pathlib import Path

BASE = Path('/home/suliu/data/LIMER_GRAY_GATE_2026-11-12')
CAMPAIGN = BASE/'results/confirmation-v2'
RUN = CAMPAIGN/'runs/sustained_50_early-candidate_gate-s111213033'

def digest(path):
    h = hashlib.sha256()
    with path.open('rb') as stream:
        for block in iter(lambda: stream.read(4*1024*1024), b''):
            h.update(block)
    return h.hexdigest()

def read_json(path):
    return json.loads(path.read_text())

def read_rows(name):
    with (RUN/name).open() as stream:
        return list(csv.DictReader(stream))

status = read_json(RUN/'run_status.json')
attempt_path = CAMPAIGN/'attempts'/(RUN.name+'.json')
attempt = read_json(attempt_path)
audit = read_json(RUN/'audit.json')
assert not attempt['valid'] and attempt['status'] == 'runner_error'
assert audit['errors'] == ['rejected helper lease leaked after delivered release']
assert status['job_done_ns'] == 85251871 and status['monitor_end_ns'] == 250000000
controls = read_rows('control_events.csv')
peer = read_rows('peer_events.csv')
probes = [r for r in peer if r['probe'] == '1']
decisions = [json.loads(line) for line in (RUN/'policy_decisions.jsonl').read_text().splitlines()]
leases = []
for row in controls:
    if row['event'] != 'LEND_ACTIVE':
        continue
    phase, source, lease = (int(row[k]) for k in ('phase','rank','version'))
    requests = [r for r in controls if r['event'] in ('RELEASE_TX','RELEASE_RX')
                and int(r['phase']) == phase and int(r['version']) == lease]
    released = [int(r['arrival_ns']) for r in controls if r['event'] == 'LEND_RELEASED'
                and int(r['phase']) == phase and int(r['version']) == lease]
    resets = [int(r['arrival_ns']) for r in controls if r['event'] == 'RESET_TO_AB'
              and int(r['phase']) > phase]
    stop = min(released+resets, default=10**30)
    arrival = max((int(r['arrival_ns']) for r in requests), default=10**30)
    reservations = {r['route']:r for r in peer if r['event']=='RESERVE'}
    release_times = {r['route']:int(r['timestamp_ns']) for r in peer if r['event']=='RELEASE'}
    in_flight = [rid for rid,r in reservations.items() if r['relay']=='1'
                 and int(r['src']) == source and int(r['phase']) == phase
                 and int(r['timestamp_ns']) <= arrival < release_times.get(rid,10**30)]
    predicate = stop <= arrival or arrival >= status['monitor_end_ns'] or bool(in_flight)
    leases.append({'phase':phase,'source':source,'lease_id':lease,
                   'activated_ns':int(row['arrival_ns']),
                   'release_requests':requests,'release_arrival_ns':arrival,
                   'explicit_released_ns':released,'next_phase_reset_ns':min(resets,default=None),
                   'relay_routes_in_flight_at_release_arrival':in_flight,
                   'existing_audit_release_predicate_passes':predicate})
assert [r['lease_id'] for r in leases if not r['existing_audit_release_predicate_passes']] == [100500]
last_done = {}
with (RUN/'logical_events.csv').open() as stream:
    for row in csv.DictReader(stream):
        if row['event'] == 'DONE':
            last_done[int(row['phase']),int(row['src'])] = row
files = ['audit.json','run_status.json','run_manifest.json','runner_error.json',
         'control_events.csv','phase_events.csv','peer_events.csv','leg_events.csv',
         'logical_events.csv','policy_decisions.jsonl','helper_reports.jsonl','service_events.csv']
source_files = ['src/simulator/runtime/completion.h','src/simulator/recovery/proxy.h',
                'src/simulator/scheduling/dispatcher.h','src/simulator/main.cc',
                'python/limerlab/audit.py']
build = read_json(CAMPAIGN/'build.json')
source_hashes = {name:digest(BASE/'source-v2'/name) for name in source_files}
for name in source_files:
    if name.startswith('src/'):
        assert source_hashes[name] == build['source_hashes'][name]
print(json.dumps({
    'run':str(RUN),'attempt':attempt,'audit':audit,'run_status':status,
    'original_file_sha256':{name:digest(RUN/name) for name in files},
    'attempt_sha256':digest(attempt_path),'frozen_source_sha256':source_hashes,
    'native_binary_sha256':build['binary_sha256'],'lease_timeline':leases,
    'probe_resource_events':probes,
    'last_probe_leg_events':[r for r in read_rows('leg_events.csv') if r['route']=='100713'],
    'last_gate_decision':decisions[-1],
    'phase3_last_done_per_source':[row for (p,s),row in sorted(last_done.items()) if p==3],
    'terminal_phase_inference':{
        'last_workload_phase':3,'global_phase_after_last_done':4,
        'basis':'FinalAck increments phase and returns at phase==phases; StartPhase is not called',
        'release_callback_due_ns':85406150,'release_after_job_done_ns':154279,
        'guard_inference':'ReleaseLendingDone returns because p=3 != phase=4; no terminal reset'},
    'native_executed':False,'original_inputs_modified':False,
},indent=2))
