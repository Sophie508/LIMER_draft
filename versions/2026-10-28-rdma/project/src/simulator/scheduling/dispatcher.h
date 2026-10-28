#pragma once
namespace limer { namespace engine {
static void Pump(unsigned src){
 if(phase>=phases)return;
 // Migrate existing B chunks before offering future B work. Prefixes survive cancellation.
 if(binding[src].ready){
  for(auto id:cohort[src]){auto& c=chunks.at(id);if(c.done||c.epoch||c.lane!=1||!CanLaunch(src,1,true))continue;
   std::vector<uint64_t> old;
   for(const auto& it:routes)if(it.second.chunk==id)old.push_back(it.first);
   for(auto rid:old){
    std::vector<uint64_t> tags;for(const auto& it:legs)if(it.second.route==rid)tags.push_back(it.first);
    for(auto tag:tags){auto l=legs.at(tag);auto hw=n.Get(l.src)->GetObject<RdmaDriver>()->m_rdma;hw->CancelRto(l.qp);l.qp->m_limerState=LIMER_RDMA_QP_ERROR;hw->DeleteQueuePair(l.qp);
     legsLog<<PeerNow()<<",LEG_CANCEL,"<<rid<<','<<tag<<','<<l.index<<','<<l.src<<','<<l.dst<<','<<l.nic<<','<<routes.at(rid).length<<'\n';Forget(tag);}
    Reserve(routes.at(rid),false);routes.erase(rid);
   }
   ++c.epoch;c.migrated=true;++proxyChunks;++rescuedChunks;PeerEvent("MIGRATE",c);Launch(c,true);
  }
 }
 while(offered[src]<Bytes&&active[src]<8){
  std::vector<unsigned> available;
  for(unsigned lane=0;lane<2;++lane){
   bool relay=lane==1&&binding[src].disabled;
   if(!feedback&&nextOffset[src][lane]>=Bytes)continue;
   if(CanLaunch(src,lane,relay))available.push_back(lane);
  }
  if(available.empty())break;unsigned lane=available.front();
  if(!feedback){if(std::find(available.begin(),available.end(),turn[src])!=available.end())lane=turn[src];turn[src]=1-lane;}
  else{
   bool explore=false;for(auto l:available){unsigned slot=l==1&&binding[src].disabled?2:l;if(!launches[src][slot]){lane=l;explore=true;break;}}
   if(!explore){double sum=0;for(auto l:available)sum+=rates[src][l==1&&binding[src].disabled?2:l];if(sum<=0)break;
    double best=-1e300;for(auto l:available){unsigned slot=l==1&&binding[src].disabled?2:l;credits[src][slot]+=ChunkBytes*rates[src][slot]/sum;if(credits[src][slot]>best){best=credits[src][slot];lane=l;}}
    credits[src][lane==1&&binding[src].disabled?2:lane]-=ChunkBytes;
   }
  }
  uint64_t offset=feedback?offered[src]:nextOffset[src][lane];if(!feedback)nextOffset[src][lane]+=2*ChunkBytes;
  PeerChunk c{++serial,offset,0,0,PeerNow(),src,Dest(src),phase,lane,false};bool relay=lane==1&&binding[src].disabled;
  if(relay){c.epoch=1;++proxyChunks;++newProxyChunks;}chunks.emplace(c.id,c);cohort[src].push_back(c.id);offered[src]+=ChunkBytes;++active[src];++launches[src][relay?2:lane];
  PeerEvent("ALLOC",c);Launch(chunks.at(c.id),relay);
 }
}

static void StartPhase(){
 phaseStart=PeerNow();finished=0;offered.fill(0);active.fill(0);outDone.fill(0);inDone.fill(0);aFinished.fill(0);idleAt.fill(0);turn.fill(0);
 for(unsigned s=0;s<16;++s){cohort[s].clear();nextOffset[s][0]=0;nextOffset[s][1]=ChunkBytes;binding[s].ready=false;binding[s].pending=false;
  // One bounded fresh B-prime exploration per phase after idle helpers become ready.
  if(binding[s].disabled)launches[s][2]=0;}
 statusLog<<PeerNow()<<",PHASE,"<<phase<<'\n';for(unsigned s=0;s<16;++s)Simulator::ScheduleWithContext(s,NanoSeconds(0),&Pump,s);
}

}}
