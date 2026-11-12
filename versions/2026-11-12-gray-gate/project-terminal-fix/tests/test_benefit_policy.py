import dataclasses
import math
from pathlib import Path
import shutil
import subprocess
import tempfile
import unittest

from limerlab.benefit_policy import (
    BenefitInput, RelaySample, ServiceSample, evaluate_benefit, finish_time)


class BenefitPolicyTests(unittest.TestCase):
    def case(self, **changes):
        value = BenefitInput(
            a_bytes=65536, b_bytes=65536, pending_bytes=0,
            service_a=ServiceSample(1.0, known=True),
            service_b=ServiceSample(0.0, known=True),
            relay=RelaySample(65536, (1000., 100000., 1000.),
                              1000000., known=True),
            setup_ns=4_000_000.)
        return dataclasses.replace(value, **changes)

    def test_observed_blackhole_can_switch(self):
        result = evaluate_benefit(self.case())
        self.assertTrue(result['should_switch'])
        self.assertTrue(math.isinf(result['stay_ns']))
        self.assertTrue(math.isfinite(result['switch_ns']))

    def test_short_work_and_working_direct_route_stays(self):
        result = evaluate_benefit(self.case(
            service_b=ServiceSample(.1, known=True)))
        self.assertFalse(result['should_switch'])
        self.assertGreater(result['switch_ns'], result['stay_ns'])

    def test_long_severe_degradation_can_switch(self):
        result = evaluate_benefit(self.case(
            b_bytes=8_000_000, service_b=ServiceSample(.01, known=True)))
        self.assertTrue(result['should_switch'])

    def test_recovered_transient_stays_without_fault_end_oracle(self):
        result = evaluate_benefit(self.case(
            service_b=ServiceSample(1.0, known=True)))
        self.assertFalse(result['should_switch'])

    def test_slow_local_helpers_stay(self):
        result = evaluate_benefit(self.case(
            b_bytes=8_000_000, service_b=ServiceSample(.1, known=True),
            relay=RelaySample(65536, (40_000_000., 100_000., 40_000_000.),
                              1_000_000., known=True)))
        self.assertFalse(result['should_switch'])

    def test_unknown_or_stale_candidate_needs_paid_probe(self):
        for relay in (RelaySample(),
                      RelaySample(1024, (1., 1., 1.), known=True),
                      RelaySample(65536, (1., 1., 1.), age_ns=20_000_001,
                                  known=True)):
            result = evaluate_benefit(self.case(relay=relay))
            self.assertFalse(result['should_switch'])
            self.assertTrue(result['probe_required'])

    def test_missing_helpers_does_not_probe(self):
        result = evaluate_benefit(self.case(helper_ready=False))
        self.assertEqual(result['reason'], 'helpers_not_ready')
        self.assertFalse(result['probe_required'])

    def test_unknown_or_stale_direct_service_cannot_commit(self):
        for service in (ServiceSample(), ServiceSample(1., 20_000_001, True)):
            result = evaluate_benefit(self.case(service_b=service))
            self.assertEqual(result['reason'], 'insufficient_service_evidence')
            self.assertFalse(result['should_switch'])

    def test_remaining_owned_a_can_hide_b_gain(self):
        result = evaluate_benefit(self.case(
            a_bytes=100_000_000, b_bytes=1_000_000,
            service_b=ServiceSample(.1, known=True)))
        self.assertFalse(result['should_switch'])
        self.assertEqual(result['stay_ns'], result['switch_ns'])

    def test_final_ack_and_credit_limit_are_charged(self):
        result = evaluate_benefit(self.case())
        self.assertAlmostEqual(result['relay_bytes_per_ns'],
                               4 * 65536 / 1102000.)
        slow_ack = evaluate_benefit(self.case(relay=RelaySample(
            65536, (1000., 100000., 1000.), 10_000_000., known=True)))
        self.assertLess(slow_ack['relay_bytes_per_ns'], result['relay_bytes_per_ns'])

    def test_one_chunk_pays_full_three_leg_and_final_ack_latency(self):
        result = evaluate_benefit(self.case(a_bytes=0, setup_ns=0.))
        self.assertAlmostEqual(result['switch_ns'], 1_102_000.)

    def test_more_credits_do_not_shorten_first_chunk_latency(self):
        one = evaluate_benefit(self.case(a_bytes=0, setup_ns=0., relay=RelaySample(
            65536, (1000., 100000., 1000.), 1000000., parallel_chunks=1, known=True)))
        four = evaluate_benefit(self.case(a_bytes=0, setup_ns=0.))
        self.assertAlmostEqual(one['switch_ns'], four['switch_ns'])

    def test_144_byte_tail_pays_complete_first_relay_ack_cycle(self):
        result = evaluate_benefit(self.case(a_bytes=0, b_bytes=144, setup_ns=0.))
        self.assertAlmostEqual(result['switch_ns'], 1_102_000.)
        self.assertGreaterEqual(result['switch_ns'], 1_000_000.)
        self.assertTrue(result['should_switch'])

    def test_144_byte_tail_cannot_scale_away_coordination(self):
        result = evaluate_benefit(self.case(a_bytes=0, b_bytes=144, setup_ns=4_000_000.))
        self.assertAlmostEqual(result['switch_ns'], 5_102_000.)

    def test_recovering_144_byte_tail_does_not_justify_switch(self):
        result = evaluate_benefit(self.case(
            a_bytes=0, b_bytes=144, setup_ns=0.,
            service_b=ServiceSample(.001, known=True)))
        self.assertFalse(result['should_switch'])

    def test_pipeline_cannot_exceed_bottleneck_leg(self):
        result = evaluate_benefit(self.case(relay=RelaySample(
            65536, (1., 1_000_000., 1.), 0., parallel_chunks=100, known=True)))
        self.assertEqual(result['relay_bytes_per_ns'], 65536 / 1_000_000.)

    def test_larger_probe_does_not_scale_away_fixed_latency(self):
        large = evaluate_benefit(self.case(relay=RelaySample(
            131072, (1000., 100000., 1000.), 1000000., known=True)))
        normal = evaluate_benefit(self.case())
        self.assertEqual(large['relay_bytes_per_ns'], normal['relay_bytes_per_ns'])

    def test_adaptive_pending_can_use_a_during_setup(self):
        self.assertAlmostEqual(finish_time(0, 0, 1000, 1., 1., 1000.), 1000.)
        self.assertAlmostEqual(finish_time(0, 0, 3000, 1., 1., 1000.), 2000.)

    def test_all_done_does_not_probe(self):
        result = evaluate_benefit(self.case(a_bytes=0, b_bytes=0))
        self.assertEqual(result['reason'], 'no_remaining_work')
        self.assertFalse(result['should_switch'])

    def test_small_gain_below_margin_stays(self):
        x = self.case(a_bytes=0, b_bytes=1_000_000,
                      service_b=ServiceSample(.1, known=True), setup_ns=0.)
        # Make the predicted improvement positive but below the 1 ms margin.
        x.relay = RelaySample(65536, (100., 65536 / .105, 100.), 0., known=True)
        result = evaluate_benefit(x)
        self.assertGreater(result['gain_ns'], 0.)
        self.assertFalse(result['should_switch'])

    def test_invalid_inputs_rejected(self):
        for changes in (dict(b_bytes=-1), dict(setup_ns=-1),
                        dict(service_b=ServiceSample(float('nan'), known=True))):
            with self.assertRaises(ValueError):
                evaluate_benefit(self.case(**changes))

    def test_native_policy_matches_python_reference(self):
        compiler = shutil.which('c++')
        if not compiler:
            self.skipTest('native C++ compiler unavailable')
        root = Path(__file__).resolve().parents[1]
        program = r'''
#include "src/simulator/recovery/benefit_policy.h"
#include <iomanip>
#include <iostream>
int main(){
 using namespace limer::recovery;
 std::cout<<std::setprecision(17);
 for(unsigned i=0;i<17;++i){
  BenefitInput x;x.a_bytes=65536*(i+1);x.b_bytes=131072*(i+1);
  x.pending_bytes=i%3?1000000:0;
  x.service_a.bytes_per_ns=.5;x.service_a.known=true;
  x.service_b.bytes_per_ns=i%4?.01*i:0;x.service_b.known=i!=3;
  x.relay.sample_bytes=i==5?1024:65536;
  x.relay.leg_ns={{1000.,100000.+i*1000.,1000.}};
  x.relay.final_ack_ns=1000000.;x.relay.known=true;
  x.relay.age_ns=i==7?20000001:0;
  x.setup_ns=4000000.;x.helper_ready=i!=9;
  if(i==16){x.a_bytes=0;x.b_bytes=144;x.pending_bytes=0;}
  auto d=EvaluateBenefit(x);
  std::cout<<d.should_switch<<' '<<d.probe_required<<' '<<d.reason<<' '
           <<d.stay_ns<<' '<<d.switch_ns<<' '<<d.relay_bytes_per_ns<<'\n';
 }
}'''
        with tempfile.TemporaryDirectory(prefix='limer-benefit-parity-') as tmp:
            source = Path(tmp) / 'policy.cc'
            executable = Path(tmp) / 'policy'
            source.write_text(program)
            subprocess.run([compiler, '-std=c++14', '-I', str(root), str(source),
                            '-o', str(executable)], check=True,
                           capture_output=True, text=True)
            rows = subprocess.run([str(executable)], check=True,
                                  capture_output=True, text=True).stdout.splitlines()
        self.assertEqual(len(rows), 17)
        for i, row in enumerate(rows):
            result = evaluate_benefit(BenefitInput(
                a_bytes=0 if i == 16 else 65536*(i+1),
                b_bytes=144 if i == 16 else 131072*(i+1),
                pending_bytes=1_000_000 if i % 3 and i != 16 else 0,
                service_a=ServiceSample(.5, known=True),
                service_b=ServiceSample(.01*i if i % 4 else 0., known=i != 3),
                relay=RelaySample(1024 if i == 5 else 65536,
                                  (1000., 100000.+i*1000., 1000.), 1000000.,
                                  age_ns=20_000_001 if i == 7 else 0, known=True),
                setup_ns=4_000_000., helper_ready=i != 9))
            fields = row.split()
            self.assertEqual(int(fields[0]), result['should_switch'])
            self.assertEqual(int(fields[1]), result['probe_required'])
            self.assertEqual(fields[2], result['reason'])
            for key, value in zip(('stay_ns', 'switch_ns', 'relay_bytes_per_ns'),
                                  fields[3:]):
                number = float(value)
                if math.isinf(result[key]):
                    self.assertTrue(math.isinf(number))
                else:
                    self.assertAlmostEqual(number, result[key],
                                           delta=max(1e-9, abs(number)*1e-12))


if __name__ == '__main__':
    unittest.main()
