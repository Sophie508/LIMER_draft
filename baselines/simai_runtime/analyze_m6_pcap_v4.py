"""Header-only PCAP analysis; gaps are diagnostic observations, not alarms."""
from pathlib import Path
import json,struct,ipaddress,statistics,re
ROOT=Path('/home/suliu/scratch/LIMER_WORK_2026-10-10')

def packets(path):
 with path.open('rb') as f:
  header=f.read(24)
  if len(header)!=24:raise ValueError('missing pcap header')
  fmt={b'\xd4\xc3\xb2\xa1':('<',1000),b'\xa1\xb2\xc3\xd4':('>',1000),b'\x4d\x3c\xb2\xa1':('<',1),b'\xa1\xb2\x3c\x4d':('>',1)}
  endian,scale=fmt[header[:4]]
  assert struct.unpack(endian+'I',header[20:24])[0]==1,'requires Ethernet pcap'
  while True:
   h=f.read(16)
   if not h:return
   if len(h)!=16:raise ValueError('truncated record header')
   sec,frac,caplen,wirelen=struct.unpack(endian+'IIII',h);b=f.read(caplen)
   if len(b)!=caplen:raise ValueError('truncated capture bytes')
   if len(b)<54 or b[12:14]!=b'\x08\x00':continue
   ihl=(b[14]&15)*4;tcp=14+ihl
   if b[23]!=6 or len(b)<tcp+20:continue
   total=struct.unpack('!H',b[16:18])[0];tcph=(b[tcp+12]>>4)*4
   if len(b)<tcp+tcph:raise ValueError('truncated TCP options')
   src=str(ipaddress.ip_address(b[26:30]));dst=str(ipaddress.ip_address(b[30:34]))
   sport,dport,seq,ack=struct.unpack('!HHII',b[tcp:tcp+12])
   yield dict(t_real_ns=sec*1_000_000_000+frac*scale,src=src,dst=dst,
    sport=sport,dport=dport,seq=seq,ack=ack,flags=b[tcp+13],payload_len=total-ihl-tcph,ip_len=total,wire_len=wirelen)

def analyze_capture(path,offset,fault):
 states={};data_count=0;oversized=0;lengths=[];early_data=0;first_gap=None;first_repeat=None;first_data=None
 for p in packets(path):
  if p['src']!='10.0.0.3' or p['dst']!='10.0.0.4' or p['dport']!=15000:continue
  t=p['t_real_ns']+offset;key=(p['src'],p['dst'],p['sport'],p['dport'])
  if p['flags']&2:states[key]=dict(base=(p['seq']+1)%(1<<32),front=0,pending=[])
  if p['payload_len']<=0:continue
  if key not in states:raise ValueError('data seen without initial SYN')
  s=states[key];a=(p['seq']-s['base'])%(1<<32);b=a+p['payload_len']
  data_count+=1;lengths.append(p['ip_len']);oversized+=p['ip_len']>1500
  if fault<=t<=fault+100_000_000:early_data+=1
  if t>=fault and first_data is None:first_data=t
  if a>s['front'] and t>=fault and first_gap is None:first_gap=dict(t_ns=t,start=s['front'],end=a,resolved_ns=None)
  if a<s['front'] and t>=fault and first_repeat is None:first_repeat=t
  if a<=s['front']:
   s['front']=max(s['front'],b)
   while s['pending'] and s['pending'][0][0]<=s['front']:
    left,right=s['pending'].pop(0);s['front']=max(s['front'],right)
  else:
   s['pending'].append((a,b));s['pending'].sort()
  if first_gap and first_gap['resolved_ns'] is None and s['front']>=first_gap['end']:first_gap['resolved_ns']=t
 return dict(data_packets=data_count,ip_length_max=max(lengths,default=None),ip_length_median=statistics.median(lengths) if lengths else None,
  ip_lengths_above_mtu1500=oversized,data_packets_first100ms=early_data,
  first_data_after_fault_ms=(first_data-fault)/1e6 if first_data else None,
  first_gap_ms=(first_gap['t_ns']-fault)/1e6 if first_gap else None,
  first_gap_duration_ms=(first_gap['resolved_ns']-first_gap['t_ns'])/1e6 if first_gap and first_gap['resolved_ns'] else None,
  first_repeated_sequence_ms=(first_repeat-fault)/1e6 if first_repeat else None)

results=[]
for folder in sorted((ROOT/'mininet_results').glob('m6_packet_v4_*')):
 if not (folder/'summary.json').exists():continue
 try:
  events=[json.loads(l) for l in (folder/'events.jsonl').open()]
  fault=next(e['record']['t_after_ns'] for e in events if e['event']=='FAULT_APPLIED')
  clocks=[json.loads((folder/f'capture_clock_{phase}.json').read_text()) for phase in ['start','end']]
  offsets=[(c['monotonic_before_ns']+c['monotonic_after_ns'])//2-c['realtime_ns'] for c in clocks]
  sample=next((e for e in events if e['event']=='HOST_RETRANS_SAMPLE' and e['rank']==2 and e['fabric']=='A' and e['sample_t_monotonic_ns']>=fault and (e['retrans_delta'] or 0)>0),None)
  result=dict(name=folder.name,status=json.loads((folder/'summary.json').read_text())['status'],clock_offset_drift_ns=offsets[1]-offsets[0],
    clock_bracket_width_ns=[c['monotonic_after_ns']-c['monotonic_before_ns'] for c in clocks],
    observer_first_positive_ms=(sample['sample_t_monotonic_ns']-fault)/1e6 if sample else None)
  for side in ['sender','switch']:
   result[side]=analyze_capture(folder/f'{side}.pcap',offsets[0],fault)
   text=(folder/f'{side}_capture.stderr').read_text()
   result[side]['capture_stats']=text.splitlines()[-3:]
   match=re.search(r'(\d+) packets dropped by kernel',text)
   if match is None or int(match[1])!=0:raise ValueError('capture loss not zero or unavailable: '+side)
  result['diagnostic_valid']=True
 except Exception as exc:result=dict(name=folder.name,diagnostic_valid=False,error=str(exc))
 results.append(result)
(ROOT/'logs/m6_packet_analysis.json').write_text(json.dumps(results,indent=2)+'\n')
for r in results:print(r)
