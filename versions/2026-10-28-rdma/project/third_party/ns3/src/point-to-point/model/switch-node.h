#ifndef SWITCH_NODE_H
#define SWITCH_NODE_H

#include <map>
#include <mutex>
#include <unordered_map>
#include <ns3/node.h>
#include "limer-route-choice.h"
#include "qbb-net-device.h"
#include "switch-mmu.h"
#include "pint.h"

namespace ns3 {

class Packet;

class SwitchNode : public Node{
	static const uint32_t pCnt = 1025;	// Number of ports used
	static const uint32_t qCnt = 8;	// Number of queues/priorities used
	uint32_t m_ecmpSeed;
	std::unordered_map<uint32_t, std::vector<int> > m_rtTable; // map from ip address (u32) to possible ECMP port (index of dev)
	std::set<uint32_t> active_ports;	// record active ports in switch
	std::set<LimerRouteChoiceKey> m_limerRouteChoices;
	std::mutex m_limerRouteChoiceMutex;

	// Admission accounting needs values only for ingress/egress/queue tuples
	// that currently contain bytes.  The former 1025 x 1025 x 8 dense array
	// consumed about 33.6 MiB in every switch even though true-16 switches have
	// at most a few dozen ports.  A sorted sparse map preserves deterministic
	// key semantics while making memory proportional to non-empty tuples.
	std::map<uint64_t, uint32_t> m_bytes;
	
	uint64_t m_txBytes[pCnt]; // counter of tx bytes

	uint32_t m_lastPktSize[pCnt];
	uint64_t m_lastPktTs[pCnt]; // ns
	double m_u[pCnt];

protected:
	bool m_ecnEnabled;
	uint32_t m_ccMode;
	uint64_t m_maxRtt;

	uint32_t m_ackHighPrio; // set high priority for ACK/NACK

private:
	static uint64_t QueueByteKey(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex);
	void AddQueuedBytes(uint32_t inDev, uint32_t outDev, uint32_t qIndex,
		uint32_t bytes);
	void RemoveQueuedBytes(uint32_t inDev, uint32_t outDev, uint32_t qIndex,
		uint32_t bytes, const char* underflowMessage);
	int GetOutDev(Ptr<const Packet>, CustomHeader &ch);
	bool RememberLimerRouteChoice(const LimerRouteChoiceEvent& event);
	void SendToDev(Ptr<Packet>p, CustomHeader &ch);
	static uint32_t EcmpHash(const uint8_t* key, size_t len, uint32_t seed);
	void CheckAndSendPfc(uint32_t inDev, uint32_t outDev, uint32_t qIndex,
		const CustomHeader& trigger);
	void CheckAndSendResume(uint32_t inDev, uint32_t qIndex);
	void CheckAndSendResumeForPacket(uint32_t inDev, uint32_t outDev,
		uint32_t qIndex, const CustomHeader& trigger);
	void RecordPfcSend(bool pause, uint32_t inDev, bool hasOutDev,
		uint32_t outDev, uint32_t qIndex, const CustomHeader* trigger);
public:
	Ptr<SwitchMmu> m_mmu;

	static TypeId GetTypeId (void);
	SwitchNode();
	void SetEcmpSeed(uint32_t seed);
	void AddTableEntry(Ipv4Address &dstAddr, uint32_t intf_idx);
	void ClearTable();
	bool SwitchReceiveFromDevice(Ptr<NetDevice> device, Ptr<Packet> packet, CustomHeader &ch);
	void SwitchNotifyDequeue(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p);
	void SwitchNotifyDrop(uint32_t ifIndex, uint32_t qIndex, Ptr<Packet> p);

	// LIMER telemetry: read-only accessor for the existing private
	// m_txBytes counter (same value PrintSwitchBw already reads internally).
	uint64_t GetLimerTxBytes(uint32_t ifIndex) const { return m_txBytes[ifIndex]; }

	// for approximate calc in PINT
	int logres_shift(int b, int l);
	int log2apprx(int x, int b, int m, int l); // given x of at most b bits, use most significant m bits of x, calc the result in l bits
	
	// for monitor
	uint64_t last_txBytes[pCnt]; // last sampling of the counter of tx bytes
	uint64_t last_port_qlen[pCnt]; // last sampling of the port length
	
	/**
	 * outoput format:
	 * time, sw_id, port_id, q_id, qlen, port_len
	 */
	void PrintSwitchQlen(FILE* qlen_output);
	/**
	 * outoput format:
	 * time, sw_id, port_id, txBytes
	 */
	void PrintSwitchBw(FILE* bw_output, uint32_t bw_mon_interval);

	// LIMER telemetry counters (read-only from the outside; incremented at
	// the same sites as the existing m_bytes/m_txBytes counters above).
	// Cumulative, per egress port index. Do not reset during a run.
	uint64_t m_limerTxPkts[pCnt] = {0};
	uint64_t m_limerRxPkts[pCnt] = {0};
	uint64_t m_limerDropPkts[pCnt] = {0};
	uint64_t m_limerDropBytes[pCnt] = {0};
	uint64_t m_limerEcnMarks[pCnt] = {0};
	uint64_t m_limerPfcEvents[pCnt] = {0};
};

} /* namespace ns3 */

#endif /* SWITCH_NODE_H */
