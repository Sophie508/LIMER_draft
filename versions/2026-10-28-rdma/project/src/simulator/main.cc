// LIMER: standalone dual-plane performance-recovery simulator.
#include <array>
#include <memory>
#include <iomanip>
#include "limer/network/bootstrap.h"
#include "limer/control/channel.h"
#include "limer/detection/observer.h"
#include "limer/detection/probe_budget.h"
#include "limer/detection/service_detector.h"
#include "limer/recovery/benefit_policy.h"
#include "limer/experiment/faults.h"
#include "limer/runtime/state.h"
#include "limer/runtime/declarations.h"
#include "limer/telemetry/events.h"
#include "limer/recovery/resources.h"
#include "limer/detection/spacing.h"
#include "limer/transport/rdma.h"
#include "limer/runtime/completion.h"
#include "limer/recovery/decision.h"
#include "limer/recovery/proxy.h"
#include "limer/scheduling/dispatcher.h"
#include "limer/detection/monitor.h"

using namespace limer::engine;
int main(int argc,char** argv){try{
 if(argc!=9&&argc!=13)throw std::runtime_error("topology config out method rounds horizon fault chunks-per-phase [detector policy canary-period canary-bytes]");output=argv[3];method=argv[4];phases=std::stoul(argv[5])*30;horizon=std::stoull(argv[6]);
 if(argc==13){std::string dm=argv[9],pm=argv[10];if(dm!="legacy"&&dm!="service")throw std::runtime_error("detector mode");if(pm!="always"&&pm!="benefit")throw std::runtime_error("policy mode");serviceMode=dm=="service";benefitMode=pm=="benefit";canaryPeriod=std::stoull(argv[11]);canaryBytes=std::stoull(argv[12]);if(canaryPeriod<100000||canaryBytes!=65536)throw std::runtime_error("canary geometry");}
 phaseChunks=std::stoul(argv[8]);if(phaseChunks<16||phaseChunks%2)throw std::runtime_error("even phase chunks >=16 required");Bytes=uint64_t(phaseChunks)*ChunkBytes;
 feedback=method=="G10"||method=="G11";proxy=method=="G01"||method=="G11";
 if(method!="G00"&&method!="G10"&&!proxy)throw std::runtime_error("unsupported method");
 GlobalValue::Bind("SimulatorImplementationType",StringValue("ns3::DefaultSimulatorImpl"));
 if(InitializeNetwork(argv[1],argv[2])||node_num-switch_num-nvswitch_num!=16||gpus_per_server!=4)throw std::runtime_error("true16 required");
 events.open(output+"/logical_events.csv");events<<"timestamp_ns,event,chunk_id,phase,src,dst,offset,length,acked,epoch,lane,route\n";
 legsLog.open(output+"/leg_events.csv");legsLog<<"timestamp_ns,event,route,tag,index,src,dst,nic,length\n";
 peers.open(output+"/peer_events.csv");peers<<"timestamp_ns,event,route,chunk,phase,src,dst,helper_src,helper_dst,rail,relay,probe,length\n";
 wireLog.open(output+"/wire_events.csv");wireLog<<"timestamp_ns,route,tag,src,dst,nic,probe,relay,sequence,wire_bytes,retransmission\n";
 packets.open(output+"/packet_events.csv");packets<<"timestamp_ns,event,path_id,probe,batch,sequence,attempt_or_port,offset,accepted,payload_bytes\n";
 observations.open(output+"/observations.jsonl");alarms.open(output+"/detector_events.csv");alarms<<"timestamp_ns,path_id,signal,alarm_origin\n";
 controls.open(output+"/control_events.csv");controls<<"sent_ns,arrival_ns,event,rank,phase,version,wire_bytes\n";
 statusLog.open(output+"/phase_events.csv");statusLog<<"timestamp_ns,event,phase\n";
 serviceEvents.open(output+"/service_events.csv");serviceEvents<<"timestamp_ns,event,path_id,token,bytes,last_progress_ns,spacing_ns,sample_count\n";
 serviceAlarms.open(output+"/service_alarms.csv");serviceAlarms<<"timestamp_ns,path_id,signal\n";
 serviceDecisions.open(output+"/service_decisions.jsonl");policyLog.open(output+"/policy_decisions.jsonl");policyLog<<std::setprecision(17);
 detector.open(output+"/m13_alarms.jsonl",output+"/m13_baseline.jsonl");detector.onAlarm=Alarm;
 for(unsigned s=0;s<16;++s){ports[s]=10000;auto hw=n.Get(s)->GetObject<RdmaDriver>()->m_rdma;hw->m_qpCompleteCallback=MakeCallback(&Completed);hw->m_sendCompleteCallback=MakeCallback(&Sent);}
 limer_experiment::Load(argv[7],output+"/fault_events.csv",n);
 Simulator::Schedule(MilliSeconds(1),&StartPhase);
 if(serviceMode){Simulator::Schedule(MilliSeconds(1),&ServiceTick);if(spacingEnd<horizon)Simulator::Schedule(NanoSeconds(spacingEnd),&ReceiverSpacingTick);}else{Simulator::Schedule(MilliSeconds(1),&ProbeTick);Simulator::Schedule(MilliSeconds(10),&ObserveTick);}
 Simulator::Schedule(NanoSeconds(1050000),&Tick);
 Simulator::Stop(NanoSeconds(horizon));Simulator::Run();
 std::ofstream status(output+"/run_status.json");status<<"{\"detector_mode\":\""<<(serviceMode?"service":"legacy")<<"\",\"policy_mode\":\""<<(benefitMode?"benefit":"always")<<"\",\"monitor_end_ns\":"<<PeerNow()<<",\"status\":\""<<(jobDone?"completed":"task_unfinished")<<"\",\"method\":\""<<method<<"\",\"job_done_ns\":"<<jobDone<<",\"horizon_ns\":"<<horizon<<",\"world_size\":16,\"physical_planes\":2,\"phases_done\":"<<phase<<",\"phases_expected\":"<<phases<<",\"chunks_per_phase\":"<<phaseChunks<<",\"proxy_chunks\":"<<proxyChunks<<",\"new_proxy_chunks\":"<<newProxyChunks<<",\"rescued_chunks\":"<<rescuedChunks<<",\"health_probe_routes\":"<<probeRoutes<<",\"network_wire_bytes\":"<<networkWire<<",\"local_wire_bytes\":"<<localWire<<",\"probe_wire_bytes\":"<<probeWire<<",\"relay_wire_bytes\":"<<rescueWire<<",\"retransmission_wire_bytes\":"<<retransWire<<",\"control_wire_bytes\":"<<control.wire_bytes<<",\"stale_acks\":"<<staleAcks<<",\"extra_rto\":false,\"scope\":\""<<(serviceMode?"service-driven persistent B-prime replacement v2":"M13-driven persistent B-prime replacement v1")<<"\"}\n";
 Simulator::Destroy();return jobDone?0:2;
 }catch(const std::exception& e){std::cerr<<e.what()<<std::endl;return 1;}}
