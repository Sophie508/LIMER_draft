#pragma once
namespace limer { namespace engine {
static double RecentService(unsigned src,unsigned lane,uint64_t owned){
 auto key=Key(src,Dest(src),lane);auto& samples=ackSamples[key];
 while(!samples.empty()&&samples.front().first+10000000<PeerNow())samples.pop_front();
 uint64_t bytes=0;for(const auto& sample:samples)bytes+=sample.second;
 if(bytes)return bytes/10000000.;
 // No progress on outstanding work is an observation, not fault truth.
 if(owned)return 0.;
 auto canary=canarySamples.find(key);
 if(canary!=canarySamples.end()&&canary->second.first+20000000>=PeerNow())
  return std::min(1.25,double(canaryBytes)/std::max(uint64_t(1),canary->second.second));
 return 0.;
}

static void JsonNumber(std::ostream& out,double x){if(std::isfinite(x))out<<x;else out<<"null";}

static bool BenefitAllows(unsigned src,const char* stage){
 using namespace limer::recovery;auto& b=binding[src];BenefitInput x;
 for(auto id:cohort[src]){const auto& c=chunks.at(id);if(!c.done)(c.lane?x.b_bytes:x.a_bytes)+=ChunkBytes-c.acked;}
 uint64_t remaining=Bytes-offered[src];
 if(feedback)x.pending_bytes=remaining;
 else for(unsigned lane=0;lane<2;++lane)for(uint64_t off=nextOffset[src][lane];off<Bytes;off+=2*ChunkBytes)(lane?x.b_bytes:x.a_bytes)+=ChunkBytes;
 x.service_a={RecentService(src,0,x.a_bytes),0,PeerNow()>=20000000};
 x.service_b={RecentService(src,1,x.b_bytes),0,PeerNow()>=20000000};
 x.relay.sample_bytes=b.probeBytes;x.relay.leg_ns=b.probeLegNs;
 x.relay.age_ns=PeerNow()-b.health;x.relay.known=b.health>0;
 double queued=control.free_ns>PeerNow()?control.free_ns-PeerNow():0;
 x.relay.final_ack_ns=queued+1000000+7680;
 x.setup_ns=std::string(stage)=="commit"?0:queued+4000000+12*7680;
 x.helper_ready=Idle(b.hs)&&Idle(b.hd);
 auto d=EvaluateBenefit(x);
 policyLog<<"{\"timestamp_ns\":"<<PeerNow()<<",\"src\":"<<src<<",\"phase\":"<<phase<<",\"stage\":\""<<stage<<"\",\"input\":{\"a_bytes\":"<<x.a_bytes<<",\"b_bytes\":"<<x.b_bytes<<",\"pending_bytes\":"<<x.pending_bytes
  <<",\"service_a\":{\"bytes_per_ns\":"<<x.service_a.bytes_per_ns<<",\"age_ns\":0,\"known\":"<<x.service_a.known<<"},\"service_b\":{\"bytes_per_ns\":"<<x.service_b.bytes_per_ns<<",\"age_ns\":0,\"known\":"<<x.service_b.known<<"},\"relay\":{\"sample_bytes\":"<<x.relay.sample_bytes<<",\"leg_ns\":["<<x.relay.leg_ns[0]<<','<<x.relay.leg_ns[1]<<','<<x.relay.leg_ns[2]<<"],\"final_ack_ns\":"<<x.relay.final_ack_ns<<",\"parallel_chunks\":4,\"age_ns\":"<<x.relay.age_ns<<",\"known\":"<<x.relay.known<<"},\"setup_ns\":"<<x.setup_ns<<",\"helper_ready\":"<<x.helper_ready<<"},\"should_switch\":"<<d.should_switch<<",\"reason\":\""<<d.reason<<"\",\"stay_ns\":";
 JsonNumber(policyLog,d.stay_ns);policyLog<<",\"switch_ns\":";JsonNumber(policyLog,d.switch_ns);policyLog<<",\"gain_ns\":";JsonNumber(policyLog,d.gain_ns);policyLog<<"}\n";
 return d.should_switch;
}
}}
