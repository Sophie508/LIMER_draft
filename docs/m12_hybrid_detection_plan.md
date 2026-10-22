# M12 hybrid delivery-deficit detection implementation plan

> Execute sequentially using the executing-plans workflow. Existing authorization
> covers CPU simulation and reversible code edits. No commit or push is authorized.

**Goal:** At least 95% correctly localized decisions strictly below 100 ms in
EACH registered eligible fault condition; count late, missed and unverified
attempts in the denominator. Report false alarms separately. Preserve all older
strict-gate verdicts and loss-only stress labels.

**Architecture:** Extend the isolated M8 packet simulation with continuous small
UDP probes sharing exactly the data socket, queue, receiver and error model.
Keep the frozen 10-ms batches, 50-ms RX guard and two-deficit rule. Evaluate the
rule natively at delivered-report events; independently reproduce every alarm
from the exported causal observations in Python. Use a separately charged
10-Mb/s, 1-ms management FIFO with three identical 64-byte copies per sample.
Missing reports remain unknown. This is not native RDMA collective integration.

**Tech stack:** Existing pinned ns-3 CPU backend, rootless Docker on otakotak,
Python 3.12 host, C++ and unittest. No new dependency or host configuration.

## Evidence and alternatives

- Verified M8 low-rate 0.5% loss: 7/20 timely; all deadline failures have fewer
  than two reported deficits before the deadline. Passive threshold changes
  cannot manufacture observations on idle paths.
- Option A: lower the threshold/guard. Rejected for this first candidate because
  ordinary 40-ms reordering must remain a negative control.
- Option B (selected): add costed same-path probes and reduce collection delay.
  This tests an observation-budget explanation rather than claiming novelty.
- Option C: transfer SprayCheck's passive adaptive-routing statistics. Its
  abstract explicitly relies on traffic spraying; the current slot/one-hop
  model has no matching routing distribution. No direct-transfer assumption.

Sources: https://www.rfc-editor.org/rfc/rfc9341.html (two-ended loss counters,
correlation and timing constraints); https://www.rfc-editor.org/rfc/rfc5357.html
(active test traffic); https://arxiv.org/abs/2605.03702 (SprayCheck abstract).
The custom 12-byte batch identifiers retain many simultaneous batches and are
NOT the two-color RFC wire protocol; 50-ms guard exceeds the 10-ms batch period.
These sources motivate components, not this algorithm's efficacy or novelty.

## Frozen development v1 model

- Probe rate: 25,000 packets/s/path, 64 bytes ON WIRE (10 payload + 12 mark +
  8 UDP + 20 IPv4 + 14 pinned PPP). Cost: 12.8 Mb/s/path, including during idle.
- Probes start at 1 ms and stop at 250 ms, exactly the observation workload.
  Never start at fault time. Data pauses do not pause probes.
- Data packets stay 1500 bytes on wire. Source-enqueue vs destination-delivery
  accounting includes queues. Size-independent IID injected loss applies to
  BOTH traffic types. This assumption does not cover size-selective failures.
- 50 batches over 500 ms; stop at 600 ms. Reports charge all copies, including
  lost copies, through one FIFO. 2400 reports/lifecycle = 153.6 KB;
  steady load 2.4576 Mb/s = 24.576% of the 10-Mb/s collector.
- Detector accepts only path,batch,side,count,sample_t_ns,arrival_t_ns, where
  count combines accepted data and probes. Fault configuration never enters it.
- Severe impairment positives: 80-ms reorder of 25% of packets and overload
  (80% additional competing traffic). These new positive labels are prospective;
  historical M8 loss-only false alarms remain unchanged.
- Negative controls: nominal, 10%-capacity competing traffic, 60-ms DATA pause,
  and 40-ms reordering. Data pauses represent idle application, not link failure.
- Explicit boundaries: no permanent-loss attribution; no arbitrary report delay
  guarantee; no false-alarm distribution claim from deterministic controls;
  one-hop UDP detection only, no tensor reduction or route actuation.

## Tasks and verification

- [x] Add simulation/LimerHybridObservation.cc and batch_deficit_observer.h.
  Instrument separate data/probe accepted/delivered/wire counts, per-batch
  snapshots and report FIFO offers; emit native alarms at actual delivery time.
- [x] Add limer_v0/hybrid_delivery.py (frozen rule with a new version),
  simulation/run_hybrid_observation.py (registration, audit, scoring, costs),
  simulation/build_hybrid_observation.py (isolated m12 backend only).
- [x] Test denominator/p95, unknown duplicate reports, wire/probe accounting,
  FIFO tamper rejection and native-vs-Python alarm agreement. Retain baseline.
- [x] Before development launch, state changes/expected outcome. Register fresh
  run IDs 30000+, 10 trials each weak-low 0.5%, sparse, idle, report-loss; one
  per other loss/severe/control condition. Development is tuning evidence.
- [x] If development fails, preserve it and write amendment BEFORE changing
  model/rule. No validation-seed tuning or pooling conditions.
- [x] Freeze code/binary/libraries before independent validation. Fresh IDs
  40000+, 60 trials per each of eight profile/loss conditions and sparse,
  idle, 10% report loss; 20 per severe condition; 5 per negative control/profile.
  Acceptance: EACH fault condition >=95% timely, no pre-event/unaffected alarms,
  no negative-control alarms; complete conservation and exact native replay.
  Wilson 95% intervals accompany empirical rates; 60 trials alone need not
  establish a population lower confidence bound of 95%.
- [x] Add boundaries (slow collector, no-probe idle, selective fault) separately;
  never drop their failures or include easy controls in recall denominators.
- [x] Independently audit registration/source/input/binary/library hashes and all
  alarms; run full meaningful test suite. Publish diff and bounded results.
- [x] Update existing Overleaf from fresh readback only after results are verified;
  preserve old verdicts, distinguish this detector from the M11 native loop.

Expected result (hypothesis, not verified): increased packet opportunities and
shorter collection delay improve weak-loss and idle timely recall. Probe cost
may induce delivery delay; healthy/congestion controls test that effect directly.
No experiment is allowed to consume private drop counters as its detector input.

## Amendment 1: prospective development v2 (before launch)

Development v1 has an observed sparse-loss delay of 101.805999 ms. Preserve the
entire v1 registration and all runs; this is tuning evidence, not acceptance.
Use 35,000 probes/s/path (17.92 Mb/s, 17.92% of a 100-Mb/s link). The 80-Mb/s
primary data + probes now occupy 97.92% before background traffic. This cost is
material and must be reported rather than called negligible.

Keep mature RX samples at closure+50 ms with the unchanged two-deficit rule.
Add early RX samples at closure+10 ms, using the SAME cumulative batch counters.
The early lane alarms after TWO consecutive complete batches with at least
32 transmitted packets and >=40% delivery deficit. Gaps, unknown observations
and nonsevere batches break the streak. It does not use fault time or identity.
The 40% threshold deliberately exceeds the 25% independently delayed packets
in the ordinary 40-ms reorder control; this is a hypothesis to test, not proof
of immunity. Either lane can alarm; retain the first alarm per path per lifecycle.
Multiple-episode rearming is outside this validation.

The observer schema adds the observable `guard_ns`: 0 for the common TX sample,
10,000,000 for early RX and 50,000,000 for mature RX. Common TX reports go to
both lanes. Each of the 1200 samples has three charged report copies, for
230.4 KB/lifecycle and 3.6864 Mb/s steady collector load (36.864% of 10 Mb/s).
Native decisions and Python replay must agree exactly across both lanes.

Use a SEPARATE m12b backend while v1 finishes, preserving the v1 executable and
logs. Development v2 fresh run IDs 31000+; add five overload and five 80-ms
reorder trials, plus the previous development weak/sparse/idle/report-loss tests.
The validation matrix stays 740 registrations, fresh 40000+ run IDs. Do not
launch validation until development engineering gates and all per-condition
95%/negative-control gates pass. Boundaries use fresh 50000+ IDs. Schedule at
most four independent one-core/1-GiB containers in bounded batches; process
wall time never enters simulated detection metrics.

## Amendment 2: development v3 service-rate lane (before launch)

V1 overload was measured at 124.068598 ms, confirming that the 50-ms guard
alone can wait too long after a queue starts growing. V2 is retained and still
running. Code review finds a separate risk in v2: per-batch age deficits can
reach 40% under modest sustained queueing even if delivery rate stays high.
With 80 Mb/s data, 17.92 Mb/s probes and a 10-Mb/s background, mild overload is
caused partly by the observer itself. Do not label that negative control severe.

Replace ONLY the early lane's per-batch age counts with cumulative accepted and
cumulative delivered packet counters. Each early pair has TX at closure and RX
at closure+10 ms. Compare successive complete, adjacent pairs: alarm after TWO
consecutive windows with TX delta >=32 packets and RX delta <=60% of TX delta.
A gap/expired/invalid pair or nonsevere window breaks the streak; a gap also
resets the rate reference. Source pauses can never count as service collapse.
RX cumulative credit may exceed TX sampled earlier because of the 10-ms offset;
this is valid. Both deltas must be monotonic. The early claim is impaired
packet delivery SERVICE, not 40% permanent loss. Mature lane stays unchanged.

Early and mature lanes now have separate TX samples, identified by guard_ns
10 ms and 0 respectively. Schema remains the same seven observable fields;
the guard describes the configured lane, not a hidden cause. There are 1600
samples and 4800 report copies/lifecycle: 307.2 KB, 4.9152 Mb/s steady load,
49.152% of the declared 10-Mb/s collector. Probe cost stays 17.92 Mb/s/path.
Use isolated m12c backend and development IDs 32000+. V3 is prospective, never
an overwrite of v1/v2. The 740-trial validation matrix and 40000+ fresh run IDs
are unchanged. These remain isolated one-hop IID-loss/queue-model simulations.

## Amendment 3: scheduling and verified v2 negative control

V2 completed 65/65 engineering gates but FAILED scientific acceptance because
its low-congestion negative control alarmed once. That result validates the
code-review concern recorded before v3. Preserve its full frozen audit.
Read-only capacity verification found 128 CPU cores, about 4 load average and
428 GiB available memory. Raise the bounded simulation schedule from four to
at most eight single-core/1-GiB containers. This changes only wall-clock
throughput, not packet seeds, simulated schedules, costs or acceptance criteria.
Register worker count and all executable/source hashes. V3 development uses
four workers; validation can use eight after v3 passes.

Boundary selective-loss case uses 1-Mb/s data, 0.5% IID loss applied only to
packets >128 bytes, making 64-byte probes unrepresentative. The original
same-path/queue remains intact; this explicit boundary cannot be hidden by the
size-independent main model. The delayed-report boundary observes until 800 ms
so the last 120-ms-delayed report drains; all primary lifecycles stay 600 ms.

## Research check during frozen validation (no tuning)

Read SprayCheck's primary paper introduction, design, evaluation, limitations
and conclusion: https://arxiv.org/html/2605.03702v1. Its signal relies on
predictable packet spraying; Section 6 sketches an access-link count/NACK
extension, so access-link observation is prior art. The paper warns probes may
not represent application faults. Retain size-selective boundaries and do not
convert training-iteration timing into a 100-ms comparison or claim superiority.

Idealized opportunity calculation (not a performance prediction): under IID
per-packet p=0.005, P(K>=2)=1-(1-p)^n-n*p*(1-p)^(n-1). The smallest n giving
>=0.95 is 947. In a hypothetical 40-ms usable observation interval, 80-Mb/s
1500-byte packets provide only 266 complete packets, while 35,000 probes/s
provide 1400 opportunities and ideal P(K>=2)=0.9928004. Queueing, report loss,
reset rules and fault phase still require actual prospective validation.

## Amendment 4: development v4 aligned service windows (before launch)

Frozen validation v1 (v3 algorithm) has a high-throughput data-pause control
with eight early-lane alarms at a 53.000326-ms pause onset. It therefore FAILS
scientific acceptance regardless of timely fault recall. Continue all 740
registrations and audit its complete ledger; do not delete or tune its seeds.
The offset early counters compared TX service in one 10-ms interval with RX
service in the NEXT interval. A pause edge can create two artificial severe
windows despite a healthy link. V3 development did not sample this edge.

V4 samples BOTH early cumulative counters at closure+10 ms, on the same
simulated time. The detector rejects unequal/early sample timestamps and RX
credit exceeding simultaneous source acceptance. Mature lane, rate threshold,
two-window rule, probes, costs, collector, primary faults and 95% gates remain
unchanged. This is a prospective measurement correction, not a relabeling.
Add regression coverage for ordinary 1-ms FIFO delivery across source-pause
phases from 50 to 60 ms and explicit rejection of the old mismatched schedule.

Use isolated m12d backend. Development IDs 33000+, with ten each of every
negative-control/profile condition (137 lifecycles total); development pause
phases cover the interval rather than relying on one draw. Only after these
gates pass, freeze v4 and validate on fresh IDs 41000+ (740 unchanged conditions).
These phase/RNG draws are independent of v1's 40000+ seed range. Boundary v2
uses 51000+. The old v1 boundary remains separately available.

Verified capacity permits at most 16 independent single-core/1-GiB simulation
containers across the retained v3 and new v4 campaigns, each campaign at most
eight. A separate one-core build uses an isolated backend. This changes only
wall-clock scheduling; simulated schedules and scientific gates stay frozen.
Archive all source generations before replacing local working copies.

## Amendment 5: retained v4 build/setup failure (before corrected launch)

The first eight v4 development attempts FAILED engineering replay; all other
129 registrations remain UNRUN. The copied build retained the v3 executable:
source file timestamps from the local machine were older than copied server
objects, so incremental compilation skipped the modified native source.
Preserve this registration, binary, source and eight raw lifecycles as a setup
failure, not scientific v4 measurements. Do not reuse its 33000+ run IDs.

Correct the build in a fresh m12e backend: touch staged source/header using the
server's clock before compilation and reject a binary lacking the v4 native
rule-version strings. Use development tag v4b, fresh 34000+ IDs and exactly the
same aligned v4 algorithm and 137-condition development schedule. Validation
41000+ and boundary 51000+ remain unlaunched and unchanged. Re-run meaningful
tests after the corrected source/build package is staged. Never modify the
failed m12d executable or its archived provenance.

## Amendment 6: representative probe boundary (before supplementary launch)

Audit of the five v1 size-selective sparse cases found ZERO realized business
packet drops in every case (21 business packets/lifecycle). Their registered
fault-configuration outcomes stay in the ledger, but they cannot be presented
as five demonstrated failures to detect actual damaged business traffic.
The v2 sparse boundary remains unchanged and will likewise disclose realized
damage. Do not censor zero-damage realizations or move the main denominator.

Add a separate matched representativeness experiment using the SAME frozen v4
binary and detector: 20 IID and 20 size-selective 0.5% loss lifecycles at 80-Mb/s
business traffic, with identical probes/costs/collector. Fresh ns-3 seeds
52000–52019 and prospective 50–60-ms phases are deliberately reused ACROSS the
two arms to couple business-packet realizations; these are 20 matched pairs,
not 40 independent seeds. Run all IID lifecycles before selective lifecycles,
so equal-seed Docker names never overlap. The selective model drops only >128
byte packets, leaving 64-byte probes unaffected. Expected outcome: reduced
timely detection despite matched realized business loss, which limits the
main size-independent-fault claim. Zero realized damage remains explicitly
reported. This supplement is not validation-seed tuning or a main-matrix pass.

Record the external registration adapter's hash as well as unchanged frozen
source/binary/library hashes. Audit each lifecycle and separately verify
paired phases, business send/loss counts and probe damage. At most four
supplement containers alongside eight validation containers, within the
sixteen-container global cap. Keep all failed and no-damage outcomes.

## Verified outcome after frozen execution

The corrected v4b development, fresh validation v2 and boundary v2 ledgers
are complete and independently audited. Validation yields 698/700 timely
fault decisions, no misses, two late and 40 controls without alarms. Every
registered eligible condition passes the empirical >=95% target; maximum
condition p95 is 80.694006 ms. The original strict all-trial/report-availability
gate remains FAIL. Final validation audit checks 3,523,470 report rows and
51,592,800 injected probes. All historical scientific/setup failures remain.

The 15 separate fresh boundary cases have zero timely decisions; four of five
sparse selective cases realize no business drops. The informative 20-pair
active-load supplement has 123 business drops in each arm and no zero-damage
pairs, but only 5/20 selective decisions are timely versus 20/20 IID. This
verified limitation keeps broader fast gray-fault coverage unresolved.
The separate cumulative-counter audit passes 1834 trials/14672 path lifecycles.
Linux tests: 292 pass without skips; local macOS: 289 pass/3 platform skips.

See [the full frozen results](m12_hybrid_detection_results.md). These findings
do not integrate the hybrid detector with the collective route loop or establish
a population timing guarantee. Git changes remain uncommitted for review.

The existing Overleaf main.tex was updated after exact fresh readback of its
previous source. Exact full-source readback confirms the new saved text.
Live compilation produces nine pages, zero errors, the same four draft warnings
and zero typesetting-info messages. Pages 1, 6, 7 and 9 were visually checked;
the experiment table, cost/failure boundary and conclusion remain readable.
