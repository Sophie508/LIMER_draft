// Native finite-horizon alarm, observable cost and pending-flow execution gate.
#include "astra-sim/system/AstraNetworkAPI.hh"
#include "astra-sim/system/Sys.hh"
#include "astra-sim/system/RecvPacketEventHadndlerData.hh"
#include "replay_entry.h"
#define main LimerUnusedNativeMain
#include "AstraSimNetwork.cc"
#undef main
#include <memory>
#include <stdexcept>
#include <set>
#include <cmath>

struct ReplayFlow {
  int id, src, dst, plane, port_src, port_dst;
  uint64_t bytes;
  std::vector<int> deps, children;
  int remaining = 0;
  int version = 0;
  bool started = false, sent = false, received = false;
  AstraSim::sim_request request{};
};

static int logical_ranks = 0;
static std::map<int, ReplayFlow> flows;
static std::vector<std::unique_ptr<ASTRASimNetwork>> networks;
static std::ofstream trace;
static int send_count = 0, recv_count = 0;
static std::set<std::pair<int,int>> released_edges;
static std::map<int,std::unique_ptr<AstraSim::SendPacketEventHandlerData>> send_events;

static uint64_t event_order = 0;
static int current_version = 0, request_count = 0, terminal_requests = 0;
static bool observer_complete = false;
static std::map<int,int> route_override;
static std::map<int,std::unique_ptr<AstraSim::RecvPacketEventHadndlerData>> receive_events;

static void record(int id, const char* event) {
  trace << "{\"id\":" << id << ",\"event\":\"" << event
        << "\",\"ns\":" << Simulator::Now().GetNanoSeconds()
        << ",\"order\":" << event_order++
        << ",\"version\":" << flows.at(id).version
        << ",\"plane\":" << flows.at(id).plane
        << ",\"port_src\":" << flows.at(id).port_src
        << ",\"port_dst\":" << flows.at(id).port_dst << "}\n";
  trace.flush();
}

static std::map<int,int64_t> earliest_launch;
static std::set<int> delayed_launches;
static void launch(int id);
static void release(int id, bool at_sender) {
  auto& parent = flows.at(id);
  int endpoint = at_sender ? parent.src : parent.dst;
  for (int child_id : parent.children) {
    auto& child = flows.at(child_id);
    if (child.src != endpoint) continue;
    if (!released_edges.insert({id, child_id}).second)
      throw std::runtime_error("Duplicate dependency release");
    if (--child.remaining < 0) throw std::runtime_error("Negative indegree");
    if (child.remaining == 0) launch(child_id);
  }
}

static void maybe_stop() {
  if (send_count == int(flows.size()) && recv_count == int(flows.size()) && terminal_requests == request_count && observer_complete)
    Simulator::Stop();
}

static void sent(void* argument) {
  auto* event = static_cast<AstraSim::SendPacketEventHandlerData*>(argument);
  auto& flow = flows.at(event->flowTag.current_flow_id);
  if (flow.sent || !flow.started) throw std::runtime_error("Invalid send completion");
  flow.sent = true;
  ++send_count;
  record(flow.id, "send");
  release(flow.id, true);
  maybe_stop();
}

static void received(void* argument) {
  auto* event = static_cast<AstraSim::RecvPacketEventHadndlerData*>(argument);
  auto& flow = flows.at(event->flowTag.current_flow_id);
  if (flow.received || !flow.started || event->flowTag.flow_size != flow.bytes)
    throw std::runtime_error("Invalid receive completion");
  flow.received = true;
  ++recv_count;
  record(flow.id, "recv");
  release(flow.id, false);
  maybe_stop();
}

static void launch(int id) {
  auto& flow = flows.at(id);
  if (flow.started || flow.remaining) throw std::runtime_error("Invalid launch");
  int64_t now = Simulator::Now().GetNanoSeconds();
  if (earliest_launch.count(id) && now < earliest_launch.at(id)) {
    if (!delayed_launches.insert(id).second) throw std::runtime_error("Duplicate delayed launch");
    Simulator::Schedule(NanoSeconds(earliest_launch.at(id)-now),launch,id); return;
  }
  delayed_launches.erase(id);
  flow.version = current_version;
  if (flow.plane == 0 && route_override.count(flow.src)) flow.plane = route_override.at(flow.src);
  flow.port_src = flow.src + logical_ranks*flow.plane;
  flow.port_dst = flow.dst + logical_ranks*flow.plane;
  auto& tag = flow.request.flowTag;
  tag.channel_id = 0; tag.chunk_id = 0; tag.current_flow_id = flow.id;
  tag.sender_node = flow.port_src; tag.receiver_node = flow.port_dst;
  tag.flow_size = flow.bytes; tag.tag_id = flow.id; tag.nvls_on = false;
  auto placeholder = tag; placeholder.current_flow_id = -1;
  receive_events[flow.id].reset(new AstraSim::RecvPacketEventHadndlerData(
      AstraSim::EventType::PacketReceived, placeholder));
  // One selected receive is posted before its matching send can launch.
  networks[flow.port_dst]->sim_recv(nullptr, flow.bytes, 0, flow.port_src, flow.id,
      &flow.request, received, receive_events[flow.id].get());
  flow.started = true;
  record(id, "start");
  send_events[id].reset(new AstraSim::SendPacketEventHandlerData(
      static_cast<AstraSim::Sys*>(nullptr), flow.port_src, flow.port_dst, id));
  networks[flow.port_src]->sim_send(nullptr, flow.bytes, 0, flow.port_dst, id,
                              &flow.request, sent, send_events[id].get());
}


// A reliable, separate modeled management FIFO. Messages consume real modeled
// serialization time, but are not packetized on the RDMA data network.
struct Transaction {
  int version, rank, unavailable;
  bool terminal = false;
  std::set<int> ready, commits;
};
static std::map<int,Transaction> transactions;
static uint64_t control_capacity = 1'000'000'000;
static int64_t control_propagation = 1'000, control_timeout = 1'000'000;
static int64_t control_free = 0;
static uint64_t control_bytes = 0;

static void control_record(const char* event, int version, int rank) {
  trace << "{\"event\":\"" << event << "\",\"version\":" << version
        << ",\"rank\":" << rank << ",\"ns\":" << Simulator::Now().GetNanoSeconds()
        << ",\"order\":" << event_order++ << "}\n"; trace.flush();
}
static int64_t offer(int version, int rank, const char* kind) {
  int64_t now = Simulator::Now().GetNanoSeconds();
  int64_t start = std::max(now, control_free);
  int64_t end = start + int64_t(std::ceil(512.0*1e9/control_capacity));
  control_free = end; control_bytes += 64;
  trace << "{\"event\":\"control_offer\",\"version\":" << version
        << ",\"rank\":" << rank << ",\"kind\":\"" << kind
        << "\",\"ns\":" << now << ",\"start_ns\":" << start << ",\"end_ns\":" << end
        << ",\"bytes\":64,\"order\":" << event_order++ << "}\n"; trace.flush();
  return end + control_propagation;
}
static void activate(int version) {
  auto& t=transactions.at(version);
  if (t.terminal || int(t.ready.size())!=logical_ranks || int(t.commits.size())!=logical_ranks)
    throw std::runtime_error("Activation without unanimous readiness/commit delivery");
  if (version != current_version+1) throw std::runtime_error("Stale activation");
  current_version=version; route_override[t.rank]=1;
  t.terminal=true; ++terminal_requests;
  control_record("activate",version,t.rank); maybe_stop();
}
static void committed(int version, int rank) {
  auto& t=transactions.at(version);
  if (!t.commits.insert(rank).second) throw std::runtime_error("Duplicate commit delivery");
  control_record("commit_delivery",version,rank);
}
static void ready(int version, int rank) {
  auto& t=transactions.at(version);
  if (!t.ready.insert(rank).second) throw std::runtime_error("Duplicate ready vote");
  control_record("ready",version,rank);
  if (int(t.ready.size())==logical_ranks) {
    int64_t latest=0, now=Simulator::Now().GetNanoSeconds();
    for(int i=0;i<logical_ranks;++i) {
      int64_t arrival=offer(version,i,"commit_delivery"); latest=std::max(latest,arrival);
      Simulator::Schedule(NanoSeconds(arrival-now),committed,version,i);
    }
    Simulator::Schedule(NanoSeconds(latest+1-now),activate,version);
  }
}
static void prepared(int version, int rank) {
  control_record("prepare",version,rank);
  if (rank==transactions.at(version).unavailable) return;
  int64_t arrival=offer(version,rank,"ready");
  Simulator::Schedule(NanoSeconds(arrival-Simulator::Now().GetNanoSeconds()),ready,version,rank);
}
static void timeout(int version) {
  auto& t=transactions.at(version);
  if (t.terminal) return;
  if(int(t.ready.size())==logical_ranks)
    throw std::runtime_error("Control budget too small for the declared timeout");
  t.terminal=true; ++terminal_requests;
  control_record("timeout",version,t.rank); maybe_stop();
}
static void request(int version, int rank, int unavailable) {
  if (version!=current_version+1 || transactions.count(version))
    throw std::runtime_error("Nonconsecutive/stale route version");
  for(const auto& pair:transactions) if(!pair.second.terminal)
    throw std::runtime_error("Overlapping staged route plans");
  transactions.emplace(version,Transaction{version,rank,unavailable});
  control_record("request",version,rank);
  int64_t now=Simulator::Now().GetNanoSeconds();
  for(int i=0;i<logical_ranks;++i) {
    int64_t arrival=offer(version,i,"prepare");
    Simulator::Schedule(NanoSeconds(arrival-now),prepared,version,i);
  }
  Simulator::Schedule(NanoSeconds(control_timeout),timeout,version);
}
static void load_controls(const char* path) {
  std::ifstream input(path);
  if(!(input>>control_capacity>>control_propagation>>control_timeout>>request_count)
     || control_capacity==0 || control_propagation<0 || control_timeout<=0 || request_count<0)
    throw std::runtime_error("Invalid modeled control header");
  for(int i=0;i<request_count;++i) {
    int version,rank,unavailable;int64_t at;
    if(!(input>>version>>at>>rank>>unavailable) || at<0 || at>=10'000'000'000LL
       || version<=0 || rank<0 || rank>=logical_ranks || unavailable< -1 || unavailable>=logical_ranks)
      throw std::runtime_error("Invalid control request");
    Simulator::Schedule(NanoSeconds(at),request,version,rank,unavailable);
  }
  std::string trailing;if(input>>trailing)throw std::runtime_error("Unexpected control input");
}

#include "ack_progress_policy_observer.h"

int main(int argc, char** argv) {
  try {
    if (argc != 11) throw std::runtime_error("Usage: replay topo config graph trace controls observer rate_events progress policy_mode releases");
    MockNcclLog::set_log_name("SimAI_replay.log");
    // Shared DAG state requires globally chronological callbacks. MTP may run
    // separate node logical processes out of order even with one worker thread.
    GlobalValue::Bind("SimulatorImplementationType", StringValue("ns3::DefaultSimulatorImpl"));
    if (main1(argv[1], argv[2]) != 0) throw std::runtime_error("Network setup failed");
    std::ifstream graph(argv[3]);
    int ranks = 0, count = 0;
    if (!(graph >> ranks >> count) || 2*ranks != int(node_num - switch_num - nvswitch_num)
        || gpus_per_server != 1 || count <= 0) throw std::runtime_error("Invalid header/topology");
    logical_ranks = ranks;
    for (int i = 0; i < count; ++i) {
      ReplayFlow flow;
      int parents;
      if (!(graph >> flow.id >> flow.src >> flow.dst >> flow.bytes >> flow.plane >> parents)
          || flow.id <= 0 || flow.src < 0 || flow.src >= ranks || flow.dst < 0
          || flow.dst >= ranks || flow.src == flow.dst || flow.bytes == 0 || parents < 0
          || flow.plane < 0 || flow.plane > 1)
        throw std::runtime_error("Invalid flow");
      std::set<int> unique;
      for (int j = 0; j < parents; ++j) {
        int parent;
        if (!(graph >> parent) || !unique.insert(parent).second)
          throw std::runtime_error("Invalid dependency");
        flow.deps.push_back(parent);
      }
      flow.port_src = flow.src + ranks*flow.plane;
      flow.port_dst = flow.dst + ranks*flow.plane;
      flow.remaining = parents;
      if (!flows.emplace(flow.id, flow).second) throw std::runtime_error("Duplicate ID");
    }
    std::string trailing;
    if (graph >> trailing) throw std::runtime_error("Unexpected trailing input");
    for (auto& entry : flows) {
      auto& flow = entry.second;
      for (int parent_id : flow.deps) {
        auto& parent = flows.at(parent_id);
        if (flow.src != parent.src && flow.src != parent.dst)
          throw std::runtime_error("Remote dependency");
        parent.children.push_back(flow.id);
      }
    }
    // Validate acyclicity independently of the Python converter.
    std::map<int,int> degrees;
    std::queue<int> roots;
    for (const auto& entry : flows) {
      degrees[entry.first] = entry.second.remaining;
      if (!entry.second.remaining) roots.push(entry.first);
    }
    int visited = 0;
    while (!roots.empty()) {
      int id = roots.front(); roots.pop(); ++visited;
      for (int child : flows.at(id).children) if (--degrees[child] == 0) roots.push(child);
    }
    if (visited != count) throw std::runtime_error("Cyclic graph");
    for (int rank = 0; rank < 2*ranks; ++rank)
      networks.emplace_back(new ASTRASimNetwork(rank, 0));
    trace.open(argv[4]);
    if (!trace) throw std::runtime_error("Cannot open trace");
    load_controls(argv[5]);
    load_progress(argv[6],argv[8]);
    load_rate_events(argv[7]);
    load_policy_mode(argv[9]);
    load_release_times(argv[10]);
    for (auto& entry : flows) if (!entry.second.remaining) launch(entry.first);
    Simulator::Stop(Seconds(10));
    Simulator::Run();
    bool complete = send_count == count && recv_count == count && terminal_requests == request_count && observer_complete && sentHash.empty()
       && recvHash.empty() && expeRecvHash.empty() && receiver_pending_queue.empty()
       && sender_src_port_map.empty() && waiting_to_sent_callback.empty()
       && waiting_to_notify_receiver.empty() && sent_chunksize.empty() && received_chunksize.empty();
    std::cout << "REPLAY_SUMMARY nodes=" << count << " sent=" << send_count
              << " received=" << recv_count << " released_edges=" << released_edges.size()
              << " control_bytes=" << control_bytes << " versions=" << current_version
              << " drain=" << complete << " time_ns=" << Simulator::Now().GetNanoSeconds() << '\n';
    Simulator::Destroy();
    return complete ? 0 : 2;
  } catch (const std::exception& error) {
    std::cerr << "REPLAY_ERROR " << error.what() << '\n';
    return 3;
  }
}
