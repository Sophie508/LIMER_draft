#pragma once
namespace limer { namespace engine {
static void Commit(unsigned src,unsigned p,uint64_t version){
 auto& b=binding[src];if(p!=phase||version!=b.version)return;
 if((!sharedHelpers&&(!Idle(b.hs)||!Idle(b.hd)))||PeerNow()<b.health||PeerNow()-b.health>Ttl){b.pending=false;return;}
 if(!m13[src])throw std::logic_error("replacement without M13 alarm");
 if(!b.configured&&benefitMode&&!BenefitAllows(src,"commit")){b.pending=false;b.nextAttempt=PeerNow()+5000000;return;}
 b.ready=true;b.pending=false;b.configured=true;b.disabled=true;
 if(!b.activation){b.activation=PeerNow();rates[src][2]=0;credits[src][2]=0;launches[src][2]=0;}
 controls<<PeerNow()<<','<<PeerNow()<<",ACTIVATE,"<<src<<','<<phase<<','<<version<<",0\n";Pump(src);
}

static void SendCommit(unsigned src,unsigned p,uint64_t v){
 auto& b=binding[src];if(p!=phase||v!=b.version)return;
 uint64_t at=PeerNow();for(auto rank:{src,Dest(src),b.hs,b.hd})at=std::max(at,Message("COMMIT",rank,v));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&Commit,src,p,v);
}

static void SendReady(unsigned src,unsigned p,uint64_t v){
 auto& b=binding[src];if(p!=phase||v!=b.version)return;
 uint64_t at=PeerNow();for(auto rank:{src,Dest(src),b.hs,b.hd})at=std::max(at,Message("READY",rank,v));
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&SendCommit,src,p,v);
}

static void Configure(unsigned src){
 auto& b=binding[src];if(b.p!=phase)return;
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
 auto r=routes.at(id);Reserve(routes.at(id),false);routes.erase(id);
 auto& b=binding[r.src];if(r.p!=phase||b.version!=r.bindingVersion||b.hs!=r.hs||b.hd!=r.hd)return;
 b.health=r.measurement;b.probeBytes=r.length;b.probeLegNs=r.legNs;
 if(benefitMode&&!b.configured&&!BenefitAllows(r.src,"probe_complete")){b.pending=false;b.nextAttempt=PeerNow()+5000000;return;}
 Configure(r.src);
}

static void LendReady(unsigned src,unsigned p,uint64_t version){
 auto& b=binding[src];if(p!=phase||version!=b.version)return;
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

static void Tick(){
 if(phase<phases)for(unsigned s=0;s<16;++s){
  if(binding[s].ready&&PeerNow()-binding[s].health>Ttl)binding[s].ready=false;
  Pump(s);if(!proxy||!m13[s]||binding[s].ready||binding[s].pending||outDone[s]==phaseChunks||PeerNow()<binding[s].nextAttempt)continue;
  bool found=false;unsigned hs=0,hd=0;
  if(sharedHelpers){
   if(!RequestLending(s))continue;
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
 }
 if(PeerNow()+50000<horizon)Simulator::Schedule(NanoSeconds(50000),&Tick);
}

}}
