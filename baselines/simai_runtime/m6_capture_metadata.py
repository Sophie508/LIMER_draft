"""Socket metadata capture on one task veth; no payload retained."""
import ipaddress,json,socket,struct,sys,time
from pathlib import Path
interface,prefix,stop=sys.argv[1:];prefix=Path(prefix);stop=Path(stop)
s=socket.socket(socket.AF_PACKET,socket.SOCK_RAW,socket.htons(3));s.bind((interface,0))
s.setsockopt(socket.SOL_SOCKET,socket.SO_RCVBUF,4*1024*1024)
s.setsockopt(socket.SOL_SOCKET,35,1);s.settimeout(.2)
counts=dict(received_frames=0,retained_tcp_headers=0,missing_kernel_timestamps=0)
prefix.with_suffix('.ready').write_text('ready\n')
with prefix.with_suffix('.jsonl').open('w') as out:
 while not stop.exists():
  try:packet,ancillary,flags,address=s.recvmsg(128,128,socket.MSG_TRUNC)
  except socket.timeout:continue
  counts['received_frames']+=1
  if len(packet)<54 or packet[12:14]!=b'\x08\x00':continue
  b=packet;ihl=(b[14]&15)*4;tcp=14+ihl
  if b[23]!=6 or len(b)<tcp+20:continue
  src=str(ipaddress.ip_address(b[26:30]));dst=str(ipaddress.ip_address(b[30:34]))
  sport,dport,seq,ack=struct.unpack('!HHII',b[tcp:tcp+12])
  if {src,dst}!={'10.0.0.3','10.0.0.4'} or 15000 not in [sport,dport]:continue
  stamp=next((c for level,kind,c in ancillary if level==socket.SOL_SOCKET and kind==35),None)
  if stamp is None:counts['missing_kernel_timestamps']+=1;t_real_ns=None
  else:
   seconds,nanoseconds=struct.unpack('=qq',stamp[:16]);t_real_ns=seconds*1_000_000_000+nanoseconds
  total=struct.unpack('!H',b[16:18])[0];tcph=(b[tcp+12]>>4)*4
  if len(b)<tcp+tcph:raise RuntimeError('truncated TCP header')
  row=dict(t_real_ns=t_real_ns,receive_realtime_ns=time.time_ns(),src=src,dst=dst,sport=sport,dport=dport,
    seq=seq,ack=ack,flags=b[tcp+13],payload_len=total-ihl-tcph,ip_len=total)
  out.write(json.dumps(row)+'\n');counts['retained_tcp_headers']+=1
received,dropped=struct.unpack('=II',s.getsockopt(263,6,8))
counts.update(packet_socket_received=received,packet_socket_dropped=dropped)
prefix.with_suffix('.stats.json').write_text(json.dumps(counts,indent=2)+'\n')
s.close()
