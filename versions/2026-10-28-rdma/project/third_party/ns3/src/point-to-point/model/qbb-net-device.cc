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
* Author: Yuliang Li <yuliangli@g.harvard.com>
*/

#define __STDC_LIMIT_MACROS 1
#include <stdint.h>
#include <stdio.h>
#include "ns3/qbb-net-device.h"
#include "ns3/log.h"
#include "ns3/boolean.h"
#include "ns3/uinteger.h"
#include "ns3/double.h"
#include "ns3/data-rate.h"
#include "ns3/object-vector.h"
#include "ns3/pause-header.h"
#include "ns3/simple-drop-tail-queue.h"
#include "ns3/red-queue.h"
#include "ns3/assert.h"
#include "ns3/ipv4.h"
#include "ns3/ipv4-header.h"
#include "ns3/simulator.h"
#include "ns3/point-to-point-channel.h"
#include "ns3/qbb-channel.h"
#include "ns3/random-variable.h"
#include "ns3/flow-id-tag.h"
#include "ns3/qbb-header.h"
#include "ns3/error-model.h"
#include "ns3/cn-header.h"
#include "ns3/ppp-header.h"
#include "limer-congestion-signal.h"
#include "ns3/udp-header.h"
#include "ns3/seq-ts-header.h"
#include "ns3/pointer.h"
#include "ns3/custom-header.h"
#include <algorithm>
#include <cmath>
#include <iostream>
NS_LOG_COMPONENT_DEFINE("QbbNetDevice");

namespace ns3 {
	
	uint32_t RdmaEgressQueue::ack_q_idx = 3;
	// RdmaEgressQueue
	TypeId RdmaEgressQueue::GetTypeId (void)
	{
		static TypeId tid = TypeId ("ns3::RdmaEgressQueue")
			.SetParent<Object> ()
			.AddTraceSource ("RdmaEnqueue", "Enqueue a packet in the RdmaEgressQueue.",
					MakeTraceSourceAccessor (&RdmaEgressQueue::m_traceRdmaEnqueue),
					"ns3::RdmaEgressQueue::RdmaEnqueue")
			.AddTraceSource ("RdmaDequeue", "Dequeue a packet in the RdmaEgressQueue.",
					MakeTraceSourceAccessor (&RdmaEgressQueue::m_traceRdmaDequeue),
					"ns3::RdmaEgressQueue::RdmaDequeue")
			;
		return tid;
	}

	RdmaEgressQueue::RdmaEgressQueue(){
		m_rrlast = 0;
		m_qlast = 0;
		m_ackQ = CreateObject<SimpleDropTailQueue>();
		//m_ackQ = CreateObject<RedQueue>();
		m_ackQ->SetAttribute("MaxBytes", UintegerValue(0xffffffff)); // queue limit is on a higher level, not here
	}

	Ptr<Packet> RdmaEgressQueue::DequeueQindex(int qIndex){
		if (qIndex == -1){ // high prio
			Ptr<Packet> p = m_ackQ->Dequeue();
			m_qlast = -1;
			m_traceRdmaDequeue(p, 0);
			return p;
		}
		if (qIndex >= 0){ // qp
			Ptr<Packet> p = m_rdmaGetNxtPkt(m_qpGrp->Get(qIndex));
			m_rrlast = qIndex;
			m_qlast = qIndex;
			m_traceRdmaDequeue(p, m_qpGrp->Get(qIndex)->m_pg);
			return p;
		}
		return 0;
	}
	int RdmaEgressQueue::GetNextQindex(bool paused[]){
		uint32_t qIndex;
		if (!paused[ack_q_idx] && m_ackQ->GetNPackets() > 0)
			return -1;

		// no pkt in highest priority queue, do rr for each qp
		int res = -1024;
		uint32_t fcount = m_qpGrp->GetN();
		for (qIndex = 1; qIndex <= fcount; qIndex++){
			// iterate start behind the m_rrlast qp
			uint32_t idx = (qIndex + m_rrlast) % fcount;
			Ptr<RdmaQueuePair> qp = m_qpGrp->Get(idx);
			if(qp->GetBytesLeft()<=0){
				int sender_node = qp->GetSrc();
				int receiver_node = qp->GetDest();
				int tag = qp->GetTag();
				int t_count = qp->GetInitialSize();
				// qp transmission finished
			}
			if (!paused[qp->m_pg] && qp->GetBytesLeft() > 0 && !qp->IsWinBound()){
				if (m_qpGrp->Get(idx)->m_nextAvail.GetTimeStep() > Simulator::Now().GetTimeStep()) //not available now
					continue;
				res = idx;
				break;
			}
		}
		return res;
	}

	int RdmaEgressQueue::GetLastQueue(){
		return m_qlast;
	}

	uint32_t RdmaEgressQueue::GetNBytes(uint32_t qIndex){
		NS_ASSERT_MSG(qIndex < m_qpGrp->GetN(), "RdmaEgressQueue::GetNBytes: qIndex >= m_qpGrp->GetN()");
		return m_qpGrp->Get(qIndex)->GetBytesLeft();
	}

	uint32_t RdmaEgressQueue::GetFlowCount(void){
		return m_qpGrp->GetN();
	}

	Ptr<RdmaQueuePair> RdmaEgressQueue::GetQp(uint32_t i){
		return m_qpGrp->Get(i);
	}

	bool RdmaEgressQueue::RemoveQp(Ptr<RdmaQueuePair> qp){
		uint32_t oldCount = m_qpGrp->GetN();
		if (oldCount == 0)
			return false;
		uint32_t removedIndex = 0;
		uint32_t oldLast = m_rrlast % oldCount;
		if (!m_qpGrp->RemoveQp(qp, &removedIndex))
			return false;

		uint32_t newCount = oldCount - 1;
		if (newCount == 0){
			m_rrlast = 0;
		}else if (removedIndex < oldLast){
			m_rrlast = oldLast - 1;
		}else if (removedIndex == oldLast){
			// Preserve the old round-robin successor as the next candidate.
			m_rrlast = (removedIndex + newCount - 1) % newCount;
		}else{
			m_rrlast = oldLast;
		}

		if (m_qlast >= 0){
			uint32_t oldQueue = static_cast<uint32_t>(m_qlast);
			if (oldQueue == removedIndex)
				m_qlast = -1;
			else if (oldQueue > removedIndex)
				--m_qlast;
		}
		return true;
	}
 
	void RdmaEgressQueue::RecoverQueue(uint32_t i){
		NS_ASSERT_MSG(i < m_qpGrp->GetN(), "RdmaEgressQueue::RecoverQueue: qIndex >= m_qpGrp->GetN()");
		m_qpGrp->Get(i)->snd_nxt = m_qpGrp->Get(i)->snd_una;
	}

	void RdmaEgressQueue::EnqueueHighPrioQ(Ptr<Packet> p){
		m_traceRdmaEnqueue(p, 0);
		m_ackQ->Enqueue(p);
	}

	void RdmaEgressQueue::CleanHighPrio(TracedCallback<Ptr<const Packet>, uint32_t> dropCb){
		while (m_ackQ->GetNPackets() > 0){
			Ptr<Packet> p = m_ackQ->Dequeue();
			dropCb(p, 0);
		}
	}

	/******************
	 * QbbNetDevice
	 *****************/
	NS_OBJECT_ENSURE_REGISTERED(QbbNetDevice);

	TypeId
		QbbNetDevice::GetTypeId(void)
	{
		static TypeId tid = TypeId("ns3::QbbNetDevice")
			.SetParent<PointToPointNetDevice>()
			.AddConstructor<QbbNetDevice>()
			.AddAttribute("QbbEnabled",
				"Enable the generation of PAUSE packet.",
				BooleanValue(true),
				MakeBooleanAccessor(&QbbNetDevice::m_qbbEnabled),
				MakeBooleanChecker())
			.AddAttribute("QcnEnabled",
				"Enable the generation of PAUSE packet.",
				BooleanValue(false),
				MakeBooleanAccessor(&QbbNetDevice::m_qcnEnabled),
				MakeBooleanChecker())
			.AddAttribute("DynamicThreshold",
				"Enable dynamic threshold.",
				BooleanValue(false),
				MakeBooleanAccessor(&QbbNetDevice::m_dynamicth),
				MakeBooleanChecker())
			.AddAttribute("PauseTime",
				"Number of microseconds to pause upon congestion",
				UintegerValue(5),
				MakeUintegerAccessor(&QbbNetDevice::m_pausetime),
				MakeUintegerChecker<uint32_t>())
			.AddAttribute ("TxBeQueue", 
					"A queue to use as the transmit queue in the device.",
					PointerValue (),
					MakePointerAccessor (&QbbNetDevice::m_queue),
					MakePointerChecker<PacketQueue> ())
			.AddAttribute ("RdmaEgressQueue", 
					"A queue to use as the transmit queue in the device.",
					PointerValue (),
					MakePointerAccessor (&QbbNetDevice::m_rdmaEQ),
					MakePointerChecker<Object> ())
			.AddAttribute ("NVLS_enable", 
					"enable NVLS",
					UintegerValue (0),
					MakeUintegerAccessor (&QbbNetDevice::nvls_enable),
					MakeUintegerChecker<uint32_t>())
			.AddTraceSource ("QbbEnqueue", "Enqueue a packet in the QbbNetDevice.",
					MakeTraceSourceAccessor (&QbbNetDevice::m_traceEnqueue),
					"ns3::QbbEnabled::QbbEnqueue")
			.AddTraceSource ("QbbDequeue", "Dequeue a packet in the QbbNetDevice.",
					MakeTraceSourceAccessor (&QbbNetDevice::m_traceDequeue),
					"ns3::QbbEnabled::QbbDequeue")
			.AddTraceSource ("QbbDrop", "Drop a packet in the QbbNetDevice.",
					MakeTraceSourceAccessor (&QbbNetDevice::m_traceDrop),
					"ns3::QbbEnabled::QbbDrop")
			.AddTraceSource ("RdmaQpDequeue", "A qp dequeue a packet.",
					MakeTraceSourceAccessor (&QbbNetDevice::m_traceQpDequeue),
					"ns3::QbbEnabled::Dequeue")
			.AddTraceSource ("QbbPfc", "get a PFC packet. 0: resume, 1: pause",
					MakeTraceSourceAccessor (&QbbNetDevice::m_tracePfc),
					"ns3::QbbEnabled::QbbPfc")
			;

		return tid;
	}

	QbbNetDevice::QbbNetDevice()
	{
		NS_LOG_FUNCTION(this);
		m_ecn_source = new std::vector<ECNAccount>;
		for (uint32_t i = 0; i < qCnt; i++){
			m_paused[i] = false;
		}

		m_rdmaEQ = CreateObject<RdmaEgressQueue>();
	}

	uint64_t QbbNetDevice::GetLimerQueueBytes() const
	{
		uint64_t bytes = 0;
		if (m_queue != 0)
			bytes += m_queue->GetNBytesTotal();
		if (m_rdmaEQ != 0 && m_rdmaEQ->m_ackQ != 0)
			bytes += m_rdmaEQ->m_ackQ->GetNBytes();
		return bytes;
	}

	uint64_t QbbNetDevice::GetLimerQueuePackets() const
	{
		uint64_t packets = 0;
		if (m_queue != 0)
			packets += m_queue->GetNPacketsTotal();
		if (m_rdmaEQ != 0 && m_rdmaEQ->m_ackQ != 0)
			packets += m_rdmaEQ->m_ackQ->GetNPackets();
		return packets;
	}

	void QbbNetDevice::ObserveLimerQueue()
	{
		uint64_t bytes = GetLimerQueueBytes();
		uint64_t packets = GetLimerQueuePackets();
		if (bytes > m_limerMaxQueueBytes) {
			m_limerMaxQueueBytes = bytes;
			m_limerMaxQueueTimestampNs = Simulator::Now().GetNanoSeconds();
		}
		m_limerMaxQueuePackets = std::max(m_limerMaxQueuePackets, packets);
	}

	void QbbNetDevice::ResetLimerQueuePeaks()
	{
		m_limerMaxQueueBytes = GetLimerQueueBytes();
		m_limerMaxQueuePackets = GetLimerQueuePackets();
		m_limerMaxQueueTimestampNs = Simulator::Now().GetNanoSeconds();
	}

	void QbbNetDevice::SetLimerForcedLinkDown(bool down)
	{
		if (down == m_limerForcedLinkDown)
			return;
		uint64_t now = Simulator::Now().GetNanoSeconds();
		m_limerForcedLinkDown = down;
		m_limerLinkFlaps++;
		if (down) {
			m_limerLastLinkDownNs = now;
		} else {
			m_limerLastLinkUpNs = now;
			if (now >= m_limerLastLinkDownNs)
				m_limerCumulativeDownNs += now - m_limerLastLinkDownNs;
		}
	}

	bool QbbNetDevice::GetLimerLinkUp() const
	{
		return IsLinkUp() && !m_limerForcedLinkDown;
	}

	uint64_t QbbNetDevice::GetLimerCumulativeDownNs() const
	{
		uint64_t total = m_limerCumulativeDownNs;
		if (m_limerForcedLinkDown) {
			uint64_t now = Simulator::Now().GetNanoSeconds();
			if (now >= m_limerLastLinkDownNs)
				total += now - m_limerLastLinkDownNs;
		}
		return total;
	}

	void QbbNetDevice::SetLimerRecoverRxErrors(bool enabled, uint64_t delayNs)
	{
		m_limerRecoverRxErrors = enabled;
		m_limerRecoveryDelayNs = delayNs;
	}

	void QbbNetDevice::SetLimerServiceFraction(double fraction)
	{
		NS_ABORT_MSG_IF(!std::isfinite(fraction) || fraction <= 0.0 || fraction > 1.0,
			"LIMER service fraction must be finite and in (0, 1]");
		m_limerServiceFraction = fraction;
	}

	double QbbNetDevice::GetLimerServiceFraction() const
	{
		return m_limerServiceFraction;
	}

	void QbbNetDevice::ReceiveLimerCarrierDrop(Ptr<Packet> packet)
	{
		if (packet == 0)
			return;
		m_limerRxDrops++;
		m_limerRxDropBytes += packet->GetSize();
		m_phyRxDropTrace(packet);
		m_traceDrop(packet, 0);
	}

	QbbNetDevice::~QbbNetDevice()
	{
		NS_LOG_FUNCTION(this);
	}

	void
		QbbNetDevice::DoDispose()
	{
		NS_LOG_FUNCTION(this);

		// std::cout << "Do QbbNetDevice::DoDispose() function " << std::endl;

		PointToPointNetDevice::DoDispose();
	}

	void
		QbbNetDevice::TransmitComplete(void)
	{
		// if(m_node->GetId() == 0) std::cout << "transmit complete at tick: " <<  Simulator::Now().GetNanoSeconds() << std::endl;
		NS_LOG_FUNCTION(this);
		NS_ASSERT_MSG(m_txMachineState == BUSY, "Must be BUSY if transmitting");
		m_txMachineState = READY;
		NS_ASSERT_MSG(m_currentPkt != 0, "QbbNetDevice::TransmitComplete(): m_currentPkt zero");
		m_phyTxEndTrace(m_currentPkt);
		m_currentPkt = 0;
		DequeueAndTransmit();
	}

	void QbbNetDevice::SwitchAsHostTransmitComplete(void) {
		NS_LOG_FUNCTION(this);
		NS_ASSERT_MSG(m_txMachineState == BUSY, "Must be BUSY if transmitting");
		m_txMachineState = READY;
		NS_ASSERT_MSG(m_currentPkt != 0, "QbbNetDevice::TransmitComplete(): m_currentPkt zero");
		m_phyTxEndTrace(m_currentPkt);
		m_currentPkt = 0;
		SwitchAsHostSend();
	}

	void
		QbbNetDevice::DequeueAndTransmit(void)
	{
		NS_LOG_FUNCTION(this);
		// if(m_node->GetId() == 0) std::cout << "QP start send at tick: " << Simulator::Now().GetNanoSeconds() << std::endl;
		if (!m_linkUp) return; // if link is down, return
		if (m_txMachineState == BUSY) return;	// Quit if channel busy
		Ptr<Packet> p;
		if (m_node->GetNodeType() == 0 || (m_node->GetNodeType() == 2 && nvls_enable == 1)){
			int qIndex = m_rdmaEQ->GetNextQindex(m_paused);
			if (qIndex != -1024){
				if (qIndex == -1){ // high prio
					p = m_rdmaEQ->DequeueQindex(qIndex);
					
					m_traceDequeue(p, 0);
					// update statistics for monitor
					m_rdmaUpdateTxBytes(m_ifIndex, p->GetSize());
					TransmitStart(p);
					return;
				}
				// a qp dequeue a packet
				Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);
				p = m_rdmaEQ->DequeueQindex(qIndex);
				// update statistics for monitor
				m_rdmaUpdateTxBytes(m_ifIndex, p->GetSize());
				// transmit
				m_traceQpDequeue(p, lastQp);
				TransmitStart(p);

				// update for the next avail time
				m_rdmaPktSent(lastQp, p, m_tInterframeGap);
			}else { // no packet to send
				NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
				Time t = Simulator::GetMaximumSimulationTime();
				for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++){
					Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
					t = Min(qp->m_nextAvail, t);
				}
				if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()){
					m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::DequeueAndTransmit, this);
				}
			}
			return;
		}else{   //switch, doesn't care about qcn, just send
			p = m_queue->DequeueRR(m_paused);		//this is round-robin
			if (p != 0){
				m_snifferTrace(p);
				m_promiscSnifferTrace(p);
				Ipv4Header h;
				Ptr<Packet> packet = p->Copy();
				uint16_t protocol = 0;
				ProcessHeader(packet, protocol);
				packet->RemoveHeader(h);
				FlowIdTag t;
				uint32_t qIndex = m_queue->GetLastQueue();
				if (qIndex == 0){//this is a pause or cnp, send it immediately!
					m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
					p->RemovePacketTag(t);
				}else{
					m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
					p->RemovePacketTag(t);
				}
				m_traceDequeue(p, qIndex);
				TransmitStart(p);
				return;
			}else{ //No queue can deliver any packet
				NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
				if (m_node->GetNodeType() == 0 && m_qcnEnabled){ //nothing to send, possibly due to qcn flow control, if so reschedule sending
					Time t = Simulator::GetMaximumSimulationTime();
					for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++){
						Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
						t = Min(qp->m_nextAvail, t);
					}
					if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()){
						m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::DequeueAndTransmit, this);
					}
				}
			}
		}
		return;
	}

	void QbbNetDevice::SwitchAsHostSend(void) {
		NS_LOG_FUNCTION(this);
		if (!m_linkUp) return; // if link is down, return
		if (m_txMachineState == BUSY) return;	// Quit if channel busy
		Ptr<Packet> p;
		int qIndex = m_rdmaEQ->GetNextQindex(m_paused);
		if (qIndex != -1024){
			if (qIndex == -1){ // high prio
				p = m_rdmaEQ->DequeueQindex(qIndex);
				m_traceDequeue(p, 0);
				// update statistics for monitor
				m_rdmaUpdateTxBytes(m_ifIndex, p->GetSize());
				SwitchAsHostTransmitStart(p);
				return;
			}
			// a qp dequeue a packet
			Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);
			NS_ASSERT_MSG(lastQp->nvls_enable == 1 && m_node->GetNodeType() == 2, "Switch as host send must with NVLS ON!");
			p = m_rdmaEQ->DequeueQindex(qIndex);
			// update statistics for monitor
			m_rdmaUpdateTxBytes(m_ifIndex, p->GetSize());
			// transmit
			m_traceQpDequeue(p, lastQp);
			SwitchAsHostTransmitStart(p);

			// update for the next avail time
			m_rdmaPktSent(lastQp, p, m_tInterframeGap);
		}else { // no packet to send
			NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
			Time t = Simulator::GetMaximumSimulationTime();
			for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++){
				Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
				t = Min(qp->m_nextAvail, t);
			}
			if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()){
				m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::SwitchAsHostSend, this);
			}
		}
		return;
	}

	void QbbNetDevice::SwitchDequeueAndTransmit(void) {
		NS_LOG_FUNCTION(this);
		// if(m_node->GetId() == 0) std::cout << "QP start send at tick: " << Simulator::Now().GetNanoSeconds() << std::endl;
		if (!m_linkUp) return; // if link is down, return
		if (m_txMachineState == BUSY) return;	// Quit if channel busy
		Ptr<Packet> p;
		p = m_queue->DequeueRR(m_paused);		//this is round-robin
		if (p != 0){
			m_snifferTrace(p);
			m_promiscSnifferTrace(p);
			Ipv4Header h;
			Ptr<Packet> packet = p->Copy();
			uint16_t protocol = 0;
			ProcessHeader(packet, protocol);
			packet->RemoveHeader(h);
			FlowIdTag t;
			uint32_t qIndex = m_queue->GetLastQueue();
			if (qIndex == 0){//this is a pause or cnp, send it immediately!
				m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
				p->RemovePacketTag(t);
			}else{
				m_node->SwitchNotifyDequeue(m_ifIndex, qIndex, p);
				p->RemovePacketTag(t);
			}
			m_traceDequeue(p, qIndex);
			TransmitStart(p);
			return;
		}else{ //No queue can deliver any packet
			NS_LOG_INFO("PAUSE prohibits send at node " << m_node->GetId());
			if (m_node->GetNodeType() == 0 && m_qcnEnabled){ //nothing to send, possibly due to qcn flow control, if so reschedule sending
				Time t = Simulator::GetMaximumSimulationTime();
				for (uint32_t i = 0; i < m_rdmaEQ->GetFlowCount(); i++){
					Ptr<RdmaQueuePair> qp = m_rdmaEQ->GetQp(i);
					t = Min(qp->m_nextAvail, t);
				}
				if (m_nextSend.IsExpired() && t < Simulator::GetMaximumSimulationTime() && t > Simulator::Now()){
					m_nextSend = Simulator::Schedule(t - Simulator::Now(), &QbbNetDevice::DequeueAndTransmit, this);
				}
			}
		}
	}

	void
		QbbNetDevice::Resume(unsigned qIndex)
	{
		NS_LOG_FUNCTION(this << qIndex);
		NS_ASSERT_MSG(m_paused[qIndex], "Must be PAUSEd");
		m_paused[qIndex] = false;
		NS_LOG_INFO("Node " << m_node->GetId() << " dev " << m_ifIndex << " queue " << qIndex <<
			" resumed at " << Simulator::Now().GetSeconds());
		Ptr<RdmaQueuePair> lastQp = m_rdmaEQ->GetQp(qIndex);
		if(lastQp->nvls_enable == 1 && m_node->GetNodeType() == 2) SwitchAsHostSend(); 
		else DequeueAndTransmit();
	}

	void
		QbbNetDevice::Receive(Ptr<Packet> packet)
	{
		NS_LOG_FUNCTION(this << packet);
		if (!m_linkUp){
			ReceiveLimerCarrierDrop(packet);
			return;
		}

		if (m_receiveErrorModel && m_receiveErrorModel->IsCorrupt(packet))
		{
			m_phyRxDropTrace(packet);
			m_limerLinkErrors++;
			if (m_limerRecoverRxErrors) {
				m_limerRecoveredPackets++;
				m_limerRecoveredBytes += packet->GetSize();
				Simulator::Schedule(NanoSeconds(m_limerRecoveryDelayNs),
					&QbbNetDevice::DeliverLimerReceivedPacket, this, packet);
			} else {
				m_limerRxDrops++;
				m_limerRxDropBytes += packet->GetSize();
			}
			return;
		}
		DeliverLimerReceivedPacket(packet);
	}

	void QbbNetDevice::DeliverLimerReceivedPacket(Ptr<Packet> packet)
	{
		m_limerRxPackets++;
		m_limerRxBytes += packet->GetSize();

		m_macRxTrace(packet);
		CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
		ch.getInt = 1; // parse INT header
		packet->PeekHeader(ch);
		if (ch.l3Prot == 0xFE){ // PFC
			if (!m_qbbEnabled) return;
			unsigned qIndex = ch.pfc.qIndex;
			NS_ABORT_MSG_IF(qIndex >= qCnt, "received PFC PG exceeds device queues");
			const bool pause_before = m_paused[qIndex];
			bool transitioned = false;
			if (ch.pfc.time > 0){
				m_tracePfc(1);
				if (!pause_before) {
					m_paused[qIndex] = true;
					transitioned = true;
				}
			}else{
				m_tracePfc(0);
				if (pause_before) {
					Resume(qIndex);
					transitioned = true;
				}
			}
			// Duplicate PAUSE/RESUME frames are real wire traffic, but they do not
			// constitute another local pause-state transition and therefore are
			// deliberately absent from the transition evidence stream.
			if (transitioned && HasLimerCongestionSignalSink()) {
				LimerCongestionSignalEvent event;
				event.timestamp_ns = Simulator::Now().GetNanoSeconds();
				event.event_type = ch.pfc.time > 0
					? LIMER_SIGNAL_PFC_PAUSE_RECEIVE
					: LIMER_SIGNAL_PFC_RESUME_RECEIVE;
				event.node_id = m_node->GetId();
				event.node_type = m_node->GetNodeType();
				event.port_id = m_ifIndex;
				event.pg = static_cast<uint16_t>(qIndex);
				event.has_queue_state = true;
				// Receive-side PFC gates an RDMA priority but RdmaEgressQueue does
				// not expose bytes aggregated by PG.  Record the real port total;
				// leave MMU thresholds invalid rather than inventing per-PG bytes.
				event.queue_bytes = GetLimerQueueBytes();
				event.signal_before = pause_before ? 1 : 0;
				event.signal_after = m_paused[qIndex] ? 1 : 0;
				event.pause_time = ch.pfc.time;
				EmitLimerCongestionSignal(event);
			}
		}else { // non-PFC packets (data, ACK, NACK, CNP...)
			uint32_t sip = ch.sip;
			uint32_t sid = (sip >> 8) & 0xffff;
			uint32_t dip = ch.dip;
			uint32_t did = (dip >> 8) & 0xffff;
			if (m_node->GetNodeType() > 0 && ch.m_tos != 4 && did != m_node->GetId()){ // switch
				// std::cout << "id: " << m_node->GetId() << " switch receive from " << sid << std::endl;
				packet->AddPacketTag(FlowIdTag(m_ifIndex));
				m_node->SwitchReceiveFromDevice(this, packet, ch);
			}else { // NIC
				// send to RdmaHw
				// std::cout << "id: " << m_node->GetId() << " NIC receive from " << sid << std::endl;
				if (ch.l3Prot == 0xFC) {
				}
				int ret = m_rdmaReceiveCb(packet, ch);
				// TODO we may based on the ret do something
			}
		}
	}

	bool QbbNetDevice::Send(Ptr<Packet> packet, const Address &dest, uint16_t protocolNumber)
	{
		NS_ASSERT_MSG(false, "QbbNetDevice::Send not implemented yet\n");
		return false;
	}

	bool QbbNetDevice::SwitchSend (uint32_t qIndex, Ptr<Packet> packet, CustomHeader &ch){
 		m_macTxTrace(packet);
		m_traceEnqueue(packet, qIndex);
		m_queue->Enqueue(packet, qIndex);
		ObserveLimerQueue();
		// DequeueAndTransmit();
		SwitchDequeueAndTransmit();
		return true;
	}

	void QbbNetDevice::SendPfc(uint32_t qIndex, uint32_t type){
		Ptr<Packet> p = Create<Packet>(0);
		PauseHeader pauseh((type == 0 ? m_pausetime : 0), m_queue->GetNBytes(qIndex), qIndex);
		p->AddHeader(pauseh);
		Ipv4Header ipv4h;  // Prepare IPv4 header
		ipv4h.SetProtocol(0xFE);
		ipv4h.SetSource(m_node->GetObject<Ipv4>()->GetAddress(m_ifIndex, 0).GetLocal());
		ipv4h.SetDestination(Ipv4Address("255.255.255.255"));
		ipv4h.SetPayloadSize(p->GetSize());
		ipv4h.SetTtl(1);
		ipv4h.SetIdentification(UniformVariable(0, 65536).GetValue());
		p->AddHeader(ipv4h);
		AddHeader(p, 0x800);
		CustomHeader ch(CustomHeader::L2_Header | CustomHeader::L3_Header | CustomHeader::L4_Header);
		p->PeekHeader(ch);
		SwitchSend(0, p, ch);
	}

	Ptr<Packet> QbbNetDevice::NICSendPfc(uint32_t qIndex, uint32_t type) {
	Ptr<Packet> p = Create<Packet>(0);
	PauseHeader pauseh((type == 0 ? m_pausetime : 0), m_queue->GetNBytes(qIndex),
						qIndex);
	// std::cout << "m_pausetime " << pauseh.GetTime() << " " << pauseh.GetQIndex() <<std::endl;
	p->AddHeader(pauseh);
	Ipv4Header ipv4h;  // Prepare IPv4 header
	ipv4h.SetProtocol(0xFE);
	//ipv4h.SetProtocol(L3ProtType::kPFC);
	ipv4h.SetSource(
		m_node->GetObject<Ipv4>()->GetAddress(m_ifIndex, 0).GetLocal());
	ipv4h.SetDestination(Ipv4Address("255.255.255.255"));
	ipv4h.SetPayloadSize(p->GetSize());
	ipv4h.SetTtl(1);
	ipv4h.SetIdentification(UniformVariable(0, 65536).GetValue());
	p->AddHeader(ipv4h);
	AddHeader(p, 0x800);
	return p;
	}

	bool
		QbbNetDevice::Attach(Ptr<QbbChannel> ch)
	{
		NS_LOG_FUNCTION(this << &ch);
		m_channel = ch;
		m_channel->Attach(this);
		NotifyLinkUp();
		return true;
	}
    void QbbNetDevice::SendCallback(Ptr<Packet> packet) {
        CustomHeader ch(
                CustomHeader::L2_Header | CustomHeader::L3_Header |
                CustomHeader::L4_Header);
        packet->PeekHeader(ch);
        m_rdmaSentCb(packet, ch);
    }
	bool
		QbbNetDevice::TransmitStart(Ptr<Packet> p)
	{
		NS_LOG_FUNCTION(this << p);
		NS_LOG_LOGIC("UID is " << p->GetUid() << ")");
		//
		// This function is called to start the process of transmitting a packet.
		// We need to tell the channel that we've started wiggling the wire and
		// schedule an event that will be executed when the transmission is complete.
		//
		NS_ASSERT_MSG(m_txMachineState == READY, "Must be READY to transmit");
		if(m_txMachineState == READY){
			//std:://cout<<"must be ready to transmit\n";
		}
		m_txMachineState = BUSY;
		m_currentPkt = p;
		m_phyTxBeginTrace(m_currentPkt);
		Time txTime = m_bps.CalculateBytesTxTime(p->GetSize());
		if (m_limerServiceFraction < 1.0) {
			uint64_t impairedNs = static_cast<uint64_t>(std::ceil(
				static_cast<double>(txTime.GetNanoSeconds()) /
				m_limerServiceFraction));
			txTime = NanoSeconds(impairedNs);
		}
		// Sender completion is emitted by RdmaHw::QpComplete only after the
		// final byte is ACKed.  The former packet-size heuristic here fired on
		// short packets before an RDMA WC existed and could let ASTRA advance a
		// collective while data was still unacknowledged.
		Time txCompleteTime = txTime + m_tInterframeGap;
		NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.GetSeconds() << "sec");
		Simulator::Schedule(txCompleteTime, &QbbNetDevice::TransmitComplete, this);

		bool result = m_channel->TransmitStart(p, this, txTime);

		if (result == false)
		{
			m_phyTxDropTrace(p);
			m_limerTxDrops++;
			m_limerTxDropBytes += p->GetSize();
		} else {
			m_limerTxPackets++;
			m_limerTxBytes += p->GetSize();
		}
		return result;
	}

	bool QbbNetDevice::SwitchAsHostTransmitStart(Ptr<Packet> p) {
		NS_LOG_FUNCTION(this << p);
		NS_LOG_LOGIC("UID is " << p->GetUid() << ")");
		//
		// This function is called to start the process of transmitting a packet.
		// We need to tell the channel that we've started wiggling the wire and
		// schedule an event that will be executed when the transmission is complete.
		//
		NS_ASSERT_MSG(m_txMachineState == READY, "Must be READY to transmit");
		if(m_txMachineState == READY){
			//std:://cout<<"must be ready to transmit\n";
		}
		m_txMachineState = BUSY;
		m_currentPkt = p;
		m_phyTxBeginTrace(m_currentPkt);
		Time txTime = m_bps.CalculateBytesTxTime(p->GetSize());
		if (m_limerServiceFraction < 1.0) {
			uint64_t impairedNs = static_cast<uint64_t>(std::ceil(
				static_cast<double>(txTime.GetNanoSeconds()) /
				m_limerServiceFraction));
			txTime = NanoSeconds(impairedNs);
		}
		// NVSwitch-hosted sends use the same ACK-qualified completion path in
		// RdmaHw; do not infer completion from the final packet's length.
		Time txCompleteTime = txTime + m_tInterframeGap;
		// std::cout << "txCompleteTime: " << txCompleteTime << std::endl;
		NS_LOG_LOGIC("Schedule TransmitCompleteEvent in " << txCompleteTime.GetSeconds() << "sec");
		Simulator::Schedule(txCompleteTime, &QbbNetDevice::SwitchAsHostTransmitComplete, this);

		bool result = m_channel->TransmitStart(p, this, txTime);

		if (result == false)
		{
			m_phyTxDropTrace(p);
			m_limerTxDrops++;
			m_limerTxDropBytes += p->GetSize();
		} else {
			m_limerTxPackets++;
			m_limerTxBytes += p->GetSize();
		}
		return result;
	}

	Ptr<Channel>
		QbbNetDevice::GetChannel(void) const
	{
		return m_channel;
	}

   bool QbbNetDevice::IsQbb(void) const{
	   return true;
   }

   void QbbNetDevice::NewQp(Ptr<RdmaQueuePair> qp){
	   qp->m_nextAvail = Simulator::Now();
	   if(qp->nvls_enable == 1 && m_node->GetNodeType() == 2) SwitchAsHostSend();
	   else DequeueAndTransmit();
   }
   void QbbNetDevice::ReassignedQp(Ptr<RdmaQueuePair> qp){
	   DequeueAndTransmit();
   }
   bool QbbNetDevice::RemoveQp(Ptr<RdmaQueuePair> qp){
	   return m_rdmaEQ != 0 && m_rdmaEQ->RemoveQp(qp);
   }
   void QbbNetDevice::TriggerTransmit(){
	   DequeueAndTransmit();
   }

	void QbbNetDevice::SetQueue(Ptr<BEgressQueue> q){
		NS_LOG_FUNCTION(this << q);
		m_queue = q;
	}

	Ptr<BEgressQueue> QbbNetDevice::GetQueue(){
		return m_queue;
	}

	Ptr<RdmaEgressQueue> QbbNetDevice::GetRdmaQueue(){
		return m_rdmaEQ;
	}

	void QbbNetDevice::RdmaEnqueueHighPrioQ(Ptr<Packet> p){
		m_traceEnqueue(p, 0);
		m_rdmaEQ->EnqueueHighPrioQ(p);
		ObserveLimerQueue();
	}

	void QbbNetDevice::TakeDown(){
			// Carrier loss is authoritative but may later be reversed by BringUp().
			// Set it before draining/notifying so no same-timestamp callback can send
			// another packet on the failed port.
			if (!m_linkUp)
				return;
			m_linkUp = false;
			m_linkChangeCallbacks();
			SetLimerForcedLinkDown(true);
		if (!m_nextSend.IsExpired())
			Simulator::Cancel(m_nextSend);

		if (m_node->GetNodeType() == 0){
			// clean the high prio queue
			while (m_rdmaEQ->m_ackQ->GetNPackets() > 0) {
				Ptr<Packet> p = m_rdmaEQ->m_ackQ->Dequeue();
				m_limerTxDrops++;
				m_limerTxDropBytes += p->GetSize();
				m_phyTxDropTrace(p);
				m_traceDrop(p, 0);
			}
			// notify driver/RdmaHw that this link is down
			m_rdmaLinkDownCb(this);
		}else { // switch
			// Drain the failed egress and release the switch MMU's ingress and
			// egress admission accounting for every discarded packet.
			for (uint32_t i = 0; i < qCnt; i++)
				m_paused[i] = false;
			while (1){
				Ptr<Packet> p = m_queue->DequeueRR(m_paused);
				if (p == 0)
					 break;
				uint32_t qIndex = m_queue->GetLastQueue();
				m_node->SwitchNotifyDrop(m_ifIndex, qIndex, p);
				m_limerTxDrops++;
				m_limerTxDropBytes += p->GetSize();
				m_phyTxDropTrace(p);
				m_traceDrop(p, qIndex);
			}
			// TODO: Notify switch that this link is down
			}
		}

	void QbbNetDevice::BringUp(){
			if (m_linkUp)
				return;

			// A carrier reset clears link-local PFC state.  In particular, a resume
			// frame may have been lost while the carrier was down; retaining that
			// pause bit would leave an otherwise healthy restored port deadlocked.
			for (uint32_t i = 0; i < qCnt; i++)
				m_paused[i] = false;

			// Clear the event latch before NotifyLinkUp() fires callbacks so an
			// observer invoked by the callback sees one coherent UP state.
			SetLimerForcedLinkDown(false);
			NotifyLinkUp();

			// PhysicalLinkUp restores both endpoints and their shared channel in one
			// public-LP barrier.  Put the actual dequeue kick back onto this node's
			// private LP; a ScheduleNow() from the public LP would permanently move
			// later TransmitComplete/RTO work onto the global synchronization path.
			// Preserve the NVLS-specific send/completion chain as well.
			if (m_node->GetNodeType() == 0) {
				Simulator::ScheduleWithContext(m_node->GetId(), TimeStep(0),
					&QbbNetDevice::DequeueAndTransmit, this);
			} else if (m_node->GetNodeType() == 2 && nvls_enable == 1) {
				Simulator::ScheduleWithContext(m_node->GetId(), TimeStep(0),
					&QbbNetDevice::SwitchAsHostSend, this);
			} else {
				Simulator::ScheduleWithContext(m_node->GetId(), TimeStep(0),
					&QbbNetDevice::SwitchDequeueAndTransmit, this);
			}
		}

	void QbbNetDevice::UpdateNextAvail(Time t){
		if (!m_nextSend.IsExpired() && t < Time(m_nextSend.GetTs())){
			Simulator::Cancel(m_nextSend);
			Time delta = t < Simulator::Now() ? Time(0) : t - Simulator::Now();
			m_nextSend = Simulator::Schedule(delta, &QbbNetDevice::DequeueAndTransmit, this);
		}
	}
} // namespace ns3
