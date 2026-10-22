# M13 business-traffic coverage diagnosis

## Question and verified answer

“General gray-fault detection remains unresolved” means that an observation
which is healthy for a small probe can coexist with actual business damage.
It does not define a measurable promise to detect every possible fault.
The concrete outstanding case is the frozen M12 size-selective supplement:
20/20 IID cases are timely, but only 5/20 selective cases are timely. Both
arms realize 123 business drops, with zero no-damage pairs. The selective
arm has no probe drops. Main registered M12 acceptance remains unchanged.

## Read-only diagnosis completed

The script uses only delivered observable reports for counter pairing. Fault
path/time enter its final scorer, not the observation procedure. It verifies
archived input/truth hashes and complete independently audited ledgers.
No candidate parameter, frozen source, binary or recorded verdict is changed.

In the 20 selective cases, mature reports provide at least ONE positive
accepted-minus-delivered batch deficit before fault+100 ms in 17/20 cases;
at least TWO missing packets are available in only 7/20. The frozen rule
actually alarms promptly in 5/20. Its two-active-clean-batch reset can discard
pending weak-loss evidence. These facts distinguish rule loss of evidence
from availability of the underlying observations.

17/20 is a retrospective evidence-availability bound for an immediate
one-deficit rule USING THESE MATURE REPORTS. It is not a tested candidate,
a new validation result or an impossibility bound for all earlier reports,
sequence observations or measurement architectures. Mature reporting waits
50 ms before sampling receiver batches; batching and report transport add
time. Merely lowering this rule's threshold cannot reach 19/20 here.

The diagnostic also reads all 740 primary lifecycles. In those registered
controls, it finds zero mature positive-deficit rows. This does not validate
an altered detector or quantify a population false-alarm rate. The existing
early service lane still supplies severe-overload detections that a mature
missing-count rule cannot provide.

Evidence: /Users/sophie/Documents/LIMER_WORK_2026-10-10/m13_observability_diagnostic.json
Script: /Users/sophie/Documents/LIMER_WORK_2026-10-10/m13_observability_diagnostic.py
Server originals: /home/suliu/scratch/LIMER_WORK_2026-10-10/logs/m13_observability_diagnostic.json

## Research routes and choice

1. Retune the mature threshold/reset only. Cheap and worth a separately
   versioned ablation, but the delivered-record bound already rules out
   this alone reaching 95% in the observed selective supplement.
2. Add causal business-traffic observations. Selected next direction:
   separate business and probe accepted/delivered progress, and export
   receiver sequence gaps plus later gap closure. Account for FIFO delays,
   endpoint source pauses and non-loss reordering. Healthy probe credit must
   not stand in for business progress. New fields and reports must be charged.
3. Use probes matching application packet sizes and traffic treatment.
   Complementary hypothesis for sparse traffic, not a universal replacement
   for observing business. Do not target the artificial >128-byte cutoff.
   Fix a packet-size mixture from the actual workload before new development,
   conserve the offered byte budget and disclose any reduced packet opportunity.

This design direction is a hypothesis, not an implemented or verified repair.
Active streams add measurement traffic; passive streams require real traffic.
RFC 7799 defines this distinction and requires considering measurement load:
https://www.rfc-editor.org/rfc/rfc7799.html . The custom LIMER protocol is not
an implementation of that RFC or TWAMP.

## Acceptance before claiming a repair

- Preserve all M12 native sources, verdicts and the original 20 matched pairs.
- Before implementation, write the concrete observable schema, message byte
  cost, report service and candidate rules; only causal network/application
  observations may reach the detector. Injector state remains scorer-only.
- Develop on fresh IDs, with the business-only selective fault as a primary
  positive rather than merely a discarded boundary. Include both packet-size
  selective and flow/processing-selective cases, so representative padding
  alone cannot be advertised as broad coverage.
- Keep healthy, source-pause, mild-congestion and reordering controls. Include
  sparse reordering as well as 25%-packet reordering to test ambiguity with
  weak loss. Severity and duration envelopes must be explicit before launch.
- Unavailable idle business observations remain unknown; retain registrations
  and misses. Never move the injection-to-decision clock to first observed harm.
- After development, freeze source/binary/parameters and register fresh seeds.
  At least 95% correctly localized decisions STRICTLY below 100 ms must hold
  separately in each declared eligible condition, with all attempts retained.
  Keep false alarms and observation costs as separate acceptance constraints.
- Native/report-only replay, conservation and input provenance must pass.
  Integrating the new observer into the collective route loop is another
  measured step, not implied by an isolated detection result.

No universal <100-ms claim is possible from an unspecified observable/fault
scope: two situations producing identical observations through the deadline
cannot be reliably distinguished using those observations alone. This is a
logical observation, not a theorem that the concrete research target is
impossible. The practical objective is broader, explicit and tested coverage.


## Follow-up implementation and evidence

This diagnosis is the retained pre-implementation record. M13 now implements
class-separated business observations, exact receiver gap reconstruction,
representative probe interventions and a causal traffic-compensating policy.
The fixed-budget failures remain. An explicit 10 Gb/s observation envelope
passes independent validation; its same-report baseline also passes, so the
observation intervention is the main demonstrated improvement. See
[the measured results](m13_business_detection_results.md) and
[the prospective plan and amendments](m13_business_detection_plan.md).
Joint collective-route integration remains a separate experiment.
