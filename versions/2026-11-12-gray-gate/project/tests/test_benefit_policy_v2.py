import dataclasses
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from limerlab.benefit_policy import (BenefitInputV2, HelperSample, RelaySample,
    ServiceSample, evaluate_benefit, evaluate_benefit_v2)


class BenefitPolicyV2Tests(unittest.TestCase):
    def case(self, **changes):
        value = BenefitInputV2(0, 8_000_000, 0,
            ServiceSample(.5, known=True), ServiceSample(.01, known=True),
            RelaySample(65536, (304., 59460., 304.), 1007680., known=True),
            setup_ns=4092160., helpers=(HelperSample(known=True), HelperSample(known=True)))
        return dataclasses.replace(value, **changes)

    def test_observed_tail_persistence_overrides_misleading_aggregate_ack_rate(self):
        x = self.case(b_bytes=288, b_no_progress_ns=8_000_000,
                      service_b=ServiceSample(.5034416, known=True))
        old, new = evaluate_benefit(x), evaluate_benefit_v2(x)
        self.assertLess(old['stay_ns'], 1000.)
        self.assertFalse(old['should_switch'])
        self.assertEqual(new['source_stay_ns'], 8_000_000.)
        self.assertTrue(new['should_switch'])

    def test_resumed_chunk_progress_clears_stall_forecast(self):
        x = self.case(b_bytes=288, b_no_progress_ns=100_000,
                      service_b=ServiceSample(.5034416, known=True))
        new = evaluate_benefit_v2(x)
        self.assertEqual(new['tail_forecast_ns'], 0.)
        self.assertLess(new['stay_ns'], 1000.)
        self.assertFalse(new['should_switch'])

    def test_zero_remaining_work_does_not_need_helper_reports(self):
        self.assertEqual(evaluate_benefit_v2(self.case(
            b_bytes=0, helpers=(None, None)))['reason'], 'no_remaining_work')

    def test_pipelined_physical_release_does_not_wait_for_final_ack(self):
        x = self.case()
        new, old = evaluate_benefit_v2(x), evaluate_benefit(x)
        self.assertAlmostEqual(new['relay_bytes_per_ns'], 65536 / 59460.)
        self.assertGreater(new['relay_bytes_per_ns'], 4*old['relay_bytes_per_ns'])
        legacy_release = evaluate_benefit_v2(dataclasses.replace(x, pipelined=False))
        self.assertEqual(legacy_release['relay_bytes_per_ns'], old['relay_bytes_per_ns'])

    def test_source_confirmation_window_still_limits_long_ack_cycles(self):
        result = evaluate_benefit_v2(self.case(relay=RelaySample(
            65536, (304., 59460., 304.), 10_000_000., known=True)))
        self.assertAlmostEqual(result['relay_bytes_per_ns'], 32*65536 / 10060068.)

    def test_first_chunk_and_subchunk_always_pay_complete_cycle(self):
        for size in (144, 65536):
            result = evaluate_benefit_v2(self.case(b_bytes=size, setup_ns=0.,
                service_b=ServiceSample(0., known=True)))
            self.assertAlmostEqual(result['switch_ns'], 1067748.)
            self.assertTrue(result['should_switch'])

    def test_helper_critical_work_can_reverse_source_only_benefit(self):
        x = self.case(b_bytes=8_000_000,
            helpers=(HelperSample(500_000_000, .5, known=True), HelperSample(known=True)))
        result = evaluate_benefit_v2(x)
        self.assertLess(result['source_switch_ns'], result['source_stay_ns'])
        self.assertGreater(result['helper_switch_ns'], result['helper_stay_ns'])
        self.assertFalse(result['should_switch'])

    def test_zero_work_helper_has_no_invented_background_burden(self):
        result = evaluate_benefit_v2(self.case())
        self.assertEqual(result['helper_stay_ns'], 0.)
        self.assertEqual(result['helper_switch_ns'], 0.)
        self.assertTrue(result['should_switch'])

    def test_paid_known_fresh_reports_required(self):
        for report in (None, HelperSample(), HelperSample(age_ns=20_000_001, known=True)):
            result = evaluate_benefit_v2(self.case(helpers=(report, HelperSample(known=True))))
            self.assertEqual(result['reason'], 'paid_helper_reports_required')
            self.assertFalse(result['should_switch'])

    def test_unresolved_helper_work_is_not_free_capacity(self):
        result = evaluate_benefit_v2(self.case(helpers=(
            HelperSample(1, 0., known=True), HelperSample(known=True))))
        self.assertEqual(result['reason'], 'helper_service_unresolved')
        self.assertFalse(result['should_switch'])

    def test_no_loss_moving_short_work_can_stay(self):
        result = evaluate_benefit_v2(self.case(b_bytes=65536,
            service_b=ServiceSample(.25, known=True), b_no_progress_ns=500_000))
        self.assertFalse(result['should_switch'])

    def test_no_loss_long_slow_work_can_switch(self):
        result = evaluate_benefit_v2(self.case(b_bytes=16_000_000,
            service_b=ServiceSample(.25, known=True), b_no_progress_ns=500_000))
        self.assertTrue(result['should_switch'])

    def test_observed_recovered_service_can_stay(self):
        result = evaluate_benefit_v2(self.case(b_bytes=65536,
            service_b=ServiceSample(1.2, known=True), b_no_progress_ns=0))
        self.assertFalse(result['should_switch'])

    def test_missing_representative_probe_fails_closed(self):
        result = evaluate_benefit_v2(self.case(relay=RelaySample()))
        self.assertFalse(result['should_switch'])
        self.assertTrue(result['probe_required'])

    def test_a_can_finish_pending_work_during_coordination(self):
        result = evaluate_benefit_v2(self.case(b_bytes=288, pending_bytes=65536,
            b_no_progress_ns=8_000_000, service_b=ServiceSample(.5, known=True)))
        self.assertEqual(result['relay_assigned_bytes'], 288.)

    def test_invalid_v2_parameters_rejected(self):
        for changes in (dict(source_window=0), dict(b_no_progress_ns=-1),
                        dict(helpers=(HelperSample(-1), HelperSample()))):
            with self.assertRaises(ValueError):
                evaluate_benefit_v2(self.case(**changes))

    def test_native_decision_rejects_stale_or_unleased_paid_reports(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        root = Path(__file__).resolve().parents[1]
        program = r'''#include "src/simulator/recovery/benefit_policy.h"
#include <deque>
#include <map>
#include <vector>
#include <sstream>
#include <iostream>
namespace limer { namespace engine {
uint64_t PeerNow(){return 100000000;} unsigned Dest(unsigned s){return s+4;}
unsigned Key(unsigned s,unsigned d,unsigned l){return (s*16+d)*3+l;}
unsigned SourceWindow(){return 32;}bool Idle(unsigned){return true;}
bool benefitV2=true,feedback=true,sharedHelpers=true,pipelined=true;
unsigned phase=0;uint64_t Bytes=65536,ChunkBytes=65536,canaryBytes=65536;
struct Chunk{bool done=false;unsigned lane=1;uint64_t acked=65248,lastProgress=92000000,allocated=80000000;};
struct Report{uint64_t own_remaining_bytes=0;double own_bytes_per_ns=0;
 uint64_t sampled_ns=95000000,delivered_ns=96000000,version=7,lease_id=5,report_id=10;
 bool known=true;unsigned rank=1,phase=0;};
struct Binding{unsigned hs=1,hd=5;uint64_t probeBytes=65536,health=99000000,version=7,leaseId=5;
 bool lending=true,loanReady=true,releasing=false;
 std::array<double,3> probeLegNs{{304,59460,304}};std::array<Report,2> helperReports;};
std::array<Binding,16> binding;std::array<std::vector<uint64_t>,16> cohort;
std::map<uint64_t,Chunk> chunks;std::array<uint64_t,16> offered;
uint64_t nextOffset[16][2]{};struct Control{uint64_t free_ns=0;}control;
std::map<unsigned,std::deque<std::pair<uint64_t,uint64_t>>> ackSamples;
std::map<unsigned,std::pair<uint64_t,uint64_t>> canarySamples;
std::ostringstream policyLog;
}}
#include "src/simulator/recovery/decision.h"
int main(){using namespace limer::engine;
 cohort[0]={1};chunks[1]=Chunk{};offered[0]=Bytes;
 ackSamples[Key(0,4,0)].push_back({95000000,5000000});
 ackSamples[Key(0,4,1)].push_back({95000000,5000000});
 for(unsigned i=0;i<10;++i){binding[0]=Binding{};auto& b=binding[0];b.helperReports[1].rank=5;
  if(i==1)b.helperReports[0].lease_id=6;
  if(i==2)b.helperReports[0].rank=2;
  if(i==3)b.helperReports[0].delivered_ns=100000001;
  if(i==4)b.helperReports[0].sampled_ns=97000000;
  if(i==5)b.releasing=true;if(i==6)b.loanReady=false;if(i==7)b.lending=false;
  if(i==8)b.helperReports[0].phase=1;if(i==9)b.helperReports[0].version=8;
  std::cout<<BenefitAllows(0,"probe_complete")<<"\n";
 }
}'''
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'decision.cc';binary=Path(tmp)/'decision'
            source.write_text(program)
            subprocess.run([compiler,'-std=c++14','-I',str(root),str(source),'-o',str(binary)],
                           check=True,capture_output=True,text=True)
            rows=subprocess.run([str(binary)],check=True,capture_output=True,text=True).stdout.splitlines()
        self.assertEqual(rows,['1']+['0']*9)

    def test_native_reference_matches_all_v2_components(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('C++ compiler unavailable')
        root = Path(__file__).resolve().parents[1]
        fields = ('stay_ns', 'switch_ns', 'gain_ns', 'relay_bytes_per_ns',
                  'source_stay_ns', 'source_switch_ns', 'helper_stay_ns',
                  'helper_switch_ns', 'relay_assigned_bytes', 'tail_forecast_ns')
        cases = [self.case(a_bytes=65536*(i%3), b_bytes=144 if i%3 else 8_000_000,
            pending_bytes=1_000_000 if i%5 else 0,
            service_b=ServiceSample(.01*i if i%4 else 0., known=i!=3),
            b_no_progress_ns=i*1_000_000, source_window=8 if i%2 else 32,
            pipelined=not bool(i%2),
            helpers=(HelperSample(i*1_000_000, .5, known=i!=7),
                     HelperSample(known=True))) for i in range(20)]
        program = ['#include "src/simulator/recovery/benefit_policy.h"',
                   '#include <iostream>', '#include <iomanip>',
                   'int main(){using namespace limer::recovery;std::cout<<std::setprecision(17);']
        for x in cases:
            program.append('{BenefitInputV2 x;')
            for name in ('a_bytes','b_bytes','pending_bytes','b_no_progress_ns',
                         'source_window','setup_ns'):
                program.append('x.{}={};'.format(name, getattr(x, name)))
            program.append('x.pipelined={};'.format(int(x.pipelined)))
            for name in ('service_a','service_b'):
                value=getattr(x,name)
                program.append('x.{}={{{},{},{}}};'.format(name, value.bytes_per_ns,
                    value.age_ns, int(value.known)))
            program.append('x.relay.sample_bytes=65536;x.relay.leg_ns={{304.,59460.,304.}};'
                           'x.relay.final_ack_ns=1007680.;x.relay.known=true;')
            for i,h in enumerate(x.helpers):
                program.append('x.helpers[{}]={{{},{},{},{}}};'.format(i,
                    h.own_remaining_bytes,h.own_bytes_per_ns,h.age_ns,int(h.known)))
            program.append('auto d=EvaluateBenefitV2(x);std::cout<<d.should_switch<<" "<<d.reason')
            program.append(''.join('<<" "<<d.'+key for key in fields)+'<<"\\n";}')
        program.append('}')
        with tempfile.TemporaryDirectory() as tmp:
            source=Path(tmp)/'policy.cc';binary=Path(tmp)/'policy'
            source.write_text('\n'.join(program))
            subprocess.run([compiler,'-std=c++14','-I',str(root),str(source),'-o',str(binary)],
                           check=True,capture_output=True,text=True)
            rows=subprocess.run([str(binary)],check=True,capture_output=True,text=True).stdout.splitlines()
        for x,row in zip(cases,rows):
            expected=evaluate_benefit_v2(x);values=row.split()
            self.assertEqual(bool(int(values[0])),expected['should_switch'])
            self.assertEqual(values[1],expected['reason'])
            for key,raw in zip(fields,values[2:]):
                actual=float(raw)
                if math.isinf(expected[key]): self.assertEqual(actual,expected[key])
                else: self.assertAlmostEqual(actual,expected[key],delta=max(1e-8,abs(actual)*1e-12))
        self.assertEqual(len(rows),len(cases))


if __name__ == '__main__':
    unittest.main()
