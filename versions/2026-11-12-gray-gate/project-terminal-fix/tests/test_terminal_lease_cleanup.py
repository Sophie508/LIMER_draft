"""Production callback regressions for charged final-phase helper cleanup."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


def function(text, signature):
    start = text.index(signature)
    end = text.index('{', start) + 1
    depth = 1
    while depth:
        depth += (text[end] == '{') - (text[end] == '}')
        end += 1
    return text[start:end]


def harness(root):
    state = (root/'src/simulator/runtime/state.h').read_text()
    types = state[state.index('struct PeerChunk'):state.index('struct Leg')]
    types += state[state.index('struct HelperSnapshot'):state.index('static std::array<Binding,16> binding;')]
    proxy = (root/'src/simulator/recovery/proxy.h').read_text()
    completion = (root/'src/simulator/runtime/completion.h').read_text()
    selected = ['static void ReleaseLendingDone(', 'static void ReleaseLendingV2(',
                'static void LendReadyV2(', 'static bool RequestLendingV2(']
    header = (root/'src/simulator/control/channel.h').as_posix()
    return r'''
#include <array>
#include <map>
#include <vector>
#include <sstream>
#include <algorithm>
#include <cassert>
#include <cstdint>
#include <functional>
#include <queue>
#include <string>
'''+f'#include "{header}"\n'+types+r'''
std::array<Binding,16> binding;
bool benefitV2=true,sharedHelpers=true,pipelined=true;
unsigned phase=3,phases=4,phaseChunks=512,finished=0,pumps=0,workLaunches=0,starts=0;
uint64_t serial=100500,now=0,jobDone=0,ChunkBytes=65536;
std::array<bool,16> loanTx{},loanRx{};
std::array<uint64_t,16> plannedTx{},plannedRx{},idleAt{};
std::array<unsigned,16> active{},outDone{},inDone{};
double rates[16][3]{};
std::map<uint64_t,Route> routes;std::map<uint64_t,PeerChunk> chunks;
std::ostringstream controls;
limer::control::ControlFifo control;
uint64_t PeerNow(){return now;}uint64_t NanoSeconds(uint64_t n){return n;}
unsigned Dest(unsigned s){return s<12?s+4:(s+1)%4;}
uint64_t Message(const char* event,unsigned rank,uint64_t version){
 auto at=control.send(now,96);
 controls<<now<<','<<at<<','<<event<<','<<rank<<','<<phase<<','<<version<<",96\n";return at;}
void Pump(unsigned){++pumps;if(phase<phases)++workLaunches;}
void StartPhase(){++starts;}
bool Idle(unsigned s){return outDone[s]==phaseChunks&&inDone[s]==phaseChunks;}
void Progress(PeerChunk& c,uint64_t ack,uint64_t){c.acked=ack;}
void PeerEvent(const char*,const PeerChunk&,uint64_t){}
void Reserve(Route& r,bool add){r.reserved=add;}
struct Event{uint64_t at,order;std::function<void()> fn;
 bool operator<(const Event& b)const{return at>b.at||(at==b.at&&order>b.order);}};
std::priority_queue<Event> events;uint64_t order=0;
struct Simulator{
 template<class F,class... Args>static void Schedule(uint64_t dt,F f,Args... args){
  events.push(Event{now+dt,++order,std::bind(f,args...)});}
 template<class F,class... Args>static void ScheduleWithContext(unsigned,uint64_t dt,F f,Args... args){
  Schedule(dt,f,args...);}
};
void runUntil(uint64_t t){while(!events.empty()&&events.top().at<=t){
 auto e=events.top();events.pop();now=e.at;e.fn();}now=t;}
'''+ '\n'.join(function(proxy,s) for s in selected)+'\n'+function(completion,'static void FinalAck(')+r'''
void seed(unsigned src,unsigned hs,unsigned hd,uint64_t lease){
 auto& b=binding[src];b.p=phase;b.hs=hs;b.hd=hd;b.leaseId=lease;
 b.lending=true;b.loanReady=true;loanTx[hs]=true;loanRx[hd]=true;
 plannedTx[hs]=lease;plannedRx[hd]=lease;
}
void finish(uint64_t t,unsigned src=0){
 now=t;finished=16*phaseChunks-1;active[src]=1;
 PeerChunk c{};c.id=900000;c.src=src;c.dst=Dest(src);c.p=phase;
 chunks[c.id]=c;Route r{};r.id=900001;r.chunk=c.id;r.src=src;r.dst=c.dst;
 r.p=phase;r.length=65536;r.started=now-100000;r.reserved=true;
 routes[r.id]=r;FinalAck(r.id);
 assert(jobDone==t&&phase==phases&&starts==0&&chunks[c.id].done);
}
unsigned count(const std::string& word){unsigned n=0;auto s=controls.str();
 for(size_t pos=0;(pos=s.find(word,pos))!=std::string::npos;pos+=word.size())++n;return n;}
void emptyLease(unsigned src,unsigned hs,unsigned hd){
 assert(!binding[src].lending&&!binding[src].releasing&&!binding[src].loanReady);
 assert(binding[src].leaseId==0&&!loanTx[hs]&&!loanRx[hd]);
 assert(!plannedTx[hs]&&!plannedRx[hd]);}
int main(int argc,char** argv){
 assert(argc==2);std::string mode=argv[1];
 if(mode=="exact"||mode=="probe"){
  seed(0,1,5,100500);now=84390790;ReleaseLendingV2(0);
  if(mode=="probe"){Route r{};r.id=888;r.src=0;r.p=3;r.relay=true;r.probe=true;r.reserved=true;routes[r.id]=r;}
  finish(85251871);assert(count("RELEASE_TX")==1&&count("RELEASE_RX")==1);
  runUntil(85406149);assert(loanTx[1]&&binding[0].releasing);
  runUntil(85406150);
  if(mode=="probe"){
   assert(loanTx[1]&&routes.at(888).reserved&&count("LEND_RELEASED")==0);
   runUntil(85506150);assert(loanTx[1]&&routes.at(888).reserved);
   Reserve(routes.at(888),false);runUntil(85556150);assert(routes.count(888));
  }
  emptyLease(0,1,5);assert(count("LEND_RELEASED")==1&&control.wire_bytes==192);
  assert(controls.str().find(",LEND_RELEASED,0,3,100500,0")!=std::string::npos);
  assert(workLaunches==0);
 }else if(mode=="absent"){
  seed(0,1,5,100500);seed(7,6,10,100501);finish(85251871,15);
  assert(binding[0].releasing&&binding[7].releasing);
  assert(count("RELEASE_TX")==2&&count("RELEASE_RX")==2);
  assert(controls.str().find("85251871,86259551,RELEASE_TX,1,3,100500,96")!=std::string::npos);
  runUntil(87251871);emptyLease(0,1,5);emptyLease(7,6,10);
  assert(count("LEND_RELEASED")==2&&control.wire_bytes==384&&workLaunches==0);
 }else if(mode=="pending"){
  now=85250871;assert(!RequestLendingV2(0));auto lease=binding[0].leaseId;
  assert(!loanTx[1]&&binding[0].pending);finish(85251871,15);
  assert(binding[0].releasing&&!loanTx[1]);
  runUntil(86266231);assert(loanTx[1]&&binding[0].loanReady&&binding[0].releasing);
  assert(count("LEND_ACTIVE")==1&&count("LEND_RELEASED")==0&&workLaunches==0);
  assert(controls.str().find(",LEND_ACTIVE,0,3,"+std::to_string(lease)+",0")!=std::string::npos);
  runUntil(86281591);emptyLease(0,1,5);
  assert(count("LEND_RELEASED")==1&&control.wire_bytes==384&&workLaunches==0);
 }else if(mode=="stale"){
  phase=2;seed(0,1,5,101);binding[0].releasing=true;
  phase=3;binding[0].p=3;binding[0].leaseId=102;
  plannedTx[1]=plannedRx[5]=102;
  ReleaseLendingDone(0,2,101);LendReadyV2(0,2,101);
  assert(binding[0].leaseId==102&&loanTx[1]&&controls.str().empty());
  phase=4;jobDone=85251871;
  ReleaseLendingDone(0,3,101);LendReadyV2(0,3,101);
  assert(binding[0].leaseId==102&&loanTx[1]&&controls.str().empty());
  binding[0].releasing=false;ReleaseLendingDone(0,3,102);LendReadyV2(0,3,102);
  assert(binding[0].leaseId==102&&controls.str().empty());
  binding[0].releasing=true;jobDone=0;ReleaseLendingDone(0,3,102);
  assert(binding[0].leaseId==102&&controls.str().empty());
 }else if(mode=="legacy"){
  benefitV2=false;seed(0,1,5,100500);finish(85251871,15);
  assert(binding[0].lending&&!binding[0].releasing&&controls.str().empty());
  assert(control.wire_bytes==0&&workLaunches==0);
 }else assert(false);
}
'''


@unittest.skipUnless(shutil.which('c++'), 'requires C++ compiler')
class TerminalLeaseCleanupTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.TemporaryDirectory()
        cls.addClassCleanup(cls.tmp.cleanup)
        cls.binaries = {}
        for label, root in [('fixed',ROOT),('frozen',ROOT.parent/'project')]:
            source=Path(cls.tmp.name)/(label+'.cc')
            binary=Path(cls.tmp.name)/label
            source.write_text(harness(root))
            built=subprocess.run(['c++','-std=c++14',str(source),'-o',str(binary)],capture_output=True,text=True)
            if built.returncode:
                raise AssertionError(built.stderr)
            cls.binaries[label]=binary

    def run_case(self, name, fixed=True):
        run=subprocess.run([str(self.binaries['fixed' if fixed else 'frozen']),name],capture_output=True,text=True)
        if fixed:
            self.assertEqual(run.returncode,0,run.stderr)
        else:
            self.assertNotEqual(run.returncode,0,'Frozen callbacks unexpectedly passed '+name)

    def test_exact_paid_release_after_final_completion(self):
        self.run_case('exact')

    def test_physical_probe_must_drain_before_terminal_release(self):
        self.run_case('probe')

    def test_final_completion_sends_missing_releases_for_all_held_leases(self):
        self.run_case('absent')

    def test_paid_pending_lending_then_release_preserve_phase_and_fifo(self):
        self.run_case('pending')

    def test_stale_phase_reacquired_lease_and_unrequested_release_are_rejected(self):
        self.run_case('stale')

    def test_legacy_terminal_behavior_is_unchanged(self):
        self.run_case('legacy')

    def test_frozen_callbacks_reproduce_all_four_terminal_failures(self):
        for case in ('exact','probe','absent','pending'):
            with self.subTest(case=case):
                self.run_case(case,fixed=False)


if __name__=='__main__':
    unittest.main()
