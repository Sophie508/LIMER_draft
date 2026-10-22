"""Registered isolated ns-3 campaigns; replay uses counter reports only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import struct
import csv
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from limer_v0.business_delivery import BusinessDeliveryDetector
from limer_v0.hybrid_delivery import HybridDeliveryDetector

BINARY_REL = Path("m13b_backend/simulation/build/scratch/ns3.36.1-LimerBusinessObservation-debug")
DOCKER = ["docker", "--host", "unix:///run/user/1005/limer-docker/docker.sock"]
IMAGE = "limer-simai-cpu:2026-10-10"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def replay(path, end_ns):
    detector = BusinessDeliveryDetector()
    shadow=HybridDeliveryDetector();baseline=[]
    alarms = []
    rows = 0
    observed = defaultdict(set)
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        alarm = detector.observe(row)
        old=shadow.observe({k:row[k] for k in HybridDeliveryDetector.FIELDS})
        if old: baseline.append(old)
        observed[(row["path"],row["batch"])].add(row["side"]+str(row["guard_ns"]))
        rows += 1
        if alarm:
            alarms.append(alarm)
    detector.advance(end_ns)
    # The configured reporting schedule, not fault truth, supplies this universe.
    # Count also batches where both reports were lost and no pending pair existed.
    expected={(f"{rank}/{plane}",batch) for rank in range(4) for plane in ("A","B")
              for batch in range(50)}
    if set(observed)-expected: raise ValueError("report outside configured observation schedule")
    unavailable=sum(observed[key]!={"tx0","tx10000000","rx10000000","rx50000000"} for key in expected)
    return dict(alarms=alarms, input_rows=rows, baseline_alarms=baseline, completed_batches=detector.baseline.completed_batches,
                unavailable_batches=unavailable,
                expired_partial_batches=detector.baseline.unavailable_batches,
                invalid_batches=detector.baseline.invalid_batches,
                retained_batches=detector.baseline.retained_batches)


def audit(truth):
    if len(truth["paths"])!=8: raise ValueError("missing audited paths")
    for row in truth["paths"]:
        if row["duplicates"] or row["send_rejected"]: raise ValueError("duplicate/rejected source")
        if row["sent"]!=row["data_sent"]+row["probe_sent"]: raise ValueError("source traffic split")
        if row["received"]!=row["data_received"]+row["probe_received"]: raise ValueError("receiver traffic split")
        if row["sent"]-row["received"]!=row["permanent_drops"]+row["application_drops"]: raise ValueError("undrained delivery/drop")
        if row["probe_wire_packets"]!=row["probe_sent"]: raise ValueError("probe serialization")
        if row["wire_packets"]!=row["sent"]+row["background_sent"]: raise ValueError("wire packet split")
        expected=64*row["probe_sent"]+1500*(row["data_sent"]+row["background_sent"])
        if row["wire_bytes"]!=expected: raise ValueError("wire byte cost")
        if row["max_wire_bytes"]!=1500 or row["min_wire_bytes"]!=(64 if row["probe_sent"] else 1500):
            raise ValueError("actual serialized packet lengths")
    return True


def audit_observations(directory, trial, truth, observer):
    directory=Path(directory)
    audit_configuration(trial,truth)
    samples=[json.loads(x) for x in (directory/"samples.jsonl").read_text().splitlines()]
    offers=[json.loads(x) for x in (directory/"offers.jsonl").read_text().splitlines()]
    reports=[json.loads(x) for x in (directory/"reports.jsonl").read_text().splitlines()]
    indexed={ (r["path"],r["batch"],r["side"],r["guard_ns"]):r for r in samples }
    expected_keys={(f"{rank}/{plane}",batch,side,guard) for rank in range(4) for plane in ("A","B")
                   for batch in range(50) for side,guard in (("tx",0),("tx",10_000_000),("rx",10_000_000),("rx",50_000_000))}
    if set(indexed)!=expected_keys or len(samples)!=1600: raise ValueError("sample schedule incomplete")
    for row in samples:
        expected=(row["batch"]+1)*10_000_000+(row["guard_ns"] if row["side"]=="rx" or row["guard_ns"]==10_000_000 else 0)
        if row["sample_t_ns"]!=expected: raise ValueError("sample guard/schedule")
    free=0; delivered=[]; identities=set()
    service=math.ceil(768/trial["reportRateMbps"]*1000)
    propagation=round(trial["reportDelayMs"]*1e6)
    for offer in offers:
        key=(offer["path"],offer["batch"],offer["side"],offer["guard_ns"])
        identity=key+(offer["copy"],)
        if identity in identities or not 0<=offer["copy"]<trial["reportCopies"]:
            raise ValueError("duplicate/invalid report copy")
        identities.add(identity)
        sample=indexed[key]
        index=int(sample["path"].split('/')[0])*2+int(sample["path"].endswith('B'))
        encoded=struct.pack('>BBBBIQQQQIIQQI',index,int(sample['side']=='rx'),
            {0:0,10_000_000:1,50_000_000:2}[sample['guard_ns']],1,sample['batch'],
            sample['count'],sample['data_count'],sample['probe_count'],sample['sample_t_ns'],
            sample['data_gaps'],sample['probe_gaps'],sample['data_gap_age_ns'],sample['probe_gap_age_ns'],0)
        if len(encoded)!=68 or offer['payload_hex']!=encoded.hex():raise ValueError('serialized report payload')
        if offer["sample_t_ns"]!=sample["sample_t_ns"]: raise ValueError("report before sample")
        start=max(free,sample["sample_t_ns"]);free=start+service
        if offer["start_ns"]!=start or offer["end_ns"]!=free: raise ValueError("FIFO cost/order")
        if not offer["lost"]: delivered.append(dict(sample,arrival_t_ns=free+propagation))
    if len(offers)!=1600*trial["reportCopies"] or truth["reports_offered"]!=len(offers):
        raise ValueError("report copy schedule")
    if truth["reports_dropped"]!=sum(r["lost"] for r in offers): raise ValueError("report loss ledger")
    delivered.sort(key=lambda r:r["arrival_t_ns"])
    if delivered!=reports: raise ValueError("causal delivered report content/time")
    if delivered[-1]["arrival_t_ns"]>truth["observation_end_ns"]: raise ValueError("report tail did not drain")
    # Local source batches partition all accepted traffic; receiver guard may exclude
    # packets later delivered. Neither private drop counters nor fault time enter replay.
    for path in truth["paths"]:
        tx=sum(r["count"] for r in samples if r["path"]==path["path"] and r["side"]=="tx" and r["guard_ns"]==0)
        rx=sum(r["count"] for r in samples if r["path"]==path["path"] and r["side"]=="rx" and r["guard_ns"]==50_000_000)
        if tx!=path["sent"] or not 0<=rx<=path["received"]: raise ValueError("snapshot counter bounds")
    audit_packet_observations(directory,indexed,truth)
    native=[json.loads(x) for x in (directory/"alarms.jsonl").read_text().splitlines()]
    if native!=observer["alarms"]: raise ValueError("native/report-only replay disagreement")
    native_baseline=[json.loads(x) for x in (directory/"baseline_alarms.jsonl").read_text().splitlines()]
    if native_baseline!=observer["baseline_alarms"]: raise ValueError("native shadow baseline disagreement")
    for path in truth["paths"]:
        for kind in ("data","probe"):
            tx=sum(r[kind+"_count"] for r in samples if r["path"]==path["path"] and r["side"]=="tx" and r["guard_ns"]==0)
            if tx!=path[kind+"_sent"]:raise ValueError("class source snapshot bounds")
    return dict(native_alarm_replay=True, shadow_alarm_replay=True, fifo_audit=True, sample_audit=True)


def audit_configuration(trial,truth):
    if truth['scenario']!=trial['scenario'] or truth['fault_time_ns']!=round(trial['faultTimeMs']*1e6) or truth['run_id']!=trial['runId']:
        raise ValueError('actual injection differs from registration')
    if truth['observation_end_ns']!=round(trial['observationEndMs']*1e6):raise ValueError('observation endpoint differs')
    scenario=trial['scenario']
    for p in truth['paths']:
        affected=p['path']=='2/A'
        expected=dict(network_loss=0,network_data_only=False,network_defer_ns=0,
                      network_defer_fraction=0,application_loss=0,application_defer_ns=0,
                      application_defer_fraction=0)
        if affected:
            if scenario in ('loss','sparse','idle','selective'):expected['network_loss']=trial['lossRate']
            if scenario=='selective':expected['network_data_only']=True
            if scenario in ('reorder40','sparse_reorder40','reorder80'):
                expected['network_defer_ns']=(80 if scenario=='reorder80' else 40)*1_000_000
                expected['network_defer_fraction']=.005 if scenario=='sparse_reorder40' else .25
            if scenario=='businessloss':expected['application_loss']=trial['lossRate']
            if scenario in ('processing40','processing80'):
                expected['application_defer_ns']=(40 if scenario=='processing40' else 80)*1_000_000
                expected['application_defer_fraction']=.25
        if any(p[k]!=v for k,v in expected.items()):raise ValueError('actual fault severity/class differs from registration')


def audit_packet_observations(directory,samples,truth):
    counts=defaultdict(int);next_tx=defaultdict(int);next_rx=defaultdict(int)
    holes=defaultdict(dict);identities=set();snapshots=set();now=-1
    with (directory/'packet_events.csv').open() as handle:
        for event in csv.reader(handle):
            kind,path,batch,cls,value,stamp=event
            path,batch,cls,value,stamp=map(int,(path,batch,cls,value,stamp))
            if stamp<now:raise ValueError('packet observation clock regressed')
            now=stamp;name=f"{path//2}/{'AB'[path%2]}"
            if kind=='snapshot':
                side='rx' if cls else 'tx';key=(name,batch,side,value)
                if key in snapshots:raise ValueError('duplicate packet snapshot')
                snapshots.add(key);r=samples[key]
                for c,label in enumerate(('data','probe')):
                    count=(sum(n for (p,sd,cl,b),n in counts.items() if (p,sd,cl)==(path,side,c))
                           if value==10_000_000 else counts[(path,side,c,batch)])
                    if count!=r[label+'_count']:raise ValueError('class counter differs from packet events')
                    active=holes[(path,c)] if side=='rx' else {}
                    age=max((stamp-t for t in active.values()),default=0)
                    if len(active)!=r[label+'_gaps'] or age!=r[label+'_gap_age_ns']:
                        raise ValueError('receiver gap differs from actual packet arrivals')
                continue
            if kind not in ('tx','rx') or cls not in (0,1):raise ValueError('invalid packet event')
            key=(path,cls);identity=(path,cls,value)
            if kind=='tx':
                if value!=next_tx[key]:raise ValueError('source sequence gap')
                next_tx[key]+=1;identities.add(identity)
            else:
                if identity not in identities:raise ValueError('receiver packet without accepted source')
                identities.remove(identity)
                if value>=next_rx[key]:
                    holes[key].update((v,stamp) for v in range(next_rx[key],value))
                    next_rx[key]=value+1
                else:holes[key].pop(value,None)
            counts[(path,kind,cls,batch)]+=1
    if snapshots!=set(samples):raise ValueError('missing packet snapshots')
    for path in truth['paths']:
        p=int(path['path'].split('/')[0])*2+int(path['path'].endswith('B'))
        for cls,label in enumerate(('data','probe')):
            for side,suffix in (('tx','sent'),('rx','received')):
                total=sum(n for (pn,sd,c,b),n in counts.items() if (pn,sd,c)==(p,side,cls))
                if total!=path[label+'_'+suffix]:raise ValueError('final class accounting differs')


def score(trial, truth, observer):
    fault = trial["kind"] == "fault"
    matching = [a for a in observer["alarms"] if a["path"] == truth["fault_path"]
                and a["decision_t_ns"] >= truth["fault_time_ns"]]
    delay = ((matching[0]["decision_t_ns"] - truth["fault_time_ns"]) / 1e6
             if matching and fault else None)
    false = [a for a in observer["alarms"] if not fault or
             a["path"] != truth["fault_path"] or a["decision_t_ns"] < truth["fault_time_ns"]]
    return dict(delay_ms=delay, timely=fault and delay is not None and delay < 100,
                missed=fault and delay is None,
                late=fault and delay is not None and delay >= 100,
                false_alarm_events=len(false), **observer)


def wilson(k, n):
    if not n:
        return None
    z = 1.959963984540054
    center = (k/n + z*z/(2*n))/(1+z*z/n)
    half = z*math.sqrt(k/n*(1-k/n)/n + z*z/(4*n*n))/(1+z*z/n)
    return [max(0,center-half), min(1,center+half)]


def legacy_aggregate(registration, results):
    indexed = {row["id"]: row for row in results}
    if len(indexed) != len(results):
        raise ValueError("duplicate terminal attempts")
    groups = defaultdict(list)
    for trial in registration["trials"]:
        groups[trial["condition"]].append((trial,indexed.get(trial["id"],{})))
    summary = {}
    for condition, pairs in groups.items():
        fault = pairs[0][0]["kind"] == "fault"
        verified = [r for _, r in pairs if r.get("status") == "PASS"]
        delays = sorted(r.get("delay_ms") if r.get("delay_ms") is not None else math.inf
                        for _,r in pairs) if fault else []
        timely = sum(r.get("timely",False) for _,r in pairs)
        p95 = delays[math.ceil(.95*len(delays))-1] if delays else None
        summary[condition] = dict(kind="fault" if fault else "control", registered=len(pairs),
            verified=len(verified), timely=timely if fault else None,
            late=sum(r.get("late",False) for _,r in pairs) if fault else None,
            missed_or_unverified=sum(r.get("delay_ms") is None for _,r in pairs) if fault else None,
            p95_ms="infinite" if p95 is not None and math.isinf(p95) else p95,
            timely_wilson95=wilson(timely,len(pairs)) if fault else None,
            false_alarm_runs=sum(r.get("false_alarm_events",0)>0 for _,r in pairs),
            false_alarm_events=sum(r.get("false_alarm_events",0) for _,r in pairs),
            unknown_batches=sum(r.get("unavailable_batches",0) for _,r in pairs),
            invalid_batches=sum(r.get("invalid_batches",0) for _,r in pairs),
            delays_ms=[None if math.isinf(x) else x for x in delays])
    faults=[(t,indexed.get(t["id"],{})) for t in registration["trials"] if t["kind"]=="fault"]
    controls=[(t,indexed.get(t["id"],{})) for t in registration["trials"] if t["kind"]=="control"]
    passed = all(r.get("status")=="PASS" for _,r in faults+controls) and all(
        r.get("timely",False) and r.get("false_alarm_events",0)==0 for _,r in faults) and all(
        r.get("false_alarm_events",0)==0 for _,r in controls) and all(
        r.get("unavailable_batches",0)==0 and r.get("invalid_batches",0)==0 for _,r in faults+controls)
    return dict(groups=summary, registered=len(registration["trials"]),
                terminal=len(results), strict_verdict="PASS" if passed else "FAIL",
                primary_faults=len(faults), timely_faults=sum(r.get("timely",False) for _,r in faults),
                verified_control_trials=sum(r.get("status")=="PASS" for _,r in controls),
                claim="Isolated UDP delivery-deficit simulation; no collective recovery evidence")


def aggregate(registration, results):
    summary=legacy_aggregate(registration,results)
    groups=summary["groups"]
    gate=all(r.get("status")=="PASS" for r in results) and len(results)==len(registration["trials"])
    gate=gate and all(g["false_alarm_events"]==0 and g["invalid_batches"]==0 for g in groups.values())
    gate=gate and all(g["timely"]/g["registered"]>=.95 for g in groups.values() if g["kind"]=="fault")
    summary["per_condition_95_verdict"]="PASS" if gate else "FAIL"
    summary["claim"]="Class-separated causal UDP/application observations and charged probes/reports; not collective recovery"
    return summary


def make_trials(campaign):
    trials=[]
    def add(profile,scenario,kind,n,**overrides):
        capacity,offered=(100,80) if profile=="low" else (10000,1000)
        condition=f"{profile}_{scenario}"
        for rep in range(n):
            trial=dict(id=f"{condition}_r{rep+1:03d}",condition=condition,kind=kind,
                scenario=scenario,capacityMbps=capacity,offeredMbps=offered,lossRate=.005,
                reportLoss=0,probePps=35000,reportCopies=3,
                reportRateMbps=10,reportDelayMs=1,observationEndMs=600)
            trial.update(overrides);trials.append(trial)
    if campaign=="smoke":
        add("low","nominal","control",1)
        add("low","selective","fault",1)
        add("low","processing80","fault",1)
        base=59100
    elif campaign in ("development","validation"):
        validation=campaign=="validation"
        for scenario in ("selective","businessloss","loss"):
            add("low",scenario,"fault",60 if validation else 20)
        add("high","loss","fault",60 if validation else 3)
        for scenario in ("processing80","reorder80","overload"):
            add("low",scenario,"fault",20 if validation else 5)
        add("low","sparse","fault",60 if validation else 3,offeredMbps=1)
        add("low","idle","fault",60 if validation else 3)
        for scenario in ("nominal","pause","congestion","reorder40","sparse_reorder40","processing40"):
            add("low",scenario,"control",20 if validation else 10)
        add("high","pause","control",20 if validation else 5)
        base=63000 if validation else 62000
    else: raise ValueError("unknown campaign")
    rng=random.Random(base+20261010)
    for i,trial in enumerate(trials):
        trial["runId"]=base+i;trial["faultTimeMs"]=round(50+rng.random()*10,6)
    random.Random(base).shuffle(trials)
    return trials


RUN_TRIAL=None


def trial_worker(trial):
    return RUN_TRIAL(trial)


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--campaign",choices=("smoke","development","validation"),required=True)
    parser.add_argument("--tag",default="v1")
    parser.add_argument("--workers",type=int,default=4,choices=range(1,9))
    args=parser.parse_args()
    root=args.root.resolve()
    directory=root/"runs"/f"m13_{args.campaign}_{args.tag}"
    directory.mkdir(exist_ok=False)
    binary=root/BINARY_REL
    registration=dict(campaign=args.campaign,rule=BusinessDeliveryDetector.RULE_VERSION,
        registration_unix=time.time(),workers=args.workers,trials=make_trials(args.campaign),
        parameters=dict(batch_ms=10,guard_ms=50,window_ms=100,report_ttl_ms=200,
                        report_rate_Mbps=10,report_bytes=96,gap_guard_ms=40,report_delay_ms=1,report_copies=3,probe_pps=35000,probe_wire_bytes=64,
                        data_wire_bytes=1500,mark_bytes=12,observation_end_ms=600),
        hashes={"binary":digest(binary),"detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/business_delivery.py"),
                "runner":digest(__file__),"cpp":digest(Path(__file__).with_name("LimerBusinessObservation.cc")),
                "header":digest(Path(__file__).with_name("business_observer.h")),
                "native_base":digest(Path(__file__).with_name("m13_batch_deficit_observer.h")),
                "hybrid_base":digest(Path(__file__).resolve().parents[1]/"limer_v0/hybrid_delivery.py"),
                "early_detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/early_delivery.py"),
                "base_detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/batch_loss.py")},
        image_id=subprocess.check_output(DOCKER+["image","inspect",IMAGE,"--format","{{.Id}}"],text=True).strip())
    registration["library_hashes"]={p.name:digest(p) for p in sorted((root/"m13b_backend/simulation/build/lib").glob("*.so"))}
    registration["cmake_sha256"]=digest(root/"m13b_backend/simulation/scratch/CMakeLists.txt")
    write(directory/"registration.json",registration)
    results=[]
    def run_trial(trial):
        run_dir=directory/trial["id"]; run_dir.mkdir()
        name="limer-m13-"+str(trial["runId"])
        command=DOCKER+["run","--rm","--name",name,"--cpus=1","--memory=1g",
                       "-v",str(root)+":/work",
                       "-e","LD_LIBRARY_PATH=/work/m13b_backend/simulation/build/lib",
                       IMAGE,"/work/"+str(BINARY_REL),
                       "--out=/work/"+str(run_dir.relative_to(root))]
        for key in ("scenario","capacityMbps","offeredMbps","lossRate","reportLoss","runId","faultTimeMs","probePps","reportCopies","reportRateMbps","reportDelayMs","observationEndMs"):
            command.append(f"--{key}={trial[key]}")
        result=dict(id=trial["id"],start_unix=time.time(),command=command,status="RUNNING")
        write(run_dir/"status.json",result)
        try:
            if digest(binary)!=registration["hashes"]["binary"]: raise ValueError("frozen binary changed")
            for lib_name,sha in registration["library_hashes"].items():
                if digest(root/"m13b_backend/simulation/build/lib"/lib_name)!=sha:
                    raise ValueError("frozen simulator library changed")
            with (run_dir/"stdout.log").open("w") as log:
                process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            result["exit_code"]=process.returncode
            if process.returncode: raise ValueError("simulation process failed")
            truth=json.loads((run_dir/"truth.json").read_text())
            audit(truth)
            observer=replay(run_dir/"reports.jsonl",truth["observation_end_ns"])
            evidence=audit_observations(run_dir,trial,truth,observer)
            result.update(score(trial,truth,observer),**evidence,status="PASS",packet_audit=True,
                          input_sha256=digest(run_dir/"reports.jsonl"),
                          truth_sha256=digest(run_dir/"truth.json"),
                          report_bytes=truth["reports_offered"]*96,
                          probe_wire_bytes=sum(p["probe_sent"]*64 for p in truth["paths"]),
                          data_wire_bytes=sum(p["data_sent"]*1500 for p in truth["paths"]),
                          reports_dropped=truth["reports_dropped"],
                          sent_packets=sum(p["sent"] for p in truth["paths"]),
                          report_cost_basis="separate serialized modeled channel; not shared data-plane congestion")
        except (ValueError,FileNotFoundError,subprocess.TimeoutExpired) as e:
            result.update(status="FAILED",failure=str(e))
            subprocess.run(DOCKER+["rm","-f",name],capture_output=True)
        result["wall_seconds"]=time.time()-result["start_unix"]
        write(run_dir/"status.json",result)
        return result
    # Independently seeded single-thread CPU simulations, bounded by registration.
    # Batch barrier records every already-dispatched attempt before stopping.
    from multiprocessing import get_context
    global RUN_TRIAL
    RUN_TRIAL=run_trial
    trials=registration["trials"]
    with get_context("fork").Pool(args.workers) as executor:
        for start in range(0,len(trials),args.workers):
            batch=trials[start:start+args.workers]
            completed=list(executor.map(trial_worker,batch))
            results.extend(completed)
            write(directory/"summary.json",aggregate(registration,results))
            for trial,result in zip(batch,completed):
                print(trial["id"],result["status"],result.get("delay_ms"),
                      result.get("false_alarm_events"),result.get("failure",""),flush=True)
            if any(r["status"]=="FAILED" for r in completed): break
    write(directory/"terminal.json",dict(complete=len(results)==len(registration["trials"]),
         statuses=dict(Counter(r["status"] for r in results)),summary=aggregate(registration,results)))


if __name__=="__main__": main()
