#pragma once
namespace limer { namespace engine {
static void Commit(unsigned src,unsigned p,uint64_t version){
 auto& b=binding[src];if(p!=phase||version!=b.version||(benefitV2&&b.releasing))return;
 if((!sharedHelpers&&(!Idle(b.hs)||!Idle(b.hd)))||PeerNow()<b.health||PeerNow()-b.health>Ttl){
  b.pending=false;if(benefitV2){b.nextAttempt=PeerNow()+5000000;if(!b.configured)ReleaseLendingV2(src);}return;}
 if(!m13[src])throw std::logic_error("replacement without M13 alarm");
 if(!b.configured&&benefitMode&&!BenefitAllows(src,"commit")){b.pending=false;b.nextAttempt=PeerNow()+5000000;if(benefitV2)ReleaseLendingV2(src);return;}
 b.ready=true;b.pending=false;b.configured=true;b.disabled=true;
 if(!b.activation){b.activation=PeerNow();rates[src][2]=0;credits[src][2]=0;launches[src][2]=0;}
 controls<<PeerNow()<<','<<PeerNow()<<",ACTIVATE,"<<src<<','<<phase<<','<<version<<",0\n";Pump(src);
}

static void SendCommit(unsigned src,unsigned p,uint64_t v){
 auto& b=binding[src];if(p!=phase||v!=b.version||(benefitV2&&b.releasing))return;
 uint64_t at=PeerNow();for(auto rank:{src,Dest(src),b.hs,b.hd})at=std::max(at,Message("COMMIT",rank,v));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&Commit,src,p,v);
}

static void SendReady(unsigned src,unsigned p,uint64_t v){
 auto& b=binding[src];if(p!=phase||v!=b.version||(benefitV2&&b.releasing))return;
 uint64_t at=PeerNow();for(auto rank:{src,Dest(src),b.hs,b.hd})at=std::max(at,Message("READY",rank,v));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&SendCommit,src,p,v);
}

static void Configure(unsigned src){
 auto& b=binding[src];if(b.p!=phase||(benefitV2&&b.releasing))return;
 uint64_t at=PeerNow();
 // Messages are enqueued at their actual causal send times, without reserving future FIFO gaps.
 if(!b.configured){
  for(auto rank:{src,Dest(src),b.hs,b.hd})at=std::max(at,Message("PREPARE",rank,b.version));
  Simulator::Schedule(NanoSeconds(at-PeerNow()+1000000),&SendReady,src,phase,b.version);
 }else{
  for(auto rank:{b.hs,b.hd})at=std::max(at,Message("HELPER_READY",rank,b.version));
  Simulator::Schedule(NanoSeconds(at-PeerNow()),&Commit,src,phase,b.version);
 }
}

static void HealthDone(uint64_t id){
 if(benefitV2&&abortedProbes.count(id))return;
 auto r=routes.at(id);Reserve(routes.at(id),false);routes.erase(id);
 auto& b=binding[r.src];if(r.p!=phase||b.version!=r.bindingVersion||b.hs!=r.hs||b.hd!=r.hd)return;
 b.health=r.measurement;b.probeBytes=r.length;b.probeLegNs=r.legNs;
 if(benefitV2&&!b.configured){CollectHelperReports(r.src);return;}
 if(benefitMode&&!b.configured&&!BenefitAllows(r.src,"probe_complete")){b.pending=false;b.nextAttempt=PeerNow()+5000000;return;}
 Configure(r.src);
}

static void LendReady(unsigned src,unsigned p,uint64_t version){
 auto& b=binding[src];if(p!=phase||version!=b.version||(benefitV2&&b.releasing))return;
 loanTx[b.hs]=true;loanRx[b.hd]=true;b.loanReady=true;b.pending=false;
 controls<<PeerNow()<<','<<PeerNow()<<",LEND_ACTIVE,"<<src<<','<<phase<<','<<version<<",0\n";
}

static bool RequestLending(unsigned src){
 auto& b=binding[src];if(b.lending)return b.loanReady;
 bool found=false;unsigned hs=0,hd=0;
 for(unsigned h=src/4*4;h<src/4*4+4&&!found;++h)if(h!=src&&!plannedTx[h]&&!plannedRx[h])
  for(unsigned d=Dest(src)/4*4;d<Dest(src)/4*4+4;++d)if(d!=Dest(src)&&!plannedRx[d]&&!plannedTx[d]){hs=h;hd=d;found=true;break;}
 if(!found)return false;
 b.hs=hs;b.hd=hd;b.lending=true;b.pending=true;b.p=phase;b.version=++serial;
 plannedTx[hs]=b.version;plannedRx[hd]=b.version;
 // Lending changes only admission of future own traffic, after paid delivery.
 // Existing transfers drain normally and all traffic retains physical caps.
 uint64_t at=Message("LEND_TX",hs,b.version);at=std::max(at,Message("LEND_RX",hd,b.version));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&LendReady,src,phase,b.version);
 return false;
}

// V2 leases have their own identity: a fresh probe may change binding.version.
// A rejected decision releases only future admission reservations; route credits
// remain owned by Reserve/ReleaseDelivered/FinalAck and are never cleared here.
static void ReleaseLendingDone(unsigned src,unsigned p,uint64_t lease){
 auto& b=binding[src];if(p!=phase||b.p!=p||lease!=b.leaseId||!b.releasing)return;
 for(const auto& item:routes)if(item.second.relay&&item.second.src==src&&item.second.p==p&&item.second.reserved){
  Simulator::Schedule(NanoSeconds(50000),&ReleaseLendingDone,src,p,lease);return;}
 if(plannedTx[b.hs]==lease){plannedTx[b.hs]=0;loanTx[b.hs]=false;}
 if(plannedRx[b.hd]==lease){plannedRx[b.hd]=0;loanRx[b.hd]=false;}
 b.releasing=false;b.lending=false;b.loanReady=false;b.pending=false;b.leaseId=0;
 b.helperReportsReady=0;b.helperReports={};
 controls<<PeerNow()<<','<<PeerNow()<<",LEND_RELEASED,"<<src<<','<<p<<','<<lease<<",0\n";
 // Freed admission can help the helpers' own work immediately.
 Pump(b.hs);Pump(b.hd);
}

static void ReleaseLendingV2(unsigned src){
 auto& b=binding[src];if(!benefitV2||!sharedHelpers||!b.lending||b.releasing)return;
 b.releasing=true;b.pending=false;b.ready=false;
 uint64_t at=Message("RELEASE_TX",b.hs,b.leaseId);
 at=std::max(at,Message("RELEASE_RX",b.hd,b.leaseId));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&ReleaseLendingDone,src,phase,b.leaseId);
}

static void LendReadyV2(unsigned src,unsigned p,uint64_t lease){
 auto& b=binding[src];if(p!=phase||b.p!=p||lease!=b.leaseId||b.releasing||
  plannedTx[b.hs]!=lease||plannedRx[b.hd]!=lease)return;
 loanTx[b.hs]=true;loanRx[b.hd]=true;b.loanReady=true;b.pending=false;
 controls<<PeerNow()<<','<<PeerNow()<<",LEND_ACTIVE,"<<src<<','<<phase<<','<<lease<<",0\n";
}

static bool RequestLendingV2(unsigned src){
 auto& b=binding[src];if(b.releasing)return false;if(b.lending)return b.loanReady;
 bool found=false;unsigned hs=0,hd=0;
 for(unsigned h=src/4*4;h<src/4*4+4&&!found;++h)if(h!=src&&!plannedTx[h]&&!plannedRx[h])
  for(unsigned d=Dest(src)/4*4;d<Dest(src)/4*4+4;++d)if(d!=Dest(src)&&!plannedRx[d]&&!plannedTx[d]){hs=h;hd=d;found=true;break;}
 if(!found)return false;
 b.hs=hs;b.hd=hd;b.lending=true;b.pending=true;b.p=phase;b.version=++serial;b.leaseId=b.version;
 b.helperReportsReady=0;b.helperReports={};
 plannedTx[hs]=b.leaseId;plannedRx[hd]=b.leaseId;
 uint64_t at=Message("LEND_TX",hs,b.leaseId);at=std::max(at,Message("LEND_RX",hd,b.leaseId));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&LendReadyV2,src,phase,b.leaseId);
 return false;
}

static void LogHelperSnapshot(const char* event,unsigned src,unsigned slot,const HelperSnapshot& x){
 helperReports<<"{\"event\":\""<<event<<"\",\"timestamp_ns\":"<<PeerNow()<<",\"source\":"<<src
  <<",\"slot\":"<<slot<<",\"rank\":"<<x.rank<<",\"phase\":"<<x.phase<<",\"version\":"<<x.version
  <<",\"lease_id\":"<<x.lease_id<<",\"report_id\":"<<x.report_id<<",\"sampled_ns\":"<<x.sampled_ns
  <<",\"delivered_ns\":"<<x.delivered_ns<<",\"own_remaining_bytes\":"<<x.own_remaining_bytes
  <<",\"own_bytes_per_ns\":"<<x.own_bytes_per_ns<<",\"known\":"<<x.known<<"}\n";
}

static void DeliverHelperSnapshot(unsigned src,unsigned slot,HelperSnapshot x){
 auto& b=binding[src];
 if(x.phase!=phase||b.p!=x.phase||b.version!=x.version||b.leaseId!=x.lease_id||b.releasing){
  LogHelperSnapshot("STALE",src,slot,x);return;}
 b.helperReports[slot]=x;b.helperReportsReady|=1u<<slot;LogHelperSnapshot("DELIVERED",src,slot,x);
 if(b.helperReportsReady!=3)return;
 if(!BenefitAllows(src,"probe_complete")){
  b.pending=false;b.nextAttempt=PeerNow()+5000000;ReleaseLendingV2(src);return;}
 Configure(src);
}

static void SampleHelperSnapshot(unsigned src,unsigned slot,unsigned p,uint64_t version,uint64_t lease,uint64_t request){
 auto& b=binding[src];if(p!=phase||b.p!=p||b.version!=version||b.leaseId!=lease||b.releasing)return;
 unsigned helper=slot?b.hd:b.hs;HelperSnapshot x;x.rank=helper;x.phase=p;x.version=version;
 x.lease_id=lease;x.report_id=request;x.sampled_ns=PeerNow();x.known=true;
 // These are local sender observations at the helper, never injector state.
 x.own_remaining_bytes=Bytes-offered[helper];
 for(auto id:cohort[helper]){const auto& c=chunks.at(id);if(!c.done)x.own_remaining_bytes+=ChunkBytes-c.acked;}
 auto& samples=helperOwnAckSamples[helper];
 while(!samples.empty()&&samples.front().first+10000000<PeerNow())samples.pop_front();
 uint64_t acknowledged=0;for(const auto& value:samples)acknowledged+=value.second;
 x.own_bytes_per_ns=acknowledged/10000000.;
 x.delivered_ns=Message(slot?"HELPER_REPORT_RX":"HELPER_REPORT_TX",src,request);
 LogHelperSnapshot("SENT",src,slot,x);
 Simulator::Schedule(NanoSeconds(x.delivered_ns-PeerNow()),&DeliverHelperSnapshot,src,slot,x);
}

static void CollectHelperReports(unsigned src){
 auto& b=binding[src];b.helperReportsReady=0;b.helperReports={};
 // Requests reach each helper before sampling; the source waits for both replies.
 for(unsigned slot=0;slot<2;++slot){uint64_t request=++serial;
  uint64_t at=Message(slot?"HELPER_QUERY_RX":"HELPER_QUERY_TX",slot?b.hd:b.hs,request);
  Simulator::Schedule(NanoSeconds(at-PeerNow()),&SampleHelperSnapshot,src,slot,phase,b.version,b.leaseId,request);}
}

static void AbortProbeV2(uint64_t id){
 if(!benefitV2)return;auto found=routes.find(id);if(found==routes.end())return;
 auto r=found->second;if(!r.relay||!r.probe)throw std::logic_error("probe timeout targeted payload");
 abortedProbes.emplace(id,r);
 std::vector<uint64_t> tags;for(const auto& item:legs)if(item.second.route==id)tags.push_back(item.first);
 for(auto tag:tags){auto leg=legs.at(tag);abortedProbeLegs.emplace(tag,leg);
  auto hw=n.Get(leg.src)->GetObject<RdmaDriver>()->m_rdma;
  hw->CancelRto(leg.qp);leg.qp->m_limerState=LIMER_RDMA_QP_ERROR;hw->DeleteQueuePair(leg.qp);
  legsLog<<PeerNow()<<",LEG_CANCEL,"<<id<<','<<tag<<','<<leg.index<<','<<leg.src<<','<<leg.dst<<','<<leg.nic<<','<<r.length<<'\n';
  // Keep packet identities for exact accounting if a send was already issued.
  legs.erase(tag);
 }
 if(routes.at(id).reserved)Reserve(routes.at(id),false);routes.erase(id);
 controls<<PeerNow()<<','<<PeerNow()<<",PROBE_ABORT,"<<r.src<<','<<r.p<<','<<id<<",0\n";
 auto& b=binding[r.src];if(r.p!=phase||b.p!=r.p||b.version!=r.bindingVersion)return;
 b.pending=false;b.ready=false;b.nextAttempt=PeerNow()+5000000;
 // A configured route retains its participants and retries health. Only an
 // uncommitted loan or a source with no remaining work may be relinquished.
 if(!b.configured||outDone[r.src]==phaseChunks)ReleaseLendingV2(r.src);
}

static void Tick(){
 if(phase<phases)for(unsigned s=0;s<16;++s){
  if(benefitV2&&binding[s].lending&&outDone[s]==phaseChunks)ReleaseLendingV2(s);
  if(binding[s].ready&&PeerNow()-binding[s].health>Ttl)binding[s].ready=false;
  Pump(s);if(!proxy||!m13[s]||binding[s].ready||binding[s].pending||outDone[s]==phaseChunks||PeerNow()<binding[s].nextAttempt)continue;
  bool found=false;unsigned hs=0,hd=0;
  if(sharedHelpers){
   if(!(benefitV2?RequestLendingV2(s):RequestLending(s)))continue;
   hs=binding[s].hs;hd=binding[s].hd;
   Route r;r.src=s;r.dst=Dest(s);r.hs=hs;r.hd=hd;r.relay=true;r.rail=1;found=Capacity(r);
  }else{
   for(unsigned h=s/4*4;h<s/4*4+4&&!found;++h)if(h!=s&&Idle(h))
    for(unsigned d=Dest(s)/4*4;d<Dest(s)/4*4+4;++d)if(d!=Dest(s)&&Idle(d)){
     Route r;r.src=s;r.dst=Dest(s);r.hs=h;r.hd=d;r.relay=true;r.rail=1;if(Capacity(r)){hs=h;hd=d;found=true;break;}}
  }
  if(!found)continue;
  auto& b=binding[s];b.hs=hs;b.hd=hd;b.pending=true;b.p=phase;b.version=++serial;
  controls<<PeerNow()<<','<<PeerNow()<<",M13_REPLACEMENT_PREPARE,"<<s<<','<<phase<<','<<b.version<<",0\n";
  Route r;r.id=++serial;r.src=s;r.dst=Dest(s);r.hs=hs;r.hd=hd;r.p=phase;r.relay=true;r.probe=true;r.length=(serviceMode||benefitMode)?ChunkBytes:1024;r.started=PeerNow();
  r.bindingVersion=b.version;
  routes.emplace(r.id,r);Reserve(routes.at(r.id),true);++probeRoutes;StartLeg(r.id);
  if(benefitV2)Simulator::Schedule(NanoSeconds(Ttl),&AbortProbeV2,r.id);
 }
 if(PeerNow()+50000<horizon)Simulator::Schedule(NanoSeconds(50000),&Tick);
}

}}
