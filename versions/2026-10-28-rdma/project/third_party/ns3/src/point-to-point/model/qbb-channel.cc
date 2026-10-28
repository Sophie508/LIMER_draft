/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
/*
 * Copyright (c) 2007, 2008 University of Washington
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
 */

#include "qbb-channel.h"
#include "qbb-net-device.h"
#include "ns3/trace-source-accessor.h"
#include "ns3/packet.h"
#include "ns3/simulator.h"
#include "ns3/log.h"
#include <iostream>
#include <fstream>

NS_LOG_COMPONENT_DEFINE ("QbbChannel");

namespace ns3 {

NS_OBJECT_ENSURE_REGISTERED (QbbChannel);

TypeId 
QbbChannel::GetTypeId (void)
{
    
    static TypeId tid = TypeId ("ns3::QbbChannel")
    .SetParent<Channel> ()
    .AddConstructor<QbbChannel> ()
    .AddAttribute ("Delay", "Transmission delay through the channel",
                   TimeValue (Seconds (0)),
                   MakeTimeAccessor (&QbbChannel::m_delay),
                   MakeTimeChecker ())
    .AddTraceSource ("TxRxQbb",
                     "Trace source indicating transmission of packet from the QbbChannel, used by the Animation interface.",
                     MakeTraceSourceAccessor (&QbbChannel::m_txrxQbb),
		     "ns3::QbbChannel::Double")
  ;
  return tid;
}

//
// By default, you get a channel that 
// has an "infitely" fast transmission speed and zero delay.
QbbChannel::QbbChannel()
  :
    PointToPointChannel (),
    m_carrierUp (true),
    m_carrierEpoch (0)
{
  NS_LOG_FUNCTION_NOARGS ();
  m_nDevices = 0;
}

void
QbbChannel::Attach (Ptr<QbbNetDevice> device)
{
  
  //std::cout << m_nDevices << " " << N_DEVICES << "\n";
  //fflush(stdout);
  NS_LOG_FUNCTION (this << device);
  NS_ASSERT_MSG (m_nDevices < N_DEVICES, "Only two devices permitted");
  NS_ASSERT (device != 0);

  // std::cout << "m_nDevices: " << m_nDevices << " , device: " << device << std::endl;
  m_link[m_nDevices++].m_src = device;
//
// If we have both devices connected to the channel, then finish introducing
// the two halves and set the links to IDLE.
//
  if (m_nDevices == N_DEVICES)
    {
      m_link[0].m_dst = m_link[1].m_src;
      m_link[1].m_dst = m_link[0].m_src;
      m_link[0].m_state = IDLE;
      m_link[1].m_state = IDLE;
    }


}

bool
QbbChannel::TransmitStart (
  Ptr<Packet> p,
  Ptr<QbbNetDevice> src,
  Time txTime)
{
  NS_LOG_FUNCTION (this << p << src);
  NS_LOG_LOGIC ("UID is " << p->GetUid () << ")");

  NS_ASSERT (m_link[0].m_state != INITIALIZING);
  NS_ASSERT (m_link[1].m_state != INITIALIZING);

  uint32_t wire = src == m_link[0].m_src ? 0 : 1;
  NS_ASSERT_MSG (src == m_link[wire].m_src,
                 "QbbChannel::TransmitStart source is not attached");
  Ptr<QbbNetDevice> dst = m_link[wire].m_dst;

  // Read the epoch on both sides of the state check.  NotifyCarrierDown()
  // stores DOWN before advancing the epoch, so a transmission concurrent with
  // the transition either observes DOWN or detects an epoch change.
  uint64_t carrierEpoch = m_carrierEpoch.load (std::memory_order_acquire);
  if (!m_carrierUp.load (std::memory_order_acquire) ||
      !src->IsLinkUp () || !dst->IsLinkUp ())
    {
      return false;
    }
  if (!m_carrierUp.load (std::memory_order_acquire) ||
      carrierEpoch != m_carrierEpoch.load (std::memory_order_acquire))
    {
      return false;
    }

  Simulator::ScheduleWithContext (dst->GetNode ()->GetId (),
                                  txTime + m_delay,
                                  &QbbChannel::DeliverWithCarrierEpoch,
                                  this, p, dst, carrierEpoch);

  // Call the tx anim callback on the net device
  m_txrxQbb (p, src, m_link[wire].m_dst, txTime, txTime + m_delay);
  return true;
}

void
QbbChannel::NotifyCarrierDown (void)
{
  // DOWN must become visible before the epoch changes; TransmitStart's
  // double-check then closes the race between its first epoch read and send.
  bool wasUp = m_carrierUp.exchange (false, std::memory_order_acq_rel);
  if (wasUp)
    {
      m_carrierEpoch.fetch_add (1, std::memory_order_acq_rel);
    }
}

void
QbbChannel::NotifyCarrierUp (void)
{
  m_carrierUp.store (true, std::memory_order_release);
}

bool
QbbChannel::IsCarrierUp (void) const
{
  return m_carrierUp.load (std::memory_order_acquire);
}

uint64_t
QbbChannel::GetCarrierEpoch (void) const
{
  return m_carrierEpoch.load (std::memory_order_acquire);
}

void
QbbChannel::DeliverWithCarrierEpoch (Ptr<Packet> p,
                                     Ptr<QbbNetDevice> dst,
                                     uint64_t carrierEpoch)
{
  if (!m_carrierUp.load (std::memory_order_acquire) ||
      carrierEpoch != m_carrierEpoch.load (std::memory_order_acquire) ||
      !dst->IsLinkUp ())
    {
      dst->ReceiveLimerCarrierDrop (p);
      return;
    }
  dst->Receive (p);
}

size_t
QbbChannel::GetNDevices (void) const
{
  NS_LOG_FUNCTION_NOARGS ();

  //std::cout<<m_nDevices<<"\n";
  //std::cout.flush();


  return m_nDevices;
}

Ptr<QbbNetDevice>
QbbChannel::GetQbbDevice (uint32_t i) const
{
  NS_LOG_FUNCTION_NOARGS ();
  NS_ASSERT (i < 2);
  // std::cout << "GetQbbDevice: " << m_link[i].m_src << std::endl;
  return m_link[i].m_src;
}

Ptr<NetDevice>
QbbChannel::GetDevice (std::size_t i) const
{
  NS_LOG_FUNCTION_NOARGS ();
  return GetQbbDevice (i);
}

Time
QbbChannel::GetDelay (void) const
{
  return m_delay;
}

Ptr<QbbNetDevice>
QbbChannel::GetSource (uint32_t i) const
{
  return m_link[i].m_src;
}

Ptr<QbbNetDevice>
QbbChannel::GetDestination (uint32_t i) const
{
  return m_link[i].m_dst;
}

bool
QbbChannel::IsInitialized (void) const
{
  NS_ASSERT (m_link[0].m_state != INITIALIZING);
  NS_ASSERT (m_link[1].m_state != INITIALIZING);
  return true;
}

} // namespace ns3
