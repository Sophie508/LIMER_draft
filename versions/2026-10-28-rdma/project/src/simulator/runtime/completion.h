#pragma once
namespace limer { namespace engine {
static void FinalAck(uint64_t id){
 auto r=routes.at(id);auto& c=chunks.at(r.chunk);
 if(c.epoch!=r.epoch||c.done)throw std::logic_error("late route completion");
 Progress(c,ChunkBytes,id);c.done=true;PeerEvent("DONE",c,id);
 Reserve(routes.at(id),false);--active[c.src];++outDone[c.src];++inDone[c.dst];++finished;
 if(Idle(c.src)&&!idleAt[c.src])idleAt[c.src]=PeerNow();if(Idle(c.dst)&&!idleAt[c.dst])idleAt[c.dst]=PeerNow();
 // A rescued suffix is not a fresh B-prime bandwidth sample.
 unsigned slot=r.relay?2:c.lane;
 if(!c.migrated)rates[c.src][slot]=r.length*8e9/std::max(uint64_t(1),PeerNow()-r.started);
 routes.erase(id);
 if(finished==16*phaseChunks){++phase;if(phase==phases){jobDone=PeerNow();return;}Simulator::Schedule(NanoSeconds(1),&StartPhase);}
 else Simulator::ScheduleWithContext(c.src,NanoSeconds(1),&Pump,c.src);
}

}}
