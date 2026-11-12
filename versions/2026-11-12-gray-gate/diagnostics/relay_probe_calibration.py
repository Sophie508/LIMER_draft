"""Read-only, bounded-window relay calibration from one frozen native archive."""
import bisect
import csv
import hashlib
import io
import json
import math
from pathlib import Path
import statistics
import sys
import tarfile

# The fixed phase/source/helper selection below is for this accepted run only.
# This is deliberately not a general-purpose calibration or scenario selector.
EXPECTED_RUN = 'sustained_25_early-direct-s111213001'
EXPECTED_SCENE = {
    'family':'quarter', 'rounds':1, 'chunks_per_phase':512,
    'horizon_ns':250000000, 'fault_ns':24000000, 'node':0,
    'seed':111213001, 'local_gbps':2400, 'detector':'service',
    'policy':'always', 'fault_duration_ns':0, 'canary_period_ns':2000000,
    'canary_bytes':65536, 'replacement_lifetime':'phase',
    'phases_per_round':4, 'relay_completion':'pipelined',
    'helper_mode':'shared', 'slowdown_fraction':0.25,
}
EXPECTED_TOPOLOGY_SHA256 = '169bc777ab9f172b5f3ce665b8f939768adb029d75d8fb176727d95005c52602'

def require_scope(condition, description):
    if not condition:
        raise ValueError('unsupported calibration input: '+description)

def validate_scope(run_record, result, status, attempt, manifest):
    """Reject other scenarios/layouts or unaccepted/inconsistent evidence."""
    require_scope(result['name']==attempt['name']==EXPECTED_RUN, 'run identity')
    require_scope(run_record['method']==result['method']==status['method']=='G11', 'G11 method')
    require_scope(run_record['scene']==result['scene']==EXPECTED_SCENE, 'fixed quarter/24-ms scenario')
    require_scope(result['family']=='quarter', 'quarter result family')
    require_scope(result['status']==status, 'result/status agreement')
    expected_status = {
        'status':'completed', 'world_size':16, 'physical_planes':2,
        'phases_done':4, 'phases_expected':4, 'phases_per_round':4,
        'chunks_per_phase':512, 'source_window':32, 'detector_mode':'service',
        'policy_mode':'always', 'replacement_lifetime':'phase',
        'relay_completion':'pipelined', 'helper_mode':'shared',
    }
    for key,value in expected_status.items():
        require_scope(status.get(key)==value, 'status.'+key)
    require_scope(attempt['valid'] is True and attempt['status']=='completed'
                  and attempt['exit_code']==0 and attempt['score']['valid'] is True,
                  'valid accepted attempt')
    require_scope(result['archive']==manifest and attempt['archive_sha256']==manifest['sha256']
                  and manifest['all_content_hashes_verified'] is True, 'accepted archive identity')
    require_scope(run_record['input_hashes']['inputs/topology.txt']==EXPECTED_TOPOLOGY_SHA256
                  and manifest['files']['inputs/topology.txt']==EXPECTED_TOPOLOGY_SHA256,
                  'fixed 16-rank topology')
    audit=result['audit']
    require_scope(audit['pass'] is True and audit['errors']==[]
                  and audit['logical_chunks']==audit['completed_chunks']==16*4*512
                  and audit['unique_ack_bytes']==16*4*512*65536,
                  'accepted 512-by-64-KiB workload')
    require_scope(result['observation_audit']['pass'] is True
                  and result['observation_audit']['errors']==[], 'observation audit')
    require_scope(result['performance']['task_completed'] is True
                  and result['performance']['scored_affected_sources']==[0,15],
                  'completed run and fixed affected sources')

archive = Path(sys.argv[1])
run = Path(sys.argv[2])
manifest = json.loads((run/'archive_manifest.json').read_text())
require_scope(run.name==EXPECTED_RUN and archive.name==EXPECTED_RUN+'.tar.gz', 'input names')
run_record=json.loads((run/'run_manifest.json').read_text())
result=json.loads((run/'result.json').read_text())
status=json.loads((run/'run_status.json').read_text())
attempt=json.loads((run.parent.parent/'attempts'/(run.name+'.json')).read_text())
validate_scope(run_record,result,status,attempt,manifest)
# Bind the compact records used for scope checks to the archive's content hashes.
for name,record in (('run_manifest.json',run_record),('run_status.json',status),
                    ('audit.json',result['audit']),('performance.json',result['performance']),
                    ('observation_audit.json',result['observation_audit'])):
    raw=(run/name).read_bytes()
    require_scope(hashlib.sha256(raw).hexdigest()==manifest['files'][name]
                  and json.loads(raw)==record, 'archived metadata '+name)
hash_archive = hashlib.sha256()
with archive.open('rb') as stream:
    for block in iter(lambda:stream.read(4*1024*1024),b''):hash_archive.update(block)
assert hash_archive.hexdigest() == manifest['sha256'], 'archive hash mismatch'
selected = {'peer_events.csv','leg_events.csv','logical_events.csv','control_events.csv','phase_events.csv'}
member_hashes={};reservations={};releases={};starts={};ends={};controls=[];phases={};migrated=set();logical_done={}
own={};own_cumulative={};done_time={};phase_bytes=512*65536
with tarfile.open(archive,'r|gz') as tar:
    for member in tar:
        name=Path(member.name).name
        if name not in selected:continue
        h=hashlib.sha256();raw=tar.extractfile(member)
        def lines():
            for line in raw:
                h.update(line);yield line.decode('utf-8')
        for row in csv.DictReader(lines()):
            if name=='peer_events.csv':
                if int(row['phase']) not in (2,3):continue
                r={k:int(v) for k,v in row.items() if k!='event'}
                if row['event']=='RESERVE':reservations[r['route']]=r
                else:releases[r['route']]=r['timestamp_ns']
            elif name=='leg_events.csv':
                key=int(row['route']),int(row['index'])
                if row['event']=='LEG_START':starts[key]=int(row['timestamp_ns'])
                elif row['event']=='LEG_DONE':ends[key]=int(row['timestamp_ns'])
            elif name=='logical_events.csv':
                p,src,t=(int(row[k]) for k in ('phase','src','timestamp_ns'))
                if p not in (1,2,3):continue
                c=int(row['chunk_id'])
                if row['event']=='MIGRATE':migrated.add(c)
                if row['event']=='DONE':
                    logical_done[int(row['route'])]=t
                    done_time[p,src]=max(t,done_time.get((p,src),0))
                if src not in (1,5,12,2):continue
                if row['event']=='ALLOC':own[c]=0
                elif row['event']=='ACK_PROGRESS':
                    ack=int(row['acked']);delta=ack-own.get(c,0);own[c]=ack
                    values=own_cumulative.setdefault((p,src),[])
                    total=(values[-1][1] if values else 0)+delta
                    values.append((t,total))
            elif name=='control_events.csv':controls.append(row)
            elif name=='phase_events.csv':phases[int(row['phase'])]=int(row['timestamp_ns'])
        member_hashes[name]=h.hexdigest()
        assert member_hashes[name]==manifest['files'][name], 'member hash mismatch '+name
assert set(member_hashes)==selected

def cumulative(p,rank,t):
    entries=own_cumulative.get((p,rank),[]);pos=bisect.bisect_right(entries,(t,10**30))-1
    return entries[pos][1] if pos>=0 else 0

def helper(p,rank,t):
    return {'rank':rank,'at_ns':t,'own_remaining_bytes':phase_bytes-cumulative(p,rank,t),
            'own_done_ns':done_time.get((p,rank)),
            'previous_phase_own_done_ns':done_time.get((p-1,rank))}

def summary(values):
    if not values:return None
    ordered=sorted(values)
    return {'n':len(values),'min':ordered[0],'median':statistics.median(ordered),
            'p95_nearest_rank':ordered[math.ceil(.95*len(ordered))-1],'max':ordered[-1]}

def overlap(items,a,b):
    events=[];active=0;area=0
    for r in items:
        lo,hi=max(a,r['timestamp_ns']),min(b,ends.get((r['route'],2),10**30))
        if lo>=hi:continue
        events.extend(((lo,1),(hi,-1)));area+=hi-lo
    peak=0
    for _,delta in sorted(events):active+=delta;peak=max(peak,active)
    return peak,area/(b-a)

output=[]
for p in (2,3):
    for src in (0,15):
        activations=[int(r['arrival_ns']) for r in controls if r['event']=='ACTIVATE' and int(r['phase'])==p and int(r['rank'])==src]
        if not activations:continue
        activation=min(activations)
        probe=min((r for r in reservations.values() if r['relay'] and r['probe'] and r['phase']==p and r['src']==src and r['timestamp_ns']<activation), key=lambda r:r['timestamp_ns'])
        rid=probe['route'];helpers=[probe['helper_src'],probe['helper_dst']]
        durations=[ends[rid,i]-starts[rid,i] for i in range(3)]
        reports=[r for r in controls if r['event']=='HEALTH_REPORT' and int(r['version'])==rid]
        data=[r for r in reservations.values() if r['relay'] and not r['probe'] and r['phase']==p and r['src']==src and [r['helper_src'],r['helper_dst']]==helpers]
        data.sort(key=lambda r:r['timestamp_ns'])
        windows=[]
        # Fixed descriptive windows, selected before reading throughput results.
        for lo,hi in ((0,1_000_000),(1_000_000,2_000_000),(2_000_000,3_000_000),(0,4_000_000)):
            a,b=activation+lo,activation+hi
            delivered=[r for r in data if a<=ends.get((r['route'],2),-1)<b]
            acked=[r for r in data if a<=logical_done.get(r['route'],-1)<b]
            admitted=[r for r in data if a<=r['timestamp_ns']<b]
            completed_admitted=[r for r in admitted if (r['route'],2) in ends]
            unique=sum(r['length'] for r in delivered)
            fresh=[r for r in delivered if r['chunk'] not in migrated]
            windows.append({'start_after_activation_ns':lo,'end_after_activation_ns':hi,'start_ns':a,'end_ns':b,
                'delivered_routes':len(delivered),'delivered_unique_bytes':unique,'delivered_Gbps':8*unique/(b-a),
                'logical_ack_routes':len(acked),'logical_ack_Gbps':8*sum(r['length'] for r in acked)/(b-a),
                'fresh_delivered_routes':len(fresh),'fresh_delivered_Gbps':8*sum(r['length'] for r in fresh)/(b-a),
                'max_same_pair_data_routes_in_physical_flight':overlap(data,a,b)[0],
                'mean_same_pair_data_routes_in_physical_flight':overlap(data,a,b)[1],
                'admitted_route_count':len(admitted),'admitted_final_leg_latency_ns':summary([ends[r['route'],2]-r['timestamp_ns'] for r in completed_admitted]),
                'admitted_middle_leg_latency_ns':summary([ends[r['route'],1]-starts[r['route'],1] for r in completed_admitted]),
                'helpers':[{'begin':helper(p,h,a),'end':helper(p,h,b),'own_ACK_Gbps':8*(cumulative(p,h,b)-cumulative(p,h,a))/(b-a)} for h in helpers]})
        output.append({'phase':p,'source':src,'helper_pair':helpers,'phase_start_ns':phases[p],
            'probe':{'route':rid,'start_ns':probe['timestamp_ns'],'length':probe['length'],'leg_ns':durations,
                'final_leg_done_ns':ends[rid,2],'health_report_sent_ns':int(reports[0]['sent_ns']),
                'health_report_arrival_ns':int(reports[0]['arrival_ns']),
                'chunk_over_max_leg_Gbps':8*probe['length']/max(durations),
                'physical_four_credit_over_cycle_Gbps':8*4*probe['length']/sum(durations),
                'helpers_at_probe':[helper(p,h,probe['timestamp_ns']) for h in helpers]},
            'activation_ns':activation,'activation_after_probe_start_ns':activation-probe['timestamp_ns'],
            'data_routes_total':len(data),'data_unique_bytes_total':sum(r['length'] for r in data),
            'windows':windows,
            'first_8_routes':[{'route':r['route'],'length':r['length'],'fresh':r['chunk'] not in migrated,
                'reserved_ns':r['timestamp_ns'],'leg_ns':[ends[r['route'],i]-starts[r['route'],i] for i in range(3)],
                'final_leg_done_ns':ends[r['route'],2],'physical_release_ns':releases.get(r['route']),
                'logical_done_ns':logical_done.get(r['route'])} for r in data[:8]]})
print(json.dumps({'analysis_version':1,'scope':'one accepted direct run; descriptive calibration, not counterfactual policy evidence',
    'run':str(run),'archive':str(archive),'archive_sha256':hash_archive.hexdigest(),
    'verified_member_sha256':member_hashes,'window_rule':'activation+[0,1),[1,2),[2,3),[0,4) ms; last-leg completed unique relay bytes / elapsed wall time',
    'calibration':output},indent=2))
