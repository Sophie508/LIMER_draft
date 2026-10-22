// M13 class-separated receiver observations; isolated UDP/application model.
#include "ns3/core-module.h"
#include "ns3/network-module.h"
#include "ns3/internet-module.h"
#include "ns3/point-to-point-module.h"
#include <array>
#include <iomanip>
#include <sstream>
#include <cmath>
#include <fstream>
#include <map>
#include <set>
#include <stdexcept>

using namespace ns3;
#include "business_observer.h"
static BusinessObserver observer;

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
  bool dataOnly=false;
  Time extraDelay = Seconds(0);
  uint64_t permanentDrops = 0, deferred = 0;
private:
  bool DoCorrupt(Ptr<Packet> p) override {
    DeferredTag tag;
    if (p->RemovePacketTag(tag)) return false;
    if (random->GetValue() < loss && (!dataOnly || p->GetSize()>128)) { ++permanentDrops; return true; }
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
  std::map<uint32_t,uint64_t> tx, rx, dataTx, dataRx, probeTx, probeRx;
  GapTracker dataGap,probeGap;
  Ptr<UniformRandomVariable> applicationRandom;
  double applicationLoss=0,applicationDefer=0;
  Time applicationDelay=Seconds(0);
  uint64_t applicationDrops=0,applicationDeferred=0;
  std::set<uint64_t> seen;
  uint64_t nextData=0,nextProbe=0, duplicates = 0, rejected = 0, backgroundSent = 0;
  uint64_t wirePackets = 0, wireBytes = 0, probeWire = 0;
  uint64_t dataSent=0, dataReceived=0, probeSent=0, probeReceived=0;
  uint32_t minWire = UINT32_MAX, maxWire = 0;
};

static std::array<Path,8> paths;
static std::ofstream reports, offers, samples,packetEvents;
static std::string scenario = "nominal", out = ".";
static double capacityMbps = 100, offeredMbps = 80, lossRate = .005;
static double reportRateMbps = 10, reportDelayMs = 1, reportLoss = 0;
static double probePps=35000;
static uint32_t reportCopies=3;
static double faultTimeMs = 50, observationEndMs=600;
static int64_t faultNs = 50'000'000;
static uint32_t runId = 1;
static Time reportFree = Seconds(0);
static Ptr<UniformRandomVariable> reportRandom;
static uint64_t offeredReports = 0, droppedReports = 0;
static constexpr int64_t periodNs = 10'000'000;

static void wireSend(uint32_t i, Ptr<const Packet> p) {
  ++paths[i].wirePackets; paths[i].wireBytes += p->GetSize();
  if(p->GetSize()==64) ++paths[i].probeWire;
  paths[i].minWire = std::min(paths[i].minWire, p->GetSize());
  paths[i].maxWire = std::max(paths[i].maxWire, p->GetSize());
}

// The modeled report wire encoding is 20 IPv4 + 8 UDP + 68 payload bytes.
// Payload: identifiers/version 4, batch 4, class/total counters 24, sample 8,
// gap counts 8, gap ages 16, reserved 4. Arrival is collector-local, not transmitted.
static void writeObservation(std::ostream& stream,const BusinessObservation& r,bool arrival) {
  auto& b=r.base;
  stream << "{\"path\":\"" << b.path/2 << '/' << (b.path%2?'B':'A')
    << "\",\"batch\":" << b.batch << ",\"side\":\"" << (b.rx?"rx":"tx")
    << "\",\"count\":" << b.count << ",\"data_count\":" << r.data << ",\"probe_count\":" << r.probe
    << ",\"sample_t_ns\":" << b.sample << ",\"guard_ns\":" << r.guard
    << ",\"data_gaps\":" << r.dataGaps << ",\"probe_gaps\":" << r.probeGaps
    << ",\"data_gap_age_ns\":" << r.dataAge << ",\"probe_gap_age_ns\":" << r.probeAge;
  if(arrival) stream << ",\"arrival_t_ns\":" << b.arrival;
  stream << "}\n";
}
static void deliverReport(BusinessObservation r) {
  r.base.arrival=Simulator::Now().GetNanoSeconds();
  writeObservation(reports,r,true);observer.observe(r);
}
static uint64_t sampleCount(std::map<uint32_t,uint64_t>& counts,uint32_t batch,int64_t guard) {
  if(guard!=10'000'000) return counts[batch];
  uint64_t total=0;for(auto c:counts) total+=c.second;return total;
}
static std::string encodePayload(const BusinessObservation& r) {
  std::array<uint8_t,68> bytes{};size_t offset=0;
  auto put=[&](uint64_t value,unsigned n) {
    if(n<8 && value>=(uint64_t(1)<<(8*n))) throw std::runtime_error("report field overflow");
    for(unsigned j=n;j>0;--j) bytes[offset++]=uint8_t(value>>(8*(j-1)));
  };
  put(r.base.path,1);put(r.base.rx,1);put(r.guard==0?0:(r.guard==10'000'000?1:2),1);put(1,1);
  put(r.base.batch,4);put(r.base.count,8);put(r.data,8);put(r.probe,8);put(r.base.sample,8);
  put(r.dataGaps,4);put(r.probeGaps,4);put(r.dataAge,8);put(r.probeAge,8);put(0,4);
  if(offset!=68) throw std::runtime_error("report payload size mismatch");
  std::ostringstream encoded;encoded<<std::hex<<std::setfill('0');
  for(auto byte:bytes) encoded<<std::setw(2)<<unsigned(byte);
  return encoded.str();
}
static void snapshot(uint32_t i,uint32_t batch,bool atReceiver,int64_t guardNs) {
  auto& p=paths[i];int64_t sampleNs=Simulator::Now().GetNanoSeconds();
  uint64_t data=sampleCount(atReceiver?p.dataRx:p.dataTx,batch,guardNs);
  uint64_t probe=sampleCount(atReceiver?p.probeRx:p.probeTx,batch,guardNs);
  BusinessObservation r{{int(i),batch,atReceiver,data+probe,sampleNs,0},data,probe,guardNs,
    atReceiver?p.dataGap.holes.size():0,atReceiver?p.probeGap.holes.size():0,
    atReceiver?p.dataGap.age(sampleNs):0,atReceiver?p.probeGap.age(sampleNs):0};
  writeObservation(samples,r,false);
  packetEvents<<"snapshot,"<<i<<','<<batch<<','<<atReceiver<<','<<guardNs<<','<<sampleNs<<'\n';
  std::string payload=encodePayload(r);
  for(uint32_t copy=0;copy<reportCopies;++copy) {
    Time start=std::max(Simulator::Now(),reportFree);
    reportFree=start+NanoSeconds(int64_t(std::ceil(768.0/reportRateMbps*1000)));
    ++offeredReports;bool lost=reportRandom->GetValue()<reportLoss;
    offers << "{\"path\":\"" << i/2 << '/' << (i%2?'B':'A')
      << "\",\"batch\":" << batch << ",\"side\":\"" << (atReceiver?"rx":"tx")
      << "\",\"guard_ns\":" << guardNs << ",\"copy\":" << copy << ",\"sample_t_ns\":" << sampleNs
      << ",\"start_ns\":" << start.GetNanoSeconds() << ",\"end_ns\":" << reportFree.GetNanoSeconds()
      << ",\"lost\":" << (lost?"true":"false") << ",\"payload_hex\":\"" << payload << "\"}\n";
    if(lost) {++droppedReports;continue;}
    Simulator::Schedule(reportFree+MilliSeconds(reportDelayMs)-Simulator::Now(),deliverReport,r);
  }
}
static void acceptPacket(uint32_t i,BatchHeader h) {
  auto& p=paths[i];bool probe=h.sequence>>63;
  if(!p.seen.insert(h.sequence).second) {++p.duplicates;return;}
  ++p.rx[h.batch];int64_t now=Simulator::Now().GetNanoSeconds();
  packetEvents<<"rx,"<<i<<','<<h.batch<<','<<probe<<','<<(h.sequence&~(uint64_t(1)<<63))<<','<<now<<'\n';
  if(probe) {++p.probeRx[h.batch];++p.probeReceived;p.probeGap.receive(h.sequence&~(uint64_t(1)<<63),now);}
  else {++p.dataRx[h.batch];++p.dataReceived;p.dataGap.receive(h.sequence,now);}
}
static void receive(uint32_t i,Ptr<Socket> socket) {
  while(Ptr<Packet> packet=socket->Recv()) {
    BatchHeader h;
    if(packet->RemoveHeader(h)!=12 || packet->GetSize()!=((h.sequence>>63)?10:1446))
      throw std::runtime_error("corrupt class payload/header");
    auto& p=paths[i];
    // Fault injection affects application arrivals; observation reads only acceptPacket.
    if(!(h.sequence>>63)) {
      if(p.applicationRandom->GetValue()<p.applicationLoss) {++p.applicationDrops;continue;}
      if(p.applicationDelay.IsStrictlyPositive() && p.applicationRandom->GetValue()<p.applicationDefer) {
        ++p.applicationDeferred;Simulator::Schedule(p.applicationDelay,acceptPacket,i,h);continue;
      }
    }
    acceptPacket(i,h);
  }
}

static void sendData(uint32_t i) {
  int64_t ns = Simulator::Now().GetNanoSeconds();
  if (ns >= 250'000'000) return;
  bool paused = scenario == "pause" && ns >= faultNs && ns < faultNs+60'000'000;
  bool idle = scenario == "idle" && ns >= 40'000'000 && ns < 200'000'000;
  if (!paused && !idle) {
    Ptr<Packet> p = Create<Packet>(1446);
    BatchHeader h; h.batch = ns / periodNs; h.sequence = paths[i].nextData;
    p->AddHeader(h);
    if (paths[i].source->Send(p) == 1458) { ++paths[i].tx[h.batch]; ++paths[i].dataTx[h.batch]; ++paths[i].dataSent; ++paths[i].nextData;
      packetEvents<<"tx,"<<i<<','<<h.batch<<",0,"<<h.sequence<<','<<ns<<'\n'; }
    else ++paths[i].rejected;
  }
  Simulator::Schedule(NanoSeconds(int64_t(std::ceil(12'000.0 / offeredMbps * 1000))), sendData, i);
}

static void sendProbe(uint32_t i) {
  int64_t ns=Simulator::Now().GetNanoSeconds();
  if(ns>=250'000'000 || probePps==0) return;
  Ptr<Packet> p=Create<Packet>(10);
  BatchHeader h; h.batch=ns/periodNs; h.sequence=(paths[i].nextProbe) | (uint64_t(1)<<63);
  p->AddHeader(h);
  // Identical UDP socket, queue, route, receiver and error hook to data packets.
  if(paths[i].source->Send(p)==22) {++paths[i].tx[h.batch];++paths[i].probeTx[h.batch];++paths[i].probeSent;++paths[i].nextProbe;
    packetEvents<<"tx,"<<i<<','<<h.batch<<",1,"<<(h.sequence&~(uint64_t(1)<<63))<<','<<ns<<'\n';}
  else ++paths[i].rejected;
  Simulator::Schedule(NanoSeconds(int64_t(std::ceil(1e9/probePps))),sendProbe,i);
}

static void sendBackground(uint32_t i) {
  if (Simulator::Now() >= MilliSeconds(250)) return;
  if (paths[i].background->Send(Create<Packet>(1458)) == 1458) ++paths[i].backgroundSent;
  double rate = capacityMbps * (scenario == "overload" ? .8 : .1);
  Simulator::Schedule(NanoSeconds(int64_t(std::ceil(12'000.0 / rate * 1000))), sendBackground, i);
}

static void event() {
  if(scenario=="selective") {paths[4].model->loss=lossRate;paths[4].model->dataOnly=true;}
  if (scenario == "loss" || scenario == "sparse" || scenario == "idle") paths[4].model->loss = lossRate;
  if (scenario == "reorder40" || scenario == "reorder80" || scenario=="sparse_reorder40") {
    paths[4].model->extraDelay = MilliSeconds(scenario == "reorder80" ? 80 : 40);
    paths[4].model->deferFraction = scenario=="sparse_reorder40"?.005:.25;
  }
  if(scenario=="businessloss") paths[4].applicationLoss=lossRate;
  if(scenario=="processing40" || scenario=="processing80") {
    paths[4].applicationDelay=MilliSeconds(scenario=="processing40"?40:80);
    paths[4].applicationDefer=.25;
  }
  if (scenario == "congestion" || scenario == "overload") sendBackground(4);
}

int main(int argc, char** argv) {
  try {
    CommandLine cmd;
    cmd.AddValue("observationEndMs", "Drain observation/report tail", observationEndMs);
    cmd.AddValue("probePps", "Continuous same-path probe rate", probePps);
    cmd.AddValue("reportCopies", "Identical independently lost copies per sample", reportCopies);
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
    if (observationEndMs<600 || probePps<0 || reportCopies==0 || capacityMbps <= 0 || offeredMbps <= 0 || reportRateMbps <= 0 ||
        reportDelayMs < 0 || lossRate < 0 || lossRate > 1 || reportLoss < 0 || reportLoss > 1)
      throw std::runtime_error("invalid model parameters");
    RngSeedManager::SetSeed(20261010); RngSeedManager::SetRun(runId);
    faultNs = int64_t(std::llround(faultTimeMs*1e6));
    GlobalValue::Bind("SimulatorImplementationType", StringValue("ns3::DefaultSimulatorImpl"));
    reportRandom = CreateObject<UniformRandomVariable>(); reportRandom->SetStream(100);
    reports.open(out + "/reports.jsonl");
    offers.open(out+"/offers.jsonl"); samples.open(out+"/samples.jsonl");
    packetEvents.open(out+"/packet_events.csv");
    observer.open(out+"/alarms.jsonl",out+"/baseline_alarms.jsonl");
    if (!reports || !offers || !samples || !packetEvents) throw std::runtime_error("cannot open observations");
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
      paths[i].applicationRandom=CreateObject<UniformRandomVariable>();
      paths[i].applicationRandom->SetStream(200+i);
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
      if(probePps>0) Simulator::Schedule(MilliSeconds(1),sendProbe,i);
      for (uint32_t batch=0; batch<50; ++batch) {
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs),snapshot,i,batch,false,int64_t(0));
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs+10'000'000),snapshot,i,batch,false,int64_t(10'000'000));
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs+50'000'000),snapshot,i,batch,true,int64_t(50'000'000));
        Simulator::Schedule(NanoSeconds((batch+1)*periodNs+10'000'000),snapshot,i,batch,true,int64_t(10'000'000));
      }
    }
    Simulator::Schedule(NanoSeconds(faultNs),event);
    Simulator::Stop(MilliSeconds(observationEndMs)); Simulator::Run();
    observer.advance(int64_t(std::llround(observationEndMs*1e6))); reports.close(); offers.close(); samples.close();packetEvents.close();
    std::ofstream truth(out+"/truth.json");
    truth << "{\"fault_time_ns\":" << faultNs << ",\"fault_path\":\"2/A\",\"scenario\":\""
          << scenario << "\",\"run_id\":" << runId << ",\"observation_end_ns\":" << int64_t(std::llround(observationEndMs*1e6)) << ",\"reports_offered\":"
          << offeredReports << ",\"reports_dropped\":" << droppedReports << ",\"paths\":[";
    for (uint32_t i=0; i<8; ++i) {
      uint64_t tx=0,rx=0; for (auto x:paths[i].tx) tx+=x.second; for (auto x:paths[i].rx) rx+=x.second;
      truth << (i ? "," : "") << "{\"path\":\"" << i/2 << '/' << (i%2 ? 'B':'A')
            << "\",\"sent\":" << tx << ",\"received\":" << rx
            << ",\"duplicates\":" << paths[i].duplicates << ",\"send_rejected\":" << paths[i].rejected
            << ",\"network_loss\":" << paths[i].model->loss
            << ",\"network_data_only\":" << (paths[i].model->dataOnly?"true":"false")
            << ",\"network_defer_ns\":" << paths[i].model->extraDelay.GetNanoSeconds()
            << ",\"network_defer_fraction\":" << paths[i].model->deferFraction
            << ",\"application_loss\":" << paths[i].applicationLoss
            << ",\"application_defer_ns\":" << paths[i].applicationDelay.GetNanoSeconds()
            << ",\"application_defer_fraction\":" << paths[i].applicationDefer
            << ",\"permanent_drops\":" << paths[i].model->permanentDrops
            << ",\"deferred\":" << paths[i].model->deferred
            << ",\"application_drops\":" << paths[i].applicationDrops
            << ",\"application_deferred\":" << paths[i].applicationDeferred
            << ",\"wire_packets\":" << paths[i].wirePackets << ",\"wire_bytes\":" << paths[i].wireBytes
            << ",\"min_wire_bytes\":" << paths[i].minWire << ",\"max_wire_bytes\":" << paths[i].maxWire
            << ",\"background_sent\":" << paths[i].backgroundSent
            << ",\"data_sent\":" << paths[i].dataSent << ",\"data_received\":" << paths[i].dataReceived
            << ",\"probe_sent\":" << paths[i].probeSent << ",\"probe_received\":" << paths[i].probeReceived
            << ",\"probe_wire_packets\":" << paths[i].probeWire << "}";
    }
    truth << "]}\n"; truth.close(); Simulator::Destroy(); return 0;
  } catch(const std::exception& e) { std::cerr << "M13_ERROR " << e.what() << '\n'; return 2; }
}
