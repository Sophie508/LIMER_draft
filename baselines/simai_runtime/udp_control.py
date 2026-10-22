"""Paced UDP background load on B, with explicit byte/interval accounting."""
import json
from pathlib import Path
import signal
import socket
import sys
import time

mode,host,output=sys.argv[1:]
running=True

def stop(*_):
    global running
    running=False

signal.signal(signal.SIGTERM,stop)
s=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
s.settimeout(.1)
start=time.monotonic_ns()
count=0
if mode=='receive':
    s.bind((host,19000))
    while running:
        try:count+=len(s.recv(65535))
        except socket.timeout:pass
else:
    payload=b'x'*1200
    interval=len(payload)*8/50_000_000
    deadline=time.monotonic()
    while running:
        count+=s.sendto(payload,(host,19000))
        deadline+=interval
        wait=deadline-time.monotonic()
        if wait>0:time.sleep(wait)
        else:deadline=time.monotonic()
end=time.monotonic_ns()
Path(output).write_text(json.dumps(dict(mode=mode,bytes=count,start_ns=start,end_ns=end,
    requested_Mbit_s=50 if mode=='send' else None,measured_Mbit_s=count*8000/(end-start)),indent=2)+'\n')
