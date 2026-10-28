#pragma once
// Injector-only input and state. Observers and the path manager never receive it.
#include <fstream>
#include <sstream>
namespace limer_experiment {
static std::ofstream log;
class Loss : public ns3::ErrorModel {
 public:
  double probability=0;
  ns3::Ptr<ns3::UniformRandomVariable> random=ns3::CreateObject<ns3::UniformRandomVariable>();
  uint64_t seen=0,dropped=0;
 private:
  bool DoCorrupt(ns3::Ptr<ns3::Packet>) override {++seen;bool drop=random->GetValue()<probability;if(drop) ++dropped;return drop;}
  void DoReset() override {}
};
static std::vector<ns3::Ptr<Loss>> losses;
static void Apply(ns3::Ptr<ns3::QbbNetDevice> dev,ns3::Ptr<Loss> loss,double service,double probability) {
  dev->SetLimerServiceFraction(service);loss->probability=probability;
  log<<ns3::Simulator::Now().GetNanoSeconds()<<','<<dev->GetNode()->GetId()<<','<<dev->GetIfIndex()<<','<<service<<','<<probability<<'\n';
}
static void SetDelay(ns3::Ptr<ns3::Channel> channel,uint64_t delay){channel->SetAttribute("Delay",ns3::TimeValue(ns3::NanoSeconds(delay)));}
static void Load(const std::string& input,const std::string& output,const ns3::NodeContainer& nodes) {
  log.open(output);log<<"timestamp_ns,node,nic,service_fraction,packet_loss\n";
  std::ifstream in(input);uint64_t start,end,seed;unsigned node;double service,probability;
  if(!in) throw std::runtime_error("missing injector input");
  std::string line;while(std::getline(in,line)) {
    if(line.empty())continue;std::istringstream fields(line);uint64_t delay=0;
    if(!(fields>>start>>end>>node>>service>>probability>>seed))throw std::runtime_error("invalid fault record");fields>>delay;
    if(node>=16||end<=start||service<=0||service>1||probability<0||probability>1) throw std::runtime_error("invalid fault input");
    auto hw=nodes.Get(node)->GetObject<ns3::RdmaDriver>()->m_rdma;
    auto device=hw->m_nic[3].dev;auto channel=device->GetChannel();
    if(delay){ns3::TimeValue old;channel->GetAttribute("Delay",old);
      ns3::Simulator::Schedule(ns3::NanoSeconds(start),&SetDelay,channel,delay);
      ns3::Simulator::Schedule(ns3::NanoSeconds(end),&SetDelay,channel,uint64_t(old.Get().GetNanoSeconds()));}
    for(unsigned side=0;side<2;++side) {
      auto endpoint=ns3::DynamicCast<ns3::QbbNetDevice>(channel->GetDevice(side));
      auto loss=ns3::CreateObject<Loss>();loss->random->SetStream(seed*2+side);losses.push_back(loss);
      endpoint->SetReceiveErrorModel(loss);
      ns3::Simulator::ScheduleWithContext(endpoint->GetNode()->GetId(),ns3::NanoSeconds(start),&Apply,endpoint,loss,service,probability);
      ns3::Simulator::ScheduleWithContext(endpoint->GetNode()->GetId(),ns3::NanoSeconds(end),&Apply,endpoint,loss,1.0,0.0);
    }
  }
  if(!in.eof()) throw std::runtime_error("malformed fault input");
}
}
