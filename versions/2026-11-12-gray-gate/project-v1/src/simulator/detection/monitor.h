#pragma once
namespace limer { namespace engine {
static void Alarm(int key,int64_t t,const std::string& signal){
 alarms<<t<<','<<key<<','<<signal<<','<<(serviceMode?"SERVICE-R":"M13-R")<<"\n";
 unsigned src=key/48;
 if(src<16&&unsigned(key)==Key(src,Dest(src),1)){m13[src]=true;binding[src].alarm=t;}
}

static void DeliverServiceAlarm(unsigned path,std::string signal){
 serviceAlarms<<PeerNow()<<','<<path<<','<<signal<<'\n';
 Alarm(path,PeerNow(),signal);
}

static void OnServiceAlarm(const limer::detection::ServiceAlarm& a){
 serviceDecisions<<"{\"rule_version\":\""<<a.rule_version<<"\",\"signal\":\""<<a.signal<<"\",\"path\":"<<a.path<<",\"decision_t_ns\":"<<a.decision_t_ns<<",\"baseline_ns\":"<<a.baseline_ns<<",\"deadline_ns\":"<<a.deadline_ns<<",\"tokens\":[";
 for(size_t i=0;i<a.evidence_tokens.size();++i)serviceDecisions<<(i?",":"")<<a.evidence_tokens[i];
 serviceDecisions<<"]}\n";
 auto at=Message("SERVICE_ALARM",a.path,0);
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&DeliverServiceAlarm,a.path,a.signal);
}

static void ServiceCompleted(const Route& r){
 unsigned path=Key(r.src,r.dst,r.rail);
 serviceEvents<<PeerNow()<<",COMPLETE,"<<path<<','<<r.id<<','<<r.length<<'\n';
 canarySamples[path]={PeerNow(),PeerNow()-r.started};
 serviceDetector.complete(path,r.id,PeerNow());
}

static void ServiceTick(){
 serviceDetector.onAlarm=OnServiceAlarm;
 serviceEvents<<PeerNow()<<",ADVANCE,0,0,0\n";
 serviceDetector.advance(PeerNow());
 for(unsigned s=0;s<16;++s)for(unsigned rail=0;rail<2;++rail){
  Route r;r.id=++serial;r.src=s;r.dst=Dest(s);r.rail=rail;r.length=canaryBytes;r.probe=true;r.service=true;r.p=phase;r.started=PeerNow();
  unsigned path=Key(s,Dest(s),rail);
  serviceEvents<<PeerNow()<<",SUBMIT,"<<path<<','<<r.id<<','<<r.length<<'\n';
  serviceDetector.submit(path,r.id,PeerNow(),r.length);routes.emplace(r.id,r);StartLeg(r.id);
 }
 for(unsigned s=0;s<16;++s)for(auto id:cohort[s]){const auto& c=chunks.at(id);unsigned path=Key(c.src,c.dst,c.lane);
  auto progress=std::max(c.allocated,c.lastProgress);
  if(c.done||c.epoch||serviceDetector.alarmed(path)||PeerNow()-progress<uint64_t(serviceDetector.config().business_stall_ns))continue;
  serviceEvents<<PeerNow()<<",STALL,"<<path<<','<<c.id<<','<<ChunkBytes-c.acked<<','<<progress<<'\n';
  serviceDetector.stall(path,c.id,PeerNow(),progress,ChunkBytes-c.acked);
 }
 if(PeerNow()+canaryPeriod<horizon)Simulator::Schedule(NanoSeconds(canaryPeriod),&ServiceTick);
}

static void DeliverReport(BusinessObservation r){
 r.base.arrival=PeerNow();const auto& b=r.base;
 observations<<"{\"path\":\""<<b.path<<"\",\"batch\":"<<b.batch<<",\"side\":\""<<(b.rx?"rx":"tx")<<"\",\"count\":"<<b.count<<",\"data_count\":"<<r.data<<",\"probe_count\":"<<r.probe<<",\"sample_t_ns\":"<<b.sample<<",\"guard_ns\":"<<r.guard<<",\"data_gaps\":"<<r.dataGaps<<",\"probe_gaps\":"<<r.probeGaps<<",\"data_gap_age_ns\":"<<r.dataAge<<",\"probe_gap_age_ns\":"<<r.probeAge<<",\"arrival_t_ns\":"<<b.arrival<<"}\n";detector.observe(r);
}

static void Report(unsigned key,unsigned batch,bool receive,int64_t guard){
 packets<<PeerNow()<<",snapshot,"<<key<<','<<receive<<','<<batch<<','<<guard<<",0,0,0,0\n";auto& c=counts[key];BusinessObservation r{};r.base.path=key;r.base.batch=batch;r.base.rx=receive;r.base.sample=PeerNow();r.guard=guard;
 for(unsigned k=0;k<2;++k){uint64_t value=guard==10000000?(receive?c.totalRx[k]:c.totalTx[k]):(receive?c.rx[k][batch]:c.tx[k][batch]);if(k)r.probe=value;else r.data=value;}
 r.base.count=r.data+r.probe;if(receive){r.dataGaps=c.gaps[0].holes.size();r.probeGaps=c.gaps[1].holes.size();r.dataAge=c.gaps[0].age(PeerNow());r.probeAge=c.gaps[1].age(PeerNow());}
 auto at=control.send(PeerNow(),96);controls<<PeerNow()<<','<<at<<",OBSERVATION,"<<key<<','<<phase<<",0,96\n";
 Simulator::Schedule(NanoSeconds(at-PeerNow()),&DeliverReport,r);
}

static void ObserveTick(){
 unsigned batch=PeerNow()/10000000-1;
 for(unsigned s=0;s<16;++s)for(unsigned rail=0;rail<2;++rail){unsigned key=Key(s,Dest(s),rail);Report(key,batch,false,0);
  if(PeerNow()+10000000<horizon){Simulator::Schedule(MilliSeconds(10),&Report,key,batch,false,int64_t(10000000));Simulator::Schedule(MilliSeconds(10),&Report,key,batch,true,int64_t(10000000));}
  if(PeerNow()+50000000<horizon)Simulator::Schedule(MilliSeconds(50),&Report,key,batch,true,int64_t(50000000));}
 if(PeerNow()+10000000<horizon)Simulator::Schedule(MilliSeconds(10),&ObserveTick);
}

static void ProbeTick(){
 for(unsigned s=0;s<16;++s)for(unsigned rail=0;rail<2;++rail){unsigned key=Key(s,Dest(s),rail),batch=PeerNow()/10000000;uint64_t previous=batch?counts[key].tx[0][batch-1]:0;
  if(!ProbeBudget(previous,1000000,1000))continue;Route r;r.id=++serial;r.src=s;r.dst=Dest(s);r.rail=rail;r.length=976;r.probe=true;r.p=phase;r.started=PeerNow();routes.emplace(r.id,r);StartLeg(r.id);}
 if(PeerNow()+1000000<horizon)Simulator::Schedule(MilliSeconds(1),&ProbeTick);
}

}}
