"""Exercise production V2 lease callbacks and paid helper report transport."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start=text.index(signature);end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


class HelperLeaseV2Tests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'), 'requires C++ compiler')
    def test_release_report_reacquisition_and_phase_guards(self):
        state=(ROOT/'src/simulator/runtime/state.h').read_text()
        structures=state[state.index('struct HelperSnapshot'):state.index('static std::array<Binding,16> binding;')]
        proxy=(ROOT/'src/simulator/recovery/proxy.h').read_text()
        selected=['static void ReleaseLendingDone(', 'static void ReleaseLendingV2(',
                  'static void LendReadyV2(', 'static bool RequestLendingV2(',
                  'static void LogHelperSnapshot(', 'static void DeliverHelperSnapshot(',
                  'static void SampleHelperSnapshot(', 'static void CollectHelperReports(']
        source=r'''
#include <array>
#include <deque>
#include <map>
#include <vector>
#include <sstream>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <queue>
#include <string>
'''+structures+r'''
std::array<Binding,16> binding;
bool benefitV2=true,sharedHelpers=true,allow=false;
unsigned phase=2,phases=4,gateCalls=0,configured=0,pumps=0;uint64_t serial=1,now=100000000,jobDone=0;
std::array<bool,16> loanTx{},loanRx{};
std::array<uint64_t,16> plannedTx{},plannedRx{},offered{};
std::array<std::vector<uint64_t>,16> cohort;
std::array<std::deque<std::pair<uint64_t,uint64_t>>,16> helperOwnAckSamples;
uint64_t Bytes=65536*16,ChunkBytes=65536;
struct Route{bool relay=true,reserved=true;unsigned src=0,p=2;};
struct Chunk{bool done=false;uint64_t acked=0;};
std::map<uint64_t,Route> routes;std::map<uint64_t,Chunk> chunks;
std::ostringstream controls,helperReports;
uint64_t PeerNow(){return now;}uint64_t NanoSeconds(uint64_t n){return n;}
unsigned Dest(unsigned s){return s<12?s+4:(s+1)%4;}
uint64_t Message(const char* event,unsigned rank,uint64_t version){
 uint64_t at=now+1007680;controls<<now<<','<<at<<','<<event<<','<<rank<<','<<phase<<','<<version<<",96\n";return at;}
void Pump(unsigned){++pumps;}
bool BenefitAllows(unsigned,const char*){++gateCalls;return allow;}
void Configure(unsigned){++configured;}
struct Event{uint64_t at,order;std::function<void()> fn;
 bool operator<(const Event& b)const{return at>b.at||(at==b.at&&order>b.order);}};
std::priority_queue<Event> events;uint64_t order=0;
struct Simulator{template<class F,class... Args>static void Schedule(uint64_t dt,F f,Args... args){
 events.push(Event{now+dt,++order,std::bind(f,args...)});}};
void runUntil(uint64_t t){while(!events.empty()&&events.top().at<=t){auto e=events.top();events.pop();now=e.at;e.fn();}now=t;}
'''+ '\n'.join(function(proxy,signature) for signature in selected)+r'''
int main(){
 // Lending cannot become visible before both paid requests arrive.
 assert(!RequestLendingV2(0));auto lease=binding[0].leaseId;
 assert(!loanTx[1]&&!loanRx[5]&&binding[0].pending);
 runUntil(now+1007679);assert(!loanTx[1]);runUntil(now+1);
 assert(loanTx[1]&&loanRx[5]&&binding[0].loanReady);
 binding[0].version=++serial;binding[0].pending=true;
 offered[1]=65536;cohort[1].push_back(100);chunks[100]={false,32768};
 helperOwnAckSamples[1].push_back({now,32768});
 auto start=now;CollectHelperReports(0);
 assert(gateCalls==0&&binding[0].helperReportsReady==0);
 runUntil(start+1007680); // Helpers sampled, reports still in transit.
 assert(gateCalls==0&&binding[0].helperReportsReady==0);
 chunks[100].acked=65536; // Later local progress cannot alter the sent payload.
 runUntil(start+2015360);
 assert(gateCalls==1&&binding[0].releasing&&loanTx[1]);
 assert(binding[0].helperReports[0].own_remaining_bytes==Bytes-32768);
 assert(binding[0].helperReports[0].own_bytes_per_ns==32768/10000000.);
 assert(binding[0].helperReports[0].lease_id==lease);
 // A live route is never erased by an admission lease release.
 routes[77]=Route{};runUntil(now+1007680);
 assert(binding[0].releasing&&loanTx[1]&&routes[77].reserved);
 routes[77].reserved=false;runUntil(now+50000);
 assert(!binding[0].releasing&&!binding[0].lending&&!loanTx[1]&&!loanRx[5]);
 assert(plannedTx[1]==0&&plannedRx[5]==0&&routes.count(77));
 assert(helperReports.str().find("DELIVERED")!=std::string::npos);
 assert(controls.str().find("LEND_RELEASED")!=std::string::npos);
 // Old callbacks cannot release or enable a newly acquired lease.
 assert(!RequestLendingV2(0));auto replacement=binding[0].leaseId;assert(replacement!=lease);
 runUntil(now+1007680);ReleaseLendingDone(0,phase,lease);
 assert(binding[0].leaseId==replacement&&loanTx[1]);
 auto stale=binding[0].helperReports[0];stale.phase=phase;stale.version=binding[0].version;
 stale.lease_id=lease;stale.delivered_ns=now;stale.report_id=999;
 DeliverHelperSnapshot(0,0,stale);assert(binding[0].helperReportsReady==0);
 // A phase reset makes both report and release callbacks harmless.
 unsigned oldPhase=phase++;binding[0]=Binding{};binding[0].p=phase;
 loanTx.fill(false);loanRx.fill(false);plannedTx.fill(0);plannedRx.fill(0);
 LendReadyV2(0,oldPhase,replacement);ReleaseLendingDone(0,oldPhase,replacement);
 DeliverHelperSnapshot(0,0,stale);
 assert(!loanTx[1]&&!loanRx[5]&&binding[0].helperReportsReady==0);
 assert(helperReports.str().find("STALE")!=std::string::npos);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp=Path(tmp)/'lease.cc';binary=Path(tmp)/'lease';cpp.write_text(source)
            compiled=subprocess.run(['c++','-std=c++14',str(cpp),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(compiled.returncode,0,compiled.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)

if __name__=='__main__':unittest.main()
