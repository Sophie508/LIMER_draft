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
from limer_v0.batch_loss import BatchLossDetector

BINARY_REL = Path("m8_backend/simulation/build/scratch/ns3.36.1-LimerBatchObservation-debug")
DOCKER = ["docker", "--host", "unix:///run/user/1005/limer-docker/docker.sock"]
IMAGE = "limer-simai-cpu:2026-10-10"


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def write(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False) + "\n")


def replay(path, end_ns):
    detector = BatchLossDetector()
    alarms = []
    rows = 0
    observed = defaultdict(set)
    for line in Path(path).read_text().splitlines():
        row = json.loads(line)
        alarm = detector.observe(row)
        observed[(row["path"],row["batch"])].add(row["side"])
        rows += 1
        if alarm:
            alarms.append(alarm)
    detector.advance(end_ns)
    # The configured reporting schedule, not fault truth, supplies this universe.
    # Count also batches where both reports were lost and no pending pair existed.
    expected={(f"{rank}/{plane}",batch) for rank in range(4) for plane in ("A","B")
              for batch in range(50)}
    if set(observed)-expected: raise ValueError("report outside configured observation schedule")
    unavailable=sum(observed[key]!={"tx","rx"} for key in expected)
    return dict(alarms=alarms, input_rows=rows, completed_batches=detector.completed_batches,
                unavailable_batches=unavailable,
                expired_partial_batches=detector.unavailable_batches,
                invalid_batches=detector.invalid_batches,
                retained_batches=detector.retained_batches)


def audit(truth):
    paths = truth["paths"]
    if len(paths) != 8 or len({p["path"] for p in paths}) != 8:
        raise ValueError("all eight paths must be audited")
    for path in paths:
        if path["duplicates"] or path["send_rejected"]:
            raise ValueError("duplicate/corrupt or rejected source payload")
        if path["sent"] - path["received"] != path["permanent_drops"]:
            raise ValueError("final packet delivery/drop accounting did not drain")
        if path["min_wire_bytes"] != 1500 or path["max_wire_bytes"] != 1500:
            raise ValueError("wire packet size does not match the declared mark budget")
        if path["wire_packets"] != path["sent"] + path["background_sent"]:
            raise ValueError("source accepted vs serialized packet accounting mismatch")
        if path["wire_bytes"] != 1500 * path["wire_packets"]:
            raise ValueError("wire byte accounting mismatch")
    return True


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


def aggregate(registration, results):
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


def make_trials(campaign):
    trials=[]
    def add(profile,scenario,kind,repetitions,loss=.005,report_loss=0,rate=None):
        capacity,offered = (100,80) if profile=="low" else (10000,1000)
        if rate is not None: offered=rate
        for rep in range(repetitions):
            condition=f"{profile}_{scenario}" + (f"_{loss:g}" if kind=="fault" else "")
            trials.append(dict(id=f"{condition}_r{rep+1:02d}",condition=condition,kind=kind,
                               scenario=scenario,capacityMbps=capacity,offeredMbps=offered,
                               lossRate=loss,reportLoss=report_loss))
    if campaign=="development":
        for profile in ("low","high"):
            add(profile,"nominal","control",1)
            add(profile,"loss","fault",1)
        add("low","loss","fault",1,loss=.01)
        add("low","reorder40","control",1)
        add("low","pause","control",1)
        add("low","reportloss","control",1,report_loss=.1)
    elif campaign=="validation":
        for profile in ("low","high"):
            for loss in (.005,.01,.02,.05): add(profile,"loss","fault",20,loss)
            for control in ("nominal","congestion","pause","reorder40"):
                add(profile,control,"control",5)
    else:
        add("low","reorder80","control",5)
        add("low","overload","control",5)
        add("low","sparse","fault",5,rate=1)
        add("low","idle","fault",5)
        add("low","loss","fault",5,report_loss=.1)
    seed_base={"development":1000,"validation":10000,"stress":20000}[campaign]
    phase_rng=random.Random(seed_base+20261010)
    for i,trial in enumerate(trials):
        trial["runId"]=seed_base+i
        trial["faultTimeMs"]=50 if campaign=="development" else round(50+phase_rng.random()*10,6)
    random.Random(20261010).shuffle(trials)
    return trials


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--campaign",choices=("development","validation","stress"),required=True)
    parser.add_argument("--tag",default="v1")
    args=parser.parse_args()
    root=args.root.resolve()
    directory=root/"runs"/f"m8_{args.campaign}_{args.tag}"
    directory.mkdir(exist_ok=False)
    binary=root/BINARY_REL
    registration=dict(campaign=args.campaign,rule=BatchLossDetector.RULE_VERSION,
        registration_unix=time.time(),trials=make_trials(args.campaign),
        parameters=dict(batch_ms=10,guard_ms=50,window_ms=100,report_ttl_ms=200,
                        report_rate_Mbps=1,report_bytes=64,report_delay_ms=5,
                        data_wire_bytes=1500,mark_bytes=12,observation_end_ms=600),
        hashes={"binary":digest(binary),"detector":digest(Path(__file__).resolve().parents[1]/"limer_v0/batch_loss.py"),
                "runner":digest(__file__),"cpp":digest(Path(__file__).with_name("LimerBatchObservation.cc"))},
        image_id=subprocess.check_output(DOCKER+["image","inspect",IMAGE,"--format","{{.Id}}"],text=True).strip())
    registration["library_hashes"]={p.name:digest(p) for p in sorted((root/"m8_backend/simulation/build/lib").glob("*.so"))}
    registration["cmake_sha256"]=digest(root/"m8_backend/simulation/scratch/CMakeLists.txt")
    write(directory/"registration.json",registration)
    results=[]
    for trial in registration["trials"]:
        run_dir=directory/trial["id"]; run_dir.mkdir()
        name="limer-m8-"+str(trial["runId"])
        command=DOCKER+["run","--rm","--name",name,"--cpus=4","--memory=4g",
                       "-v",str(root)+":/work",
                       "-e","LD_LIBRARY_PATH=/work/m8_backend/simulation/build/lib",
                       IMAGE,"/work/"+str(BINARY_REL),
                       "--out=/work/"+str(run_dir.relative_to(root))]
        for key in ("scenario","capacityMbps","offeredMbps","lossRate","reportLoss","runId","faultTimeMs"):
            command.append(f"--{key}={trial[key]}")
        result=dict(id=trial["id"],start_unix=time.time(),command=command,status="RUNNING")
        write(run_dir/"status.json",result)
        try:
            if digest(binary)!=registration["hashes"]["binary"]: raise ValueError("frozen binary changed")
            for name,sha in registration["library_hashes"].items():
                if digest(root/"m8_backend/simulation/build/lib"/name)!=sha:
                    raise ValueError("frozen simulator library changed")
            with (run_dir/"stdout.log").open("w") as log:
                process=subprocess.run(command,stdout=log,stderr=subprocess.STDOUT,timeout=120)
            result["exit_code"]=process.returncode
            if process.returncode: raise ValueError("simulation process failed")
            truth=json.loads((run_dir/"truth.json").read_text())
            audit(truth)
            observer=replay(run_dir/"reports.jsonl",truth["observation_end_ns"])
            result.update(score(trial,truth,observer),status="PASS",packet_audit=True,
                          input_sha256=digest(run_dir/"reports.jsonl"),
                          truth_sha256=digest(run_dir/"truth.json"),
                          report_bytes=truth["reports_offered"]*64,
                          reports_dropped=truth["reports_dropped"],
                          sent_packets=sum(p["sent"] for p in truth["paths"]),
                          report_cost_basis="separate serialized modeled channel; not shared data-plane congestion")
        except (ValueError,FileNotFoundError,subprocess.TimeoutExpired) as e:
            result.update(status="FAILED",failure=str(e))
            subprocess.run(DOCKER+["rm","-f",name],capture_output=True)
        result["wall_seconds"]=time.time()-result["start_unix"]
        write(run_dir/"status.json",result);results.append(result)
        write(directory/"summary.json",aggregate(registration,results))
        print(trial["id"],result["status"],result.get("delay_ms"),
              result.get("false_alarm_events"),result.get("failure",""),flush=True)
        if result["status"]=="FAILED":
            # Engineering failure blocks more launches. Remaining registrations stay unverified.
            break
    write(directory/"terminal.json",dict(complete=len(results)==len(registration["trials"]),
         statuses=dict(Counter(r["status"] for r in results)),summary=aggregate(registration,results)))


if __name__=="__main__": main()
