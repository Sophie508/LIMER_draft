#include "ns3/ipv4.h"
#include "ns3/packet.h"
#include "ns3/ipv4-header.h"
#include "ns3/pause-header.h"
#include "ns3/flow-id-tag.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "nvswitch-node.h"
#include "qbb-net-device.h"
#include "rdma-queue-pair.h"
#include "ppp-header.h"
#include "ns3/int-header.h"
#include "ns3/simulator.h"
#include <cmath>
#include <limits>

namespace ns3 {

static_assert(LIMER_ROUTE_BACKGROUND_SPORT_MIN == LIMER_BACKGROUND_SPORT_MIN,
	"route recorder and RDMA background source-port bounds differ");
static_assert(LIMER_ROUTE_BACKGROUND_SPORT_MAX == LIMER_BACKGROUND_SPORT_MAX,
	"route recorder and RDMA background source-port bounds differ");

TypeId NVSwitchNode::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::NVSwitchNode")
    .SetParent<Node> ()
    .AddConstructor<NVSwitchNode> ()
	.AddAttribute("AckHighPrio",
			"Set high priority for ACK/NACK or not",
			UintegerValue(0),
			MakeUintegerAccessor(&NVSwitchNode::m_ackHighPrio),
			MakeUintegerChecker<uint32_t>())
  ;
  return tid;
}

NVSwitchNode::NVSwitchNode(){
	m_ecmpSeed = m_id;
	m_node_type = 2;
	m_mmu = CreateObject<SwitchMmu>();
	for (uint32_t i = 0; i < pCnt; i++){
		m_txBytes[i] = 0;
		last_txBytes[i] = 0;
		last_port_qlen[i] = 0;
	}
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastPktSize[i] = m_lastPktTs[i] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_u[i] = 0;
}

uint64_t NVSwitchNode::QueueByteKey(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex){
	NS_ASSERT_MSG(inDev < pCnt, "NVSwitch ingress port exceeds accounting bound");
	NS_ASSERT_MSG(outDev < pCnt, "NVSwitch egress port exceeds accounting bound");
	NS_ASSERT_MSG(qIndex < qCnt, "NVSwitch queue exceeds accounting bound");
	return (static_cast<uint64_t>(inDev) * pCnt + outDev) * qCnt + qIndex;
}

void NVSwitchNode::AddQueuedBytes(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, uint32_t bytes){
	uint32_t &queued = m_bytes[QueueByteKey(inDev, outDev, qIndex)];
	NS_ASSERT_MSG(queued <= std::numeric_limits<uint32_t>::max() - bytes,
		"NVSwitch queued-byte accounting overflow");
	queued += bytes;
}

void NVSwitchNode::RemoveQueuedBytes(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, uint32_t bytes, const char* underflowMessage){
	uint64_t key = QueueByteKey(inDev, outDev, qIndex);
	auto it = m_bytes.find(key);
	NS_ASSERT_MSG(it != m_bytes.end() && it->second >= bytes,
		underflowMessage);
	it->second -= bytes;
	if (it->second == 0)
		m_bytes.erase(it);
}

bool NVSwitchNode::RememberLimerRouteChoice(
		const LimerRouteChoiceEvent& event){
	std::lock_guard<std::mutex> guard(m_limerRouteChoiceMutex);
	return EmitLimerRouteChoiceOnce(&m_limerRouteChoices, event);
}

int NVSwitchNode::GetOutDev(Ptr<const Packet> p, CustomHeader &ch){
	// look up entries
	auto entry = m_rtTable.find(ch.dip);

	// no matching entry
	if (entry == m_rtTable.end())
		return -1;

	// entry found
	auto &nexthops = entry->second;

	// pick one next hop based on hash
	union {
		uint8_t u8[4+4+2+2];
		uint32_t u32[3];
	} buf = {};
	buf.u32[0] = ch.sip;
	buf.u32[1] = ch.dip;
	uint16_t packet_sport = 0;
	uint16_t packet_dport = 0;
	uint16_t pg = 0;
	if (ch.l3Prot == 0x6)
		buf.u32[2] = ch.tcp.sport | ((uint32_t)ch.tcp.dport << 16);
	else if (ch.l3Prot == 0x11){
		buf.u32[2] = ch.udp.sport | ((uint32_t)ch.udp.dport << 16);
		packet_sport = ch.udp.sport;
		packet_dport = ch.udp.dport;
		pg = ch.udp.pg;
	}else if (ch.l3Prot == 0xFC || ch.l3Prot == 0xFD){
		buf.u32[2] = ch.ack.sport | ((uint32_t)ch.ack.dport << 16);
		packet_sport = ch.ack.sport;
		packet_dport = ch.ack.dport;
		pg = ch.ack.pg;
	}

	const uint32_t hash = EcmpHash(buf.u8, 12, m_ecmpSeed);
	const LimerEcmpSelection selection = LimerSelectEcmp(hash, nexthops);
	NS_ABORT_MSG_IF(!selection.ok,
		"NVSwitch route has no valid ECMP candidate");
	if (HasLimerRouteChoiceSink()) {
		LimerRouteChoiceEvent event;
		if (LimerClassifyBackgroundRoute(
				ch.l3Prot, ch.sip, ch.dip, packet_sport, packet_dport,
				pg, &event)) {
			event.timestamp_ns = Simulator::Now().GetNanoSeconds();
			event.node_id = GetId();
			event.node_type = GetNodeType();
			event.ecmp_seed = m_ecmpSeed;
			event.ecmp_hash = hash;
			event.candidate_count = selection.candidate_count;
			event.bucket = selection.bucket;
			event.egress_port = selection.egress_port;
			RememberLimerRouteChoice(event);
		}
	}
	return static_cast<int>(selection.egress_port);
}

void NVSwitchNode::SendToDev(Ptr<Packet>p, CustomHeader &ch){
	int idx = GetOutDev(p, ch);
	if (idx >= 0){
		NS_ASSERT_MSG(m_devices[idx]->IsLinkUp(), "The routing table look up should return link that is up");

		// determine the qIndex
		uint32_t qIndex;
		if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))){  //QCN or PFC or NACK, go highest priority
			qIndex = 0;
		}else{
			qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg); // if TCP, put to queue 1
		}


		// admission control
		FlowIdTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetFlowId();
		if (qIndex != 0){ //not highest priority
			if (m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize()) && m_mmu->CheckEgressAdmission(idx, qIndex, p->GetSize())){			// Admission control
				m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize());
				m_mmu->UpdateEgressAdmission(idx, qIndex, p->GetSize());
			}else{
				m_limerDropPkts[idx]++;
				m_limerDropBytes[idx] += p->GetSize();
				return; // Drop
			}
			AddQueuedBytes(inDev, idx, qIndex, p->GetSize());
		}
		m_devices[idx]->SwitchSend(qIndex, p, ch);
	}else
	{
		FlowIdTag limerNoRouteTag;
		p->PeekPacketTag(limerNoRouteTag);
		uint32_t limerInDev = limerNoRouteTag.GetFlowId();
		if (limerInDev < pCnt) {
			m_limerDropPkts[limerInDev]++;
			m_limerDropBytes[limerInDev] += p->GetSize();
		}
		return; // Drop
	}
}

uint32_t NVSwitchNode::EcmpHash(const uint8_t* key, size_t len, uint32_t seed) {
  uint32_t h = seed;
  if (len > 3) {
    const uint32_t* key_x4 = (const uint32_t*) key;
    size_t i = len >> 2;
    do {
      uint32_t k = *key_x4++;
      k *= 0xcc9e2d51;
      k = (k << 15) | (k >> 17);
      k *= 0x1b873593;
      h ^= k;
      h = (h << 13) | (h >> 19);
      h += (h << 2) + 0xe6546b64;
    } while (--i);
    key = (const uint8_t*) key_x4;
  }
  if (len & 3) {
    size_t i = len & 3;
    uint32_t k = 0;
    key = &key[i - 1];
    do {
      k <<= 8;
      k |= *key--;
    } while (--i);
    k *= 0xcc9e2d51;
    k = (k << 15) | (k >> 17);
    k *= 0x1b873593;
    h ^= k;
  }
  h ^= len;
  h ^= h >> 16;
  h *= 0x85ebca6b;
  h ^= h >> 13;
  h *= 0xc2b2ae35;
  h ^= h >> 16;
  return h;
}

void NVSwitchNode::SetEcmpSeed(uint32_t seed){
	m_ecmpSeed = seed;
}

void NVSwitchNode::AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx){
	uint32_t dip = dstAddr.Get();
	m_rtTable[dip].push_back(intf_idx);
}

void NVSwitchNode::ClearTable(){
	m_rtTable.clear();
}

// This function can only be called in switch mode
bool NVSwitchNode::SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch){
	SendToDev(packet, ch);
	return true;
}

void NVSwitchNode::SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p){
	FlowIdTag t;
	p->PeekPacketTag(t);
	if (qIndex != 0){
		uint32_t inDev = t.GetFlowId();
		m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize());
		m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize());
		RemoveQueuedBytes(inDev, ifIndex, qIndex, p->GetSize(),
			"NVSwitch dequeue admission accounting underflow");
	}
	m_txBytes[ifIndex] += p->GetSize();
	m_lastPktSize[ifIndex] = p->GetSize();
	m_lastPktTs[ifIndex] = Simulator::Now().GetTimeStep();
}

void NVSwitchNode::SwitchNotifyDrop(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p){
	if (qIndex == 0)
		return;
	FlowIdTag t;
	NS_ASSERT_MSG(p->PeekPacketTag(t),
		"A queued NVSwitch packet must retain its ingress FlowIdTag until purge");
	uint32_t inDev = t.GetFlowId();
	m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize());
	m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize());
	RemoveQueuedBytes(inDev, ifIndex, qIndex, p->GetSize(),
		"NVSwitch purge admission accounting underflow");
}
// for monitor
/**
 * outoput format:
 * time, sw_id, port_id, q_id, qlen, port_len
*/
void NVSwitchNode::PrintSwitchQlen(FILE* qlen_output){
	uint32_t n_dev = this->GetNDevices();
	for(uint32_t i = 1; i < n_dev; ++i){
		uint64_t port_len = 0;
		for(uint32_t j=0; j < qCnt; ++j){
			port_len += m_mmu->egress_bytes[i][j];
		}
		if(port_len == last_port_qlen[i]){
			continue;
		}
		for(uint32_t j=0; j < qCnt; ++j){
			fprintf(qlen_output, "%lu, %u, %u, %u, %u, %lu\n", Simulator::Now().GetTimeStep(), m_id, i, j, m_mmu->egress_bytes[i][j], port_len);
			fflush(qlen_output);
		}
		last_port_qlen[i] = port_len;
	}		
}

/**
 * outoput format:
 * time, sw_id, port_id, txBytes
*/
void NVSwitchNode::PrintSwitchBw(FILE* bw_output, uint32_t bw_mon_interval){
	uint32_t n_dev = this->GetNDevices();
	for(uint32_t i = 1; i < n_dev; ++i){
		if(last_txBytes[i] == m_txBytes[i]){
			continue;
		}
		double bw = (m_txBytes[i] - last_txBytes[i]) * 8 * 1e6 / bw_mon_interval; // bit/s
		bw = bw*1.0 / 1e9; // Gbps
		fprintf(bw_output, "%lu, %u, %u, %f\n", Simulator::Now().GetTimeStep(), m_id, i, bw);
		fflush(bw_output);
		last_txBytes[i] = m_txBytes[i];
	}		
}
} /* namespace ns3 */
