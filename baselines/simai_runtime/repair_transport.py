"""Repair measured final-packet completion failures in the copied backend."""
import difflib
from pathlib import Path

root=Path('/work')
backend=root/'baselines/SimAI-official/astra-sim-alibabacloud/extern/network_backend/ns3-interface/simulation'
directory=backend/'src/point-to-point/model'
diff=''

def update(name, transform):
    global diff
    path=directory/name
    original=path.read_text()
    modified=transform(original)
    if original==modified:
        raise RuntimeError('Expected a new change: '+name)
    path.write_text(modified)
    diff+=''.join(difflib.unified_diff(original.splitlines(True),modified.splitlines(True),
                  fromfile='a/src/point-to-point/model/'+name,
                  tofile='b/src/point-to-point/model/'+name))

def device(text):
    condition='if(p->GetSize()<9000&&p->GetSize()>60)'
    callback='Simulator::Schedule(txTime,&QbbNetDevice::SendCallback,this,p);'
    assert text.count(condition)==2 and text.count(callback)==2
    return text.replace(condition,'if (p->GetSize() > 0)').replace(
        callback,'if (ch.l3Prot == 0x11) '+callback)

def hardware(text):
    start=text.index('int RdmaHw::SendPacketComplete(')
    end=text.index('\nvoid RdmaHw::SendComplete',start)
    function='''int RdmaHw::SendPacketComplete(Ptr<Packet> p, CustomHeader &ch)
{
    if (ch.l3Prot != 0x11) return 0;
    Ptr<RdmaQueuePair> qp = GetQp(ch.dip, ch.udp.sport, ch.udp.pg);
    if (qp == NULL || qp->m_serializationComplete) return 0;
    if (p->GetSize() < ch.GetSerializedSize()) return 0;
    uint64_t end = uint64_t(ch.udp.seq) + p->GetSize() - ch.GetSerializedSize();
    if (end >= qp->m_size) {
        qp->m_serializationComplete = true;
        SendComplete(qp);
    }
    return 0;
}
'''
    return text[:start]+function+text[end:]

def queue_pair(text):
    anchor='\tuint64_t m_size, m_init_size, m_tag;'
    assert text.count(anchor)==1
    return text.replace(anchor,anchor+'\n\tbool m_serializationComplete = false; // One final serialization notification per QP.')

update('qbb-net-device.cc',device)
update('rdma-hw.cc',hardware)
update('rdma-queue-pair.h',queue_pair)
(root/'baselines/simai_runtime/transport_repair.diff').write_text(diff)
print('Shared transport repair written; rebuild and repeat all gates before measurements')
