"""Inventory isolated emulator interface settings; no changes."""
import json,subprocess
from pathlib import Path
from limer_v0.topology import build_topology
p=Path('/results/m6_offload_inventory');p.mkdir(exist_ok=False)
d=build_topology('dual')
try:
    rows=[]
    for fabric,endpoints in d.fabrics.items():
        for rank,e in endpoints.items():
            for side,name,run in [('host',e.host_interface,d._host_command_runner(rank)),('switch',e.switch_interface,lambda cmd:subprocess.run(cmd,check=True,capture_output=True,text=True))]:
                rows.append(dict(fabric=fabric,rank=rank,side=side,interface=name,
                    link=json.loads(run(['ip','-j','link','show','dev',name]).stdout),
                    features=run(['ethtool','-k',name]).stdout))
    (p/'inventory.json').write_text(json.dumps(rows,indent=2)+'\n')
    print(json.dumps(rows,indent=2))
finally:d.stop()
