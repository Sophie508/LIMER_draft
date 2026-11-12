"""Exercise the production phase initializer with native state and stub events."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]


class PhaseLifecycleTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'), 'requires a C++ compiler')
    def test_original_lanes_and_gate_are_reset_at_each_phase(self):
        text = (ROOT / 'src/simulator/scheduling/dispatcher.h').read_text()
        start = text.index('static void StartPhase(){')
        end, depth = start + len('static void StartPhase(){'), 1
        while depth:
            depth += (text[end] == '{') - (text[end] == '}')
            end += 1
        function = text[start:end]
        harness = r'''
#include <array>
#include <vector>
#include <sstream>
#include <cassert>
#include <cstdint>
struct Binding {bool pending=false,ready=false,configured=false,disabled=false;
 unsigned hs=0,hd=0,p=0;uint64_t health=0,version=0,activation=0,nextAttempt=0;};
std::array<Binding,16> binding;
unsigned phase=1,finished=0;uint64_t phaseStart=0,serial=100;
bool phaseScoped=true;
std::array<uint64_t,16> offered{},aFinished{},idleAt{};
std::array<unsigned,16> active{},outDone{},inDone{},turn{};
std::array<std::vector<uint64_t>,16> cohort;
uint64_t nextOffset[16][2]{},ChunkBytes=65536;
double rates[16][3]{},credits[16][3]{};unsigned launches[16][3]{};
std::ostringstream statusLog,controls;
uint64_t PeerNow(){return 123;}
void Pump(unsigned){};uint64_t NanoSeconds(unsigned n){return n;}
struct Simulator {template<class F>static void ScheduleWithContext(unsigned,uint64_t,F,unsigned){}};
'''
        main = r'''
int main(){
 auto seed=[](){binding[0].disabled=true;binding[0].configured=true;
  binding[0].ready=true;binding[0].pending=true;binding[0].activation=40;
  binding[0].health=50;binding[0].version=7;
  for(unsigned l=0;l<3;++l){launches[0][l]=9;credits[0][l]=99;rates[0][l]=1;}};
 seed();StartPhase();
 assert(!binding[0].disabled && !binding[0].configured && !binding[0].ready);
 assert(!binding[0].pending && binding[0].activation==0 && binding[0].health==0);
 assert(binding[0].p==phase && binding[0].version>100);
 for(unsigned l=0;l<3;++l)assert(launches[0][l]==0 && credits[0][l]==0);
 assert(rates[0][2]==0 && rates[0][0]==1);
 assert(controls.str().find("RESET_TO_AB")!=std::string::npos);
 // Historical comparison mode retains its previous binding semantics.
 phaseScoped=false;seed();StartPhase();
 assert(binding[0].disabled && binding[0].configured && !binding[0].ready);
 assert(launches[0][2]==0 && launches[0][0]==9);
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp, binary = Path(tmp)/'phase.cc', Path(tmp)/'phase'
            cpp.write_text(harness + function + main)
            built = subprocess.run(['c++','-std=c++14',str(cpp),'-o',str(binary)], capture_output=True,text=True)
            self.assertEqual(built.returncode,0,built.stderr)
            result = subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(result.returncode,0,result.stderr)


if __name__ == '__main__':
    unittest.main()
