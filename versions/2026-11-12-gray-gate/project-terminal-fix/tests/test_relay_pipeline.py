"""Native resource-lifetime regression using the production header."""
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'python'))
from limerlab.config import Scenario


class PipelineTests(unittest.TestCase):
    def test_mode_validation(self):
        for kw in ({'helper_mode':'unbounded'}, {'relay_completion':'skip_ack'},
                   {'helper_mode':'shared','replacement_lifetime':'persistent'}):
            with self.assertRaises(ValueError): Scenario(**kw)
        self.assertEqual(Scenario().relay_completion,'final_ack')

    @unittest.skipUnless(shutil.which('c++'), 'requires C++ compiler')
    def test_actual_resource_header_preserves_ownership_until_final_ack(self):
        resources=(ROOT/'src/simulator/recovery/resources.h').as_posix()
        completion=(ROOT/'src/simulator/runtime/completion.h').as_posix()
        source=r'''
#include <array>
#include <vector>
#include <map>
#include <sstream>
#include <stdexcept>
#include <algorithm>
#include <cassert>
#include <cstdint>
namespace limer { namespace engine {
bool pipelined=true,sharedHelpers=false,benefitV2=false;uint64_t now=100,jobDone=0;
uint64_t ChunkBytes=65536;unsigned phase=0,phases=30,finished=0,phaseChunks=512;
std::array<bool,16> loanTx{},loanRx{};
unsigned tx[16][5]{},rx[16][5]{},buffers[16]{};
std::array<unsigned,16> active{},outDone{},inDone{};
std::array<uint64_t,16> idleAt{};double rates[16][3]{};
std::ostringstream peers;
struct Route {uint64_t id=1,chunk=1,p=0,epoch=1,length=65536,started=1,delivered=0;
 unsigned src=0,dst=4,hs=1,hd=5,rail=1;bool relay=true,probe=false,reserved=false;};
struct Chunk {uint64_t epoch=1;unsigned src=0,dst=4,lane=1;bool done=false,migrated=false;};
std::map<uint64_t,Route> routes;std::map<uint64_t,Chunk> chunks;
uint64_t PeerNow(){return now;}
bool Idle(unsigned){return false;}
void Progress(Chunk&,uint64_t,uint64_t){}
void PeerEvent(const char*,const Chunk&,uint64_t){}
void Pump(unsigned){};void StartPhase(){}
void ReleaseLendingV2(unsigned){}
uint64_t NanoSeconds(unsigned n){return n;}
struct Simulator {
template<class F>static void ScheduleWithContext(unsigned,uint64_t,F,unsigned){}
template<class F>static void Schedule(uint64_t,F){}
};
}}
'''+f'#include "{resources}"\n#include "{completion}"\n'+r'''
using namespace limer::engine;
int main(){
 for(bool mode:{false,true}){
  pipelined=mode;now=100;routes[1]=Route{};chunks[1]=Chunk{};active[0]=1;
  Reserve(routes[1],true);assert(tx[1][3]==1&&buffers[1]==1);
  ReleaseDelivered(routes[1]);
  assert(!chunks[1].done&&active[0]==1); // Delivery cannot claim logical completion.
  assert(tx[1][3]==(mode?0:1)&&buffers[1]==(mode?0:1));
  bool rejected=false;try{ReleaseDelivered(routes[1]);}catch(const std::logic_error&){rejected=true;}
  assert(rejected); // Duplicate delivery cannot release twice.
  now=1000100;FinalAck(1);
  assert(chunks[1].done&&active[0]==0&&routes.empty());
  assert(tx[1][3]==0&&rx[5][3]==0&&buffers[1]==0&&buffers[5]==0);
 }
 sharedHelpers=true;loanTx[1]=true;loanRx[5]=true;
 Route own;own.relay=false;own.src=1;own.dst=5;
 tx[1][3]=rx[5][3]=3;
 assert(!Capacity(own)); // Owner keeps three of four credits during lending.
 Route relay;
 assert(Capacity(relay)); // One physical slot remains, not an extra link.
 tx[1][3]=4;assert(!Capacity(relay));
}
'''
        with tempfile.TemporaryDirectory() as tmp:
            cpp=Path(tmp)/'regression.cc';binary=Path(tmp)/'regression'
            cpp.write_text(source)
            build=subprocess.run(['c++','-std=c++14',str(cpp),'-o',str(binary)],capture_output=True,text=True)
            self.assertEqual(build.returncode,0,build.stderr)
            run=subprocess.run([str(binary)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)


if __name__=='__main__': unittest.main()
