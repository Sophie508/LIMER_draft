# Simulation scope and continuation pipeline

## Authorized objective

**[User decision, 2026-10-10, after M8]** Severe slowdown also belongs to the
detection target. Detect a delivery impairment and then evaluate whether changing
routes pays; an alarm does not itself mandate switching. Permanent loss is not
the only eligible impairment. Preserve the original M8 loss-only ledger, control
labels and strict verdict. New impairment evaluations require prospective labels
and an explicit severity/duration envelope; no retroactive pass is claimed.

**[User decision, 2026-10-10]** Implement and evaluate LIMER in simulation;
real switch/NIC, GPU experiments and deployment are outside the project scope.
Continue autonomously on CPU infrastructure, including otakotak scratch.

**[User requirement]** Keep <100 ms detection as the core target. Study when
switching routes pays off and coordinated execution correctness alongside it.
Rapid gray-fault detection remains an unresolved constraint until supported by
registered results; simulation scope does not waive it.

**[User decision, M12]** The prospective empirical acceptance target is at
least 95% correctly localized alarms STRICTLY below 100 ms in EACH registered
eligible fault condition. Every registered fault attempt stays in its own
condition's denominator: late, missed and unverified outcomes do not disappear.
Controls never inflate recall. Negative-control, pre-event and unaffected-path
alarms are reported separately and must be zero in this acceptance matrix.
This fraction is not a population guarantee or a 95% confidence lower bound.
The earlier all-attempt/no-unavailable-report strict gate remains separately
reported rather than retroactively rewritten.

## Existing evidence and the next branch

**[Fact, archived M7 results]** The frozen passive TCP candidate produces 72/80
correctly localized decisions below 100 ms; eight are late. The separately
registered 40 ms reordering stress produces false alarms in 3/5 trials.
This candidate cannot yet support the full intended detector claim.

**[Fact, current architecture]** Mininet executes a framed CPU/TCP ring and
coordinated route plans. The separate SimAI/ns-3 adapters replay network work;
static routing benefits do not include a working dynamic detector or its costs.
Mininet wall-clock timings and discrete-event simulated timings are different
measurements and must not be pooled.

**[Fact, M9–M11]** Native pending-flow execution, causal sender ACK-progress
reports and an observable cost-to-commit loop are now implemented. The first
finite fourteen-ring comparison selects switch with faster B and stay with
slower B. These configured-rate deterministic scenes do not establish the
weak-loss/idle/report-noise envelope or replace the original M8 verdict. See
[online results](m10_m11_online_results.md).

**[Proposal]** Compare three signal choices before the next implementation:

1. Retune passive TCP feedback. This is cheap to implement, but archived tails
   include feedback arriving after the deadline, and reordering can imitate
   loss. Retuning alone does not address that missing information.
2. Add two-ended packet observations in the packet-level simulator. This is the
   preferred design investigated in M8: model sender/receiver records, their
   delivery latency and their completeness, then distinguish delayed delivery
   from missing delivery under an explicit delay envelope. This is a bounded
   hypothesis under evaluation, not an achieved detector or a zero-cost
   telemetry assumption. The implemented frozen candidate completes 200 primary
   and 25 stress trials: 139/160 primary loss decisions are timely, with weak-loss
   failures and excess-delay alarms retained. See [M8 results](m8_batch_observation_results.md).
3. Add processing-aware probes. This covers idle paths but adds traffic and
   responder load. Probe loss/delay must follow the same modeled path and
   competing queues as data; independent fault-free probe paths are invalid.

An ideal instantaneous drop counter may be evaluated as an explicitly labeled
oracle upper bound. It cannot serve as the main detector result.

## Pipeline and gates

1. **Baseline:** preserve the pinned OptCC/SimAI reconstruction, gates and
   missing-author-artifact limitations. Reuse completed runs before launching
   more. Keep paper numbers, local reconstruction and LIMER emulation separate.
2. **Observation model:** inspect existing ns-3 send/receive traces and transport
   callbacks. Specify packet identity, outstanding bytes, queue/processing delay,
   sampling period, report loss and report transport cost. Keep hidden fault
   state in the scorer. State both what changes and the expected observation
   before each experiment.
3. **Detector candidate:** implement one bounded hypothesis on those observations.
   Test weak loss (0.5/1/2/5%), rate reduction, healthy traffic, congestion,
   endpoint pause, reordering, sparse/idle traffic and repeated episodes. A lack
   of observations is an unavailable result, not a healthy zero.
4. **Fresh validation:** freeze code and parameters after development. Register
   independent seeds and controls; retain setup failures, late decisions, misses
   and all observed false alarms. Report all-attempt timely localization,
   per-condition p95 with misses as infinity, and the strict all-run gate.
   Detection uses simulated fault time to simulated decision time in ns-3;
   scorer access to that time does not give it to the algorithm.
5. **Switch/stay cost:** separately compare fixed stay, fixed localized switch,
   oracle switch and the candidate policy. Charge detection/observation,
   coordination, drain/replay of unfinished work and alternate-path congestion.
   Use matched workload/fault realizations where supported and disclose seed
   coupling. Judge total remaining-work completion time, not just post-switch
   steady-state throughput.
6. **Execution:** verify no lost/duplicate payloads, matching route versions and
   fingerprints, and correct ownership of unfinished transfers. Preserve the
   existing Mininet correctness evidence separately; it does not automatically
   validate a new ns-3 execution model. Label network-DAG completion distinctly
   from numerical tensor AllReduce.
7. **Paper and scale:** write frozen measured outcomes into the existing
   Overleaf document, including failed conditions and assumptions. Expand
   simulated scale only after the small dynamic loop is correct and its
   runtime/memory budget is measured. Real-device transfer is outside scope.

## Decisions that still warrant human input

Ask Sophie if evidence requires changing the <100 ms target, accepting an
observation assumption that materially narrows the research claim, or choosing
between conflicting scientific objectives. Routine implementation choices and
CPU experiments are already authorized. No hardware-access question is required.

Git changes remain reviewable and uncommitted. Show the diff for review before
committing; obtain explicit permission before every push.

## M12 measured outcome and remaining constraint

**[Fact, frozen independent validation]** The hybrid one-hop UDP detector has
698/700 correctly localized alarms strictly below 100 ms. Every one of the
13 prospectively registered eligible fault conditions reaches at least 95%;
40 controls have zero alarms. Two late decisions remain in their denominators.
The separate all-trial/no-unavailable-report gate remains FAIL.

**[Fact, scope and cost]** This outcome assumes size-independent packet faults,
aligned simulation clocks and configured collector service. Probes consume
17.92 Mb/s/path; collection consumes 4.9152 Mb/s. A matched selective-fault
supplement realizes business damage in every pair but yields only 5/20 timely
selective alarms versus 20/20 IID alarms. Same path does not establish probe
representativeness. Broader fast gray-fault coverage therefore remains an
unresolved constraint, rather than an achieved general guarantee.

**[Next required simulation]** Charge the observation traffic and reporting
inside the collective workload, connect the detector to the existing cost
evaluator and transaction, and assess impairment-to-completion outcomes.
A bounded detector pass does not validate that joint system. Preserve the
selective-fault failure when choosing representative observations. See
[M12 audited results](m12_hybrid_detection_results.md).
