"""Use the production helper planner to avoid competing relay directions."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

ROOT=Path(__file__).resolve().parents[1]


def function(path):
    text=path.read_text();start=text.index('static bool RequestLending(unsigned src){')
    end=text.index('{',start)+1;depth=1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]


class HelperSelectionTests(unittest.TestCase):
    @unittest.skipUnless(shutil.which('c++'),'requires C++')
    def test_two_fault_directions_use_disjoint_helpers(self):
        harness=r'''
#include <array>
#include <algorithm>
#include <cstdint>
#include <cassert>
struct Binding {bool lending=false,loanReady=false,pending=false;
 unsigned hs=0,hd=0,p=0;uint64_t version=0;};
std::array<Binding,16> binding;
std::array<uint64_t,16> plannedTx{},plannedRx{};
unsigned phase=3;uint64_t serial=1;
unsigned Dest(unsigned s){return s<12?s+4:(s+1)%4;}
uint64_t PeerNow(){return 100;}
uint64_t Message(const char*,unsigned,uint64_t){return 1000100;}
void LendReady(unsigned,unsigned,uint64_t){}
uint64_t NanoSeconds(uint64_t n){return n;}
struct Simulator {template<class F>static void Schedule(uint64_t,F,unsigned,unsigned,uint64_t){}};
'''
        main=r'''
int main(){
 assert(!RequestLending(0));assert(!RequestLending(15));
 assert(binding[0].hs==1&&binding[0].hd==5);
 assert(binding[15].hs==12&&binding[15].hd==2);
 assert(binding[0].hs!=binding[15].hd);
 assert(binding[0].pending&&!binding[0].loanReady);
}
'''
        files=[(ROOT/'src/simulator/recovery/proxy.h',True)]
        # The negative control is the original throughput-v1 helper selector.
        # A sibling gray-gate project-v1 has a different, already-correct selector.
        previous=ROOT.parent.parent/'2026-11-12-throughput/project-v1/src/simulator/recovery/proxy.h'
        if previous.exists():files.insert(0,(previous,False))
        with tempfile.TemporaryDirectory() as tmp:
            for index,(path,expected) in enumerate(files):
                cpp=Path(tmp)/f'check{index}.cc';binary=Path(tmp)/f'check{index}'
                cpp.write_text(harness+function(path)+main)
                build=subprocess.run(['c++','-std=c++14',str(cpp),'-o',str(binary)],capture_output=True,text=True)
                self.assertEqual(build.returncode,0,build.stderr)
                run=subprocess.run([str(binary)],capture_output=True,text=True)
                self.assertEqual(run.returncode==0,expected,run.stderr)


if __name__=='__main__':unittest.main()
