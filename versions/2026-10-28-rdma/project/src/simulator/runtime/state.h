#pragma once
namespace limer { namespace engine {
static uint64_t PeerNow(){return Simulator::Now().GetNanoSeconds();}
static unsigned Dest(unsigned s){return s<12?s+4:(s+1)%4;}
static unsigned Key(unsigned s,unsigned d,unsigned rail){return (s*16+d)*3+rail;}
static std::string output,method;
static bool feedback=false,proxy=false;
static bool serviceMode=false,benefitMode=false;
static uint64_t canaryPeriod=2000000,canaryBytes=65536;
static limer::detection::ServiceDetector serviceDetector;
static std::ofstream serviceEvents,serviceAlarms,serviceDecisions,policyLog;
static std::map<unsigned,std::deque<std::pair<uint64_t,uint64_t>>> ackSamples;
static std::map<unsigned,std::pair<uint64_t,uint64_t>> canarySamples;
static unsigned phase=0,phases=60,finished=0,phaseChunks=64;
static uint64_t horizon=500000000,jobDone=0,serial=0,phaseStart=0;
static uint64_t Bytes=4194304;
static constexpr uint64_t ChunkBytes=65536,Ttl=20000000;
static limer::control::ControlFifo control;
static BusinessObserver detector;
static std::ofstream events,legsLog,wireLog,packets,observations,alarms,controls,peers,statusLog;
static uint64_t networkWire=0,localWire=0,probeWire=0,rescueWire=0,retransWire=0;
static unsigned staleAcks=0,proxyChunks=0,probeRoutes=0,newProxyChunks=0,rescuedChunks=0;
struct PeerChunk {uint64_t id,offset,acked=0,epoch=0,allocated=0;unsigned src,dst,p,lane;bool done=false,migrated=false;uint64_t lastProgress=0;};
struct Route {uint64_t id=0,chunk=0,epoch=0,base=0,length=0;unsigned src=0,dst=0,hs=0,hd=0,rail=1,index=0,p=0;
 bool relay=false,probe=false,reserved=false,service=false;uint64_t started=0,measurement=0,bindingVersion=0;
 std::array<double,3> legNs{{0,0,0}};};
struct Leg {uint64_t tag,route,started;unsigned src,dst,nic,index;Ptr<RdmaQueuePair> qp;};
struct Wire {unsigned path,batch;bool probe;uint64_t seq,submitted;};
struct Count {uint64_t next[2]{},totalTx[2]{},totalRx[2]{};std::map<unsigned,uint64_t> tx[2],rx[2];GapTracker gaps[2];};
static std::map<uint64_t,PeerChunk> chunks;
static std::map<uint64_t,Route> routes;
static std::map<uint64_t,Leg> legs;
static std::map<unsigned,Count> counts;
static std::map<std::pair<uint64_t,uint64_t>,Wire> identities;
static std::set<std::pair<uint64_t,unsigned>> sentWire;
static std::array<std::vector<uint64_t>,16> cohort;
static std::array<unsigned,16> ports{},active{},outDone{},inDone{},turn{};
static std::array<uint64_t,16> offered{},aFinished{},idleAt{};
static uint64_t nextOffset[16][2]{};
static double rates[16][3]{},credits[16][3]{};
static unsigned launches[16][3]{},tx[16][5]{},rx[16][5]{},buffers[16]{};
struct Binding {bool pending=false,ready=false,configured=false,disabled=false;unsigned hs=0,hd=0,p=0;uint64_t health=0,version=0,alarm=0,activation=0,nextAttempt=0;
 std::array<double,3> probeLegNs{{0,0,0}};uint64_t probeBytes=0;};
static std::array<Binding,16> binding;
static std::array<bool,16> m13{};
static void Pump(unsigned);
static void StartPhase();
static void StartLeg(uint64_t);
static bool Idle(unsigned g){return outDone[g]==phaseChunks&&inDone[g]==phaseChunks;}

}}
