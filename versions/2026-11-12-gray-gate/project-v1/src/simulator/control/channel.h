#pragma once
#include <algorithm>
#include <cstdint>
#include <stdexcept>
namespace limer { namespace control {
// All control messages enqueue at their actual causal send time.
class ControlFifo {
 public:
  uint64_t free_ns=0,wire_bytes=0;
  uint64_t rate_bps=100000000,propagation_ns=1000000;
  uint64_t send(uint64_t now,uint64_t bytes) {
    if(!bytes||!rate_bps) throw std::logic_error("invalid control message");
    free_ns=std::max(now,free_ns)+(bytes*8000000000ULL+rate_bps-1)/rate_bps;
    wire_bytes+=bytes;return free_ns+propagation_ns;
  }
};
}}
