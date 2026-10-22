"""Pilot-only environmental controls; no detector/policy input or source patch."""
import json
from pathlib import Path
import time
from limer_v0 import orchestrator as o

args=o.parse_args(None)
config=json.loads(args.config.read_text())
kind=config.get('pilot_control_kind','nominal')
original_build=o.build_topology
original_round=o._run_collective_round


def build(*a,**kw):
    descriptor=original_build(*a,**kw)
    original_apply=descriptor.apply_fault_profile
    def apply(profile,route='A',rank=2):
        record=original_apply(profile,route,rank)
        if kind=='reorder' and route=='A':
            command=['tc','qdisc','change','dev',descriptor.fault_interface(route,rank),
                     'root','handle','1:','netem','limit','1000','delay','10ms',
                     'rate','100mbit','reorder','25%','50%']
            t=time.monotonic_ns()
            result=descriptor._host_command_runner(rank)(command)
            record.update(control_kind=kind,control_command=command,
                          control_before_ns=t,t_after_ns=time.monotonic_ns(),
                          control_stdout=result.stdout,control_stderr=result.stderr)
        return record
    descriptor.apply_fault_profile=apply
    if kind=='congestion':
        folder=args.results_dir/args.run_id
        destination=descriptor.fabrics['B'][3].local_ip
        receiver=descriptor.hosts[3].popen(['python3','/runtime/udp_control.py',
            'receive',destination,str(folder/'background_receiver.json')])
        time.sleep(.1)
        sender=descriptor.hosts[2].popen(['python3','/runtime/udp_control.py',
            'send',destination,str(folder/'background_sender.json')])
        original_stop=descriptor.stop
        def stop():
            for process in (sender,receiver):
                if process.poll() is None:process.terminate()
            for process in (sender,receiver):
                try:process.wait(timeout=3)
                except Exception:process.kill();process.wait()
            original_stop()
        descriptor.stop=stop
    return descriptor


def run_round(*a,**kw):
    if kind=='burst_pause':
        start=time.monotonic_ns()
        time.sleep(.25)
        a[4].emit('CONTROL_ROUND_PAUSE',control_kind=kind,
                  start_ns=start,end_ns=time.monotonic_ns(),duration_s=.25)
    return original_round(*a,**kw)


o.build_topology=build
o._run_collective_round=run_round
summary=o.execute_run(config,args.results_dir,args.workdir,args.run_id)
print(json.dumps(summary,indent=2))
raise SystemExit(0 if summary.get('status')=='complete' else 1)
