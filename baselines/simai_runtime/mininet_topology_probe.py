"""Validate original kernel-OVS topology inside the isolated rootless container."""
import json
from limer_v0.topology import build_topology

topology=build_topology('dual')
try:
    results={}
    for fabric in ('A','B'):
        destination=topology.fabrics[fabric][1].local_ip
        output=topology.hosts[0].cmd('ping -c 3 -W 2 '+destination)
        results[fabric]=output
        if '0% packet loss' not in output:
            raise RuntimeError('Connectivity gate failed on '+fabric)
    print(json.dumps({'status':'PASS','datapath':'kernel','ping':results},indent=2))
finally:
    topology.stop()
