#include <functional>
#include <vector>
// Native counterpart of the frozen M8 report-only decision rule.
#include <deque>
#include <set>
#include <tuple>
#include <algorithm>
struct CounterObservation {
  int path; uint32_t batch; bool rx; uint64_t count; int64_t sample, arrival;
};
struct CounterPair { bool tx=false, rx=false; uint64_t sent=0, received=0; };
static std::ofstream hybrid_alarm_log;
static std::set<int> hybrid_alarmed_paths;
struct DeficitState {
  std::deque<std::tuple<int64_t,uint64_t,uint32_t>> history;
  bool armed=true; int clean=0; int64_t latest=-1;
  bool previous_counts=false;uint64_t last_sent=0,last_received=0;
};
class NativeDeficitObserver {
  std::map<std::pair<int,uint32_t>,CounterPair> pending, done;
  std::map<int,DeficitState> states;
  bool fast;
  int64_t now=-1;
  static constexpr int64_t period=10'000'000, guard=50'000'000;
  static constexpr int64_t ttl=200'000'000, window=100'000'000;
  void interrupt(int path) { states[path].history.clear(); states[path].clean=0; states[path].previous_counts=false; }
public:
  bool callbackOnly=false;
  std::function<void(int,int64_t,uint64_t,std::vector<uint32_t>,std::string)> onAlarm;
  explicit NativeDeficitObserver(bool early=false):fast(early) {}
  void open(const std::string& file) {
    hybrid_alarm_log.open(file); hybrid_alarmed_paths.clear(); if(!hybrid_alarm_log) throw std::runtime_error("Cannot open native alarms");
  }
  void advance(int64_t arrival) {
    if (arrival<now) throw std::runtime_error("Regressing observer time"); now=arrival;
    for (auto it=pending.begin();it!=pending.end();) {
      if(now > (it->first.second+1)*period+ttl) {
        interrupt(it->first.first); it=pending.erase(it);
      } else ++it;
    }
    for(auto it=done.begin();it!=done.end();) {
      if(now > (it->first.second+1)*period+ttl) it=done.erase(it); else ++it;
    }
    for(auto& entry:states) {
      auto& h=entry.second.history;
      while(!h.empty() && std::get<0>(h.front())<now-window) h.pop_front();
    }
  }
  void observe(CounterObservation r) {
    int64_t end=(r.batch+1)*period;
    if((fast && r.sample!=end+10'000'000) || (!fast && r.sample<end+(r.rx?guard:0)) || r.arrival<r.sample)
      throw std::runtime_error("Counter observed before batch/guard");
    advance(r.arrival); if(now>end+ttl) return;
    auto key=std::make_pair(r.path,r.batch);
    auto completed=done.find(key);
    CounterPair& p=completed==done.end()?pending[key]:completed->second;
    bool present=r.rx?p.rx:p.tx;
    uint64_t old=r.rx?p.received:p.sent;
    if(present) { if(old!=r.count) throw std::runtime_error("Conflicting counter duplicate"); return; }
    if(r.rx) {p.rx=true;p.received=r.count;} else {p.tx=true;p.sent=r.count;}
    if(!p.rx || !p.tx) return;
    CounterPair pair=p; pending.erase(key); done[key]=pair;
    auto& state=states[r.path];
    if(fast && pair.received>pair.sent) throw std::runtime_error("Simultaneous RX exceeds source acceptance");
    if(!fast && pair.received>pair.sent) {interrupt(r.path);return;}
    if(int64_t(r.batch)<=state.latest) return;
    if(int64_t(r.batch)>state.latest+1) interrupt(r.path);
    state.latest=r.batch;
    uint64_t missing=0;
    if(fast) {
      if(!state.previous_counts) {
        state.previous_counts=true;state.last_sent=pair.sent;state.last_received=pair.received;return;
      }
      if(pair.sent<state.last_sent || pair.received<state.last_received)
        throw std::runtime_error("Cumulative delivery counters regressed");
      uint64_t sent=pair.sent-state.last_sent,received=pair.received-state.last_received;
      state.last_sent=pair.sent;state.last_received=pair.received;
      bool severe=sent>=32 && received*5<=sent*3;
      if(!severe) {state.history.clear();return;}
      missing=sent-received;state.history.emplace_back(now,missing,r.batch);
      if(state.history.size()<2) return;
      while(state.history.size()>2) state.history.pop_front();
    } else {
      missing=pair.sent-pair.received;
      state.history.emplace_back(now,missing,r.batch);
      if(pair.sent>0 && missing==0) {
        if(++state.clean>=2) {state.armed=true;state.history.clear();}
      } else state.clean=0;
    }
    uint64_t total=0;for(auto h:state.history) total+=std::get<1>(h);
    if((!fast && !state.armed) || total<2) return;
    state.armed=false;
    std::vector<uint32_t> evidence;
    for(auto h:state.history) if(std::get<1>(h)) evidence.push_back(std::get<2>(h));
    std::string signal=fast?"global_early":"global_mature";
    if(callbackOnly) {if(onAlarm) onAlarm(r.path,now,total,evidence,"data_service");return;}
    if(hybrid_alarmed_paths.count(r.path)) return;
    hybrid_alarmed_paths.insert(r.path);
    hybrid_alarm_log << "{\"rule_version\":\"" << (fast?"hybrid-early-v4":"hybrid-delivery-v4") << "\",\"path\":\"" << r.path/2
      << '/' << (r.path%2?'B':'A') << "\",\"decision_t_ns\":" << now
      << ",\"missing_packets\":" << total << ",\"evidence_batches\":[";
    bool first=true; for(auto h:state.history) if(std::get<1>(h)) {
      hybrid_alarm_log << (first?"":",") << std::get<2>(h); first=false;
    }
    hybrid_alarm_log << "],\"claim\":\"Observed delivery deficit under the declared guard; cause unresolved\"}\n";
    hybrid_alarm_log.flush();
    if(onAlarm) onAlarm(r.path,now,total,evidence,signal);
  }
};
