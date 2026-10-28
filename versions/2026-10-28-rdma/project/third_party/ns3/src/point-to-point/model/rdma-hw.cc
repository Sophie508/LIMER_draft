extern "C" unsigned limer_peer_reverse_nic(unsigned) __attribute__((weak));
extern "C" bool limer_joint_encode(void*, unsigned char*, unsigned) __attribute__((weak));
extern "C" void limer_joint_receive(unsigned, unsigned, unsigned, unsigned, unsigned, const unsigned char*, unsigned, bool) __attribute__((weak));
extern "C" void limer_joint_wire_tx(void*, unsigned, unsigned) __attribute__((weak));
#include <ns3/simulator.h>
#include <ns3/simple-seq-ts-header.h>
#include <ns3/udp-header.h>
#include <ns3/ipv4-header.h>
#include "ns3/ppp-header.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "ns3/data-rate.h"
#include "ns3/pointer.h"
#include "rdma-hw.h"
#include "ppp-header.h"
#include "qbb-header.h"
#include "cn-header.h"
#include "limer-congestion-signal.h"
#ifdef NS3_MTP
#include "ns3/mtp-interface.h"
#endif
#include <iostream>	// debug
#include <cstdlib>
#include <limits>
#include <string>
#include <algorithm>

// Optional experimental scheduler owned by the Astra frontend. Other ns-3
// programs and the default baseline preserve the original ECMP decision.
extern "C" uint32_t limer_split_select_qp(void*, uint32_t) __attribute__((weak));
extern "C" void limer_split_ack_progress(void*, uint64_t) __attribute__((weak));

namespace ns3{

namespace {
void FillSignalFromQp(Ptr<RdmaQueuePair> qp,
		LimerCongestionSignalEvent* event) {
	if (qp == nullptr || event == nullptr) return;
	event->has_flow = true;
	event->flow_src = qp->GetSrc();
	event->flow_dst = qp->GetDest();
	event->flow_sport = qp->sport;
	event->flow_dport = qp->dport;
	event->pg = qp->m_pg;
	event->packet_sip = qp->sip.Get();
	event->packet_dip = qp->dip.Get();
	event->packet_sport = qp->sport;
	event->packet_dport = qp->dport;
}
}  // namespace

TypeId RdmaHw::GetTypeId (void)
{
	static TypeId tid = TypeId ("ns3::RdmaHw")
		.SetParent<Object> ()
		.AddAttribute("MinRate",
				"Minimum rate of a throttled flow",
				DataRateValue(DataRate("100Mb/s")),
				MakeDataRateAccessor(&RdmaHw::m_minRate),
				MakeDataRateChecker())
		.AddAttribute("Mtu",
				"Mtu.",
				UintegerValue(1000),
				MakeUintegerAccessor(&RdmaHw::m_mtu),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute ("CcMode",
				"which mode of DCQCN is running",
				UintegerValue(0),
				MakeUintegerAccessor(&RdmaHw::m_cc_mode),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("NACKGenerationInterval",
				"The NACK Generation interval",
				DoubleValue(500.0),
				MakeDoubleAccessor(&RdmaHw::m_nack_interval),
				MakeDoubleChecker<double>())
		.AddAttribute("L2ChunkSize",
				"Layer 2 chunk size. Disable chunk mode if equals to 0.",
				UintegerValue(0),
				MakeUintegerAccessor(&RdmaHw::m_chunk),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("L2AckInterval",
				"Layer 2 Ack intervals. Disable ack if equals to 0.",
				UintegerValue(0),
				MakeUintegerAccessor(&RdmaHw::m_ack_interval),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("L2BackToZero",
				"Layer 2 go back to zero transmission.",
				BooleanValue(false),
				MakeBooleanAccessor(&RdmaHw::m_backto0),
				MakeBooleanChecker())
		.AddAttribute("EwmaGain",
				"Control gain parameter which determines the level of rate decrease",
				DoubleValue(1.0 / 16),
				MakeDoubleAccessor(&RdmaHw::m_g),
				MakeDoubleChecker<double>())
		.AddAttribute ("RateOnFirstCnp",
				"the fraction of rate on first CNP",
				DoubleValue(1.0),
				MakeDoubleAccessor(&RdmaHw::m_rateOnFirstCNP),
				MakeDoubleChecker<double> ())
		.AddAttribute("ClampTargetRate",
				"Clamp target rate.",
				BooleanValue(false),
				MakeBooleanAccessor(&RdmaHw::m_EcnClampTgtRate),
				MakeBooleanChecker())
		.AddAttribute("RPTimer",
				"The rate increase timer at RP in microseconds",
				DoubleValue(1500.0),
				MakeDoubleAccessor(&RdmaHw::m_rpgTimeReset),
				MakeDoubleChecker<double>())
		.AddAttribute("RateDecreaseInterval",
				"The interval of rate decrease check",
				DoubleValue(4.0),
				MakeDoubleAccessor(&RdmaHw::m_rateDecreaseInterval),
				MakeDoubleChecker<double>())
		.AddAttribute("FastRecoveryTimes",
				"The rate increase timer at RP",
				UintegerValue(5),
				MakeUintegerAccessor(&RdmaHw::m_rpgThreshold),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("AlphaResumInterval",
				"The interval of resuming alpha",
				DoubleValue(55.0),
				MakeDoubleAccessor(&RdmaHw::m_alpha_resume_interval),
				MakeDoubleChecker<double>())
		.AddAttribute("RateAI",
				"Rate increment unit in AI period",
				DataRateValue(DataRate("5Mb/s")),
				MakeDataRateAccessor(&RdmaHw::m_rai),
				MakeDataRateChecker())
		.AddAttribute("RateHAI",
				"Rate increment unit in hyperactive AI period",
				DataRateValue(DataRate("50Mb/s")),
				MakeDataRateAccessor(&RdmaHw::m_rhai),
				MakeDataRateChecker())
		.AddAttribute("VarWin",
				"Use variable window size or not",
				BooleanValue(false),
				MakeBooleanAccessor(&RdmaHw::m_var_win),
				MakeBooleanChecker())
		.AddAttribute("FastReact",
				"Fast React to congestion feedback",
				BooleanValue(true),
				MakeBooleanAccessor(&RdmaHw::m_fast_react),
				MakeBooleanChecker())
		.AddAttribute("MiThresh",
				"Threshold of number of consecutive AI before MI",
				UintegerValue(5),
				MakeUintegerAccessor(&RdmaHw::m_miThresh),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("TargetUtil",
				"The Target Utilization of the bottleneck bandwidth, by default 95%",
				DoubleValue(0.95),
				MakeDoubleAccessor(&RdmaHw::m_targetUtil),
				MakeDoubleChecker<double>())
		.AddAttribute("UtilHigh",
				"The upper bound of Target Utilization of the bottleneck bandwidth, by default 98%",
				DoubleValue(0.98),
				MakeDoubleAccessor(&RdmaHw::m_utilHigh),
				MakeDoubleChecker<double>())
		.AddAttribute("RateBound",
				"Bound packet sending by rate, for test only",
				BooleanValue(true),
				MakeBooleanAccessor(&RdmaHw::m_rateBound),
				MakeBooleanChecker())
		.AddAttribute("MultiRate",
				"Maintain multiple rates in HPCC",
				BooleanValue(true),
				MakeBooleanAccessor(&RdmaHw::m_multipleRate),
				MakeBooleanChecker())
		.AddAttribute("SampleFeedback",
				"Whether sample feedback or not",
				BooleanValue(false),
				MakeBooleanAccessor(&RdmaHw::m_sampleFeedback),
				MakeBooleanChecker())
		.AddAttribute("TimelyAlpha",
				"Alpha of TIMELY",
				DoubleValue(0.875),
				MakeDoubleAccessor(&RdmaHw::m_tmly_alpha),
				MakeDoubleChecker<double>())
		.AddAttribute("TimelyBeta",
				"Beta of TIMELY",
				DoubleValue(0.8),
				MakeDoubleAccessor(&RdmaHw::m_tmly_beta),
				MakeDoubleChecker<double>())
		.AddAttribute("TimelyTLow",
				"TLow of TIMELY (ns)",
				UintegerValue(50000),
				MakeUintegerAccessor(&RdmaHw::m_tmly_TLow),
				MakeUintegerChecker<uint64_t>())
		.AddAttribute("TimelyTHigh",
				"THigh of TIMELY (ns)",
				UintegerValue(500000),
				MakeUintegerAccessor(&RdmaHw::m_tmly_THigh),
				MakeUintegerChecker<uint64_t>())
		.AddAttribute("TimelyMinRtt",
				"MinRtt of TIMELY (ns)",
				UintegerValue(20000),
				MakeUintegerAccessor(&RdmaHw::m_tmly_minRtt),
				MakeUintegerChecker<uint64_t>())
		.AddAttribute("DctcpRateAI",
				"DCTCP's Rate increment unit in AI period",
				DataRateValue(DataRate("1000Mb/s")),
				MakeDataRateAccessor(&RdmaHw::m_dctcp_rai),
				MakeDataRateChecker())
		.AddAttribute("PintSmplThresh",
				"PINT's sampling threshold in rand()%65536",
				UintegerValue(65536),
				MakeUintegerAccessor(&RdmaHw::pint_smpl_thresh),
				MakeUintegerChecker<uint32_t>())
		.AddAttribute("GPUsPerServer",
				"the number of gpus in a server, used for routing",
				UintegerValue(1),
				MakeUintegerAccessor(&RdmaHw::m_gpus_per_server),
				MakeUintegerChecker<uint32_t>())	
		.AddAttribute("TotalPauseTimes",
				"The number of pause times to simulate PFC pause due to PCIe",
				UintegerValue(0),
				MakeUintegerAccessor(&RdmaHw::m_total_pause_times),
				MakeUintegerChecker<uint64_t>())
		.AddAttribute("NVLS_enable",
				"NVLS enable info",
				UintegerValue(0),
				MakeUintegerAccessor(&RdmaHw::nvls_enable),
				MakeUintegerChecker<uint32_t>());
		;
	return tid;
}

RdmaHw::RdmaHw(){
	m_limerRtoUs = 100;
	m_limerRetryLimit = 7;
	m_limerRecoveryTransportEnabled = false;

	const char *transportEnv =
		std::getenv("LIMER_RDMA_RECOVERY_TRANSPORT_ENABLE");
	// Accept only the recorded, explicit value "1".  Missing or malformed
	// ambient configuration therefore leaves the unmodified baseline active.
	m_limerRecoveryTransportEnabled =
		transportEnv != NULL && std::string(transportEnv) == "1";

	const char *rtoEnv = std::getenv("LIMER_RDMA_RTO_US");
	if (rtoEnv != NULL && *rtoEnv != '\0') {
		char *end = NULL;
		unsigned long long value = std::strtoull(rtoEnv, &end, 10);
		if (end != rtoEnv && *end == '\0' && value > 0)
			m_limerRtoUs = static_cast<uint64_t>(value);
	}
	const char *retryEnv = std::getenv("LIMER_RDMA_RETRY_LIMIT");
	if (retryEnv != NULL && *retryEnv != '\0') {
		char *end = NULL;
		unsigned long value = std::strtoul(retryEnv, &end, 10);
		if (end != retryEnv && *end == '\0' &&
			value <= std::numeric_limits<uint32_t>::max())
			m_limerRetryLimit = static_cast<uint32_t>(value);
	}
}

void RdmaHw::SetLimerEventCallback(LimerEventCallback cb){
	m_limerEventCallback = cb;
}

void RdmaHw::EmitLimerEvent(uint32_t eventType, Ptr<RdmaQueuePair> qp, uint64_t detail){
	if (!m_limerEventCallback.IsNull())
		m_limerEventCallback(eventType, qp,
			Simulator::Now().GetNanoSeconds(), detail);
}

bool RdmaHw::IsUsableNic(uint32_t nicIdx) const{
	return nicIdx < m_nic.size() && m_nic[nicIdx].dev != NULL &&
		m_nic[nicIdx].qpGrp != NULL;
}

uint32_t RdmaHw::FindNicIdx(Ptr<QbbNetDevice> dev) const{
	for (uint32_t i = 0; i < m_nic.size(); ++i) {
		if (m_nic[i].dev == dev)
			return i;
	}
	return std::numeric_limits<uint32_t>::max();
}

void RdmaHw::enable_nvls() {
	nvls_enable = 1;
}

void RdmaHw::disable_nvls() {
	nvls_enable = 0;
}

void RdmaHw::add_nvswitch(uint32_t nvswitch_id) {
	nvswitch_set.insert(nvswitch_id);
}

void RdmaHw::SetNode(Ptr<Node> node){
	m_node = node;
}
void RdmaHw::Setup(QpCompleteCallback cb,SendCompleteCallback send_cb){
	tx_bytes.resize(m_nic.size());
	last_tx_bytes.resize(m_nic.size());
	m_limerNacksByPort.resize(m_nic.size(), 0);
	for (uint32_t i = 0; i < m_nic.size(); i++){
		tx_bytes[i] = 0;
		last_tx_bytes[i] = 0;
		Ptr<QbbNetDevice> dev = m_nic[i].dev;
		if (dev == NULL)
			continue;
		// share data with NIC
		dev->m_rdmaEQ->m_qpGrp = m_nic[i].qpGrp;
		// setup callback
		dev->m_rdmaReceiveCb = MakeCallback(&RdmaHw::Receive, this);
        dev->m_rdmaSentCb = MakeCallback(&RdmaHw::SendPacketComplete, this);
        dev->m_rdmaLinkDownCb = MakeCallback(&RdmaHw::SetLinkDown, this);
		dev->m_rdmaPktSent = MakeCallback(&RdmaHw::PktSent, this);
		dev->m_rdmaUpdateTxBytes = MakeCallback(&RdmaHw::UpdateTxBytes, this);
		// config NIC
		dev->m_rdmaEQ->m_rdmaGetNxtPkt = MakeCallback(&RdmaHw::GetNxtPacket, this);
	}
	// setup qp complete callback
	m_qpCompleteCallback = cb;
    m_sendCompleteCallback = send_cb;
}
uint32_t ip_to_node_id(Ipv4Address ip) { return (ip.Get() >> 8) & 0xffff; }
uint32_t RdmaHw::GetNicIdxOfQp(Ptr<RdmaQueuePair> qp){
	if (qp != NULL && IsUsableNic(qp->m_activeNicIdx))
		return qp->m_activeNicIdx;

	uint32_t src = qp->m_src;
	uint32_t dst = qp->m_dest;
	if(src / m_gpus_per_server == dst / m_gpus_per_server || m_rtTable_nxthop_nvswitch.count(qp->dip.Get()) != 0){ // src and dst are in the same server, communicate through nvswitch
		auto &v = m_rtTable_nxthop_nvswitch[qp->dip.Get()];
		if (v.size() > 0){
			return v[qp->GetHash() % v.size()];
		}else{
			NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
		}
	}else{ // src and dst don't in the same server, communicate through swicth
		auto &v = m_rtTable[qp->dip.Get()];
		if (v.size() > 0){
			return v[qp->GetHash() % v.size()];
		}else{
			NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
		}
	}
	return std::numeric_limits<uint32_t>::max();
}
uint64_t RdmaHw::GetQpKey(uint32_t dip, uint16_t sport, uint16_t pg){
	return ((uint64_t)dip << 32) | ((uint64_t)sport << 16) | (uint64_t)pg;
}
Ptr<RdmaQueuePair> RdmaHw::GetQp(uint32_t dip, uint16_t sport, uint16_t pg){
	uint64_t key = GetQpKey(dip, sport, pg);
	auto it = m_qpMap.find(key);
	if (it != m_qpMap.end())
		return it->second;
	return NULL;
}

void RdmaHw::InitializeQpRateForNic(Ptr<RdmaQueuePair> qp, uint32_t nicIdx){
	NS_ASSERT_MSG(IsUsableNic(nicIdx), "QP is bound to an invalid NIC");
	DataRate lineRate = m_nic[nicIdx].dev->GetDataRate();
	qp->m_rate = lineRate;
	qp->m_max_rate = lineRate;
	if (m_cc_mode == 1){
		qp->mlx.m_targetRate = lineRate;
	}else if (m_cc_mode == 3){
		qp->hp.m_curRate = lineRate;
		if (m_multipleRate){
			for (uint32_t i = 0; i < IntHeader::maxHop; i++)
				qp->hp.hopState[i].Rc = lineRate;
		}
	}else if (m_cc_mode == 7){
		qp->tmly.m_curRate = lineRate;
	}else if (m_cc_mode == 10){
		qp->hpccPint.m_curRate = lineRate;
	}
}

void RdmaHw::AddQueuePair(uint32_t src, uint32_t dest, uint64_t tag, uint64_t size, uint16_t pg, Ipv4Address sip, Ipv4Address dip, uint16_t sport, uint16_t dport, uint32_t win, uint64_t baseRtt, Callback<void> notifyAppFinish, Callback<void> notifyAppSent, uint32_t limerTrafficClass){
	// create qp
	Ptr<RdmaQueuePair> qp = CreateObject<RdmaQueuePair>(pg, sip, dip, sport, dport);
	qp->SetSrc(src);
	qp->SetDest(dest);
	qp->SetTag(tag);
	qp->SetSize(size);
	qp->SetInitialSize(size);
	qp->SetWin(win);
	qp->SetBaseRtt(baseRtt);
	qp->SetVarWin(m_var_win);
	qp->SetAppNotifyCallback(notifyAppFinish);
	qp->SetAppSentCallback(notifyAppSent);
	qp->SetLimerTrafficClass(limerTrafficClass);
	qp->m_rtoUs = m_limerRtoUs;
	qp->m_retryLimit = m_limerRetryLimit;

	// Preserve the original SimAI ECMP decision for the active rail in every
	// mode.  Recovery transport may additionally pre-bind another usable rail,
	// but opting in must never remap the primary baseline traffic.
	uint32_t nic_idx = GetNicIdxOfQp(qp);
	if (limer_split_select_qp) {
		const uint32_t selected = limer_split_select_qp(PeekPointer(qp), nic_idx);
		if (selected != nic_idx) {
			auto route = m_rtTable.find(dip.Get());
			NS_ABORT_MSG_IF(route == m_rtTable.end() ||
				std::find(route->second.begin(),route->second.end(),selected)==route->second.end(),
				"split-selected NIC is not an eligible route to destination");
		}
		nic_idx = selected;
	}
	NS_ASSERT_MSG(IsUsableNic(nic_idx), "QP is bound to an invalid primary NIC");
	NS_ASSERT_MSG(m_gpus_per_server > 0, "GPUsPerServer must be non-zero");
	bool interServer = src / m_gpus_per_server != dest / m_gpus_per_server;
	qp->m_primaryNicIdx = nic_idx;
	qp->m_activeNicIdx = nic_idx;
	if (interServer && m_limerRecoveryTransportEnabled){
		auto route = m_rtTable.find(dip.Get());
		NS_ASSERT_MSG(route != m_rtTable.end() && !route->second.empty(),
			"Inter-server QP has no route candidates");
		const std::vector<int> &candidates = route->second;
		for (uint32_t i = 0; i < candidates.size(); ++i){
			int candidate = candidates[i];
			if (candidate >= 0 && static_cast<uint32_t>(candidate) != nic_idx &&
				IsUsableNic(static_cast<uint32_t>(candidate))){
				qp->m_backupNicIdx = static_cast<uint32_t>(candidate);
				qp->m_backupReady = true;
				qp->m_backupReadyTimestampNs = Simulator::Now().GetNanoSeconds();
				break;
			}
		}
	}
	qp->m_limerState = LIMER_RDMA_QP_ACTIVE_PRIMARY;

	uint64_t key = GetQpKey(dip.Get(), sport, pg);
	auto existingQp = m_qpMap.find(key);
	NS_ABORT_MSG_IF(existingQp != m_qpMap.end(),
		"RDMA QP key collision before install: src=" << src
		<< " dst=" << dest << " dip=" << dip << " sport=" << sport
		<< " pg=" << pg << " existing_qp=" << PeekPointer(existingQp->second)
		<< " new_qp=" << PeekPointer(qp));

	// std::cout << "src is: " << src << ", dst is: " << dest <<  ", nic_idx: " << nic_idx << ", and the m_nic size is: " << m_nic.size() << std::endl;
	// Assign the qp to specific qbbnetdevice
	m_nic[nic_idx].qpGrp->AddQp(qp);
	auto insertedQp = m_qpMap.emplace(key, qp);
	NS_ABORT_MSG_IF(!insertedQp.second,
		"RDMA QP key insertion unexpectedly failed: src=" << src
		<< " dst=" << dest << " sport=" << sport << " pg=" << pg);
	qp_cnp[key] = 0;
	last_qp_cnp[key] = 0;
	last_qp_rate[key] = 0;

	// set init variables
	InitializeQpRateForNic(qp, nic_idx);
	// NVLS settings
	if(nvls_enable == 1) qp->nvls_enable = 1;
	else qp->nvls_enable = 0;
	EmitLimerEvent(LIMER_RDMA_EVENT_QP_CREATED, qp, nic_idx);
	if (qp->m_backupReady)
		EmitLimerEvent(LIMER_RDMA_EVENT_BACKUP_READY, qp, qp->m_backupNicIdx);
	// Notify Nic
	m_nic[nic_idx].dev->NewQp(qp);
}

void RdmaHw::DeleteQueuePair(Ptr<RdmaQueuePair> qp){
	CancelRto(qp);
	// Completion is handled on the sender node's private LP, the same LP that
	// owns its Qbb schedulers.  Remove the terminal Ptr immediately from every
	// possible rail without taking the global MTP critical section (callbacks
	// above may themselves use it, and nested acquisition would deadlock).
	uint32_t removedGroups = 0;
	for (uint32_t i = 0; i < m_nic.size(); ++i){
		if (m_nic[i].dev != NULL && m_nic[i].dev->RemoveQp(qp))
			++removedGroups;
	}
	NS_ASSERT_MSG(removedGroups == 1,
		"A completed RDMA QP must have exactly one active egress binding");
	// remove qp from the m_qpMap
	uint64_t key = GetQpKey(qp->dip.Get(), qp->sport, qp->m_pg);
	auto installedQp = m_qpMap.find(key);
	NS_ABORT_MSG_IF(installedQp == m_qpMap.end(),
		"RDMA QP deletion found no installed key: src=" << qp->m_src
		<< " dst=" << qp->m_dest << " sport=" << qp->sport
		<< " pg=" << qp->m_pg);
	NS_ABORT_MSG_IF(installedQp->second != qp,
		"RDMA QP deletion found a different QP at key: src=" << qp->m_src
		<< " dst=" << qp->m_dest << " sport=" << qp->sport
		<< " pg=" << qp->m_pg << " installed_qp="
		<< PeekPointer(installedQp->second) << " deleting_qp=" << PeekPointer(qp));
	m_qpMap.erase(installedQp);
	qp_cnp.erase(key);
	last_qp_cnp.erase(key);
	last_qp_rate.erase(key);
}

Ptr<RdmaRxQueuePair> RdmaHw::GetRxQp(uint32_t sip, uint32_t dip, uint16_t sport, uint16_t dport, uint16_t pg, bool create){
    uint64_t key = ((uint64_t)dip << 32) | ((uint64_t)pg << 16) | (uint64_t)dport;
    #ifdef NS3_MTP
    MtpInterface::explicitCriticalSection cs;
    #endif
    auto it = m_rxQpMap.find(key);
    if (it != m_rxQpMap.end()){
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        return it->second;
    }
    if (create){
        // create new rx qp
        Ptr<RdmaRxQueuePair> q = CreateObject<RdmaRxQueuePair>();
        // init the qp
        q->sip = sip;
        q->dip = dip;
        q->sport = sport;
        q->dport = dport;
        q->m_ecn_source.qIndex = pg;
        // store in map
        m_rxQpMap[key] = q;
        #ifdef NS3_MTP
        cs.ExitSection();
        #endif
        return q;
    }
    #ifdef NS3_MTP
    cs.ExitSection();
    #endif
    return NULL;
}

uint32_t RdmaHw::GetNicIdxOfRxQp(Ptr<RdmaRxQueuePair> q){
	// BUG就出现在这里了，首先要判断m_rtTable[q->dip]是否存在，若不存在就去判断m_rtTable_nxthop_nvswitch是否存在，如果都不存在，那么就输出错误
	// auto &v = m_rtTable[q->dip];

	if(m_rtTable.count(q->dip) != 0) {
		auto &v = m_rtTable[q->dip];
		if(v.size() > 0)
			return v[q->GetHash() % v.size()];
		else 
			NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
	} else if(m_rtTable_nxthop_nvswitch.count(q->dip) != 0) {
		auto &v = m_rtTable_nxthop_nvswitch[q->dip];
		if(v.size() > 0)
			return v[q->GetHash() % v.size()];
		else 
			NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
	} else {
		NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
	}
	NS_ASSERT_MSG(false, "We assume at least one NIC is alive");
	
}
void RdmaHw::DeleteRxQp(uint32_t dip, uint16_t pg, uint16_t dport){
	uint64_t key = ((uint64_t)dip << 32) | ((uint64_t)pg << 16) | (uint64_t)dport;
	m_rxQpMap.erase(key);
}

int RdmaHw::SendPacketComplete(Ptr<Packet> p, CustomHeader &ch)
{
	// Physical serialization is not an RDMA completion.  SUCCESS is emitted
	// only from QpComplete after the receiver's cumulative ACK covers m_size.
	(void)p;
	(void)ch;
	return 0;
}

void RdmaHw::SendComplete(Ptr<RdmaQueuePair> qp)
{
	NS_ASSERT(!m_sendCompleteCallback.IsNull());

	m_sendCompleteCallback(qp);
}

int RdmaHw::ReceiveUdp(Ptr<Packet> p, CustomHeader &ch){
	uint8_t ecnbits = ch.GetIpv4EcnBits();
	
	uint32_t payload_size = p->GetSize() - ch.GetSerializedSize();
    unsigned char jointHeader[24]{};
    bool jointPacket = limer_joint_receive != nullptr;
    if (jointPacket) {
        NS_ABORT_MSG_IF(payload_size < 24, "joint wire header missing");
        Ptr<Packet> payload = p->Copy();
        payload->RemoveAtStart(ch.GetSerializedSize());
        payload->CopyData(jointHeader, 24);
        payload_size -= 24;
    }

	// TODO find corresponding rx queue pair
	Ptr<RdmaRxQueuePair> rxQp = GetRxQp(ch.dip, ch.sip, ch.udp.dport, ch.udp.sport, ch.udp.pg, true);
	if (ecnbits != 0){
		rxQp->m_ecn_source.ecnbits |= ecnbits;
		rxQp->m_ecn_source.qfb++;
	}
	rxQp->m_ecn_source.total++;
	rxQp->m_milestone_rx = m_ack_interval;

    uint64_t previousExpected = rxQp->ReceiverNextExpectedSeq;
	int x = ReceiverCheckSeq(ch.udp.seq, rxQp, payload_size);
    if (jointPacket) limer_joint_receive(m_node->GetId(), ch.sip, ch.udp.sport,
        ch.udp.seq, payload_size, jointHeader, 24,
        rxQp->ReceiverNextExpectedSeq > previousExpected);

	if (x == 1 || x == 2 || x == 3){ // ACK new data, NACK a gap, or re-ACK a duplicate
		qbbHeader seqh;
		seqh.SetSeq(rxQp->ReceiverNextExpectedSeq);
		seqh.SetPG(ch.udp.pg);
		seqh.SetSport(ch.udp.dport);
		seqh.SetDport(ch.udp.sport);
		seqh.SetIntHeader(ch.udp.ih);
		if (ecnbits)
			seqh.SetCnp();

		Ptr<Packet> newp = Create<Packet>(std::max(60-14-20-(int)seqh.GetSerializedSize(), 0));
		newp->AddHeader(seqh);

		Ipv4Header head;	// Prepare IPv4 header
		head.SetDestination(Ipv4Address(ch.sip));
		head.SetSource(Ipv4Address(ch.dip));
		head.SetProtocol(x == 2 ? 0xFD : 0xFC); //ack=0xFC nack=0xFD
		head.SetTtl(64);
		head.SetPayloadSize(newp->GetSize());
		head.SetIdentification(rxQp->m_ipid++);
		// GPU receives the packet and generate ACK with NVLS tag
		if(ch.m_tos == 4) head.SetTos(4);

		newp->AddHeader(head);
		AddHeader(newp, 0x800);	// Attach PPP header
		uint32_t sip = ch.sip;
		uint32_t sid = (sip >> 8) & 0xffff;
		uint32_t dip = ch.dip;
		uint32_t did = (dip >> 8) & 0xffff;
		// send
        uint32_t nic_idx = jointPacket ?
            (limer_peer_reverse_nic ? limer_peer_reverse_nic(uint32_t(jointHeader[0])*256 + jointHeader[1]) :
            2 + ((uint32_t(jointHeader[0])*256 + jointHeader[1]) % 3)) : GetNicIdxOfRxQp(rxQp);
        NS_ABORT_MSG_IF(!IsUsableNic(nic_idx), "joint reverse path unavailable");
		if (ecnbits != 0 && HasLimerCongestionSignalSink()) {
			LimerCongestionSignalEvent event;
			event.timestamp_ns = Simulator::Now().GetNanoSeconds();
			event.event_type = LIMER_SIGNAL_CNP_ACK_EMIT;
			event.node_id = m_node->GetId();
			event.node_type = m_node->GetNodeType();
			event.port_id = m_nic[nic_idx].dev->GetIfIndex();
			event.pg = ch.udp.pg;
			event.has_flow = true;
			event.has_packet_tuple = true;
			event.flow_src = (ch.sip >> 8) & 0xffff;
			event.flow_dst = (ch.dip >> 8) & 0xffff;
			event.flow_sport = ch.udp.sport;
			event.flow_dport = ch.udp.dport;
			event.packet_sip = ch.dip;
			event.packet_dip = ch.sip;
			event.packet_sport = ch.udp.dport;
			event.packet_dport = ch.udp.sport;
			event.signal_before = ecnbits;
			event.signal_after = 1;
			EmitLimerCongestionSignal(event);
		}
		m_nic[nic_idx].dev->RdmaEnqueueHighPrioQ(newp);
		// 发送给目标 NVSwitch 的报文
		if(did == m_node->GetId() && m_node->GetNodeType() == 2 && ch.m_tos == 4) m_nic[nic_idx].dev->SwitchAsHostSend();
		else m_nic[nic_idx].dev->TriggerTransmit();
	}
	return 0;
}

int RdmaHw::ReceiveCnp(Ptr<Packet> p, CustomHeader &ch){
	// QCN on NIC
	// This is a Congestion signal
	// Then, extract data from the congestion packet.
	// We assume, without verify, the packet is destinated to me
	uint32_t qIndex = ch.cnp.qIndex;
	if (qIndex == 1){		//DCTCP
		return 0;
	}
	uint16_t udpport = ch.cnp.fid; // corresponds to the sport
	uint8_t ecnbits = ch.cnp.ecnBits;
	uint16_t qfb = ch.cnp.qfb;
	uint16_t total = ch.cnp.total;

	uint32_t i;
	// get qp
	Ptr<RdmaQueuePair> qp = GetQp(ch.sip, udpport, qIndex);
	if (qp == NULL)
		std::cout << "ERROR: QCN NIC cannot find the flow\n";
	// get nic
	uint32_t nic_idx = GetNicIdxOfQp(qp);
	Ptr<QbbNetDevice> dev = m_nic[nic_idx].dev;

	if (qp->m_rate == 0)			//lazy initialization	
	{
		qp->m_rate = dev->GetDataRate();
		if (m_cc_mode == 1){
			qp->mlx.m_targetRate = dev->GetDataRate();
		}else if (m_cc_mode == 3){
			qp->hp.m_curRate = dev->GetDataRate();
			if (m_multipleRate){
				for (uint32_t i = 0; i < IntHeader::maxHop; i++)
					qp->hp.hopState[i].Rc = dev->GetDataRate();
			}
		}else if (m_cc_mode == 7){
			qp->tmly.m_curRate = dev->GetDataRate();
		}else if (m_cc_mode == 10){
			qp->hpccPint.m_curRate = dev->GetDataRate();
		}
	}
	return 0;
}

int RdmaHw::ReceiveAck(Ptr<Packet> p, CustomHeader &ch){
	uint16_t qIndex = ch.ack.pg;
	uint16_t port = ch.ack.dport;
	uint64_t seq = ch.ack.seq;
	uint8_t cnp = (ch.ack.flags >> qbbHeader::FLAG_CNP) & 1;

	Ptr<RdmaQueuePair> qp = GetQp(ch.sip, port, qIndex);
	if (qp == NULL || qp->IsLimerTerminal()){
		return 0;
	}

	uint32_t nic_idx = GetNicIdxOfQp(qp);
	if (cnp && HasLimerCongestionSignalSink()) {
		LimerCongestionSignalEvent event;
		event.timestamp_ns = Simulator::Now().GetNanoSeconds();
		event.event_type = LIMER_SIGNAL_CNP_ACK_RX;
		event.node_id = m_node->GetId();
		event.node_type = m_node->GetNodeType();
		event.port_id = m_nic[nic_idx].dev->GetIfIndex();
		FillSignalFromQp(qp, &event);
		event.packet_sip = ch.sip;
		event.has_packet_tuple = true;
		event.packet_dip = ch.dip;
		event.packet_sport = ch.ack.sport;
		event.packet_dport = ch.ack.dport;
		event.signal_before = 0;
		event.signal_after = 1;
		EmitLimerCongestionSignal(event);
	}
	uint64_t oldUna = qp->snd_una;
	if (!m_backto0 || m_chunk == 0){
		qp->Acknowledge(seq);
	}else {
		uint64_t goback_seq = seq / m_chunk * m_chunk;
		qp->Acknowledge(goback_seq);
	}
	bool progressed = qp->snd_una > oldUna;
	if (progressed && limer_split_ack_progress) {
		const uint64_t size=qp->GetInitialSize();
		limer_split_ack_progress(PeekPointer(qp),
			std::min(qp->snd_una,size)-std::min(oldUna,size));
	}
	if (progressed){
		qp->m_retryCount = 0;
		CancelRto(qp);
		uint64_t now = Simulator::Now().GetNanoSeconds();
		if (qp->m_firstAckProgressTimestampNs == 0)
			qp->m_firstAckProgressTimestampNs = now;
		if (qp->m_limerState == LIMER_RDMA_QP_ACTIVE_BACKUP &&
			qp->m_backupFirstAckTimestampNs == 0)
			qp->m_backupFirstAckTimestampNs = now;
		EmitLimerEvent(LIMER_RDMA_EVENT_ACK_PROGRESS, qp, qp->snd_una);
	}

	if (ch.l3Prot == 0xFD) // NACK
		RecoverQueue(qp);
	else if (progressed && !qp->IsFinished())
		ArmRto(qp, false);

	if (qp->IsFinished()){
		QpComplete(qp);
		return 0;
	}

	// handle cnp
	if (cnp){
		uint64_t key = GetQpKey(qp->dip.Get(), qp->sport, qp->m_pg);
		qp_cnp[key]++; // update for the number of cnp this qp has received
		if (m_cc_mode == 1){ // mlx version
			cnp_received_mlx(qp);
		} 
	}

	if (m_cc_mode == 3){
		HandleAckHp(qp, p, ch);
	}else if (m_cc_mode == 7){
		HandleAckTimely(qp, p, ch);
	}else if (m_cc_mode == 8){
		HandleAckDctcp(qp, p, ch);
	}else if (m_cc_mode == 10){
		HandleAckHpPint(qp, p, ch);
	}
	uint32_t dip = ch.dip;
	uint32_t did = (dip >> 8) & 0xffff;
	// ACK may advance the on-the-fly window, allowing more packets to send
	if(did == m_node->GetId() && m_node->GetNodeType() == 2) m_nic[nic_idx].dev->SwitchAsHostSend();
	else m_nic[nic_idx].dev->TriggerTransmit();
	//std:://cout << "ack triggere transmitted\n";
	return 0;
}

int RdmaHw::Receive(Ptr<Packet> p, CustomHeader &ch){
	m_limerRxPkts++; // LIMER telemetry: every packet arriving at this NIC
	m_limerRxBytes += p->GetSize();
	if (ch.l3Prot == 0x11){ // UDP
		ReceiveUdp(p, ch);
	}else if (ch.l3Prot == 0xFF){ // CNP
		ReceiveCnp(p, ch);
	}else if (ch.l3Prot == 0xFD){ // NACK
		ReceiveAck(p, ch);
	}else if (ch.l3Prot == 0xFC){ // ACK
		ReceiveAck(p, ch);
	}
	return 0;
}

int RdmaHw::ReceiverCheckSeq(uint64_t seq, Ptr<RdmaRxQueuePair> q, uint32_t size){
	uint64_t expected = q->ReceiverNextExpectedSeq;
	if (seq == expected){
		q->ReceiverNextExpectedSeq = expected + size;
		if (q->ReceiverNextExpectedSeq >= q->m_milestone_rx){
			q->m_milestone_rx += m_ack_interval;
			return 1; //Generate ACK
		}else if (q->ReceiverNextExpectedSeq % m_chunk == 0){
			return 1;
		}else {
			return 5;
		}
	} else if (seq > expected) {
		// Generate NACK
		if (Simulator::Now() >= q->m_nackTimer || q->m_lastNACK != expected){
			m_limerNacks++; // LIMER telemetry: NACK generated
			uint32_t nic_idx = GetNicIdxOfRxQp(q);
			if (nic_idx < m_limerNacksByPort.size())
				m_limerNacksByPort[nic_idx]++;
			q->m_nackTimer = Simulator::Now() + MicroSeconds(m_nack_interval);
			q->m_lastNACK = expected;
			if (m_backto0){
				q->ReceiverNextExpectedSeq = q->ReceiverNextExpectedSeq / m_chunk*m_chunk;
			}
			return 2;
		}else
			return 4;
	}else {
		// Duplicate. 
		return 3;
	}
}
void RdmaHw::AddHeader (Ptr<Packet> p, uint16_t protocolNumber){
	PppHeader ppp;
	ppp.SetProtocol (EtherToPpp (protocolNumber));
	p->AddHeader (ppp);
}
uint16_t RdmaHw::EtherToPpp (uint16_t proto){
	switch(proto){
		case 0x0800: return 0x0021;   //IPv4
		case 0x86DD: return 0x0057;   //IPv6
		default: NS_ASSERT_MSG (false, "PPP Protocol number not defined!");
	}
	return 0;
}

void RdmaHw::RecoverQueue(Ptr<RdmaQueuePair> qp){
	if (qp == NULL || qp->IsLimerTerminal())
		return;
	qp->snd_nxt = qp->snd_una;
	qp->m_nextAvail = Simulator::Now();
}

void RdmaHw::CancelRto(Ptr<RdmaQueuePair> qp){
	if (qp == NULL)
		return;
	if (!qp->m_rtoEvent.IsExpired())
		Simulator::Cancel(qp->m_rtoEvent);
	++qp->m_rtoGeneration;
}

void RdmaHw::ArmRto(Ptr<RdmaQueuePair> qp, bool force){
	if (qp == NULL || qp->IsLimerTerminal())
		return;
	if (!m_limerRecoveryTransportEnabled &&
		qp->GetLimerTrafficClass() != LIMER_RDMA_TRAFFIC_BACKGROUND)
		return;
	if (!force && qp->snd_nxt <= qp->snd_una)
		return;
	if (!qp->m_rtoEvent.IsExpired())
		return;
	uint64_t generation = ++qp->m_rtoGeneration;
	qp->m_rtoEvent = Simulator::Schedule(MicroSeconds(qp->m_rtoUs),
		&RdmaHw::RtoExpired, this, qp, generation);
}

void RdmaHw::RecordWc(Ptr<RdmaQueuePair> qp, uint32_t status){
	if (qp == NULL)
		return;
	qp->m_lastWcStatus = status;
	qp->m_lastWcTimestampNs = Simulator::Now().GetNanoSeconds();
	EmitLimerEvent(LIMER_RDMA_EVENT_WC, qp, status);
}

void RdmaHw::RtoExpired(Ptr<RdmaQueuePair> qp, uint64_t generation){
	if (qp == NULL || qp->IsLimerTerminal() ||
		generation != qp->m_rtoGeneration)
		return;
	if (!m_limerRecoveryTransportEnabled &&
		qp->GetLimerTrafficClass() != LIMER_RDMA_TRAFFIC_BACKGROUND)
		return;

	if (qp->m_retryCount >= qp->m_retryLimit){
		++qp->m_rtoGeneration;
		qp->m_limerState = LIMER_RDMA_QP_ERROR;
		RecordWc(qp, LIMER_RDMA_WC_RETRY_EXC_ERR);
		// Remove the inert/error QP from its physical egress group while
		// preserving it in m_qpMap for WC/collective inspection.
		RedistributeQp();
		return;
	}

	++qp->m_retryCount;
	qp->snd_nxt = qp->snd_una;
	qp->m_nextAvail = Simulator::Now();
	EmitLimerEvent(LIMER_RDMA_EVENT_RTO_RETRY, qp, qp->m_retryCount);

	// Arm before kicking the NIC: a physically dead device returns without a
	// PktSent callback, but retry exhaustion must still be observable.
	uint64_t nextGeneration = ++qp->m_rtoGeneration;
	qp->m_rtoEvent = Simulator::Schedule(MicroSeconds(qp->m_rtoUs),
		&RdmaHw::RtoExpired, this, qp, nextGeneration);
	if (IsUsableNic(qp->m_activeNicIdx))
		m_nic[qp->m_activeNicIdx].dev->TriggerTransmit();
}

void RdmaHw::QpComplete(Ptr<RdmaQueuePair> qp){
	if (qp == NULL || qp->IsLimerTerminal())
		return;
	NS_ASSERT(!m_qpCompleteCallback.IsNull());
	CancelRto(qp);
	qp->m_limerState = LIMER_RDMA_QP_COMPLETED;
	RecordWc(qp, LIMER_RDMA_WC_SUCCESS);
	if (m_cc_mode == 1){
		Simulator::Cancel(qp->mlx.m_eventUpdateAlpha);
		Simulator::Cancel(qp->mlx.m_eventDecreaseRate);
		Simulator::Cancel(qp->mlx.m_rpTimer);
	}

	// Sender completion is a successful ACKed WC, never mere serialization.
	// It must precede m_qpCompleteCallback: entry's qp_finish erases the source
	// port/tag lookup consumed by send_finish.
	SendComplete(qp);
	// This callback will log info
	// It may also delete the rxQp on the receiver
	m_qpCompleteCallback(qp);

	qp->m_notifyAppFinish();

	// delete the qp
	DeleteQueuePair(qp);
}

void RdmaHw::SetLinkDown(Ptr<QbbNetDevice> dev){
	uint32_t nicIdx = FindNicIdx(dev);
	printf("RdmaHw: node:%u nic:%u a link down\n", m_node->GetId(), nicIdx);
	Ptr<RdmaQueuePair> noQp;
	EmitLimerEvent(LIMER_RDMA_EVENT_LINK_DOWN, noQp, nicIdx);
}

bool RdmaHw::ActivateBackup(Ptr<RdmaQueuePair> qp, uint32_t unavailableNic){
	if (qp == NULL || qp->IsLimerTerminal())
		return false;
	if (!m_limerRecoveryTransportEnabled)
		return false;
	CancelRto(qp);
	// Outstanding primary WRs are explicitly flushed before activating the
	// pre-established standby binding.
	RecordWc(qp, LIMER_RDMA_WC_WR_FLUSH_ERR);
	bool canSwitch = qp->m_limerState == LIMER_RDMA_QP_ACTIVE_PRIMARY &&
		qp->m_backupReady && qp->m_backupNicIdx != unavailableNic &&
		IsUsableNic(qp->m_backupNicIdx);
	if (!canSwitch){
		qp->m_limerState = LIMER_RDMA_QP_ERROR;
		EmitLimerEvent(LIMER_RDMA_EVENT_FAILOVER_UNAVAILABLE, qp, unavailableNic);
		return false;
	}

	qp->m_activeNicIdx = qp->m_backupNicIdx;
	qp->m_limerState = LIMER_RDMA_QP_ACTIVE_BACKUP;
	++qp->m_epoch;
	qp->m_failoverTimestampNs = Simulator::Now().GetNanoSeconds();
	qp->m_backupFirstTxTimestampNs = 0;
	qp->m_backupFirstAckTimestampNs = 0;
	qp->m_retryCount = 0;
	qp->snd_nxt = qp->snd_una;
	qp->m_nextAvail = Simulator::Now();
	InitializeQpRateForNic(qp, qp->m_activeNicIdx);
	EmitLimerEvent(LIMER_RDMA_EVENT_FAILOVER, qp, qp->m_activeNicIdx);
	// Covers the case where the advertised standby is also physically dead
	// and therefore never reaches PktSent.
	ArmRto(qp, true);
	return true;
}

uint32_t RdmaHw::FailoverQpsFromNic(uint32_t failedPort){
	uint32_t switched = 0;
	for (auto &entry : m_qpMap){
		Ptr<RdmaQueuePair> qp = entry.second;
		if (qp != NULL && !qp->IsLimerTerminal() &&
			qp->m_activeNicIdx == failedPort && ActivateBackup(qp, failedPort))
			++switched;
	}
	// The alarm coordinator calls FailoverUnavailableQps() after FIB repair,
	// then RedistributeQp() once, making the multi-host transition atomic at
	// one simulation timestamp.
	return switched;
}

uint32_t RdmaHw::FailoverUnavailableQps(){
	uint32_t switched = 0;
	for (auto &entry : m_qpMap){
		Ptr<RdmaQueuePair> qp = entry.second;
		if (qp == NULL || qp->IsLimerTerminal())
			continue;
		NS_ASSERT_MSG(m_gpus_per_server > 0, "GPUsPerServer must be non-zero");
		if (qp->m_src / m_gpus_per_server == qp->m_dest / m_gpus_per_server)
			continue;

		auto route = m_rtTable.find(qp->dip.Get());
		bool activeRoutable = false;
		bool backupRoutable = false;
		if (route != m_rtTable.end()){
			for (uint32_t i = 0; i < route->second.size(); ++i){
				int candidate = route->second[i];
				if (candidate >= 0 && static_cast<uint32_t>(candidate) == qp->m_activeNicIdx)
					activeRoutable = true;
				if (candidate >= 0 && static_cast<uint32_t>(candidate) == qp->m_backupNicIdx)
					backupRoutable = true;
			}
		}
		if (activeRoutable)
			continue;

		uint32_t oldNic = qp->m_activeNicIdx;
		if (!backupRoutable){
			CancelRto(qp);
			RecordWc(qp, LIMER_RDMA_WC_WR_FLUSH_ERR);
			qp->m_limerState = LIMER_RDMA_QP_ERROR;
			EmitLimerEvent(LIMER_RDMA_EVENT_FAILOVER_UNAVAILABLE, qp, oldNic);
			continue;
		}
		if (ActivateBackup(qp, oldNic))
			++switched;
	}
	return switched;
}

void RdmaHw::AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx, bool is_nvswitch){
	uint32_t dip = dstAddr.Get();
	if(is_nvswitch == false)
		m_rtTable[dip].push_back(intf_idx);
	else {
		m_rtTable_nxthop_nvswitch[dip].push_back(intf_idx);
	}
}

void RdmaHw::ClearTable(){
	m_rtTable.clear();
	m_rtTable_nxthop_nvswitch.clear();
}

void RdmaHw::RedistributeQp(){
	// clear old qpGrp
	for (uint32_t i = 0; i < m_nic.size(); i++){
		if (m_nic[i].dev == NULL)
			continue;
		m_nic[i].qpGrp->Clear();
	}

	// First rebuild all groups.  Terminal QPs remain queryable in m_qpMap for
	// WC consumers but can no longer be selected by an egress scheduler.
	for (auto &it : m_qpMap){
		Ptr<RdmaQueuePair> qp = it.second;
		if (qp == NULL || qp->IsLimerTerminal())
			continue;
		uint32_t nic_idx = GetNicIdxOfQp(qp);
		NS_ASSERT_MSG(IsUsableNic(nic_idx), "Active QP binding is not usable");
		m_nic[nic_idx].qpGrp->AddQp(qp);
	}
	// Notify only after every group is complete, so immediate dequeues see a
	// consistent binding set.
	for (auto &it : m_qpMap){
		Ptr<RdmaQueuePair> qp = it.second;
		if (qp == NULL || qp->IsLimerTerminal())
			continue;
		uint32_t nic_idx = GetNicIdxOfQp(qp);
		// Notify Nic
		m_nic[nic_idx].dev->ReassignedQp(qp);
	}
}

Ptr<Packet> RdmaHw::GetNxtPacket(Ptr<RdmaQueuePair> qp){
	uint64_t payload_size = qp->GetBytesLeft();
    uint64_t payloadMtu = m_mtu - (limer_joint_encode ? 24 : 0);
    NS_ABORT_MSG_IF(m_mtu <= 24, "MTU too small for joint wire header");
    if (payloadMtu < payload_size) payload_size = payloadMtu;
	unsigned char jointHeader[24]{};
    bool jointPacket = limer_joint_encode && limer_joint_encode(PeekPointer(qp), jointHeader, 24);
    Ptr<Packet> p = jointPacket ? Create<Packet>(jointHeader, 24) : Create<Packet>();
    p->AddAtEnd(Create<Packet>((uint32_t)payload_size));
	// add SimpleSeqTsHeader
	SimpleSeqTsHeader seqTs;
	seqTs.SetSeq (qp->snd_nxt);
	seqTs.SetPG (qp->m_pg);
	p->AddHeader (seqTs);
	// add udp header
	UdpHeader udpHeader;
	udpHeader.SetDestinationPort (qp->dport);
	udpHeader.SetSourcePort (qp->sport);
	p->AddHeader (udpHeader);
	// add ipv4 header
	Ipv4Header ipHeader;
	ipHeader.SetSource (qp->sip);
	ipHeader.SetDestination (qp->dip);
	ipHeader.SetProtocol (0x11);
	ipHeader.SetPayloadSize (p->GetSize());
	ipHeader.SetTtl (64);
	// nvls <-> ToS, ToS = 1 -> NVLS enable
	if(qp->nvls_enable == 1) ipHeader.SetTos (4);
	else ipHeader.SetTos (0);
	ipHeader.SetIdentification (qp->m_ipid);
	p->AddHeader(ipHeader);
	// add ppp header
	PppHeader ppp;
	ppp.SetProtocol (0x0021); // EtherToPpp(0x800), see point-to-point-net-device.cc
	p->AddHeader (ppp);

	// update state
	qp->snd_nxt += payload_size;
	// std::cout << "current snd_nxt is: " << qp->snd_nxt << ", the window is: " << qp->m_win << std::endl;
	qp->m_ipid++;

	// return
	return p;
}

void RdmaHw::PktSent(Ptr<RdmaQueuePair> qp, Ptr<Packet> pkt, Time interframeGap){
	if (qp == NULL || qp->IsLimerTerminal())
		return;
	qp->lastPktSize = pkt->GetSize();
    if (limer_joint_wire_tx) {
        CustomHeader header(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
        pkt->PeekHeader(header);
        limer_joint_wire_tx(PeekPointer(qp), header.udp.seq, pkt->GetSize());
    }

	uint64_t now = Simulator::Now().GetNanoSeconds();
	if (!qp->m_hasFirstTxTimestamp){
		qp->m_hasFirstTxTimestamp = true;
		qp->m_firstTxTimestampNs = now;
	}
	qp->m_lastTxTimestampNs = now;
	if (qp->m_limerState == LIMER_RDMA_QP_ACTIVE_BACKUP &&
		qp->m_backupFirstTxTimestampNs == 0){
		qp->m_backupFirstTxTimestampNs = now;
		EmitLimerEvent(LIMER_RDMA_EVENT_BACKUP_FIRST_TX, qp,
			qp->m_activeNicIdx);
	}
	UpdateNextAvail(qp, interframeGap, pkt->GetSize());
	ArmRto(qp, false);
}

void RdmaHw::UpdateNextAvail(Ptr<RdmaQueuePair> qp, Time interframeGap, uint32_t pkt_size){
	Time sendingTime;
	if (m_rateBound)
		sendingTime = interframeGap + qp->m_rate.CalculateBytesTxTime(pkt_size);
	else
		sendingTime = interframeGap + qp->m_max_rate.CalculateBytesTxTime(pkt_size);
	qp->m_nextAvail = Simulator::Now() + sendingTime;
}

void RdmaHw::ChangeRate(Ptr<RdmaQueuePair> qp, DataRate new_rate){
	#if 1
	Time sendingTime = qp->m_rate.CalculateBytesTxTime(qp->lastPktSize);
	Time new_sendintTime = new_rate.CalculateBytesTxTime(qp->lastPktSize);
	qp->m_nextAvail = qp->m_nextAvail + new_sendintTime - sendingTime;
	// update nic's next avail event
	uint32_t nic_idx = GetNicIdxOfQp(qp);
	m_nic[nic_idx].dev->UpdateNextAvail(qp->m_nextAvail);
	#endif

	// change to new rate
	qp->m_rate = new_rate;
}
/**
 * when nic send a packet, update the bytes it has sent
*/
void RdmaHw::UpdateTxBytes(uint32_t port_id, uint64_t bytes){
	tx_bytes[port_id] += bytes;
	m_limerTxPkts++; // LIMER telemetry: one send-callback per packet
}
/**
 * output format:
 * time, host_id, port_id, bandwidth
*/
void RdmaHw::PrintHostBW(FILE* bw_output, uint32_t bw_mon_interval){
	for(int i = 0; i < m_nic.size(); ++i){
		if(tx_bytes[i] == last_tx_bytes[i]){
			continue;
		}
		double bw = (tx_bytes[i] - last_tx_bytes[i]) * 8 * 1e6 / (bw_mon_interval); // bit/s
		bw = bw*1.0 / 1e9; // Gbps
		fprintf(bw_output, "%lu, %u, %u, %f\n", Simulator::Now().GetTimeStep(), m_node->GetId(), i, bw);
		fflush(bw_output);
		last_tx_bytes[i] = tx_bytes[i];
	}
}
/**
 * output format:
 * time, src, dst, sport, dport, size, rate
*/
void RdmaHw::PrintQPRate(FILE* rate_output){
	std::unordered_map<uint64_t, Ptr<RdmaQueuePair>>::iterator it = m_qpMap.begin();
	for(; it != m_qpMap.end(); it++){
		Ptr<RdmaQueuePair> qp = it->second;
		uint64_t key = it->first;
		if(qp->m_rate.GetBitRate() == last_qp_rate[key]){
			continue;
		}
		fprintf(rate_output, "%lu, %u, %u, %u, %u, %u, %u\n", Simulator::Now().GetTimeStep(), qp->m_src, qp->m_dest, qp->sport, qp->dport, qp->m_size, qp->m_rate.GetBitRate());
		fflush(rate_output);
		last_qp_rate[key] = qp->m_rate.GetBitRate();
	}
}
/**
 * output format:
 * time, src, dst, sport, dport, size, cnp_number
*/
void RdmaHw::PrintQPCnpNumber(FILE* cnp_output){
	std::unordered_map<uint64_t, Ptr<RdmaQueuePair>>::iterator it = m_qpMap.begin();
	for(; it != m_qpMap.end(); it++){
		Ptr<RdmaQueuePair> qp = it->second;
		uint64_t key = it->first;
		if(qp_cnp[key] != last_qp_cnp[key]){
			fprintf(cnp_output, "%lu, %u, %u, %u, %u, %u, %u\n", Simulator::Now().GetTimeStep(), qp->m_src, qp->m_dest, qp->sport, qp->dport, qp->m_size, qp_cnp[key]);
			fflush(cnp_output);
			last_qp_cnp[key] = qp_cnp[key];
		}
	}
}
#define PRINT_LOG 0
/******************************
 * Mellanox's version of DCQCN
 *****************************/
void RdmaHw::UpdateAlphaMlx(Ptr<RdmaQueuePair> q){
	#if PRINT_LOG
	//printf("%lu alpha update: %08x %08x %u %u %.6lf->", Simulator::Now().GetTimeStep(), q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->mlx.m_alpha);
	#endif
	if (q->mlx.m_alpha_cnp_arrived){
		q->mlx.m_alpha = (1 - m_g)*q->mlx.m_alpha + m_g; 	//binary feedback
	}else {
		q->mlx.m_alpha = (1 - m_g)*q->mlx.m_alpha; 	//binary feedback
	}
	#if PRINT_LOG
	//printf("%.6lf\n", q->mlx.m_alpha);
	#endif
	q->mlx.m_alpha_cnp_arrived = false; // clear the CNP_arrived bit
	ScheduleUpdateAlphaMlx(q);
}
void RdmaHw::ScheduleUpdateAlphaMlx(Ptr<RdmaQueuePair> q){
	q->mlx.m_eventUpdateAlpha = Simulator::Schedule(MicroSeconds(m_alpha_resume_interval), &RdmaHw::UpdateAlphaMlx, this, q);
}

void RdmaHw::cnp_received_mlx(Ptr<RdmaQueuePair> q){
	q->mlx.m_alpha_cnp_arrived = true; // set CNP_arrived bit for alpha update
	q->mlx.m_decrease_cnp_arrived = true; // set CNP_arrived bit for rate decrease
	if (q->mlx.m_first_cnp){
		// init alpha
		q->mlx.m_alpha = 1;
		q->mlx.m_alpha_cnp_arrived = false;
		// schedule alpha update
		ScheduleUpdateAlphaMlx(q);
		// schedule rate decrease
		ScheduleDecreaseRateMlx(q, 1); // add 1 ns to make sure rate decrease is after alpha update
		// set rate on first CNP
		const uint64_t old_rate = q->m_rate.GetBitRate();
		q->mlx.m_targetRate = q->m_rate = m_rateOnFirstCNP * q->m_rate;
		const uint64_t new_rate = q->m_rate.GetBitRate();
		if (new_rate < old_rate && HasLimerCongestionSignalSink()) {
			LimerCongestionSignalEvent event;
			event.timestamp_ns = Simulator::Now().GetNanoSeconds();
			event.event_type = LIMER_SIGNAL_QP_RATE_DECREASE;
			event.node_id = m_node->GetId();
			event.node_type = m_node->GetNodeType();
			event.port_id = m_nic[GetNicIdxOfQp(q)].dev->GetIfIndex();
			FillSignalFromQp(q, &event);
			event.has_rate = true;
			event.old_rate_bps = old_rate;
			event.new_rate_bps = new_rate;
			event.cc_mode = m_cc_mode;
			EmitLimerCongestionSignal(event);
		}
		q->mlx.m_first_cnp = false;
	}
}

void RdmaHw::CheckRateDecreaseMlx(Ptr<RdmaQueuePair> q){
	ScheduleDecreaseRateMlx(q, 0);
	if (q->mlx.m_decrease_cnp_arrived){
		#if PRINT_LOG
		printf("%lu rate dec: %08x %08x %u %u (%0.3lf %.3lf)->", Simulator::Now().GetTimeStep(), q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
		#endif
		bool clamp = true;
		if (!m_EcnClampTgtRate){
			if (q->mlx.m_rpTimeStage == 0)
				clamp = false;
		}
		if (clamp)
			q->mlx.m_targetRate = q->m_rate;
		const uint64_t old_rate = q->m_rate.GetBitRate();
		q->m_rate = std::max(m_minRate, q->m_rate * (1 - q->mlx.m_alpha / 2));
		const uint64_t new_rate = q->m_rate.GetBitRate();
		if (new_rate < old_rate && HasLimerCongestionSignalSink()) {
			LimerCongestionSignalEvent event;
			event.timestamp_ns = Simulator::Now().GetNanoSeconds();
			event.event_type = LIMER_SIGNAL_QP_RATE_DECREASE;
			event.node_id = m_node->GetId();
			event.node_type = m_node->GetNodeType();
			event.port_id = m_nic[GetNicIdxOfQp(q)].dev->GetIfIndex();
			FillSignalFromQp(q, &event);
			event.has_rate = true;
			event.old_rate_bps = old_rate;
			event.new_rate_bps = new_rate;
			event.cc_mode = m_cc_mode;
			EmitLimerCongestionSignal(event);
		}
		// reset rate increase related things
		q->mlx.m_rpTimeStage = 0;
		q->mlx.m_decrease_cnp_arrived = false;
		Simulator::Cancel(q->mlx.m_rpTimer);
		q->mlx.m_rpTimer = Simulator::Schedule(MicroSeconds(m_rpgTimeReset), &RdmaHw::RateIncEventTimerMlx, this, q);
		#if PRINT_LOG
		printf("(%.3lf %.3lf)\n", q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
		#endif
	}
}
void RdmaHw::ScheduleDecreaseRateMlx(Ptr<RdmaQueuePair> q, uint32_t delta){
	q->mlx.m_eventDecreaseRate = Simulator::Schedule(MicroSeconds(m_rateDecreaseInterval) + NanoSeconds(delta), &RdmaHw::CheckRateDecreaseMlx, this, q);
}

void RdmaHw::RateIncEventTimerMlx(Ptr<RdmaQueuePair> q){
	q->mlx.m_rpTimer = Simulator::Schedule(MicroSeconds(m_rpgTimeReset), &RdmaHw::RateIncEventTimerMlx, this, q);
	RateIncEventMlx(q);
	q->mlx.m_rpTimeStage++;
}
void RdmaHw::RateIncEventMlx(Ptr<RdmaQueuePair> q){
	// check which increase phase: fast recovery, active increase, hyper increase
	if (q->mlx.m_rpTimeStage < m_rpgThreshold){ // fast recovery
		FastRecoveryMlx(q);
	}else if (q->mlx.m_rpTimeStage == m_rpgThreshold){ // active increase
		ActiveIncreaseMlx(q);
	}else { // hyper increase
		HyperIncreaseMlx(q);
	}
}

void RdmaHw::FastRecoveryMlx(Ptr<RdmaQueuePair> q){
	#if PRINT_LOG
	printf("%lu fast recovery: %08x %08x %u %u (%0.3lf %.3lf)->", Simulator::Now().GetTimeStep(), q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
	q->m_rate = (q->m_rate / 2) + (q->mlx.m_targetRate / 2);
	#if PRINT_LOG
	printf("(%.3lf %.3lf)\n", q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
}
void RdmaHw::ActiveIncreaseMlx(Ptr<RdmaQueuePair> q){
	#if PRINT_LOG
	printf("%lu active inc: %08x %08x %u %u (%0.3lf %.3lf)->", Simulator::Now().GetTimeStep(), q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
	// get NIC
	uint32_t nic_idx = GetNicIdxOfQp(q);
	Ptr<QbbNetDevice> dev = m_nic[nic_idx].dev;
	// increate rate
	q->mlx.m_targetRate += m_rai;
	if (q->mlx.m_targetRate > dev->GetDataRate())
		q->mlx.m_targetRate = dev->GetDataRate();
	q->m_rate = (q->m_rate / 2) + (q->mlx.m_targetRate / 2);
	#if PRINT_LOG
	printf("(%.3lf %.3lf)\n", q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
}
void RdmaHw::HyperIncreaseMlx(Ptr<RdmaQueuePair> q){
	#if PRINT_LOG
	printf("%lu hyper inc: %08x %08x %u %u (%0.3lf %.3lf)->", Simulator::Now().GetTimeStep(), q->sip.Get(), q->dip.Get(), q->sport, q->dport, q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
	// get NIC
	uint32_t nic_idx = GetNicIdxOfQp(q);
	Ptr<QbbNetDevice> dev = m_nic[nic_idx].dev;
	// increate rate
	q->mlx.m_targetRate += m_rhai;
	if (q->mlx.m_targetRate > dev->GetDataRate())
		q->mlx.m_targetRate = dev->GetDataRate();
	q->m_rate = (q->m_rate / 2) + (q->mlx.m_targetRate / 2);
	#if PRINT_LOG
	printf("(%.3lf %.3lf)\n", q->mlx.m_targetRate.GetBitRate() * 1e-9, q->m_rate.GetBitRate() * 1e-9);
	#endif
}

/***********************
 * High Precision CC
 ***********************/
void RdmaHw::HandleAckHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
	uint64_t ack_seq = ch.ack.seq;
	// update rate
	if (ack_seq > qp->hp.m_lastUpdateSeq){ // if full RTT feedback is ready, do full update
		UpdateRateHp(qp, p, ch, false);
	}else{ // do fast react
		FastReactHp(qp, p, ch);
	}
}

void RdmaHw::UpdateRateHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool fast_react){
	uint64_t next_seq = qp->snd_nxt;
	bool print = !fast_react || true;
	if (qp->hp.m_lastUpdateSeq == 0){ // first RTT
		qp->hp.m_lastUpdateSeq = next_seq;
		// store INT
		IntHeader &ih = ch.ack.ih;
		NS_ASSERT(ih.nhop <= IntHeader::maxHop);
		for (uint32_t i = 0; i < ih.nhop; i++)
			qp->hp.hop[i] = ih.hop[i];
		#if PRINT_LOG
		if (print){
			printf("%lu %s %08x %08x %u %u [%u,%u,%u]", Simulator::Now().GetTimeStep(), fast_react? "fast" : "update", qp->sip.Get(), qp->dip.Get(), qp->sport, qp->dport, qp->hp.m_lastUpdateSeq, ch.ack.seq, next_seq);
			for (uint32_t i = 0; i < ih.nhop; i++)
				printf(" %u %lu %lu", ih.hop[i].GetQlen(), ih.hop[i].GetBytes(), ih.hop[i].GetTime());
			printf("\n");
		}
		#endif
	}else {
		// check packet INT
		IntHeader &ih = ch.ack.ih;
		if (ih.nhop <= IntHeader::maxHop){
			double max_c = 0;
			bool inStable = false;
			#if PRINT_LOG
			if (print)
				printf("%lu %s %08x %08x %u %u [%u,%u,%u]", Simulator::Now().GetTimeStep(), fast_react? "fast" : "update", qp->sip.Get(), qp->dip.Get(), qp->sport, qp->dport, qp->hp.m_lastUpdateSeq, ch.ack.seq, next_seq);
			#endif
			// check each hop
			double U = 0;
			uint64_t dt = 0;
			bool updated[IntHeader::maxHop] = {false}, updated_any = false;
			NS_ASSERT(ih.nhop <= IntHeader::maxHop);
			for (uint32_t i = 0; i < ih.nhop; i++){
				if (m_sampleFeedback){
					if (ih.hop[i].GetQlen() == 0 && fast_react)
						continue;
				}
				updated[i] = updated_any = true;
				#if PRINT_LOG
				if (print)
					printf(" %u(%u) %lu(%lu) %lu(%lu)", ih.hop[i].GetQlen(), qp->hp.hop[i].GetQlen(), ih.hop[i].GetBytes(), qp->hp.hop[i].GetBytes(), ih.hop[i].GetTime(), qp->hp.hop[i].GetTime());
				#endif
				uint64_t tau = ih.hop[i].GetTimeDelta(qp->hp.hop[i]);;
				double duration = tau * 1e-9;
				double txRate = (ih.hop[i].GetBytesDelta(qp->hp.hop[i])) * 8 / duration;
				double u = txRate / ih.hop[i].GetLineRate() + (double)std::min(ih.hop[i].GetQlen(), qp->hp.hop[i].GetQlen()) * qp->m_max_rate.GetBitRate() / ih.hop[i].GetLineRate() /qp->m_win;
				#if PRINT_LOG
				if (print)
					printf(" %.3lf %.3lf", txRate, u);
				#endif
				if (!m_multipleRate){
					// for aggregate (single R)
					if (u > U){
						U = u;
						dt = tau;
					}
				}else {
					// for per hop (per hop R)
					if (tau > qp->m_baseRtt)
						tau = qp->m_baseRtt;
					qp->hp.hopState[i].u = (qp->hp.hopState[i].u * (qp->m_baseRtt - tau) + u * tau) / double(qp->m_baseRtt);
				}
				qp->hp.hop[i] = ih.hop[i];
			}

			DataRate new_rate;
			int32_t new_incStage;
			DataRate new_rate_per_hop[IntHeader::maxHop];
			int32_t new_incStage_per_hop[IntHeader::maxHop];
			if (!m_multipleRate){
				// for aggregate (single R)
				if (updated_any){
					if (dt > qp->m_baseRtt)
						dt = qp->m_baseRtt;
					qp->hp.u = (qp->hp.u * (qp->m_baseRtt - dt) + U * dt) / double(qp->m_baseRtt);
					max_c = qp->hp.u / m_targetUtil;

					if (max_c >= 1 || qp->hp.m_incStage >= m_miThresh){
						new_rate = qp->hp.m_curRate / max_c + m_rai;
						new_incStage = 0;
					}else{
						new_rate = qp->hp.m_curRate + m_rai;
						new_incStage = qp->hp.m_incStage+1;
					}
					if (new_rate < m_minRate)
						new_rate = m_minRate;
					if (new_rate > qp->m_max_rate)
						new_rate = qp->m_max_rate;
					#if PRINT_LOG
					if (print)
						printf(" u=%.6lf U=%.3lf dt=%u max_c=%.3lf", qp->hp.u, U, dt, max_c);
					#endif
					#if PRINT_LOG
					if (print)
						printf(" rate:%.3lf->%.3lf\n", qp->hp.m_curRate.GetBitRate()*1e-9, new_rate.GetBitRate()*1e-9);
					#endif
				}
			}else{
				// for per hop (per hop R)
				new_rate = qp->m_max_rate;
				for (uint32_t i = 0; i < ih.nhop; i++){
					if (updated[i]){
						double c = qp->hp.hopState[i].u / m_targetUtil;
						if (c >= 1 || qp->hp.hopState[i].incStage >= m_miThresh){
							new_rate_per_hop[i] = qp->hp.hopState[i].Rc / c + m_rai;
							new_incStage_per_hop[i] = 0;
						}else{
							new_rate_per_hop[i] = qp->hp.hopState[i].Rc + m_rai;
							new_incStage_per_hop[i] = qp->hp.hopState[i].incStage+1;
						}
						// bound rate
						if (new_rate_per_hop[i] < m_minRate)
							new_rate_per_hop[i] = m_minRate;
						if (new_rate_per_hop[i] > qp->m_max_rate)
							new_rate_per_hop[i] = qp->m_max_rate;
						// find min new_rate
						if (new_rate_per_hop[i] < new_rate)
							new_rate = new_rate_per_hop[i];
						#if PRINT_LOG
						if (print)
							printf(" [%u]u=%.6lf c=%.3lf", i, qp->hp.hopState[i].u, c);
						#endif
						#if PRINT_LOG
						if (print)
							printf(" %.3lf->%.3lf", qp->hp.hopState[i].Rc.GetBitRate()*1e-9, new_rate.GetBitRate()*1e-9);
						#endif
					}else{
						if (qp->hp.hopState[i].Rc < new_rate)
							new_rate = qp->hp.hopState[i].Rc;
					}
				}
				#if PRINT_LOG
				printf("\n");
				#endif
			}
			if (updated_any)
				ChangeRate(qp, new_rate);
			if (!fast_react){
				if (updated_any){
					qp->hp.m_curRate = new_rate;
					qp->hp.m_incStage = new_incStage;
				}
				if (m_multipleRate){
					// for per hop (per hop R)
					for (uint32_t i = 0; i < ih.nhop; i++){
						if (updated[i]){
							qp->hp.hopState[i].Rc = new_rate_per_hop[i];
							qp->hp.hopState[i].incStage = new_incStage_per_hop[i];
						}
					}
				}
			}
		}
		if (!fast_react){
			if (next_seq > qp->hp.m_lastUpdateSeq)
				qp->hp.m_lastUpdateSeq = next_seq; //+ rand() % 2 * m_mtu;
		}
	}
}

void RdmaHw::FastReactHp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
	if (m_fast_react)
		UpdateRateHp(qp, p, ch, true);
}

/**********************
 * TIMELY
 *********************/
void RdmaHw::HandleAckTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
	uint64_t ack_seq = ch.ack.seq;
	// update rate
	if (ack_seq > qp->tmly.m_lastUpdateSeq){ // if full RTT feedback is ready, do full update
		UpdateRateTimely(qp, p, ch, false);
	}else{ // do fast react
		FastReactTimely(qp, p, ch);
	}
}
void RdmaHw::UpdateRateTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool us){
	uint64_t next_seq = qp->snd_nxt;
	uint64_t rtt = Simulator::Now().GetTimeStep() - ch.ack.ih.ts;
	bool print = !us;
	if (qp->tmly.m_lastUpdateSeq != 0){ // not first RTT
		int64_t new_rtt_diff = (int64_t)rtt - (int64_t)qp->tmly.lastRtt;
		double rtt_diff = (1 - m_tmly_alpha) * qp->tmly.rttDiff + m_tmly_alpha * new_rtt_diff;
		double gradient = rtt_diff / m_tmly_minRtt;
		bool inc = false;
		double c = 0;
		#if PRINT_LOG
		if (print)
			printf("%lu node:%u rtt:%lu rttDiff:%.0lf gradient:%.3lf rate:%.3lf", Simulator::Now().GetTimeStep(), m_node->GetId(), rtt, rtt_diff, gradient, qp->tmly.m_curRate.GetBitRate() * 1e-9);
		#endif
		if (rtt < m_tmly_TLow){
			inc = true;
		}else if (rtt > m_tmly_THigh){
			c = 1 - m_tmly_beta * (1 - (double)m_tmly_THigh / rtt);
			inc = false;
		}else if (gradient <= 0){
			inc = true;
		}else{
			c = 1 - m_tmly_beta * gradient;
			if (c < 0)
				c = 0;
			inc = false;
		}
		if (inc){
			if (qp->tmly.m_incStage < 5){
				qp->m_rate = qp->tmly.m_curRate + m_rai;
			}else{
				qp->m_rate = qp->tmly.m_curRate + m_rhai;
			}
			if (qp->m_rate > qp->m_max_rate)
				qp->m_rate = qp->m_max_rate;
			if (!us){
				qp->tmly.m_curRate = qp->m_rate;
				qp->tmly.m_incStage++;
				qp->tmly.rttDiff = rtt_diff;
			}
		}else{
			qp->m_rate = std::max(m_minRate, qp->tmly.m_curRate * c);
			if (!us){
				qp->tmly.m_curRate = qp->m_rate;
				qp->tmly.m_incStage = 0;
				qp->tmly.rttDiff = rtt_diff;
			}
		}
		#if PRINT_LOG
		if (print){
			printf(" %c %.3lf\n", inc? '^':'v', qp->m_rate.GetBitRate() * 1e-9);
		}
		#endif
	}
	if (!us && next_seq > qp->tmly.m_lastUpdateSeq){
		qp->tmly.m_lastUpdateSeq = next_seq;
		// update
		qp->tmly.lastRtt = rtt;
	}
}
void RdmaHw::FastReactTimely(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
}

/**********************
 * DCTCP
 *********************/
void RdmaHw::HandleAckDctcp(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
	uint64_t ack_seq = ch.ack.seq;
	uint8_t cnp = (ch.ack.flags >> qbbHeader::FLAG_CNP) & 1;
	bool new_batch = false;

	// update alpha
	qp->dctcp.m_ecnCnt += (cnp > 0);
	if (ack_seq > qp->dctcp.m_lastUpdateSeq){ // if full RTT feedback is ready, do alpha update
		#if PRINT_LOG
		printf("%lu %s %08x %08x %u %u [%u,%u,%u] %.3lf->", Simulator::Now().GetTimeStep(), "alpha", qp->sip.Get(), qp->dip.Get(), qp->sport, qp->dport, qp->dctcp.m_lastUpdateSeq, ch.ack.seq, qp->snd_nxt, qp->dctcp.m_alpha);
		#endif
		new_batch = true;
		if (qp->dctcp.m_lastUpdateSeq == 0){ // first RTT
			qp->dctcp.m_lastUpdateSeq = qp->snd_nxt;
			qp->dctcp.m_batchSizeOfAlpha = qp->snd_nxt / m_mtu + 1;
		}else {
			double frac = std::min(1.0, double(qp->dctcp.m_ecnCnt) / qp->dctcp.m_batchSizeOfAlpha);
			qp->dctcp.m_alpha = (1 - m_g) * qp->dctcp.m_alpha + m_g * frac;
			qp->dctcp.m_lastUpdateSeq = qp->snd_nxt;
			qp->dctcp.m_ecnCnt = 0;
			qp->dctcp.m_batchSizeOfAlpha = (qp->snd_nxt - ack_seq) / m_mtu + 1;
			#if PRINT_LOG
			printf("%.3lf F:%.3lf", qp->dctcp.m_alpha, frac);
			#endif
		}
		#if PRINT_LOG
		printf("\n");
		#endif
	}

	// check cwr exit
	if (qp->dctcp.m_caState == 1){
		if (ack_seq > qp->dctcp.m_highSeq)
			qp->dctcp.m_caState = 0;
	}

	// check if need to reduce rate: ECN and not in CWR
	if (cnp && qp->dctcp.m_caState == 0){
		#if PRINT_LOG
		printf("%lu %s %08x %08x %u %u %.3lf->", Simulator::Now().GetTimeStep(), "rate", qp->sip.Get(), qp->dip.Get(), qp->sport, qp->dport, qp->m_rate.GetBitRate()*1e-9);
		#endif
		qp->m_rate = std::max(m_minRate, qp->m_rate * (1 - qp->dctcp.m_alpha / 2));
		#if PRINT_LOG
		printf("%.3lf\n", qp->m_rate.GetBitRate() * 1e-9);
		#endif
		qp->dctcp.m_caState = 1;
		qp->dctcp.m_highSeq = qp->snd_nxt;
	}

	// additive inc
	if (qp->dctcp.m_caState == 0 && new_batch)
		qp->m_rate = std::min(qp->m_max_rate, qp->m_rate + m_dctcp_rai);
}

/*********************
 * HPCC-PINT
 ********************/
void RdmaHw::SetPintSmplThresh(double p){
       pint_smpl_thresh = (uint32_t)(65536 * p);
}
void RdmaHw::HandleAckHpPint(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch){
       uint64_t ack_seq = ch.ack.seq;
       if (rand() % 65536 >= pint_smpl_thresh)
               return;
       // update rate
       if (ack_seq > qp->hpccPint.m_lastUpdateSeq){ // if full RTT feedback is ready, do full update
               UpdateRateHpPint(qp, p, ch, false);
       }else{ // do fast react
               UpdateRateHpPint(qp, p, ch, true);
       }
}

void RdmaHw::UpdateRateHpPint(Ptr<RdmaQueuePair> qp, Ptr<Packet> p, CustomHeader &ch, bool fast_react){
       uint64_t next_seq = qp->snd_nxt;
       if (qp->hpccPint.m_lastUpdateSeq == 0){ // first RTT
               qp->hpccPint.m_lastUpdateSeq = next_seq;
       }else {
               // check packet INT
               IntHeader &ih = ch.ack.ih;
               double U = Pint::decode_u(ih.GetPower());

               DataRate new_rate;
               int32_t new_incStage;
               double max_c = U / m_targetUtil;

               if (max_c >= 1 || qp->hpccPint.m_incStage >= m_miThresh){
                       new_rate = qp->hpccPint.m_curRate / max_c + m_rai;
                       new_incStage = 0;
               }else{
                       new_rate = qp->hpccPint.m_curRate + m_rai;
                       new_incStage = qp->hpccPint.m_incStage+1;
               }
               if (new_rate < m_minRate)
                       new_rate = m_minRate;
               if (new_rate > qp->m_max_rate)
                       new_rate = qp->m_max_rate;
               ChangeRate(qp, new_rate);
               if (!fast_react){
                       qp->hpccPint.m_curRate = new_rate;
                       qp->hpccPint.m_incStage = new_incStage;
               }
               if (!fast_react){
                       if (next_seq > qp->hpccPint.m_lastUpdateSeq)
                               qp->hpccPint.m_lastUpdateSeq = next_seq; //+ rand() % 2 * m_mtu;
               }
       }
}

}
