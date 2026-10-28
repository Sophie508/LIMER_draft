#include "ns3/ipv4.h"
#include "ns3/packet.h"
#include "ns3/ipv4-header.h"
#include "ns3/pause-header.h"
#include "ns3/flow-id-tag.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "switch-node.h"
#include "qbb-net-device.h"
#include "limer-congestion-signal.h"
#include "rdma-queue-pair.h"
#include "ppp-header.h"
#include "ns3/int-header.h"
#include "ns3/simulator.h"
#include <cmath>
#include <limits>

namespace ns3 {

namespace {
void FillBackgroundSignalFlow(const CustomHeader& ch,
		LimerCongestionSignalEvent* event) {
	uint16_t sport = 0, dport = 0, pg = 0;
	if (ch.l3Prot == 0x11) {
		sport = ch.udp.sport; dport = ch.udp.dport; pg = ch.udp.pg;
	} else if (ch.l3Prot == 0xFC || ch.l3Prot == 0xFD) {
		sport = ch.ack.sport; dport = ch.ack.dport; pg = ch.ack.pg;
	} else {
		return;
	}
	event->packet_sip = ch.sip;
	event->has_packet_tuple = true;
	event->packet_dip = ch.dip;
	event->packet_sport = sport;
	event->packet_dport = dport;
	LimerRouteChoiceEvent route;
	if (LimerClassifyBackgroundRoute(
			ch.l3Prot, ch.sip, ch.dip, sport, dport, pg, &route)) {
		event->has_flow = true;
		event->flow_src = route.flow_src;
		event->flow_dst = route.flow_dst;
		event->flow_sport = route.flow_sport;
		event->flow_dport = route.flow_dport;
	}
}
}  // namespace

static_assert(LIMER_ROUTE_BACKGROUND_SPORT_MIN == LIMER_BACKGROUND_SPORT_MIN,
	"route recorder and RDMA background source-port bounds differ");
static_assert(LIMER_ROUTE_BACKGROUND_SPORT_MAX == LIMER_BACKGROUND_SPORT_MAX,
	"route recorder and RDMA background source-port bounds differ");

TypeId SwitchNode::GetTypeId (void)
{
  static TypeId tid = TypeId ("ns3::SwitchNode")
    .SetParent<Node> ()
    .AddConstructor<SwitchNode> ()
	.AddAttribute("EcnEnabled",
			"Enable ECN marking.",
			BooleanValue(false),
			MakeBooleanAccessor(&SwitchNode::m_ecnEnabled),
			MakeBooleanChecker())
	.AddAttribute("CcMode",
			"CC mode.",
			UintegerValue(0),
			MakeUintegerAccessor(&SwitchNode::m_ccMode),
			MakeUintegerChecker<uint32_t>())
	.AddAttribute("AckHighPrio",
			"Set high priority for ACK/NACK or not",
			UintegerValue(0),
			MakeUintegerAccessor(&SwitchNode::m_ackHighPrio),
			MakeUintegerChecker<uint32_t>())
	.AddAttribute("MaxRtt",
			"Max Rtt of the network",
			UintegerValue(9000),
			MakeUintegerAccessor(&SwitchNode::m_maxRtt),
			MakeUintegerChecker<uint32_t>())
  ;
  return tid;
}

SwitchNode::SwitchNode(){
	m_ecmpSeed = m_id;
	m_node_type = 1;
	m_mmu = CreateObject<SwitchMmu>();
	for (uint32_t i = 0; i < pCnt; i++)
		m_txBytes[i] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_lastPktSize[i] = m_lastPktTs[i] = 0;
	for (uint32_t i = 0; i < pCnt; i++)
		m_u[i] = 0;
}

uint64_t SwitchNode::QueueByteKey(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex){
	NS_ASSERT_MSG(inDev < pCnt, "Switch ingress port exceeds accounting bound");
	NS_ASSERT_MSG(outDev < pCnt, "Switch egress port exceeds accounting bound");
	NS_ASSERT_MSG(qIndex < qCnt, "Switch queue exceeds accounting bound");
	return (static_cast<uint64_t>(inDev) * pCnt + outDev) * qCnt + qIndex;
}

void SwitchNode::AddQueuedBytes(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, uint32_t bytes){
	uint32_t &queued = m_bytes[QueueByteKey(inDev, outDev, qIndex)];
	NS_ASSERT_MSG(queued <= std::numeric_limits<uint32_t>::max() - bytes,
		"Switch queued-byte accounting overflow");
	queued += bytes;
}

void SwitchNode::RemoveQueuedBytes(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, uint32_t bytes, const char* underflowMessage){
	uint64_t key = QueueByteKey(inDev, outDev, qIndex);
	auto it = m_bytes.find(key);
	NS_ASSERT_MSG(it != m_bytes.end() && it->second >= bytes,
		underflowMessage);
	it->second -= bytes;
	if (it->second == 0)
		m_bytes.erase(it);
}

bool SwitchNode::RememberLimerRouteChoice(
		const LimerRouteChoiceEvent& event){
	std::lock_guard<std::mutex> guard(m_limerRouteChoiceMutex);
	return EmitLimerRouteChoiceOnce(&m_limerRouteChoices, event);
}

int SwitchNode::GetOutDev(Ptr<const Packet> p, CustomHeader &ch){
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
		"Switch route has no valid ECMP candidate");
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

void SwitchNode::RecordPfcSend(bool pause, uint32_t inDev, bool hasOutDev,
		uint32_t outDev, uint32_t qIndex, const CustomHeader* trigger){
	if (!HasLimerCongestionSignalSink()) return;
	LimerCongestionSignalEvent event;
	event.timestamp_ns = Simulator::Now().GetNanoSeconds();
	event.event_type = pause ? LIMER_SIGNAL_PFC_PAUSE_SEND
		: LIMER_SIGNAL_PFC_RESUME_SEND;
	event.node_id = GetId();
	event.node_type = GetNodeType();
	event.port_id = inDev;
	event.has_trigger_out_port = hasOutDev;
	event.trigger_out_port = outDev;
	event.pg = static_cast<uint16_t>(qIndex);
	event.has_queue_state = true;
	event.queue_bytes = m_mmu->ingress_bytes[inDev][qIndex];
	event.has_threshold_state = true;
	event.has_shared_state = true;
	event.has_headroom_state = true;
	event.shared_used_bytes = m_mmu->GetSharedUsed(inDev, qIndex);
	event.threshold_low_bytes = m_mmu->GetPfcThreshold(inDev);
	event.threshold_high_bytes = event.threshold_low_bytes;
	event.headroom_bytes = m_mmu->hdrm_bytes[inDev][qIndex];
	event.signal_before = pause ? 0 : 1;
	event.signal_after = pause ? 1 : 0;
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	event.pause_time = pause ? device->GetPfcPauseTime() : 0;
	if (trigger != nullptr) FillBackgroundSignalFlow(*trigger, &event);
	EmitLimerCongestionSignal(event);
}

void SwitchNode::CheckAndSendPfc(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, const CustomHeader& trigger){
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldPause(inDev, qIndex)){
		device->SendPfc(qIndex, 0);
		m_mmu->SetPause(inDev, qIndex);
		m_limerPfcEvents[inDev]++; // LIMER telemetry: PFC pause sent
		RecordPfcSend(true, inDev, true, outDev, qIndex, &trigger);
	}
}
void SwitchNode::CheckAndSendResume(uint32_t inDev, uint32_t qIndex){
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldResume(inDev, qIndex)){
		device->SendPfc(qIndex, 1);
		m_mmu->SetResume(inDev, qIndex);
		m_limerPfcEvents[inDev]++; // LIMER telemetry: PFC resume sent
		RecordPfcSend(false, inDev, false, 0, qIndex, nullptr);
	}
}
void SwitchNode::CheckAndSendResumeForPacket(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, const CustomHeader& trigger){
	Ptr<QbbNetDevice> device = DynamicCast<QbbNetDevice>(m_devices[inDev]);
	if (m_mmu->CheckShouldResume(inDev, qIndex)){
		device->SendPfc(qIndex, 1);
		m_mmu->SetResume(inDev, qIndex);
		m_limerPfcEvents[inDev]++;
		RecordPfcSend(false, inDev, true, outDev, qIndex, &trigger);
	}
}

void SwitchNode::SendToDev(Ptr<Packet>p, CustomHeader &ch){
	int idx = GetOutDev(p, ch);
	if (idx >= 0){
		// A physical fault and the corresponding online alarm are separate
		// events.  During that interval the old FIB may still select the dead
		// port.  That is a real data-plane drop, not a simulator invariant
		// violation and, importantly, not an implicit fast reroute.
		if (!m_devices[idx]->IsLinkUp()) {
			FlowIdTag limerDownTag;
			p->PeekPacketTag(limerDownTag);
			uint32_t limerInDev = limerDownTag.GetFlowId();
			if (idx < static_cast<int>(pCnt)) {
				m_limerDropPkts[idx]++;
				m_limerDropBytes[idx] += p->GetSize();
			} else if (limerInDev < pCnt) {
				m_limerDropPkts[limerInDev]++;
				m_limerDropBytes[limerInDev] += p->GetSize();
			}
			return;
		}

		// determine the qIndex
		uint32_t qIndex;
		if (ch.l3Prot == 0xFF || ch.l3Prot == 0xFE || (m_ackHighPrio && (ch.l3Prot == 0xFD || ch.l3Prot == 0xFC))){  //QCN or PFC or NACK, go highest priority
			qIndex = 0;
		}else{
			qIndex = (ch.l3Prot == 0x06 ? 1 : ch.udp.pg); // if TCP, put to queue 1
		}
		// std::cout << "qIndex is: " << qIndex << std::endl;

		// admission control
		FlowIdTag t;
		p->PeekPacketTag(t);
		uint32_t inDev = t.GetFlowId();
		if (qIndex != 0){ //not highest priority
			if (m_mmu->CheckIngressAdmission(inDev, qIndex, p->GetSize()) && m_mmu->CheckEgressAdmission(idx, qIndex, p->GetSize())){			// Admission control
				m_mmu->UpdateIngressAdmission(inDev, qIndex, p->GetSize());
				m_mmu->UpdateEgressAdmission(idx, qIndex, p->GetSize());
			}else{
				// LIMER telemetry: admission-control drop, attributed to the
				// intended egress port/queue.
				m_limerDropPkts[idx]++;
				m_limerDropBytes[idx] += p->GetSize();
				return; // Drop
			}
			CheckAndSendPfc(inDev, idx, qIndex, ch);
			AddQueuedBytes(inDev, idx, qIndex, p->GetSize());
		}
		m_limerRxPkts[inDev]++;
		m_devices[idx]->SwitchSend(qIndex, p, ch);
	}else
	{
		// LIMER telemetry: no route to destination (GetOutDev returned < 0).
		// No valid egress port exists, so attribute the drop to the ingress
		// port instead.
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

uint32_t SwitchNode::EcmpHash(const uint8_t* key, size_t len, uint32_t seed) {
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

void SwitchNode::SetEcmpSeed(uint32_t seed){
	m_ecmpSeed = seed;
}

void SwitchNode::AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx){
	uint32_t dip = dstAddr.Get();
	m_rtTable[dip].push_back(intf_idx);
}

void SwitchNode::ClearTable(){
	m_rtTable.clear();
}

// This function can only be called in switch mode
bool SwitchNode::SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch){
	SendToDev(packet, ch);
	return true;
}

void SwitchNode::SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p){
	FlowIdTag t;
	p->PeekPacketTag(t);
	CustomHeader limerSignalHeader(
		CustomHeader::L2_Header | CustomHeader::L3_Header |
		CustomHeader::L4_Header);
	p->PeekHeader(limerSignalHeader);
	if (qIndex != 0){
		uint32_t inDev = t.GetFlowId();
		m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize());
		m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize());
		RemoveQueuedBytes(inDev, ifIndex, qIndex, p->GetSize(),
			"Switch dequeue admission accounting underflow");
		if (m_ecnEnabled){
			bool egressCongested = m_mmu->ShouldSendCN(ifIndex, qIndex);
			if (egressCongested){
				m_limerEcnMarks[ifIndex]++; // LIMER telemetry: ECN mark
				PppHeader ppp;
				Ipv4Header h;
				p->RemoveHeader(ppp);
				p->RemoveHeader(h);
				h.SetEcn((Ipv4Header::EcnType)0x03);
				p->AddHeader(h);
				p->AddHeader(ppp);
				if (HasLimerCongestionSignalSink()) {
					LimerCongestionSignalEvent event;
					event.timestamp_ns = Simulator::Now().GetNanoSeconds();
					event.event_type = LIMER_SIGNAL_ECN_MARK;
					event.node_id = GetId();
					event.node_type = GetNodeType();
					event.port_id = ifIndex;
					event.pg = static_cast<uint16_t>(qIndex);
					event.has_queue_state = true;
					event.queue_bytes = m_mmu->egress_bytes[ifIndex][qIndex];
					event.has_threshold_state = true;
					event.threshold_low_bytes = m_mmu->kmin[ifIndex];
					event.threshold_high_bytes = m_mmu->kmax[ifIndex];
					event.signal_before = limerSignalHeader.GetIpv4EcnBits();
					event.signal_after = 3;
					FillBackgroundSignalFlow(limerSignalHeader, &event);
					EmitLimerCongestionSignal(event);
				}
			}
		}
		//CheckAndSendPfc(inDev, qIndex);
		CheckAndSendResumeForPacket(
			inDev, ifIndex, qIndex, limerSignalHeader);
	}
	if (1){
		uint8_t* buf = p->GetBuffer();
		if (buf[PppHeader::GetStaticSize() + 9] == 0x11){ // udp packet
			IntHeader *ih = (IntHeader*)&buf[PppHeader::GetStaticSize() + 20 + 8 + 6]; // ppp, ip, udp, SeqTs, INT
			Ptr<QbbNetDevice> dev = DynamicCast<QbbNetDevice>(m_devices[ifIndex]);
			if (m_ccMode == 3){ // HPCC
				ih->PushHop(Simulator::Now().GetTimeStep(), m_txBytes[ifIndex], dev->GetQueue()->GetNBytesTotal(), dev->GetDataRate().GetBitRate());
			}else if (m_ccMode == 10){ // HPCC-PINT
				uint64_t t = Simulator::Now().GetTimeStep();
				uint64_t dt = t - m_lastPktTs[ifIndex];
				if (dt > m_maxRtt)
					dt = m_maxRtt;
				uint64_t B = dev->GetDataRate().GetBitRate() / 8; //Bps
				uint64_t qlen = dev->GetQueue()->GetNBytesTotal();
				double newU;

				/**************************
				 * approximate calc
				 *************************/
				int b = 20, m = 16, l = 20; // see log2apprx's paremeters
				int sft = logres_shift(b,l);
				double fct = 1<<sft; // (multiplication factor corresponding to sft)
				double log_T = log2(m_maxRtt)*fct; // log2(T)*fct
				double log_B = log2(B)*fct; // log2(B)*fct
				double log_1e9 = log2(1e9)*fct; // log2(1e9)*fct
				double qterm = 0;
				double byteTerm = 0;
				double uTerm = 0;
				if ((qlen >> 8) > 0){
					int log_dt = log2apprx(dt, b, m, l); // ~log2(dt)*fct
					int log_qlen = log2apprx(qlen >> 8, b, m, l); // ~log2(qlen / 256)*fct
					qterm = pow(2, (
								log_dt + log_qlen + log_1e9 - log_B - 2*log_T
								)/fct
							) * 256;
					// 2^((log2(dt)*fct+log2(qlen/256)*fct+log2(1e9)*fct-log2(B)*fct-2*log2(T)*fct)/fct)*256 ~= dt*qlen*1e9/(B*T^2)
				}
				if (m_lastPktSize[ifIndex] > 0){
					int byte = m_lastPktSize[ifIndex];
					int log_byte = log2apprx(byte, b, m, l);
					byteTerm = pow(2, (
								log_byte + log_1e9 - log_B - log_T
								)/fct
							);
					// 2^((log2(byte)*fct+log2(1e9)*fct-log2(B)*fct-log2(T)*fct)/fct) ~= byte*1e9 / (B*T)
				}
				if (m_maxRtt > dt && m_u[ifIndex] > 0){
					int log_T_dt = log2apprx(m_maxRtt - dt, b, m, l); // ~log2(T-dt)*fct
					int log_u = log2apprx(int(round(m_u[ifIndex] * 8192)), b, m, l); // ~log2(u*512)*fct
					uTerm = pow(2, (
								log_T_dt + log_u - log_T
								)/fct
							) / 8192;
					// 2^((log2(T-dt)*fct+log2(u*512)*fct-log2(T)*fct)/fct)/512 = (T-dt)*u/T
				}
				newU = qterm+byteTerm+uTerm;

				#if 0
				/**************************
				 * accurate calc
				 *************************/
				double weight_ewma = double(dt) / m_maxRtt;
				double u;
				if (m_lastPktSize[ifIndex] == 0)
					u = 0;
				else{
					double txRate = m_lastPktSize[ifIndex] / double(dt); // B/ns
					u = (qlen / m_maxRtt + txRate) * 1e9 / B;
				}
				newU = m_u[ifIndex] * (1 - weight_ewma) + u * weight_ewma;
				printf(" %lf\n", newU);
				#endif

				/************************
				 * update PINT header
				 ***********************/
				uint16_t power = Pint::encode_u(newU);
				if (power > ih->GetPower())
					ih->SetPower(power);

				m_u[ifIndex] = newU;
			}
		}
	}
	m_txBytes[ifIndex] += p->GetSize();
	m_limerTxPkts[ifIndex]++; // LIMER telemetry: tx packet count
	m_lastPktSize[ifIndex] = p->GetSize();
	m_lastPktTs[ifIndex] = Simulator::Now().GetTimeStep();
}

void SwitchNode::SwitchNotifyDrop(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p){
	if (qIndex == 0)
		return;
	FlowIdTag t;
	NS_ASSERT_MSG(p->PeekPacketTag(t),
		"A queued switch packet must retain its ingress FlowIdTag until purge");
	uint32_t inDev = t.GetFlowId();
	m_mmu->RemoveFromIngressAdmission(inDev, qIndex, p->GetSize());
	m_mmu->RemoveFromEgressAdmission(ifIndex, qIndex, p->GetSize());
	RemoveQueuedBytes(inDev, ifIndex, qIndex, p->GetSize(),
		"Switch purge admission accounting underflow");
	// TakeDown is invoked by the public-LP fault barrier under MTP.  Keep the
	// MMU release atomic there, but move any generated PFC/resume packet and
	// its completion chain back to this switch's private LP.
	Simulator::ScheduleWithContext(GetId(), TimeStep(0),
		&SwitchNode::CheckAndSendResume, this, inDev, qIndex);
}

int SwitchNode::logres_shift(int b, int l){
	static int data[] = {0,0,1,2,2,3,3,3,3,4,4,4,4,4,4,4,4,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5,5};
	return l - data[b];
}

int SwitchNode::log2apprx(int x, int b, int m, int l){
	int x0 = x;
	int msb = int(log2(x)) + 1;
	if (msb > m){
		x = (x >> (msb - m) << (msb - m));
		#if 0
		x += + (1 << (msb - m - 1));
		#else
		int mask = (1 << (msb-m)) - 1;
		if ((x0 & mask) > (rand() & mask))
			x += 1<<(msb-m);
		#endif
	}
	return int(log2(x) * (1<<logres_shift(b, l)));
}

// for monitor
/**
 * outoput format:
 * time, sw_id, port_id, q_id, qlen, port_len
*/
void SwitchNode::PrintSwitchQlen(FILE* qlen_output){
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
 * time, sw_id, port_id, bandwidth
*/
void SwitchNode::PrintSwitchBw(FILE* bw_output, uint32_t bw_mon_interval){
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
