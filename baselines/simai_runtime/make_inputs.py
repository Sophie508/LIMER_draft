"""Create explicit, hashed simulator inputs; refuses to overwrite a run."""
import argparse
import hashlib
import json
from pathlib import Path


def make_inputs(root, name, ranks, slowdown=1, mtu=9000):
    out = root / 'runs' / name
    out.mkdir(parents=True, exist_ok=False)
    container = '/work/runs/' + name
    topology = [f'{ranks+1} 1 0 1 {ranks} A100', str(ranks)]
    for rank in range(ranks):
        bandwidth = int(200 / slowdown) if rank == ranks - 1 else 200
        topology.append(f'{rank} {ranks} {bandwidth}Gbps 500ns 0')
    (out / 'topology.txt').write_text('\n'.join(topology) + '\n')
    (out / 'flow.txt').write_text('0\n')
    (out / 'trace_nodes.txt').write_text('0\n')
    source = root / 'baselines/SimAI-official/astra-sim-alibabacloud/inputs/config/SimAI.conf'
    original = source.read_text()
    config = []
    outputs = {'FCT_OUTPUT_FILE':'fct.txt', 'TRACE_OUTPUT_FILE':'packets.tr',
               'PFC_OUTPUT_FILE':'pfc.txt', 'QLEN_MON_FILE':'qlen.txt', 'BW_MON_FILE':'bw.txt',
               'RATE_MON_FILE':'rate.txt', 'CNP_MON_FILE':'cnp.txt'}
    overrides = {'FLOW_FILE':container+'/flow.txt', 'TRACE_FILE':container+'/trace_nodes.txt',
                 'PACKET_PAYLOAD_SIZE':str(mtu), 'SIMULATOR_STOP_TIME':'10',
                 'ENABLE_TRACE':'0'}
    overrides.update({key:container+'/'+value for key,value in outputs.items()})
    for line in original.splitlines():
        parts = line.split()
        config.append(parts[0]+' '+overrides[parts[0]] if parts and parts[0] in overrides else line)
    (out / 'SimAI.conf').write_text('\n'.join(config)+'\n')
    manifest = dict(name=name, ranks=ranks, GPUs_per_server=1, switches=1,
                    healthy_Gbps=200, last_rank_Gbps=int(200/slowdown),
                    propagation_ns=500, slowdown=slowdown, MTU=mtu, CC_MODE=1,
                    AS_SEND_LAT_us=3, AS_PXN_ENABLE=0, AS_NVLS_ENABLE=0,
                    packet_loss=0, hashes={})
    for path in out.iterdir():
        manifest['hashes'][path.name] = hashlib.sha256(path.read_bytes()).hexdigest()
    (out / 'inputs.json').write_text(json.dumps(manifest,indent=2)+'\n')
    return out


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--root',type=Path,required=True)
    parser.add_argument('--name',required=True)
    parser.add_argument('--ranks',type=int,required=True)
    parser.add_argument('--slowdown',type=float,default=1)
    parser.add_argument('--mtu',type=int,default=9000)
    args=parser.parse_args()
    print(make_inputs(args.root,args.name,args.ranks,args.slowdown,args.mtu))
