// Receiver observations contain no injector fields.
#include <vector>
#include <functional>
#include <map>
#include <set>
#include <fstream>
#include <stdexcept>
#include <cstdint>
#include "m13_batch_deficit_observer.h"

struct GapTracker {
  uint64_t next=0;
  std::map<uint64_t,int64_t> holes;
  void receive(uint64_t sequence,int64_t now) {
    if(sequence>=next) {
      for(uint64_t n=next;n<sequence;++n) holes.emplace(n,now);
      next=sequence+1;
    } else holes.erase(sequence);
  }
  uint64_t age(int64_t now) const {
    uint64_t oldest=0;
    for(const auto& hole:holes) oldest=std::max(oldest,uint64_t(now-hole.second));
    return oldest;
  }
};
struct BusinessObservation {
  CounterObservation base;
  uint64_t data,probe;
  int64_t guard;
  uint64_t dataGaps,probeGaps,dataAge,probeAge;
};
class BusinessObserver {
  NativeDeficitObserver mature,early{true},business{true};
  std::ofstream output;
  std::set<int> alarmed;
  std::map<std::tuple<int,uint32_t,bool,int64_t>,BusinessObservation> seen;
  static constexpr int64_t gapGuard=40'000'000;
  void emit(int path,int64_t now,uint64_t missing,const std::vector<uint32_t>& batches,
            const std::string& signal,uint64_t age=0) {
    if(!alarmed.insert(path).second) return;
    output << "{\"rule_version\":\"business-delivery-v1\",\"path\":\"" << path/2 << '/' << (path%2?'B':'A')
      << "\",\"decision_t_ns\":" << now << ",\"signal\":\"" << signal << "\",\"missing_packets\":" << missing
      << ",\"evidence_batches\":[";
    for(size_t i=0;i<batches.size();++i) output << (i?",":"") << batches[i];
    output << "],\"gap_age_ns\":" << age << ",\"claim\":\"Observed delivery impairment; cause unresolved\"}\n";
    output.flush();
  }
public:
  void open(const std::string& file,const std::string& baselineFile) {
    output.open(file);if(!output) throw std::runtime_error("Cannot open M13 alarms");
    mature.open(baselineFile);
    auto callback=[this](int p,int64_t t,uint64_t n,std::vector<uint32_t> b,std::string s){emit(p,t,n,b,s);};
    mature.onAlarm=callback;early.onAlarm=callback;business.onAlarm=callback;business.callbackOnly=true;
  }
  void advance(int64_t now) {
    mature.advance(now);early.advance(now);business.advance(now);
    for(auto it=seen.begin();it!=seen.end();) {
      if(now>(std::get<1>(it->first)+1)*10'000'000+200'000'000) it=seen.erase(it);else ++it;
    }
  }
  void observe(const BusinessObservation& r) {
    const auto& b=r.base;
    if(r.data+r.probe!=b.count || b.arrival<b.sample) throw std::runtime_error("Invalid class counters/time");
    if((!r.dataGaps && r.dataAge)||(!r.probeGaps && r.probeAge)||r.dataAge>uint64_t(b.sample)||r.probeAge>uint64_t(b.sample)
       ||(!b.rx&&(r.dataGaps||r.probeGaps||r.dataAge||r.probeAge))) throw std::runtime_error("Invalid receiver gap");
    if(r.guard==10'000'000) early.observe(b);
    else if((!b.rx && r.guard==0)||(b.rx && r.guard==50'000'000)) mature.observe(b);
    else throw std::runtime_error("Invalid measurement lane");
    advance(b.arrival);
    if(b.arrival>(b.batch+1)*10'000'000+200'000'000) return;
    auto key=std::make_tuple(b.path,b.batch,b.rx,r.guard);
    auto found=seen.find(key);
    if(found!=seen.end()) {
      const auto& old=found->second;
      if(old.data!=r.data || old.probe!=r.probe || old.dataGaps!=r.dataGaps || old.probeGaps!=r.probeGaps
         || old.dataAge!=r.dataAge || old.probeAge!=r.probeAge || old.base.sample!=b.sample)
        throw std::runtime_error("Conflicting class duplicate");
      return;
    }
    seen.emplace(key,r);
    if(b.rx && r.dataGaps && r.dataAge>=gapGuard) emit(b.path,b.arrival,r.dataGaps,{b.batch},"data_gap",r.dataAge);
    if(b.rx && r.probeGaps && r.probeAge>=gapGuard) emit(b.path,b.arrival,r.probeGaps,{b.batch},"probe_gap",r.probeAge);
    if(r.guard==10'000'000) {CounterObservation data=b;data.count=r.data;business.observe(data);}
  }
};
