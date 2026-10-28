/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
* Copyright (c) 2006 Georgia Tech Research Corporation, INRIA
*
* This program is free software; you can redistribute it and/or modify
* it under the terms of the GNU General Public License version 2 as
* published by the Free Software Foundation;
*
* This program is distributed in the hope that it will be useful,
* but WITHOUT ANY WARRANTY; without even the implied warranty of
* MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
* GNU General Public License for more details.
*
* You should have received a copy of the GNU General Public License
* along with this program; if not, write to the Free Software
* Foundation, Inc., 59 Temple Place, Suite 330, Boston, MA  02111-1307  USA
*
* Author: Yibo Zhu <yibzh@microsoft.com>
*/
#ifndef QBB_NET_DEVICE_H
#define QBB_NET_DEVICE_H

#include "ns3/point-to-point-net-device.h"
#include "ns3/qbb-channel.h"
//#include "ns3/fivetuple.h"
#include "ns3/event-id.h"
#include "ns3/broadcom-egress-queue.h"
#include "ns3/ipv4.h"
#include "ns3/ipv4-header.h"
#include "ns3/udp-header.h"
#include "ns3/rdma-queue-pair.h"
#include <vector>
#include<map>
#include <ns3/rdma.h>

namespace ns3 {

class RdmaEgressQueue : public Object{
public:
	static const uint32_t qCnt = 8;
	static uint32_t ack_q_idx;
	int m_qlast;
	uint32_t m_rrlast;
	Ptr<SimpleDropTailQueue> m_ackQ; // highest priority queue
	//Ptr<RedQueue> m_ackQ; 
	Ptr<RdmaQueuePairGroup> m_qpGrp; // queue pairs

	// callback for get next packet
	typedef Callback<Ptr<Packet>, Ptr<RdmaQueuePair> > RdmaGetNxtPkt;
	RdmaGetNxtPkt m_rdmaGetNxtPkt;

	static TypeId GetTypeId (void);
	RdmaEgressQueue();
	Ptr<Packet> DequeueQindex(int qIndex);
	int GetNextQindex(bool paused[]);
	int GetLastQueue();
	uint32_t GetNBytes(uint32_t qIndex);
	uint32_t GetFlowCount(void);
	Ptr<RdmaQueuePair> GetQp(uint32_t i);
	bool RemoveQp(Ptr<RdmaQueuePair> qp);
	void RecoverQueue(uint32_t i);
	void EnqueueHighPrioQ(Ptr<Packet> p);
	void CleanHighPrio(TracedCallback<Ptr<const Packet>, uint32_t> dropCb);

	TracedCallback<Ptr<const Packet>, uint32_t> m_traceRdmaEnqueue;
	TracedCallback<Ptr<const Packet>, uint32_t> m_traceRdmaDequeue;
};

/**
 * \class QbbNetDevice
 * \brief A Device for a IEEE 802.1Qbb Network Link.
 */
class QbbNetDevice : public PointToPointNetDevice 
{
public:
  static const uint32_t qCnt = 8;	// Number of queues/priorities used

  static TypeId GetTypeId (void);

  QbbNetDevice ();
  virtual ~QbbNetDevice ();

  /**
   * Receive a packet from a connected PointToPointChannel.
   *
   * This is to intercept the same call from the PointToPointNetDevice
   * so that the pause messages are honoured without letting
   * PointToPointNetDevice::Receive(p) know
   *
   * @see PointToPointNetDevice
   * @param p Ptr to the received packet.
   */
  virtual void Receive (Ptr<Packet> p);

  /**
   * Send a packet to the channel by putting it to the queue
   * of the corresponding priority class
   *
   * @param packet Ptr to the packet to send
   * @param dest Unused
   * @param protocolNumber Protocol used in packet
   */
  virtual bool Send(Ptr<Packet> packet, const Address &dest, uint16_t protocolNumber);
  virtual bool SwitchSend (uint32_t qIndex, Ptr<Packet> packet, CustomHeader &ch);

  // LIMER telemetry is kept on the physical device so every endpoint
  // (HOST, SWITCH, and NVSWITCH) exposes the same authoritative counters.
  // The queue high-water marks are updated from existing enqueue events;
  // periodic sampling therefore cannot miss a transient peak between ticks.
  uint64_t m_limerTxPackets = 0;
  uint64_t m_limerTxBytes = 0;
  uint64_t m_limerRxPackets = 0;
  uint64_t m_limerRxBytes = 0;
  uint64_t m_limerTxDrops = 0;
  uint64_t m_limerTxDropBytes = 0;
  uint64_t m_limerRxDrops = 0;
  uint64_t m_limerRxDropBytes = 0;
  uint64_t m_limerLinkErrors = 0;
  uint64_t m_limerRecoveredPackets = 0;
  uint64_t m_limerRecoveredBytes = 0;
  uint64_t m_limerMaxQueueBytes = 0;
  uint64_t m_limerMaxQueuePackets = 0;
  uint64_t m_limerMaxQueueTimestampNs = 0;
  uint64_t m_limerLinkFlaps = 0;
  uint64_t m_limerLastLinkDownNs = 0;
  uint64_t m_limerLastLinkUpNs = 0;

  uint64_t GetLimerQueueBytes() const;
  uint64_t GetLimerQueuePackets() const;
  void ObserveLimerQueue();
  void ResetLimerQueuePeaks();
  // A transient benchmark flap uses a severe temporary rate reduction rather
  // than mutating SimAI's routing tables. This observability latch preserves
  // the down/up transition even when both occur between snapshots.
  void SetLimerForcedLinkDown(bool down);
  bool GetLimerLinkUp() const;
  uint64_t GetLimerCumulativeDownNs() const;
  void SetLimerRecoverRxErrors(bool enabled, uint64_t delayNs);
  // Apply a carrier-up service-rate impairment without changing the
  // configured physical DataRate.  Values are in (0, 1]; the serialization
  // time of every packet is divided by this fraction.  This lets P2 model a
  // slower egress service process (and the resulting queue/latency growth)
  // without exposing the injected fraction through configured bandwidth.
  void SetLimerServiceFraction(double fraction);
  double GetLimerServiceFraction() const;
  // Account a frame invalidated by a real carrier transition.  QbbChannel
  // calls this when the frame's captured carrier epoch no longer matches the
  // live link, including the down->up case where IsLinkUp() is true again by
  // the time the old frame would otherwise arrive.
  void ReceiveLimerCarrierDrop(Ptr<Packet> packet);

  /**
   * Get the size of Tx buffer available in the device
   *
   * @return buffer available in bytes
   */
  //virtual uint32_t GetTxAvailable(unsigned) const;

  /**
   * TracedCallback hooks
   */
  void ConnectWithoutContext(const CallbackBase& callback);
  void DisconnectWithoutContext(const CallbackBase& callback);

  bool Attach (Ptr<QbbChannel> ch);

   virtual Ptr<Channel> GetChannel (void) const;

   void SetQueue (Ptr<BEgressQueue> q);
   Ptr<BEgressQueue> GetQueue ();
   virtual bool IsQbb(void) const;
   void NewQp(Ptr<RdmaQueuePair> qp);
   void ReassignedQp(Ptr<RdmaQueuePair> qp);
   bool RemoveQp(Ptr<RdmaQueuePair> qp);
   void TriggerTransmit();
   void SwitchAsHostSend(void); // Switch as a Host to send packet, such as reply ack with NVLS ON
   void SwitchDequeueAndTransmit(void); // Switch transfer to other node
   bool SwitchAsHostTransmitStart(Ptr<Packet> p);
   void SwitchAsHostTransmitComplete(void);
   
	void SendPfc(uint32_t qIndex, uint32_t type); // type: 0 = pause, 1 = resume
  uint32_t GetPfcPauseTime() const { return m_pausetime; }
  Ptr<Packet> NICSendPfc(uint32_t qIndex, uint32_t type);

	TracedCallback<Ptr<const Packet>, uint32_t> m_traceEnqueue;
	TracedCallback<Ptr<const Packet>, uint32_t> m_traceDequeue;
	TracedCallback<Ptr<const Packet>, uint32_t> m_traceDrop;
	TracedCallback<uint32_t> m_tracePfc; // 0: resume, 1: pause
protected:

	//Ptr<Node> m_node;

  bool TransmitStart (Ptr<Packet> p);
  
  virtual void DoDispose(void);

  /// Reset the channel into READY state and try transmit again
  virtual void TransmitComplete(void);

  /// Look for an available packet and send it using TransmitStart(p)
  virtual void DequeueAndTransmit(void);

  /// Resume a paused queue and call DequeueAndTransmit()
  virtual void Resume(unsigned qIndex);

  /**
   * The queues for each priority class.
   * @see class Queue
   * @see class InfiniteQueue
   */
  Ptr<BEgressQueue> m_queue;

  Ptr<QbbChannel> m_channel;
  bool m_limerForcedLinkDown = false;
  uint64_t m_limerCumulativeDownNs = 0;
  bool m_limerRecoverRxErrors = false;
  uint64_t m_limerRecoveryDelayNs = 0;
  double m_limerServiceFraction = 1.0;

  void DeliverLimerReceivedPacket(Ptr<Packet> packet);
  
  //pfc
  bool m_qbbEnabled;	//< PFC behaviour enabled
  bool m_qcnEnabled;
  bool m_dynamicth;
  uint32_t m_pausetime;	//< Time for each Pause
  bool m_paused[qCnt];	//< Whether a queue paused
  
  uint32_t nvls_enable;

  //qcn

  /* RP parameters */
  EventId  m_nextSend;		//< The next send event
  /* State variable for rate-limited queues */

  //qcn

  struct ECNAccount{
	  Ipv4Address source;
	  uint32_t qIndex;
	  uint32_t port;
	  uint8_t ecnbits;
	  uint16_t qfb;
	  uint16_t total;
  };

  std::vector<ECNAccount> *m_ecn_source;

public:
	Ptr<RdmaEgressQueue> m_rdmaEQ;
	void RdmaEnqueueHighPrioQ(Ptr<Packet> p);
  void SendCallback(Ptr<Packet> Packet);
  // callback for send packet finish in RDMA
  typedef Callback<int, Ptr<Packet>, CustomHeader &> RdmaSentCb;
  RdmaSentCb m_rdmaSentCb;
  // callback for processing packet in RDMA
	typedef Callback<int, Ptr<Packet>, CustomHeader&> RdmaReceiveCb;
	RdmaReceiveCb m_rdmaReceiveCb;
	// callback for link down
	typedef Callback<void, Ptr<QbbNetDevice> > RdmaLinkDownCb;
	RdmaLinkDownCb m_rdmaLinkDownCb;
	// callback for sent a packet
	typedef Callback<void, Ptr<RdmaQueuePair>, Ptr<Packet>, Time> RdmaPktSent;
	RdmaPktSent m_rdmaPktSent;
  Callback<void, uint32_t, uint64_t> m_rdmaUpdateTxBytes;

	Ptr<RdmaEgressQueue> GetRdmaQueue();
	void TakeDown(); // take down this device without detaching its channel
	void BringUp();  // restore carrier state; does not rebuild routes or move QPs
	void UpdateNextAvail(Time t);

	TracedCallback<Ptr<const Packet>, Ptr<RdmaQueuePair> > m_traceQpDequeue; // the trace for printing dequeue
};

} // namespace ns3

#endif // QBB_NET_DEVICE_H
