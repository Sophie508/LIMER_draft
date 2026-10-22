"""Compare captured packet fields against independent native tcpdump decoding."""
import subprocess,re,json,importlib.util
from decimal import Decimal
from pathlib import Path
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')
# Load only parser definitions; do not rerun aggregate analysis as a side effect.
namespace={}
exec((ROOT/'baselines/simai_runtime/analyze_m6_packet_audit_v6.py').read_text().split('\nresults=[]')[0],namespace)
rows=[]
for name,sides in [('m6_packet_v4_original_l0p5',['sender','switch']),('m6_packet_v5_disabled_l0p5',['sender','receiver'])]:
 for side in sides:
  path=ROOT/'mininet_results'/name/(side+'.pcap')
  expected=iter(namespace['packets'](path))
  cmd=['docker','--host=unix:///run/user/1005/limer-docker/docker.sock','run','--rm','-v',str(ROOT/'mininet_results')+':/results:ro','limer-mininet-diagnostic:2026-10-10','tcpdump','-nn','-tt','-S','-v','-r',f'/results/{name}/{side}.pcap']
  proc=subprocess.Popen(cmd,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
  count=0;seq_count=0
  for line in proc.stdout:
   head=re.match(r'([0-9]+\.[0-9]+) IP .* length ([0-9]+)\)',line)
   if not head:raise ValueError('unexpected native header: '+line[:120])
   detail=next(proc.stdout)
   p=next(expected)
   assert int(Decimal(head[1])*1_000_000_000)==p['t_real_ns'],(name,side,'timestamp')
   assert int(head[2])==p['ip_len'],(name,side,'ip length')
   endpoint=re.match(r'\s+([0-9.]+)\.([0-9]+) > ([0-9.]+)\.([0-9]+):',detail)
   assert endpoint and (endpoint[1],int(endpoint[2]),endpoint[3],int(endpoint[4]))==(p['src'],p['sport'],p['dst'],p['dport'])
   length=re.search(r', length ([0-9]+)\s*$',detail)
   assert length and int(length[1])==p['payload_len'],(name,side,'payload length')
   seq=re.search(r'\bseq ([0-9]+)',detail)
   if seq:
    assert int(seq[1])==p['seq'],(name,side,'sequence')
    seq_count+=1
   count+=1
  assert proc.wait()==0,proc.stderr.read()
  assert next(expected,None) is None,'native missed captured records'
  rows.append(dict(name=name,side=side,all_captured_records_compared=count,absolute_sequence_fields_compared=seq_count,pass_fields=['timestamp','IPv4 length','endpoints','TCP payload length','absolute TCP sequence when printed'],status='pass'))
(ROOT/'logs/m6_native_decoder_agreement.json').write_text(json.dumps(rows,indent=2)+'\n')
print(json.dumps(rows))
