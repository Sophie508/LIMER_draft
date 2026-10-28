#ifndef RDMA_QUEUE_PAIR_H
#define RDMA_QUEUE_PAIR_H

#include <ns3/object.h>
#include <ns3/packet.h>
#include <ns3/ipv4-address.h>
#include <ns3/data-rate.h>
#include <ns3/event-id.h>
#include <ns3/custom-header.h>
#include <ns3/int-header.h>
#include <vector>

namespace ns3 {

// Transport state exposed to LIMER.  These values are deliberately stable
// integers so an out-of-module telemetry callback does not need to depend on
// C++ enum layout or strings.
enum LimerRdmaQpState {
	LIMER_RDMA_QP_ACTIVE_PRIMARY = 0,
	LIMER_RDMA_QP_ACTIVE_BACKUP = 1,
	LIMER_RDMA_QP_ERROR = 2,
	LIMER_RDMA_QP_COMPLETED = 3
};

enum LimerRdmaWcStatus {
	LIMER_RDMA_WC_NONE = 0,
	LIMER_RDMA_WC_SUCCESS = 1,
	LIMER_RDMA_WC_WR_FLUSH_ERR = 2,
	LIMER_RDMA_WC_RETRY_EXC_ERR = 3
};

enum LimerRdmaEventType {
	LIMER_RDMA_EVENT_QP_CREATED = 1,
	LIMER_RDMA_EVENT_BACKUP_READY = 2,
	LIMER_RDMA_EVENT_QP_PREESTABLISHED = LIMER_RDMA_EVENT_BACKUP_READY,
	LIMER_RDMA_EVENT_ACK_PROGRESS = 3,
	LIMER_RDMA_EVENT_RTO_RETRY = 4,
	LIMER_RDMA_EVENT_WC = 5,
	LIMER_RDMA_EVENT_FAILOVER = 6,
	LIMER_RDMA_EVENT_LINK_DOWN = 7,
	LIMER_RDMA_EVENT_FAILOVER_UNAVAILABLE = 8,
	LIMER_RDMA_EVENT_BACKUP_FIRST_TX = 9
};

// Keep application ownership explicit on the QP.  Background traffic is a
// real RDMA transfer, but it must never be mistaken for an Astra collective
// flow by the ns-3 frontend completion callbacks.
enum LimerRdmaTrafficClass {
	LIMER_RDMA_TRAFFIC_TRAINING = 0,
	LIMER_RDMA_TRAFFIC_BACKGROUND = 1
};

// Astra training QPs allocate only in [LIMER_TRAINING_SPORT_MIN,
// LIMER_BACKGROUND_SPORT_MIN).  The BackgroundFlowExecutor accepts only the
// reserved upper interval, so its independently scheduled QPs cannot alias a
// collective QP key.
static const uint16_t LIMER_TRAINING_SPORT_MIN = 10000;
static const uint16_t LIMER_BACKGROUND_SPORT_MIN = 49152;
static const uint16_t LIMER_BACKGROUND_SPORT_MAX = 65535;

class RdmaQueuePair : public Object {
public:
	Time startTime;
	Ipv4Address sip, dip;
	uint16_t sport, dport;
	uint64_t m_size, m_init_size, m_tag;
	uint32_t m_src, m_dest;
	uint64_t snd_nxt, snd_una; // next seq to send, the highest unacked seq
	uint16_t m_pg;
	uint16_t m_ipid;
	uint32_t m_win; // bound of on-the-fly packets
	uint64_t m_baseRtt; // base RTT of this qp
	DataRate m_max_rate; // max rate
	bool m_var_win; // variable window size
	Time m_nextAvail;	//< Soonest time of next send
	uint32_t wp; // current window of packets
	uint32_t lastPktSize;
	Callback<void> m_notifyAppFinish;
	Callback<void> m_notifyAppSent;

	// LIMER transport/failover state.  A backup binding is established when
	// the QP is created; switching therefore changes only m_activeNicIdx and
	// replays the cumulative-ACK gap [snd_una, snd_nxt).
	uint32_t m_primaryNicIdx;
	uint32_t m_backupNicIdx;
	uint32_t m_activeNicIdx;
	bool m_backupReady;
	uint64_t m_backupReadyTimestampNs;
	uint64_t m_epoch;
	uint32_t m_limerState;
	uint32_t m_limerTrafficClass;

	EventId m_rtoEvent;
	uint64_t m_rtoGeneration;
	uint64_t m_rtoUs;
	uint32_t m_retryCount;
	uint32_t m_retryLimit;

	uint32_t m_lastWcStatus;
	uint64_t m_lastWcTimestampNs;
	// First Qbb egress transmission attempt.  The separate validity bit keeps
	// timestamp zero representable for applications scheduled at t=0.
	bool m_hasFirstTxTimestamp;
	uint64_t m_firstTxTimestampNs;
	uint64_t m_lastTxTimestampNs;
	uint64_t m_firstAckProgressTimestampNs;
	uint64_t m_failoverTimestampNs;
	uint64_t m_backupFirstTxTimestampNs;
	uint64_t m_backupFirstAckTimestampNs;
	/******************************
	 * runtime states
	 *****************************/
	uint32_t nvls_enable;
	DataRate m_rate;	//< Current rate
	struct {
		DataRate m_targetRate;	//< Target rate
		EventId m_eventUpdateAlpha;
		double m_alpha;
		bool m_alpha_cnp_arrived; // indicate if CNP arrived in the last slot
		bool m_first_cnp; // indicate if the current CNP is the first CNP
		EventId m_eventDecreaseRate;
		bool m_decrease_cnp_arrived; // indicate if CNP arrived in the last slot
		uint32_t m_rpTimeStage;
		EventId m_rpTimer;
	} mlx;
	struct {
		uint64_t m_lastUpdateSeq;
		DataRate m_curRate;
		IntHop hop[IntHeader::maxHop];
		uint32_t keep[IntHeader::maxHop];
		uint32_t m_incStage;
		double m_lastGap;
		double u;
		struct {
			double u;
			DataRate Rc;
			uint32_t incStage;
		}hopState[IntHeader::maxHop];
	} hp;
	struct{
		uint64_t m_lastUpdateSeq;
		DataRate m_curRate;
		uint32_t m_incStage;
		uint64_t lastRtt;
		double rttDiff;
	} tmly;
	struct{
		uint64_t m_lastUpdateSeq;
		uint32_t m_caState;
		uint64_t m_highSeq; // when to exit cwr
		double m_alpha;
		uint32_t m_ecnCnt;
		uint32_t m_batchSizeOfAlpha;
	} dctcp;
	struct{
		uint64_t m_lastUpdateSeq;
		DataRate m_curRate;
		uint32_t m_incStage;
	}hpccPint;

	/***********
	 * methods
	 **********/
	static TypeId GetTypeId (void);
	RdmaQueuePair(uint16_t pg, Ipv4Address _sip, Ipv4Address _dip, uint16_t _sport, uint16_t _dport);
	void SetSize(uint64_t size);
	void SetWin(uint32_t win);
	void SetBaseRtt(uint64_t baseRtt);
	void SetVarWin(bool v);
	void SetAppNotifyCallback(Callback<void> notifyAppFinish);
	void SetAppSentCallback(Callback<void> notifyAppSent);
	void SetLimerTrafficClass(uint32_t trafficClass);
	uint32_t GetLimerTrafficClass() const;

	uint64_t GetBytesLeft();
	uint64_t GetInitialSize();
	uint32_t GetSrc();
	uint32_t GetDest();
	uint64_t GetTag();
	void SetTag(uint64_t tag);void SetSrc(uint32_t src);void SetDest(uint32_t dest);void SetInitialSize(uint64_t size);
	uint32_t GetHash(void);
	void Acknowledge(uint64_t ack);
	uint64_t GetOnTheFly();
	bool IsWinBound();
	uint64_t GetWin(); // window size calculated from m_rate
	bool IsFinished();
	bool IsLimerTerminal();
	uint64_t HpGetCurWin(); // window size calculated from hp.m_curRate, used by HPCC
};

class RdmaRxQueuePair : public Object { // Rx side queue pair
public:
	struct ECNAccount{
		uint16_t qIndex;
		uint8_t ecnbits;
		uint16_t qfb;
		uint16_t total;

		ECNAccount() { memset(this, 0, sizeof(ECNAccount));}
	};
	ECNAccount m_ecn_source;
	uint32_t sip, dip;
	uint16_t sport, dport;
	uint16_t m_ipid;
	uint64_t ReceiverNextExpectedSeq;
	Time m_nackTimer;
	int32_t m_milestone_rx;
	uint32_t m_lastNACK;
	EventId QcnTimerEvent; // if destroy this rxQp, remember to cancel this timer

	static TypeId GetTypeId (void);
	RdmaRxQueuePair();
	uint32_t GetHash(void);
};

class RdmaQueuePairGroup : public Object {
public:
	std::vector<Ptr<RdmaQueuePair> > m_qps;
	//std::vector<Ptr<RdmaRxQueuePair> > m_rxQps;

	static TypeId GetTypeId (void);
	RdmaQueuePairGroup(void);
	uint32_t GetN(void);
	Ptr<RdmaQueuePair> Get(uint32_t idx);
	Ptr<RdmaQueuePair> operator[](uint32_t idx);
	void AddQp(Ptr<RdmaQueuePair> qp);
	bool RemoveQp(Ptr<RdmaQueuePair> qp, uint32_t *removedIndex = nullptr);
	//void AddRxQp(Ptr<RdmaRxQueuePair> rxQp);
	void Clear(void);
};

}

#endif /* RDMA_QUEUE_PAIR_H */
