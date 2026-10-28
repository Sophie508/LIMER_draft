#pragma once
namespace limer { namespace engine {
static void Forget(uint64_t tag){
 identities.erase(identities.lower_bound({tag,0}),identities.upper_bound({tag,UINT64_MAX}));
 sentWire.erase(sentWire.lower_bound({tag,0}),sentWire.upper_bound({tag,UINT32_MAX}));legs.erase(tag);
}

static void Noop(){}

static void Sent(Ptr<RdmaQueuePair>){}

static void Put(unsigned char*& p,uint64_t x,unsigned n){for(unsigned i=n;i;--i)*p++=uint8_t(x>>(8*(i-1)));}

static uint64_t Get(const unsigned char*& p,unsigned n){uint64_t x=0;while(n--)x=(x<<8)|*p++;return x;}

extern "C" uint32_t limer_split_select_qp(void* opaque,uint32_t fallback){
 auto q=static_cast<RdmaQueuePair*>(opaque);auto it=legs.find(q->GetTag());return it==legs.end()?fallback:it->second.nic;
}
// This optional hook is added only to this experiment's private transport library.

extern "C" uint32_t limer_peer_reverse_nic(unsigned path){
 unsigned s=path/48,d=(path/3)%16;return s/4==d/4?1:2+path%3;
}

extern "C" bool limer_joint_encode(void* opaque,unsigned char* data,unsigned size){
 if(size!=24)throw std::logic_error("wire size");auto q=static_cast<RdmaQueuePair*>(opaque);
 auto leg=legs.at(q->GetTag());auto r=routes.at(leg.route);auto k=std::make_pair(q->GetTag(),q->snd_nxt);
 auto it=identities.find(k);
 if(it==identities.end()){
  unsigned path=Key(leg.src,leg.dst,leg.nic==1?2:leg.nic-2);auto& c=counts[path];
  Wire w{path,unsigned(PeerNow()/10000000),r.probe,c.next[r.probe]++,PeerNow()};++c.tx[r.probe][w.batch];++c.totalTx[r.probe];
  it=identities.emplace(k,w).first;packets<<PeerNow()<<",source_accept,"<<path<<','<<r.probe<<','<<w.batch<<','<<w.seq<<','<<q->GetTag()<<','<<q->snd_nxt<<",1,"<<std::min(uint64_t(976),r.length-q->snd_nxt)<<'\n';
 }
 const auto& w=it->second;auto p=data;Put(p,w.path,2);Put(p,w.probe,1);Put(p,1,1);Put(p,w.batch,4);Put(p,w.seq,8);Put(p,w.submitted,8);return true;
}

extern "C" void limer_joint_wire_tx(void* opaque,unsigned sequence,unsigned size){
 auto q=static_cast<RdmaQueuePair*>(opaque);auto leg=legs.at(q->GetTag());auto r=routes.at(leg.route);
 if(q->m_activeNicIdx!=leg.nic)throw std::logic_error("physical NIC mismatch");
 bool repeat=!sentWire.insert({q->GetTag(),sequence}).second;
 if(repeat&&r.service){unsigned path=Key(r.src,r.dst,r.rail);
  serviceEvents<<PeerNow()<<",RETRANSMIT,"<<path<<','<<r.id<<','<<size<<'\n';
  serviceDetector.retransmit(path,r.id,PeerNow());}
 if(leg.nic==1)localWire+=size;else networkWire+=size;
 if(r.probe)probeWire+=size;if(r.relay&&!r.probe)rescueWire+=size;if(repeat)retransWire+=size;
 wireLog<<PeerNow()<<','<<leg.route<<','<<q->GetTag()<<','<<leg.src<<','<<leg.dst<<','<<leg.nic<<','<<r.probe<<','<<r.relay<<','<<sequence<<','<<size<<','<<repeat<<'\n';
}

extern "C" void limer_joint_receive(unsigned dst,unsigned sip,unsigned sport,unsigned sequence,unsigned bytes,const unsigned char* data,unsigned size,bool accepted){
 if(size!=24)throw std::logic_error("wire size");auto p=data;unsigned path=Get(p,2),kind=Get(p,1),version=Get(p,1);
 unsigned batch=Get(p,4);auto seq=Get(p,8),submitted=Get(p,8);
 if(version!=1||kind>1||(path/3)%16!=dst||path/48!=((sip>>8)&65535)||submitted>PeerNow())throw std::logic_error("wire endpoint mismatch");
 auto& c=counts[path];if(accepted){++c.rx[kind][batch];++c.totalRx[kind];c.gaps[kind].receive(seq,PeerNow());}
 packets<<PeerNow()<<",network_rx,"<<path<<','<<kind<<','<<batch<<','<<seq<<','<<sport<<','<<sequence<<','<<accepted<<','<<bytes<<'\n';
 if(accepted)ReceiverSpacingObserve(path,bytes);
}

static void Progress(PeerChunk& c,uint64_t prefix,uint64_t route){
 if(prefix<=c.acked)return;if(prefix>ChunkBytes||c.done)throw std::logic_error("invalid logical ACK");
 if(!routes.at(route).relay){auto& samples=ackSamples[Key(c.src,c.dst,c.lane)];samples.emplace_back(PeerNow(),prefix-c.acked);
  while(!samples.empty()&&samples.front().first+10000000<PeerNow())samples.pop_front();}
 c.acked=prefix;c.lastProgress=PeerNow();PeerEvent("ACK_PROGRESS",c,route);
}

extern "C" void limer_split_ack_progress(void* opaque,uint64_t){
 auto q=static_cast<RdmaQueuePair*>(opaque);auto it=legs.find(q->GetTag());if(it==legs.end()){++staleAcks;return;}
 const auto& r=routes.at(it->second.route);if(r.probe||r.relay)return;
 auto& c=chunks.at(r.chunk);if(c.epoch!=r.epoch){++staleAcks;return;}Progress(c,r.base+q->snd_una,r.id);
}

static void Completed(Ptr<RdmaQueuePair> q){
 auto leg=legs.at(q->GetTag());auto r=routes.at(leg.route);
 legsLog<<PeerNow()<<",LEG_DONE,"<<r.id<<','<<leg.tag<<','<<leg.index<<','<<leg.src<<','<<leg.dst<<','<<leg.nic<<','<<r.length<<'\n';
 Forget(leg.tag);
 if(r.relay&&r.probe)routes.at(r.id).legNs[r.index]=PeerNow()-leg.started;
 if(r.relay&&r.index<2){++routes.at(r.id).index;Simulator::Schedule(NanoSeconds(1),&StartLeg,r.id);return;}
 if(r.probe){if(r.relay){
   routes.at(r.id).measurement=PeerNow();
   if(serviceMode||benefitMode){auto at=Message("HEALTH_REPORT",r.src,r.id);Simulator::Schedule(NanoSeconds(at-PeerNow()),&HealthDone,r.id);}
   else HealthDone(r.id);
  }else{if(r.service)ServiceCompleted(r);routes.erase(r.id);}return;}
 if(r.relay){auto at=Message("FINAL_ACK",r.src,r.id);Simulator::Schedule(NanoSeconds(at-PeerNow()),&FinalAck,r.id);}
 else FinalAck(r.id);
}

static void StartLeg(uint64_t id){
 auto& r=routes.at(id);auto edge=Edges(r).at(r.index);unsigned port=ports[edge[0]]++;
 if(port>=65535)throw std::runtime_error("port budget exhausted");uint64_t tag=++serial;
 legs.emplace(tag,Leg{tag,id,PeerNow(),edge[0],edge[1],edge[2],r.index,nullptr});
 legsLog<<PeerNow()<<",LEG_START,"<<id<<','<<tag<<','<<r.index<<','<<edge[0]<<','<<edge[1]<<','<<edge[2]<<','<<r.length<<'\n';
 auto hw=n.Get(edge[0])->GetObject<RdmaDriver>()->m_rdma;
 hw->AddQueuePair(edge[0],edge[1],tag,r.length,3,serverAddress[edge[0]],serverAddress[edge[1]],port,100,0,10000,MakeCallback(&Noop),MakeCallback(&Noop));
 legs.at(tag).qp=hw->GetQp(serverAddress[edge[1]].Get(),port,3);
 if(!legs.at(tag).qp||legs.at(tag).qp->m_activeNicIdx!=edge[2])throw std::logic_error("route not bound to intended physical NIC");
}

static void Launch(PeerChunk& c,bool relay){
 Route r;r.id=++serial;r.chunk=c.id;r.epoch=c.epoch;r.base=c.acked;r.length=ChunkBytes-c.acked;r.src=c.src;r.dst=c.dst;r.p=phase;r.relay=relay;r.rail=c.lane;r.started=PeerNow();
 if(relay){auto& b=binding[c.src];r.hs=b.hs;r.hd=b.hd;r.rail=1;}
 if(!Capacity(r))throw std::logic_error("launch without credits");
 routes.emplace(r.id,r);Reserve(routes.at(r.id),true);PeerEvent(relay?"PROXY_LAUNCH":"DIRECT_LAUNCH",c,r.id);StartLeg(r.id);
}

static bool CanLaunch(unsigned src,unsigned lane,bool relay){
 Route r;r.src=src;r.dst=Dest(src);r.rail=lane;r.relay=relay;
 if(relay){const auto& b=binding[src];if(!b.ready||b.p!=phase||!Idle(b.hs)||!Idle(b.hd)||PeerNow()-b.health>Ttl)return false;r.hs=b.hs;r.hd=b.hd;r.rail=1;}
 return Capacity(r);
}

}}
