# M13 Business Delivery Detection Implementation Plan

> **For agentic workers:** Use executing-plans to implement this plan task-by-task in this session. User authorized direct execution; commits and pushes require separate review.

**Goal:** Test whether causal business observations repair the M12 probe-representativeness failure under the unchanged per-condition empirical 95% below 100 ms target.

**Architecture:** Preserve M12 source/results. A separate Python/native candidate combines the M12 shadow baseline, business-only aligned cumulative service windows, and receiver-observed sequence gaps that persist for at least 40 ms. Reports contain independent business/probe counters and gap ages; every copy costs 96 on-wire bytes on the existing shared 10 Mb/s collector.

**Tech Stack:** Python unittest, C++17, pinned ns-3 CPU backend, owned rootless Docker on otakotak.

## Global Constraints

- No hardware, GPU, commit, push, or retrospective deletion of failed attempts.
- Injection time/path and private drop/defer counters enter only the scorer.
- Each eligible condition needs at least 95% correctly localized decisions strictly below 100 ms; all registered attempts remain in the denominator.
- Severe slowdown is eligible; an alarm does not itself authorize an unconditional route switch.
- Main fault phase is prospectively randomized in 50–60 ms. New development run IDs start at 60000; validation starts at 61000 after a passing development gate.
- Report copies are independently lost; all offered copies consume service, including lost copies. Source and receiver samples use the same aligned clocks as M12.
- Negative controls include 40 ms reordering of 25% and 0.5% packets, pauses, nominal delivery and mild congestion. These classifications are retained.

### Task 1: Report-only Python candidate and native parity

Files: create `limer_v0/business_delivery.py`, `simulation/business_observer.h`, `simulation/m13_batch_deficit_observer.h`, `tests/test_business_delivery.py`.

Interface: `BusinessDeliveryDetector.observe(report: dict) -> dict | None`; `advance(now_ns: int)`. Reports have M12 fields plus `data_count`, `probe_count`, `data_gaps`, `probe_gaps`, `data_gap_age_ns`, `probe_gap_age_ns`. Native callbacks project the same report order into the unchanged M12 baseline and new business service detector. A receiver gap is inferred only when a higher sequence arrives; a later arrival closes its gap. Gap age is measured at sampling, never inferred from report transit time.

- [x] Write tests for persistent gaps, filled gaps, delayed reports, hidden fields, count conservation, healthy probes with stalled business, and native/Python equality.
- [x] Run `python3 -m unittest discover -s tests -p test_business_delivery.py -v`; confirm initial import failure.
- [x] Implement strict report validation, baseline-first ordering, gap rule, business-only service lane and first alarm per path.
- [x] Run the focused tests and existing M12 parity tests; require equality of exact alarm records.

### Task 2: Costed native observations and isolated build

Files: create `simulation/LimerBusinessObservation.cc`, `simulation/build_business_observation.py`.

- [x] Use independent monotonically increasing data/probe sequences in the existing 12-byte header; maintain local acceptance/delivery counters and receiver gap maps.
- [x] Serialize 96-byte reports (20 IPv4 + 8 UDP + 68 payload) containing class counts/gap ages. Charge 768 bits per offered copy and export samples/offers/delivered reports.
- [x] Add application-only loss and 40/80 ms delivery deferrals with independently seeded injector state. Receivers observe only actual application arrivals.
- [x] Build `LimerBusinessObservation` in `m13_backend/simulation` with one CPU/4 GiB and verify its rule string. Keep the M12 executable unchanged.

### Task 3: Prospectively registered development and independent audit

Files: create `simulation/run_business_observation.py`, `simulation/audit_business_campaign.py`.

- [x] Register 20 weak selective, 20 business-only weak loss, IID regressions, severe 80 ms slowdown, and the negative controls before running. Source/binary/library/image hashes are frozen first.
- [x] Run at most eight one-CPU/1 GiB lifecycles in parallel. Hypothesis: receiver gaps provide evidence earlier than the mature counters while a 40 ms wait suppresses the declared 40 ms reordering controls; expect a recall/latency tradeoff in weak business-only faults.
- [x] Independently reconstruct the collector FIFO, exact report contents, native/Python candidate and shadow-baseline alarms, traffic conservation, and all registered denominators.
- [x] If development passes, freeze and run fresh validation. If it fails, retain results and diagnose the evidence boundary before changing the rule; fresh IDs/version are required for each amendment.

### Task 4: Results and review

- [x] Write `docs/m13_business_detection_results.md` with measured coverage, failures, costs, and model assumptions.
- [x] Export thin artifacts and a review diff under the private work root; do not commit or push.
- [x] Update the existing Overleaf only with verified results and preserve the M12 result. Verify source readback and compilation.

## Self-review

All changes isolate M13, retain original timing/denominators and negative-control classifications, and charge added observations. No universal feasibility claim is made. A failed empirical target remains a failed target, even if engineering tests pass.

## Setup amendment before corrected development (v2)

The v1 smoke (3 lifecycles) passed exact accounting and native replay. During
v1 development, sparse_reorder40 was found to inject 80 ms because its delay
ternary recognized only the dense reorder40 label. The campaign is interrupted,
all 149 registrations and dispatched artifacts are retained, and it supplies
no valid target acceptance. Fix the injector to use 80 ms only for reorder80;
export and independently verify each actual injection parameter against the
registration. The detector rule remains business-delivery-v1 (unchanged).

Corrected development uses a separate m13b backend and new run IDs 62000–62148;
smoke IDs 59100–59102, future held-out validation 63000+. Eight independent
worker processes replace threads for CPU-bound auditing; each simulated
container still uses one CPU and 1 GiB. No v1 IDs are reused.

## Cost-preserving probe ablation after corrected development

Corrected v2 completes all 149 registrations: 73/84 timely faults; selective
16/20, application-only loss 13/20; 65 controls have zero alarms. Exact final
native/report/packet replay passes. Paired shadow-baseline timely counts are
7/20 and 4/20. Retrospective lower gap guards improve recall but false-alarm
all ten lifecycles in each of three 40 ms delay controls; they are not new
native validation results. No held-out acceptance campaign is launched.

Next implement workload-shaped probes without increasing the 17.92 Mb/s/path
budget: 1500-byte packets at 1493.333333333 pps instead of 64-byte packets at
35000 pps. Preserve separate class sequences/costs; representative probes
traverse the same application handler as business data. Application loss draws
for data/probes use distinct streams 200+i/300+i. This changes observation
traffic/treatment, not the hidden application fault's probability. It does
not assume every unknown fault affects probes equally.

Freeze in m13_source_frozen_probe_v1 / m13c_backend. Probe smoke IDs 65900+
are engineering checks. Register small and representative arms on fresh,
unpaired IDs 66000+: 20 each selective/business-only weak loss, five idle
faults, five each nominal/pause/congestion/dense-40/sparse-40/application-40
controls per arm (150 registrations). Both arms use identical offered byte
budgets and the unchanged business-delivery-v1 detector. Their loss draws are
not advertised as matched. Hypothesis: representative probes help active
selective/app faults but fewer probe packets may hurt idle detection. Native
wire parsing and final accounting must distinguish class by header, not size.
Retain any failure instead of replacing the v2 verdict.

## Explicit 10 Gb/s capacity/measurement-budget envelope

The fixed-budget 150-case probe development completes: small probes give
selective 17/20, application loss 14/20 and idle 5/5; workload-shaped probes
give 20/20, 18/20 and 2/5. No counted control alarms. Both finite arms retain
FAIL as full-coverage target verdicts. This does not validate a general repair.

Test the unchanged candidate in an explicitly different envelope: 10 Gb/s
links, 1500-byte probes at 35000 pps = 420 Mb/s/path (4.2% of capacity). Probes
traverse the modeled business handler. Do not use these runs to rewrite the
100 Mb/s failures. With 80 Mb/s or 1 Gb/s data the nominal utilization is 5%
or 14.2%; sparse and idle data remain separate conditions. This intervention
changes link capacity, probe size/treatment and byte budget; it is not an
algorithm-only gain. The same 40 ms negative controls and 96-byte collector
remain; no injector fields enter the candidate.

Freeze source in m13_source_frozen_coverage_dev_v1 and build a new m13d backend.
Development IDs 67000–67099 register 100 cases: six weak-fault conditions with
10 repetitions each, two 80 ms delay conditions with five each, and six
controls with five each. The six weak conditions are 80 Mb/s selective,
80 Mb/s application loss, 1 Mb/s selective, idle size-independent loss,
1 Gb/s selective and 1 Gb/s application loss (all probability 0.5%).
Overload at 80%-capacity competing load is not registered as a severe fault
here because this changed envelope would offer only 85% total utilization;
its prior 100 Mb/s positive result is preserved.

Hypothesis before execution: restored packet opportunity should allow each
registered weak condition to reach >=95% below 100 ms while the 40 ms wait
suppresses the controls. Expect a substantial byte-cost increase (23.4375x
small-probe bytes). Only if all development gates pass, freeze unchanged source
and register held-out IDs 68000–68459: six weak conditions x60, two severe
conditions x20, six controls x10 =460. Keep all registered failures and misses.


### Coverage development gate

All 100 development registrations complete and pass independent final replay:
70/70 fault decisions are timely, 30 controls have zero alarms. Source/rules
are copied unchanged into m13_source_frozen_coverage_validation_v1. The
460-case held-out ledger is registered before dispatch and completes with 400/400 timely faults, 60 alarm-free controls and independent final audit PASS. The same-report baseline also meets every condition (396/400 timely); target achievement cannot be attributed solely to the new rule.

## Causal traffic-compensating probes

Preserve the fixed-budget and constant-frequency ledgers. Add an independently
frozen source policy using only each path's last closed 10 ms **accepted data
TX count**. Request a total opportunity target of 25000 packets/s: send enough
1500-byte business-shaped probes in the next window to make up that historical
shortfall. Do not inspect receiver loss, scenario, fault time or private error
state in this policy. For the initial 1–10 ms interval use zero prior data;
subsequent waves read only batch b-1. This policy predicts from past traffic,
not future traffic. It can overshoot after an increase in data; charge every
actual packet. Source pauses/idle need timely compensation and remain controls.

The gap guard and decision rule remain business-delivery-v1, unchanged. The
ideal one-loss opportunity calculation is 1-(1-p)^n, with tested minimum
p=0.005. A 40 ms wait plus at most a batch and collector delay leaves finite
opportunity; 25000 pps provides margin in this configured model. This argument
is not a bound for arbitrary burst/drop correlations or unknown probe treatment.

Add `simulation/probe_budget.h`; export each wave's prior-data count, packet
budget and timestamps in probe_waves.csv. The independent audit reconstructs
every probe timestamp from actual source events and the public policy. Nominal
upper bound with zero data is 300 Mb/s/path (3% of 10 Gb/s); 80 Mb/s data should
need about 220 Mb/s, and continuous 1 Gb/s data should need no steady probes
after startup. Expect lower measured bytes with preserved detection/control
performance; verify rather than assuming these nominal values.

Freeze m13_source_frozen_adaptive_dev_v1 with m13e backend. Register fresh
70000+ development: six weak conditions x20, two severe conditions x5, six
controls x5 =160. On a passing independent gate only, freeze unchanged and
register held-out 71000+: six weak x60, two severe x20, six controls x10 =460.
Do not alter the frozen 68000+ validation or reuse those IDs.

### High-traffic control supplement, registered before dispatch

The adaptive policy suppresses steady probes under 1 Gb/s business traffic, so add a separate high-traffic negative-control supplement (IDs 72000–72059): ten each nominal, pause, mild congestion, dense/sparse 40 ms network delay and 40 ms application delay. All 60 stay in the control denominator. The detector, native binary and policy stay unchanged; only the runner gains an additional campaign choice in an independently frozen controls source. This is supplementary generalization testing, not added fault successes or a replacement of the 460-case primary validation. Run with at most eight additional one-CPU/1 GiB containers while the primary campaign uses eight. Expect no control alarm, including when historical TX compensation temporarily raises probe traffic after a pause.

## Final acceptance

Adaptive development and unchanged-source primary validation both complete and pass independent audit. Primary: 400/400 timely, per-condition target PASS, 60 controls without alarms. The 60-case high-traffic supplement is independently audited and alarm-free. The fixed-rate same-observation baseline also reaches the target, while the adaptive shadow fails the idle condition at 55/60; preserve attribution and budget assumptions. Final Linux 308 checks pass, local 305 passes/3 platform skips. Review package and Overleaf edits are documented separately; no commit or push.

Final paper source is read back exactly through the authorized Chrome Overleaf editor. The ten-page PDF compiles with zero errors, four retained template warnings and two title-block typesetting notices; the new method/results paragraphs have no overfull notices. The adaptive validation table is visually checked on page 8. Thin server export is 5.72 MB; the scoped review diff includes only M13 changes and the authorized paper edit. No commit or push.
