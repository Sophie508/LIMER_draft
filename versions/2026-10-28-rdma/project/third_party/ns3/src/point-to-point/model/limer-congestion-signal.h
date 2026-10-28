#ifndef LIMER_CONGESTION_SIGNAL_H
#define LIMER_CONGESTION_SIGNAL_H

#include <cstdint>

namespace ns3 {

enum LimerCongestionSignalType : uint8_t {
  LIMER_SIGNAL_ECN_MARK = 1,
  LIMER_SIGNAL_CNP_ACK_EMIT = 2,
  LIMER_SIGNAL_CNP_ACK_RX = 3,
  LIMER_SIGNAL_QP_RATE_DECREASE = 4,
  LIMER_SIGNAL_PFC_PAUSE_SEND = 5,
  LIMER_SIGNAL_PFC_PAUSE_RECEIVE = 6,
  LIMER_SIGNAL_PFC_RESUME_SEND = 7,
  LIMER_SIGNAL_PFC_RESUME_RECEIVE = 8,
};

// A mechanism event emitted only at the real data-plane state transition.
// Validity bits keep zero representable and prevent consumers from inventing
// unavailable queue/QP context.
struct LimerCongestionSignalEvent {
  uint64_t timestamp_ns = 0;
  uint8_t event_type = 0;
  uint32_t node_id = 0;
  uint32_t node_type = 0;
  uint32_t port_id = 0;
  bool has_trigger_out_port = false;
  uint32_t trigger_out_port = 0;
  uint16_t pg = 0;

  bool has_flow = false;
  uint32_t flow_src = 0;
  uint32_t flow_dst = 0;
  uint16_t flow_sport = 0;
  uint16_t flow_dport = 0;
  bool has_packet_tuple = false;
  uint32_t packet_sip = 0;
  uint32_t packet_dip = 0;
  uint16_t packet_sport = 0;
  uint16_t packet_dport = 0;

  bool has_queue_state = false;
  uint64_t queue_bytes = 0;
  bool has_threshold_state = false;
  bool has_shared_state = false;
  bool has_headroom_state = false;
  uint64_t shared_used_bytes = 0;
  uint64_t threshold_low_bytes = 0;
  uint64_t threshold_high_bytes = 0;
  uint64_t headroom_bytes = 0;

  uint32_t signal_before = 0;
  uint32_t signal_after = 0;
  uint32_t pause_time = 0;
  bool has_rate = false;
  uint64_t old_rate_bps = 0;
  uint64_t new_rate_bps = 0;
  uint32_t cc_mode = 0;
};

typedef void (*LimerCongestionSignalSink)(
    const LimerCongestionSignalEvent&, void*);

bool RegisterLimerCongestionSignalSink(
    LimerCongestionSignalSink sink, void* context);
bool ClearLimerCongestionSignalSink(
    LimerCongestionSignalSink sink, void* context);
bool HasLimerCongestionSignalSink();
void EmitLimerCongestionSignal(const LimerCongestionSignalEvent& event);

}  // namespace ns3

#endif
