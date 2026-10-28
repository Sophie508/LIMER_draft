#pragma once
#include <algorithm>
#include <array>
#include <cmath>
#include <cstdint>
#include <limits>
#include <stdexcept>
#include <string>

namespace limer { namespace recovery {

// Rates are observed aggregate bytes/ns. Zero is an observed no-progress
// window, not an oracle for whether or when a fault will recover.
struct ServiceSample {
 double bytes_per_ns=0; uint64_t age_ns=0; bool known=false;
};
struct RelaySample {
 uint64_t sample_bytes=0; std::array<double,3> leg_ns{{0,0,0}};
 double final_ack_ns=0; unsigned parallel_chunks=4;
 uint64_t age_ns=0; bool known=false;
};
struct BenefitInput {
 uint64_t a_bytes=0,b_bytes=0,pending_bytes=0;
 ServiceSample service_a,service_b; RelaySample relay;
 double setup_ns=0; bool helper_ready=true;
 uint64_t chunk_bytes=65536,max_age_ns=20000000;
 double min_gain_ns=1000000,min_gain_fraction=.10;
};
struct BenefitDecision {
 bool should_switch=false,probe_required=false;
 std::string reason="insufficient_service_evidence";
 double stay_ns=std::numeric_limits<double>::infinity();
 double switch_ns=std::numeric_limits<double>::infinity();
 double gain_ns=0,relay_bytes_per_ns=0;
};

// Sender/phase fluid heuristic, not a distributed critical-path optimizer.
// Owned bytes cannot be shifted between A and B. Pending adaptive bytes can
// use either lane; fixed pending allocations belong in a_bytes/b_bytes.
inline double FinishTime(uint64_t a,uint64_t b,uint64_t pending,
                         double ra,double rb,double delay=0){
 const double inf=std::numeric_limits<double>::infinity();
 if((a&&ra<=0)||(b&&rb<=0))return inf;
 double lo=std::max(a?a/ra:0.,b?delay+b/rb:0.);
 if(!pending)return lo;if(ra+rb<=0)return inf;
 auto freeCapacity=[&](double t){return std::max(0.,t*ra-a)+
   std::max(0.,std::max(0.,t-delay)*rb-b);};
 double hi=lo+delay+pending/(ra+rb)+1.;
 while(freeCapacity(hi)<pending)hi=hi*2.+1.;
 for(unsigned i=0;i<80;++i){double mid=(lo+hi)/2.;
  if(freeCapacity(mid)>=pending)hi=mid;else lo=mid;}
 return hi;
}

inline BenefitDecision EvaluateBenefit(const BenefitInput& x){
 auto valid=[](double v){return std::isfinite(v)&&v>=0;};
 if(!x.chunk_bytes||!x.relay.parallel_chunks||!valid(x.setup_ns)||
    !valid(x.min_gain_ns)||!valid(x.min_gain_fraction)||
    !valid(x.service_a.bytes_per_ns)||!valid(x.service_b.bytes_per_ns)||
    !valid(x.relay.final_ack_ns))throw std::invalid_argument("invalid benefit input");
 for(auto t:x.relay.leg_ns)if(!valid(t))throw std::invalid_argument("invalid probe cost");
 BenefitDecision d;
 if(!x.a_bytes&&!x.b_bytes&&!x.pending_bytes){
  d.reason="no_remaining_work";d.stay_ns=d.switch_ns=0;return d;}
 if(!x.service_a.known||!x.service_b.known||
    x.service_a.age_ns>x.max_age_ns||x.service_b.age_ns>x.max_age_ns)return d;
 d.stay_ns=FinishTime(x.a_bytes,x.b_bytes,x.pending_bytes,
                     x.service_a.bytes_per_ns,x.service_b.bytes_per_ns);
 if(!x.helper_ready){d.reason="helpers_not_ready";return d;}
 if(!x.relay.known||x.relay.age_ns>x.max_age_ns||
    x.relay.sample_bytes<x.chunk_bytes||
    *std::min_element(x.relay.leg_ns.begin(),x.relay.leg_ns.end())<=0){
  d.reason="representative_probe_required";d.probe_required=true;return d;}
 std::array<double,3> legs=x.relay.leg_ns;
 double sum=0,largest=0;
 // Keep larger probes' measured latency rather than scaling propagation and
 // queueing down. A representative full-chunk probe is preferred.
 for(auto t:legs){sum+=t;largest=std::max(largest,t);}
 d.relay_bytes_per_ns=std::min(x.chunk_bytes/largest,
    x.relay.parallel_chunks*double(x.chunk_bytes)/(sum+x.relay.final_ack_ns));
 // Four credits improve steady-state overlap, not first-chunk latency.
 double startup=std::max(0.,sum+x.relay.final_ack_ns-
                           x.chunk_bytes/d.relay_bytes_per_ns);
 d.switch_ns=FinishTime(x.a_bytes,x.b_bytes,x.pending_bytes,
                       x.service_a.bytes_per_ns,d.relay_bytes_per_ns,x.setup_ns+startup);
 // A subchunk tail still requires the first relay/ACK cycle. Conservatively
 // retain the full representative probe cycle rather than scaling away its
 // fixed propagation, queuing and final-notification costs.
 if(x.b_bytes)d.switch_ns=std::max(d.switch_ns,x.setup_ns+sum+x.relay.final_ack_ns);
 d.gain_ns=std::isfinite(d.switch_ns)?d.stay_ns-d.switch_ns:0.;
 double margin=std::max(x.min_gain_ns,x.min_gain_fraction*d.stay_ns);
 d.should_switch=std::isfinite(d.switch_ns)&&
                 (!std::isfinite(d.stay_ns)||d.gain_ns>margin);
 d.reason=d.should_switch?"predicted_benefit":
          (d.gain_ns>0?"benefit_below_margin":"stay_no_slower");
 return d;
}

}}
