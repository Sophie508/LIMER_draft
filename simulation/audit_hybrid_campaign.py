"""Independently recompute a frozen hybrid campaign and verify its artifacts."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument("--root",type=Path,required=True)
    parser.add_argument("--frozen",required=True)
    parser.add_argument("--campaign",required=True)
    args=parser.parse_args();root=args.root.resolve();frozen=root/args.frozen
    sys.path.insert(0,str(frozen))
    spec=importlib.util.spec_from_file_location("frozen_hybrid",frozen/"simulation/run_hybrid_observation.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    directory=root/"runs"/args.campaign
    registration=json.loads((directory/"registration.json").read_text())
    terminal=json.loads((directory/"terminal.json").read_text())
    if not terminal["complete"]:raise ValueError("incomplete ledger; no success claim")
    source_paths=dict(detector="limer_v0/hybrid_delivery.py",runner="simulation/run_hybrid_observation.py",
        cpp="simulation/LimerHybridObservation.cc",header="simulation/batch_deficit_observer.h",
        base_detector="limer_v0/batch_loss.py",early_detector="limer_v0/early_delivery.py")
    for key,relative in source_paths.items():
        if key in registration["hashes"] and module.digest(frozen/relative)!=registration["hashes"][key]:
            raise ValueError(f"frozen source changed: {key}")
    binary=root/module.BINARY_REL
    if module.digest(binary)!=registration["hashes"]["binary"]:raise ValueError("binary changed")
    archived=frozen/"native_binary"/binary.name
    if module.digest(archived)!=registration["hashes"]["binary"]:raise ValueError("archived executable differs")
    for name,sha in registration["library_hashes"].items():
        if module.digest(binary.parent.parent/"lib"/name)!=sha:raise ValueError("dependency changed")
    if module.digest(binary.parent.parent.parent/"scratch/CMakeLists.txt")!=registration["cmake_sha256"]:
        raise ValueError("scratch build wiring changed")
    results=[];report_rows=0;probes=0;wire=0;records={}
    for trial in registration["trials"]:
        d=directory/trial["id"];status=json.loads((d/"status.json").read_text())
        if status["status"]!="PASS" or status["exit_code"]!=0:raise ValueError("engineering gate failed")
        truth=json.loads((d/"truth.json").read_text());module.audit(truth)
        observations=module.replay(d/"reports.jsonl",truth["observation_end_ns"])
        audits=module.audit_observations(d,trial,truth,observations)
        for key,value in dict(module.score(trial,truth,observations),**audits).items():
            if status[key]!=value:raise ValueError(f"independent replay differs: {trial['id']}/{key}")
        if module.digest(d/"reports.jsonl")!=status["input_sha256"]:raise ValueError("input changed")
        if module.digest(d/"truth.json")!=status["truth_sha256"]:raise ValueError("truth changed")
        # Offers, counter samples and native alarms were audited, and frozen here
        # with new hashes; registration/status hashes already bind input and truth.
        records[trial["id"]]={p.name:module.digest(p) for p in d.glob("*.jsonl")}
        report_rows+=observations["input_rows"]
        probes+=sum(p["probe_sent"] for p in truth["paths"])
        wire+=sum(p["wire_bytes"] for p in truth["paths"])
        results.append(status)
    summary=module.aggregate(registration,results)
    if summary!=json.loads((directory/"summary.json").read_text()) or summary!=terminal["summary"]:
        raise ValueError("aggregate differs")
    output=root/"logs"/f"{args.campaign}_final_audit.json"
    module.write(output,dict(passed=True,source=args.frozen,campaign=args.campaign,
        registrations=len(results),report_rows=report_rows,probe_packets=probes,wire_bytes=wire,
        source_hashes=registration["hashes"],artifacts=records,summary=summary,
        claim="Native causal report replay and exact accounting, not independent physical-cause proof"))
    print(json.dumps(dict(passed=True,campaign=args.campaign,registrations=len(results),
        report_rows=report_rows,probe_packets=probes,verdict=summary["per_condition_95_verdict"])))


if __name__=="__main__":main()
