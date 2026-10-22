# M5 comparison and signal pre-registration (2026-10-10)

Initial registration precedes all new topology runs. The later independently
reconstructed measurement amendment and server results are recorded separately
in `m5_execution_plan.md`; the shared-backend route-choice matrix below is unrun.

## SimAI reproduction gate

First pin the public OptCC ZIP SHA256 and the official SimAI source/submodule
commits, compiler and NS-3 configuration. Reconstruct the missing DAG ingestion
with every flow dependency and synchronization edge retained; compare imported
graphs against the reference generators. Do not treat an analytical DAG makespan
as packet-level completion time. No NVSwitch assumption is introduced.

Before any paper-figure run, derive exact message sizes and topology from its
source/figure. If missing, register the mismatch as an independent study rather
than a reproduced figure. At matched configurations, preregister the target
metric and allow at most 10% relative difference from the published value;
record rounding/digitization uncertainty. A miss is a reproduction failure,
not permission to tune and silently replace it.

Start with a single straggler, one participating GPU per server, 16 servers,
slowdown factors 1, 8/7, 4/3 and 2. This fits the 16-GPU design decision and
avoids unavailable NVLink assumptions. Expand to 32/64/128 only after the small
configuration and units are verified. Static bandwidth reduction verifies
OptCC's model; it does not verify dynamic detection or cutover.

## Shared-backend route-choice comparison

Change: implement LIMER's route-choice model in the same packet-level backend
as the validated OptCC schedule. Expected: the preferred route choice depends
on surviving-plane headroom and finite-horizon cutover cost.

Use a factorial design: {ring, OptCC schedule} x {stay, fixed localized switch,
LIMER policy}. Add healthy reference and episode-cost oracle as references.
An OptCC schedule and a route choice are different factors. No VCCL or Varuna
numbers appear as runs of these arms.

Dual-plane topology, 16 participating GPUs; message sizes 2/16/128 MiB; directed
access-link residual bandwidth 100/50/20%; alternate-plane background demand
0/50/90% of capacity. Register episode horizons of 1/10/100 healthy collective
times and common seeds 1-5. Keep hard loss of a link separate from bandwidth
degradation and packet-drop cases. Run a 4-rank calibration before the matrix.

Primary outcome: total episode completion time, including detection/decision/
coordination/redo. Secondary: completed collectives, failure rate, steady-state
retention, selected-arm regret against matched counterfactual arms, and overhead.
If detection/cutover delay is imposed, label it as a model parameter and sweep
it; never report it as simulator-measured implementation latency. Failed arms
retain their seed and receive infinite completion time for selection-regret
accounting; report finite-completion conditional statistics separately.

## New signal pilot: host retransmissions

Change: collect Linux per-socket TCP retransmission counter deltas on each
fabric's outgoing worker connection, aligned with worker step telemetry.
Expected: low-loss episodes expose retransmissions even when average switch
RX byte rate remains near baseline. This is a hypothesis; TCP recovery timers
may still delay the new signal, and reordering/congestion may generate it too.

First run observation-only with the repaired worker and existing detector; log
timestamp, connection identity, route version, cumulative retransmissions,
sample interval and any unsupported/unavailable read. Do not read the injector
qdisc as a detector input. A failed sample is missing, not zero retransmissions.
Implementation: opt-in worker sampling controlled by tcp_retrans_interval_s,
default zero (disabled). The pilot uses 0.02 s. Reads the Linux TCP_INFO ABI
prefix's tcpi_total_retrans field. Unit tests cover counter wrap, a replaced
connection and unavailable reads; Linux runtime validation remains separate.

Healthy controls: nominal, alternate-plane congestion, burst timing changes and
reordering. Faults: 0.5/1/2/5/10/25% loss on the directed access link. Run three
pilot repeats per scene; freeze a simple threshold/step gate in an amendment
before the formal run. Pilot data cannot be the final false-positive evidence.

Formal design: 20 new repeats each at 1/2/5% loss plus 20 healthy/congestion
controls. Retain misses as right-censored latency and timeouts as run failures;
report detection fraction, median/p95, false alarms per observation second,
sampling overhead and completion rate. A <100 ms guarantee is not inferred
from a median. Strong latency gate: every registered low-loss repeat detects
within 100 ms, and no control triggers recovery. Report failure if unmet.

The host signal is observation-only until its statistical gate is frozen and
validated; it is not represented as switch-resident hardware telemetry.

## Jev offline pilot

Construct six input states from existing POLICY_DECISION counter metrics with
verdicts and outcomes withheld. Pin official model and fixed instructions;
randomize option order consistently. Save inputs, responses, exact model,
latency and usage. Require an official key; do not enroll or buy access.

Treat topology-expected labels as hypotheses, not a paired optimal-arm oracle.
Main accuracy requires fresh matched episode-cost stay/switch outcomes. Report
all API errors and six-case uncertainty. This arm must not delay core evaluation
or enter the recovery hot path.
