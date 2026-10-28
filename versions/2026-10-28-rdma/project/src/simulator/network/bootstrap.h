#pragma once
// Topology metadata only; this simulator does not execute GPU kernels.
enum class GPUType { A100, A800, H100, H800, NONE, H20 };
#include "topology.h"
// The simulator owns RDMA completion callbacks; setup trace sinks stay passive.
static void LimerNetworkTrace(FILE*, ns3::Ptr<ns3::RdmaQueuePair>) {}
static int InitializeNetwork(const std::string& topology, const std::string& config) {
  if (!ReadConf(topology, config)) return -1;
  SetConfig();
  SetupNetwork(LimerNetworkTrace, LimerNetworkTrace);
  return 0;
}
