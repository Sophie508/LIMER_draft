// Isolated ns-3 two-ended observation experiment; not a collective or DAG replay.
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include <array>
#include <cmath>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>

using namespace ns3;

class BatchHeader : public Header {
public:
  uint32_t batch = 0;
  uint64_t sequence = 0;
  static TypeId GetTypeId() {
    static TypeId t = TypeId("BatchHeader").SetParent<Header>().AddConstructor<BatchHeader>();
    return t;
  }
  TypeId GetInstanceTypeId() const override { return GetTypeId(); }
  uint32_t GetSerializedSize() const override { return 12; }
  void Serialize(Buffer::Iterator i) const override { i.WriteHtonU32(batch); i.WriteHtonU64(sequence); }
  uint32_t Deserialize(Buffer::Iterator i) override {
    batch = i.ReadNtohU32(); sequence = i.ReadNtohU64(); return 12;
  }
  void Print(std::ostream& os) const override { os << batch << ':' << sequence; }
};

class DeferredTag : public Tag {
public:
  static TypeId GetTypeId() {
    static TypeId t = TypeId("DeferredTag").SetParent<Tag>().AddConstructor<DeferredTag>();
    return t;
  }
  TypeId GetInstanceTypeId() const override { return GetTypeId(); }
  uint32_t GetSerializedSize() const override { return 1; }
  void Serialize(TagBuffer b) const override { b.WriteU8(1); }
  void Deserialize(TagBuffer b) override { b.ReadU8(); }
  void Print(std::ostream& os) const override { os << "deferred"; }
};

// This hook defers selected network deliveries, without blocking later packets.
// A built-in PhyRxDrop trace fires on first deferral; it is not permanent loss.
// The candidate reads neither that trace nor this model's private audit counters.
class DeliveryModel : public ErrorModel {
public:
  Ptr<PointToPointNetDevice> receiver;
  Ptr<UniformRandomVariable> random = CreateObject<UniformRandomVariable>();
  double loss = 0, deferFraction = 0;
  Time extraDelay = Seconds(0);
  uint64_t permanentDrops = 0, deferred = 0;
private:
  bool DoCorrupt(Ptr<Packet> p) override {
    DeferredTag tag;
    if (p->RemovePacketTag(tag)) return false;
    if (random->GetValue() < loss) { ++permanentDrops; return true; }
    if (extraDelay.IsStrictlyPositive() && random->GetValue() < deferFraction) {
      Ptr<Packet> copy = p->Copy(); copy->AddPacketTag(tag); ++deferred;
      Simulator::Schedule(extraDelay, &PointToPointNetDevice::Receive, receiver, copy);
      return true;
    }
    return false;
  }
  void DoReset() override {}
};

struct Path {
  Ptr<Socket> source, sink, background, bgSink;
  Ptr<PointToPointNetDevice> device;
  Ptr<DeliveryModel> model;
  std::map<uint32_t,uint64_t> tx, rx;
  std::set<uint64_t> seen;
  uint64_t next = 0, duplicates = 0, rejected = 0, backgroundSent = 0;
  uint64_t wirePackets = 0, wireBytes = 0;
  uint32_t minWire = UINT32_MAX, maxWire = 0;
};

static std::array<Path,8> paths;
static std::ofstream reports;
static std::string scenario = "nominal", out = ".";
static double capacityMbps = 100, offeredMbps = 80, lossRate = .005;
static double reportRateMbps = 1, reportDelayMs = 5, reportLoss = 0;
static double faultTimeMs = 50;
static int64_t faultNs = 50'000'000;
static uint32_t runId = 1;
static Time reportFree = Seconds(0);
static Ptr<UniformRandomVariable> reportRandom;
static uint64_t offeredReports = 0, droppedReports = 0;
static constexpr int64_t periodNs = 10'000'000;

static void wireSend(uint32_t i, Ptr<const Packet> p) {
  ++paths[i].wirePackets; paths[i].wireBytes += p->GetSize();
  paths[i].minWire = std::min(paths[i].minWire, p->GetSize());
  paths[i].maxWire = std::max(paths[i].maxWire, p->GetSize());
}

static void deliverReport(uint32_t i, uint32_t batch, std::string side,
                          uint64_t count, int64_t sampleNs) {
  reports << "{\"path\":\"" << i/2 << '/' << (i%2 ? 'B' : 'A')
          << "\",\"batch\":" << batch << ",\"side\":\"" << side
          << "\",\"count\":" << count << ",\"sample_t_ns\":" << sampleNs
          << ",\"arrival_t_ns\":" << Simulator::Now().GetNanoSeconds() << "}\n";
}

static void snapshot(uint32_t i, uint32_t batch, bool atReceiver) {
  uint64_t count = (atReceiver ? paths[i].rx : paths[i].tx)[batch];
  int64_t sampleNs = Simulator::Now().GetNanoSeconds();
  // Independent reporting FIFO, including serialization of subsequently lost reports.
  Time start = std::max(Simulator::Now(), reportFree);
  reportFree = start + NanoSeconds(int64_t(std::ceil(512.0 / reportRateMbps * 1000)));
  ++offeredReports;
  if (reportRandom->GetValue() < reportLoss) { ++droppedReports; return; }
  Simulator::Schedule(reportFree + MilliSeconds(reportDelayMs) - Simulator::Now(),
                      deliverReport, i, batch, atReceiver ? "rx" : "tx", count, sampleNs);
}

static void receive(uint32_t i, Ptr<Socket> socket) {
  while (Ptr<Packet> p = socket->Recv()) {
    BatchHeader h;
    if (p->RemoveHeader(h) != 12 || p->GetSize() != 1446)
      throw std::runtime_error("corrupt batch payload/header");
    if (!paths[i].seen.insert(h.sequence).second) ++paths[i].duplicates;
    else ++paths[i].rx[h.batch];
  }
}

static void sendData(uint32_t i) {
  int64_t ns = Simulator::Now().GetNanoSeconds();
  if (ns >= 250'000'000) return;
  bool paused = scenario == "pause" && ns >= faultNs && ns < faultNs+60'000'000;
  bool idle = scenario == "idle" && ns >= 40'000'000 && ns < 200'000'000;
  if (!paused && !idle) {
    Ptr<Packet> p = Create<Packet>(1446);
    BatchHeader h; h.batch = ns / periodNs; h.sequence = paths[i].next++;
    p->AddHeader(h);
    if (paths[i].source->Send(p) == 1458) ++paths[i].tx[h.batch];
    else ++paths[i].rejected;
  }
  Simulator::Schedule(NanoSeconds(int64_t(std::ceil(12'000.0 / offeredMbps * 1000))), sendData, i);
}

static void sendBackground(uint32_t i) {
  if (Simulator::Now() >= MilliSeconds(250)) return;
  if (paths[i].background->Send(Create<Packet>(1458)) == 1458) ++paths[i].backgroundSent;
  double rate = capacityMbps * (scenario == "overload" ? .8 : .1);
  Simulator::Schedule(NanoSeconds(int64_t(std::ceil(12'000.0 / rate * 1000))), sendBackground, i);
}

static void event() {
  if (scenario == "loss" || scenario == "sparse" || scenario == "idle") paths[4].model->loss = lossRate;
  if (scenario == "reorder40" || scenario == "reorder80") {
    paths[4].model->extraDelay = MilliSeconds(scenario == "reorder40" ? 40 : 80);
    paths[4].model->deferFraction = .25;
  }
  if (scenario == "congestion" || scenario == "overload") sendBackground(4);
}

int main(int argc, char** argv) {
  try {
    CommandLine cmd;
    cmd.AddValue("scenario", "Declared scenario (hidden from detector)", scenario);
    cmd.AddValue("out", "Output directory", out);
    cmd.AddValue("capacityMbps", "Data link capacity", capacityMbps);
    cmd.AddValue("offeredMbps", "Wire offered rate on each of eight paths", offeredMbps);
    cmd.AddValue("lossRate", "Injected packet loss probability", lossRate);
    cmd.AddValue("reportDelayMs", "Independent telemetry propagation delay", reportDelayMs);
    cmd.AddValue("reportRateMbps", "Shared telemetry FIFO service rate", reportRateMbps);
    cmd.AddValue("reportLoss", "Independent report loss probability", reportLoss);
    cmd.AddValue("runId", "Independent ns-3 RNG run", runId);
    cmd.AddValue("faultTimeMs", "Hidden fault/pseudo-event time", faultTimeMs);
    cmd.Parse(argc, argv);
    if (capacityMbps <= 0 || offeredMbps <= 0 || reportRateMbps <= 0 ||
        reportDelayMs < 0 || lossRate < 0 || lossRate > 1 || reportLoss < 0 || reportLoss > 1)
      throw std::runtime_error("invalid model parameters");
    RngSeedManager::SetSeed(20261010); RngSeedManager::SetRun(runId);
    faultNs = int64_t(std::llround(faultTimeMs*1e6));
    GlobalValue::Bind("SimulatorImplementationType", StringValue("ns3::DefaultSimulatorImpl"));
    reportRandom = CreateObject<UniformRandomVariable>(); reportRandom->SetStream(100);
    reports.open(out + "/reports.jsonl");
    if (!reports) throw std::runtime_error("cannot open reports");
    for (uint32_t i=0; i<8; ++i) {
      NodeContainer nodes; nodes.Create(2);
      InternetStackHelper stack; stack.SetIpv6StackInstall(false); stack.Install(nodes);
      PointToPointHelper helper;
      helper.SetDeviceAttribute("DataRate", DataRateValue(DataRate(uint64_t(capacityMbps*1e6))));
      helper.SetChannelAttribute("Delay", TimeValue(MilliSeconds(1)));
      helper.SetQueue("ns3::DropTailQueue<Packet>", "MaxSize", QueueSizeValue(QueueSize("10000p")));
      NetDeviceContainer devices = helper.Install(nodes);
      paths[i].device = DynamicCast<PointToPointNetDevice>(devices.Get(0));
      paths[i].device->TraceConnectWithoutContext("PhyTxBegin",MakeBoundCallback(&wireSend,i));
      paths[i].model = CreateObject<DeliveryModel>();
      paths[i].model->receiver = DynamicCast<PointToPointNetDevice>(devices.Get(1));
      paths[i].model->random->SetStream(i+1);
      paths[i].model->receiver->SetReceiveErrorModel(paths[i].model);
      Ipv4AddressHelper address;
      address.SetBase(Ipv4Address(("10."+std::to_string(i+1)+".0.0").c_str()), "255.255.255.0");
      Ipv4InterfaceContainer ips = address.Assign(devices);
      paths[i].source = Socket::CreateSocket(nodes.Get(0), UdpSocketFactory::GetTypeId());
      paths[i].source->Connect(InetSocketAddress(ips.GetAddress(1),9000));
      paths[i].sink = Socket::CreateSocket(nodes.Get(1), UdpSocketFactory::GetTypeId());
      paths[i].sink->Bind(InetSocketAddress(Ipv4Address::GetAny(),9000));
      paths[i].sink->SetRecvCallback(MakeBoundCallback(&receive,i));
      paths[i].background = Socket::CreateSocket(nodes.Get(0), UdpSocketFactory::GetTypeId());
      paths[i].background->Connect(InetSocketAddress(ips.GetAddress(1),9001));
      // A sink drains competing traffic; no ICMP backscatter from an unbound port.
      paths[i].bgSink = Socket::CreateSocket(nodes.Get(1), UdpSocketFactory::GetTypeId());
      paths[i].bgSink->Bind(InetSocketAddress(Ipv4Address::GetAny(),9001));
      paths[i].bgSink->SetRecvCallback(MakeCallback(+[](Ptr<Socket> s){ while(s->Recv()) {} }));
      Simulator::Schedule(MilliSeconds(1),sendData,i);
      for (uint32_t batch=0; batch<50; ++batch) {
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs),snapshot,i,batch,false);
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs+50'000'000),snapshot,i,batch,true);
      }
    }
    Simulator::Schedule(NanoSeconds(faultNs),event);
    Simulator::Stop(MilliSeconds(600)); Simulator::Run(); reports.close();
    std::ofstream truth(out+"/truth.json");
    truth << "{\"fault_time_ns\":" << faultNs << ",\"fault_path\":\"2/A\",\"scenario\":\""
          << scenario << "\",\"observation_end_ns\":600000000,\"reports_offered\":"
          << offeredReports << ",\"reports_dropped\":" << droppedReports << ",\"paths\":[";
    for (uint32_t i=0; i<8; ++i) {
      uint64_t tx=0,rx=0; for (auto x:paths[i].tx) tx+=x.second; for (auto x:paths[i].rx) rx+=x.second;
      truth << (i ? "," : "") << "{\"path\":\"" << i/2 << '/' << (i%2 ? 'B':'A')
            << "\",\"sent\":" << tx << ",\"received\":" << rx
            << ",\"duplicates\":" << paths[i].duplicates << ",\"send_rejected\":" << paths[i].rejected
            << ",\"permanent_drops\":" << paths[i].model->permanentDrops
            << ",\"deferred\":" << paths[i].model->deferred
            << ",\"wire_packets\":" << paths[i].wirePackets << ",\"wire_bytes\":" << paths[i].wireBytes
            << ",\"min_wire_bytes\":" << paths[i].minWire << ",\"max_wire_bytes\":" << paths[i].maxWire
            << ",\"background_sent\":" << paths[i].backgroundSent << "}";
    }
    truth << "]}\n"; truth.close(); Simulator::Destroy(); return 0;
  } catch(const std::exception& e) { std::cerr << "M8_ERROR " << e.what() << '\n'; return 2; }
}
