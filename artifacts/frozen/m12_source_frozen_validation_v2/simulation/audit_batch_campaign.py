"""Recompute completed campaign results from frozen observations, not summaries."""
import argparse
import importlib.util
import json
from pathlib import Path
import sys


def main():
    p=argparse.ArgumentParser()
    p.add_argument("--root",type=Path,required=True)
    args=p.parse_args()
    root=args.root.resolve()
    frozen=root/"m8_source_frozen_v1"
    sys.path.insert(0,str(frozen))
    spec=importlib.util.spec_from_file_location("frozen_campaign",frozen/"simulation/run_batch_observation.py")
    module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
    records=[]
    for campaign in ("validation_v1","stress_v1"):
        directory=root/"runs"/f"m8_{campaign}"
        registration=json.loads((directory/"registration.json").read_text())
        terminal=json.loads((directory/"terminal.json").read_text())
        if not terminal["complete"]:raise ValueError("campaign is not complete")
        expected=registration["hashes"]
        if module.digest(frozen/"limer_v0/batch_loss.py")!=expected["detector"]:
            raise ValueError("frozen detector source changed")
        if module.digest(frozen/"simulation/run_batch_observation.py")!=expected["runner"]:
            raise ValueError("frozen runner changed")
        if module.digest(frozen/"simulation/LimerBatchObservation.cc")!=expected["cpp"]:
            raise ValueError("frozen packet source changed")
        if module.digest(root/module.BINARY_REL)!=expected["binary"]:
            raise ValueError("binary changed")
        for name,sha in registration["library_hashes"].items():
            if module.digest(root/"m8_backend/simulation/build/lib"/name)!=sha:
                raise ValueError("simulator dependency changed")
        results=[]
        for trial in registration["trials"]:
            d=directory/trial["id"]
            status=json.loads((d/"status.json").read_text())
            if status["status"]!="PASS" or status["exit_code"]!=0:
                raise ValueError("nonterminal or unsuccessful scientific attempt")
            truth=json.loads((d/"truth.json").read_text());module.audit(truth)
            replay=module.replay(d/"reports.jsonl",truth["observation_end_ns"])
            scored=module.score(trial,truth,replay)
            for key,value in scored.items():
                if status[key]!=value:raise ValueError(f"replay/scoring disagreement: {trial['id']}/{key}")
            if module.digest(d/"reports.jsonl")!=status["input_sha256"]:
                raise ValueError("archived observer input changed")
            if module.digest(d/"truth.json")!=status["truth_sha256"]:
                raise ValueError("archived scoring truth changed")
            results.append(status)
        summary=module.aggregate(registration,results)
        if summary!=json.loads((directory/"summary.json").read_text()):
            raise ValueError("campaign aggregate disagreement")
        records.append(dict(campaign=campaign,trials=len(results),
            report_rows=sum(r["input_rows"] for r in results),
            source_packets=sum(r["sent_packets"] for r in results),
            telemetry_bytes=sum(r["report_bytes"] for r in results),
            exact_replay=True,packet_conservation=True,hashes=expected,summary=summary))
    output=root/"logs/m8_final_audit.json"
    module.write(output,dict(campaigns=records,passed=True,
                 claim="Exact frozen-rule and accounting replay; not an independent fault-cause proof"))
    print(json.dumps(dict(passed=True,campaigns=[(r["campaign"],r["trials"]) for r in records])))


if __name__=="__main__":main()
