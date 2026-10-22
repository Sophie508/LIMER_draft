"""Registered isolated ns-3 campaigns; replay uses counter reports only."""
import argparse
from collections import Counter, defaultdict
import hashlib
import json
import math
from pathlib import Path
import random
import subprocess
import sys
import time

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from limer_v0.hybrid_delivery import HybridDeliveryDetector

BINARY_REL = Path("m12e_backend/simulation/build/scratch/ns3.36.1-LimerHybridObservation-debug")
DOCKER = ["docker", "--host", "unix:///run/user/1005/limer-docker/docker.sock"]
IMAGE = "limer-simai-cpu:2026-10-10"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def replay(path, end_ns):
    detector = HybridDeliveryDetector()
    alarms = []
    rows = 0
    observed = defaultdict(set)
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        alarm = detector.observe(row)
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
    return dict(alarms=alarms, input_rows=rows, completed_batches=detector.completed_batches,
                unavailable_batches=unavailable,
                expired_partial_batches=detector.unavailable_batches,
                invalid_batches=detector.invalid_batches,
                retained_batches=detector.retained_batches)


def audit(truth):
    if len(truth["paths"])!=8: raise ValueError("missing audited paths")
    for row in truth["paths"]:
        if row["duplicates"] or row["send_rejected"]: raise ValueError("duplicate/rejected source")
        if row["sent"]!=row["data_sent"]+row["probe_sent"]: raise ValueError("source traffic split")
        if row["received"]!=row["data_received"]+row["probe_received"]: raise ValueError("receiver traffic split")
        if row["sent"]-row["received"]!=row["permanent_drops"]: raise ValueError("undrained delivery/drop")
        if row["probe_wire_packets"]!=row["probe_sent"]: raise ValueError("probe serialization")
        if row["wire_packets"]!=row["sent"]+row["background_sent"]: raise ValueError("wire packet split")
        expected=64*row["probe_sent"]+1500*(row["data_sent"]+row["background_sent"])
        if row["wire_bytes"]!=expected: raise ValueError("wire byte cost")
        if row["max_wire_bytes"]!=1500 or row["min_wire_bytes"]!=(64 if row["probe_sent"] else 1500):
            raise ValueError("actual serialized packet lengths")
    return True


def audit_observations(directory, trial, truth, observer):
    directory=Path(directory)
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
    service=math.ceil(512/trial["reportRateMbps"]*1000)
    propagation=round(trial["reportDelayMs"]*1e6)
    for offer in offers:
        key=(offer["path"],offer["batch"],offer["side"],offer["guard_ns"])
        identity=key+(offer["copy"],)
        if identity in identities or not 0<=offer["copy"]<trial["reportCopies"]:
            raise ValueError("duplicate/invalid report copy")
        identities.add(identity)
        sample=indexed[key]
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
    native=[json.loads(x) for x in (directory/"alarms.jsonl").read_text().splitlines()]
    if native!=observer["alarms"]: raise ValueError("native/report-only replay disagreement")
    return dict(native_alarm_replay=True, fifo_audit=True, sample_audit=True)


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
    summary["claim"]="Costed same-path UDP probes and native delivery impairment decisions; not collective recovery"
    return summary


def make_trials(campaign):
    trials=[]
    def add(profile,scenario,kind,n,loss=.005,report_loss=0,rate=None,**overrides):
        capacity,offered=(100,80) if profile=="low" else (10000,1000)
        if rate is not None: offered=rate
        condition=f"{profile}_{scenario}"+(f"_{loss:g}" if kind=="fault" else "")
        for rep in range(n):
            trials.append(dict(id=f"{condition}_r{rep+1:03d}",condition=condition,kind=kind,
                scenario=scenario,capacityMbps=capacity,offeredMbps=offered,lossRate=loss,
                reportLoss=report_loss,probePps=35000,reportCopies=3,
                reportRateMbps=10,reportDelayMs=1,observationEndMs=600))
            trials[-1].update(overrides)
    if campaign in ("development","validation"):
        for profile in ("low","high"):
            for loss in (.005,.01,.02,.05):
                add(profile,"loss","fault",60 if campaign=="validation" else
                    (10 if profile=="low" and loss==.005 else 1),loss)
            for scenario in ("nominal","congestion","pause","reorder40"):
                add(profile,scenario,"control",5 if campaign=="validation" else 10)
        for scenario in ("sparse","idle"):
            add("low",scenario,"fault",60 if campaign=="validation" else 10,rate=1 if scenario=="sparse" else None)
        add("low","reportloss","fault",60 if campaign=="validation" else 10,report_loss=.1)
        for scenario in ("reorder80","overload"):
            add("low",scenario,"fault",20 if campaign=="validation" else 5)
    elif campaign=="boundary":
        add("low","idle","fault",5,probePps=0)
        add("low","loss","fault",5,reportDelayMs=120,observationEndMs=800)
        add("low","selective","fault",5,rate=1)
    seed_base={"development":34000,"validation":41000,"boundary":51000}[campaign]
    rng=random.Random(seed_base+20261010)
    for i,trial in enumerate(trials):
        trial["runId"]=seed_base+i
        trial["faultTimeMs"]=round(50+rng.random()*10,6)
        if campaign=="development" and trial["kind"]=="control":
            trial["faultTimeMs"]=50.5+int(trial["id"].rsplit("r",1)[1])-1
        if trial["scenario"]=="reportloss": trial["scenario"]="loss"
    random.Random(seed_base).shuffle(trials)
    return trials


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--campaign",choices=("development","validation","boundary"),required=True)
    parser.add_argument("--tag",default="v1")
    parser.add_argument("--workers",type=int,default=4,choices=range(1,9))
    args=parser.parse_args()
    root=args.root.resolve()
    directory=root/"runs"/f"m12_{args.campaign}_{args.tag}"
    directory.mkdir(exist_ok=False)
    binary=root/BINARY_REL
    registration=dict(campaign=args.campaign,rule=HybridDeliveryDetector.RULE_VERSION,
        registration_unix=time.time(),workers=args.workers,trials=make_trials(args.campaign),
        parameters=dict(batch_ms=10,guard_ms=50,window_ms=100,report_ttl_ms=200,
                        report_rate_Mbps=10,report_bytes=64,report_delay_ms=1,report_copies=3,probe_pps=35000,probe_wire_bytes=64,
                        data_wire_bytes=1500,mark_bytes=12,observation_end_ms=600),
        hashes={"binary":digest(binary),"detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/hybrid_delivery.py"),
                "runner":digest(__file__),"cpp":digest(Path(__file__).with_name("LimerHybridObservation.cc")),
                "header":digest(Path(__file__).with_name("batch_deficit_observer.h")),
                "early_detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/early_delivery.py"),
                "base_detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/batch_loss.py")},
        image_id=subprocess.check_output(DOCKER+["image","inspect",IMAGE,"--format","{{.Id}}"],text=True).strip())
    registration["library_hashes"]={p.name:digest(p) for p in sorted((root/"m12e_backend/simulation/build/lib").glob("*.so"))}
    registration["cmake_sha256"]=digest(root/"m12e_backend/simulation/scratch/CMakeLists.txt")
    write(directory/"registration.json",registration)
    results=[]
    def run_trial(trial):
        run_dir=directory/trial["id"]; run_dir.mkdir()
        name="limer-m12-"+str(trial["runId"])
        command=DOCKER+["run","--rm","--name",name,"--cpus=1","--memory=1g",
                       "-v",str(root)+":/work",
                       "-e","LD_LIBRARY_PATH=/work/m12e_backend/simulation/build/lib",
                       IMAGE,"/work/"+str(BINARY_REL),
                       "--out=/work/"+str(run_dir.relative_to(root))]
        for key in ("scenario","capacityMbps","offeredMbps","lossRate","reportLoss","runId","faultTimeMs","probePps","reportCopies","reportRateMbps","reportDelayMs","observationEndMs"):
            command.append(f"--{key}={trial[key]}")
        result=dict(id=trial["id"],start_unix=time.time(),command=command,status="RUNNING")
        write(run_dir/"status.json",result)
        try:
            if digest(binary)!=registration["hashes"]["binary"]: raise ValueError("frozen binary changed")
            for lib_name,sha in registration["library_hashes"].items():
                if digest(root/"m12e_backend/simulation/build/lib"/lib_name)!=sha:
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
                          report_bytes=truth["reports_offered"]*64,
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
    from concurrent.futures import ThreadPoolExecutor
    trials=registration["trials"]
    with ThreadPoolExecutor(max_workers=args.workers) as executor:
        for start in range(0,len(trials),args.workers):
            batch=trials[start:start+args.workers]
            completed=list(executor.map(run_trial,batch))
            results.extend(completed)
            write(directory/"summary.json",aggregate(registration,results))
            for trial,result in zip(batch,completed):
                print(trial["id"],result["status"],result.get("delay_ms"),
                      result.get("false_alarm_events"),result.get("failure",""),flush=True)
            if any(r["status"]=="FAILED" for r in completed): break
    write(directory/"terminal.json",dict(complete=len(results)==len(registration["trials"]),
         statuses=dict(Counter(r["status"] for r in results)),summary=aggregate(registration,results)))


if __name__=="__main__": main()
