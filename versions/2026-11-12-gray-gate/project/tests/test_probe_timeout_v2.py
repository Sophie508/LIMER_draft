"""Production probe cancellation preserves data routes and late wire accounting."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
from test_helper_lease_v2 import function

ROOT=Path(__file__).resolve().parents[1]


class ProbeTimeoutV2Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'),'requires C++')
    def test_each_leg_health_reply_and_phase_retirement(self):
        state=(ROOT/'src/simulator/runtime/state.h').read_text()
        structures=state[state.index('struct HelperSnapshot'):state.index('static std::array<Binding,16> binding;')]
        proxy=(ROOT/'src/simulator/recovery/proxy.h').read_text()
        rdma=(ROOT/'src/simulator/transport/rdma.h').read_text()
        source=r'''
#include <array>
#include <vector>
#include <map>
#include <set>
#include <string>
#include <sstream>
#include <stdexcept>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <memory>
#include <functional>
template<class T>using Ptr=std::shared_ptr<T>;
static const unsigned LIMER_RDMA_QP_ERROR=9;
struct RdmaQueuePair{uint64_t tag=99;unsigned m_limerState=0,m_activeNicIdx=3;
 uint64_t GetTag(){return tag;}};
struct Hardware{unsigned cancelled=0,deleted=0,added=0;
 void CancelRto(Ptr<RdmaQueuePair>){++cancelled;}void DeleteQueuePair(Ptr<RdmaQueuePair>){++deleted;}
 template<class... Args>void AddQueuePair(Args...){++added;}
 Ptr<RdmaQueuePair> GetQp(unsigned,unsigned,unsigned){return std::make_shared<RdmaQueuePair>();}};
struct RdmaDriver{Ptr<Hardware> m_rdma=std::make_shared<Hardware>();};
struct Node{Ptr<RdmaDriver> driver=std::make_shared<RdmaDriver>();
 template<class T>Ptr<T> GetObject(){return driver;}};
struct Nodes{std::array<Ptr<Node>,16> all;Nodes(){for(auto& x:all)x=std::make_shared<Node>();}
 Ptr<Node> Get(unsigned x){return all[x];}}n;
struct Address{unsigned Get(){return 0;}};std::array<Address,16> serverAddress;
struct Route{uint64_t id=77,chunk=0,epoch=0,base=0,length=65536,started=0,measurement=0,bindingVersion=10;
 unsigned src=0,dst=4,hs=1,hd=5,rail=1,index=0,p=2;bool relay=true,probe=true,reserved=true,service=false;
 std::array<double,3> legNs{};};
struct Leg{uint64_t tag,route,started;unsigned src,dst,nic,index;Ptr<RdmaQueuePair> qp;};
std::map<uint64_t,Route> routes,abortedProbes;std::map<uint64_t,Leg> legs,abortedProbeLegs;
'''+structures+r'''
std::array<Binding,16> binding;
bool benefitV2=true,benefitMode=true,serviceMode=true,sharedHelpers=true,pipelined=true;
unsigned phase=2,phases=4,phaseChunks=16,released=0,releaseRequests=0,configured=0,staleAcks=0,probeRoutes=0;
const uint64_t Ttl=20000000,ChunkBytes=65536;uint64_t horizon=20000001;bool proxy=false;
std::array<bool,16> m13{};double rates[16][3]{},credits[16][3]{};unsigned launches[16][3]{};
uint64_t now=20000000,serial=100;
std::array<unsigned,16> outDone{},ports{};
std::ostringstream legsLog,controls,wireLog,serviceEvents;
uint64_t networkWire=0,localWire=0,probeWire=0,rescueWire=0,retransWire=0;
std::set<std::pair<uint64_t,unsigned>> sentWire;
struct Detector{void retransmit(unsigned,uint64_t,uint64_t){}}serviceDetector;
uint64_t PeerNow(){return now;}uint64_t NanoSeconds(uint64_t t){return t;}
unsigned Dest(unsigned s){return s<12?s+4:(s+1)%4;}
unsigned Key(unsigned s,unsigned d,unsigned rail){return (s*16+d)*3+rail;}
struct Simulator{template<class... Args>static void Schedule(Args...){}
 template<class... Args>static void ScheduleWithContext(Args...){} };
template<class T>T MakeCallback(T f){return f;}
void Noop(){}void Pump(unsigned){}
void Reserve(Route& r,bool add){assert(!add&&r.reserved);r.reserved=false;++released;}
void ReleaseLendingV2(unsigned){++releaseRequests;}
void Configure(unsigned){++configured;}
bool Idle(unsigned){return true;}bool Capacity(const Route&){return false;}
bool RequestLendingV2(unsigned){return false;}bool RequestLending(unsigned){return false;}
bool BenefitAllows(unsigned,const char*){return true;}
void CollectHelperReports(unsigned){++configured;}
void Forget(uint64_t tag){legs.erase(tag);}
void ServiceCompleted(const Route&){}
void ReleaseDelivered(Route&){throw std::logic_error("payload callback invoked");}
void FinalAck(uint64_t){throw std::logic_error("payload completion invoked");}
static void StartLeg(uint64_t);static void HealthDone(uint64_t);
uint64_t Message(const char*,unsigned,uint64_t){return now+1007680;}
std::vector<std::array<unsigned,3>> Edges(const Route& r){return {{r.src,r.hs,1},{r.hs,r.hd,3},{r.hd,r.dst,1}};}
'''+ '\n'.join([function(proxy,'static void AbortProbeV2('),
               function(proxy,'static void HealthDone('),
               function(rdma,'static void Completed('),
               function(rdma,'static void StartLeg('),
               function(rdma,'extern "C" void limer_joint_wire_tx('),
               function(proxy,'static void Commit('),function(proxy,'static void Tick(')])+r'''
int main(){
 // Expired temporary health releases; configured refresh keeps participants.
 binding[0].p=phase;binding[0].version=10;binding[0].lending=true;binding[0].pending=true;
 binding[0].health=0;now=Ttl+1;unsigned initial=releaseRequests;
 Commit(0,phase,10);assert(releaseRequests==initial+1&&!binding[0].pending);
 binding[0].configured=true;binding[0].pending=true;initial=releaseRequests;
 Commit(0,phase,10);assert(releaseRequests==initial&&!binding[0].pending);
 // Completed owners release before Tick's ready/pending/outDone early exits.
 binding[0].ready=true;binding[0].pending=true;binding[0].health=now;
 outDone[0]=phaseChunks;Tick();assert(releaseRequests==initial+1);outDone[0]=0;
 // Test timeouts with each physical leg active and with only health reply pending.
 for(unsigned stage=0;stage<4;++stage){
  routes.clear();legs.clear();abortedProbes.clear();abortedProbeLegs.clear();
  Route probe;probe.index=std::min(stage,2u);routes[77]=probe;
  Route payload;payload.id=88;payload.probe=false;routes[88]=payload;
  auto qp=std::make_shared<RdmaQueuePair>();qp->tag=99+stage;
  if(stage<3)legs[qp->tag]={qp->tag,77,0,1,5,3,stage,qp};
  binding[0]=Binding{};binding[0].p=phase;binding[0].version=10;
  binding[0].lending=true;binding[0].pending=true;
  unsigned prior=released,requests=releaseRequests;
  AbortProbeV2(77);
  assert(!routes.count(77)&&routes.count(88)&&routes[88].reserved);
  assert(released==prior+1&&releaseRequests==requests+1);
  assert(!binding[0].pending&&abortedProbes.count(77));
  if(stage<3){
   assert(qp->m_limerState==LIMER_RDMA_QP_ERROR&&abortedProbeLegs.count(qp->tag));
   Completed(qp); // The callback is ignored only for an explicitly aborted tag.
   uint64_t oldWire=networkWire;limer_joint_wire_tx(qp.get(),0,1048);
   assert(networkWire==oldWire+1048); // Late issued traffic remains charged.
  }
  auto before=configured;StartLeg(77);HealthDone(77);assert(configured==before);
  AbortProbeV2(77);assert(released==prior+1); // No double release.
 }
 // Active bindings retain participants when only a refresh probe times out.
 routes[77]=Route{};binding[0].configured=true;binding[0].pending=true;
 unsigned requests=releaseRequests;AbortProbeV2(77);assert(releaseRequests==requests);
 // The same active lease is released once the source has finished its work.
 routes[77]=Route{};outDone[0]=phaseChunks;AbortProbeV2(77);assert(releaseRequests==requests+1);
 // Old-phase probe reservation is retired without touching a new-phase binding.
 routes[77]=Route{};++phase;binding[0].p=phase;binding[0].version=1000;
 requests=releaseRequests;AbortProbeV2(77);assert(releaseRequests==requests);
 // Arbitrary missing route IDs still surface a bug; guards are not blanket ignores.
 bool rejected=false;try{HealthDone(123456);}catch(const std::out_of_range&){rejected=true;}assert(rejected);
 assert(controls.str().find("PROBE_ABORT")!=std::string::npos);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp=Path(tmp)/'probe.cc';binary=Path(tmp)/'probe';cpp.write_text(source)
            build=subprocess.run(['c++','-std=c++14',str(cpp),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
