# M8 two-ended batch observation results

**Status:** A simulation-only signal candidate is implemented. All 200 primary and
25 stress lifecycles complete with audited packet conservation. The frozen primary
strict gate is **FAIL**, with 139/160 timely correctly localized decisions.
This is an isolated UDP observation experiment, not a collective recovery result.

## Task, branch and implementation

The project scope is simulation/emulation only. M7's passive TCP observations
left weak-loss timing tails and reordering false alarms. M8 investigates a
different signal: independently reported source/destination packet-batch counts.
RFC 9341 motivates two-ended batch correlation and guard intervals; this custom
12-byte batch/sequence implementation is not a reproduction or a novel claim for
alternate marking. https://www.rfc-editor.org/rfc/rfc9341.html

Each of eight rank/fabric-labeled one-hop streams sends paced UDP. Successful
source enqueue is counted before device queues; destination delivery is counted
after reception. A serialized header identifies the batch and sequence. Actual
wire packets are 1500 bytes, including 12 bytes of marking, 20 IPv4, 8 UDP and this pinned
backend's 14-byte PPP header. The remaining user payload is 1446 bytes. Accounting
does not establish numerical, CRC-framed or coordinated-cutover correctness.

Source snapshots occur at 10 ms batch boundaries; receiver snapshots wait 50 ms for
in-flight/queued/reordered delivery. An explicit separate telemetry FIFO charges
64 bytes/report at 1 Mb/s plus 5 ms propagation. Clock synchronization and complete
local counters are assumed. No control/data-plane contention is inferred from
this modeled side channel. All eight paths are observed from startup.

The frozen `batch-loss-v1` pairs same-path/same-batch reports and confirms after
two missing packets in a 100 ms report-acceptance window. Two active zero-deficit
batches clear history, including before confirmation, and rearm the detector;
idle batches do not prove recovery. This conservative reset can discard evidence
of intermittent weak loss. Missing/invalid batches interrupt evidence. Reports
older than 200 ms after batch closure are unusable. A missing RX report is unknown,
never zero delivered data. Old clean reports cannot rearm a newer episode.

Only the exact observed report schema enters the detector. Fault time/path/rate
and permanent-drop audit counters exist only in separate scorer metadata. Decisions
are produced by causal chronological replay at actual simulated report-arrival
times, not by an online route controller. There is no fault-time arming or oracle
shortcut. Exact replay consistency is not an independent physical-cause proof.

## Registered matrix and measured outcomes

Low profile: 100 Mb/s links, 80 Mb/s offered wire data per path. High profile: 10 Gb/s links,
1 Gb/s offered wire data. Both have 1 ms propagation. Data runs from 1 to 250 ms; observation
runs through 600 ms. These profiles change both capacity and offered packet rate;
their difference does not isolate a capacity-only effect or an algorithm gain.

Twenty fresh runs per profile at 0.5/1/2/5% independent per-packet loss supply 160 fault
attempts. Five nominal/congestion/pause/40 ms reorder controls per profile supply 40
controls. Fault/pseudo-event phase is registered independently in 50–60 ms. Ns-3
seed 20261010 and unique runs 10000+ drive assigned random streams. Counter snapshots,
rule, binary and all shared-library hashes are frozen. No candidate tuning uses
these runs. Nominal repeats are deterministic controls, not statistical evidence
for an unknown stochastic false-alarm distribution.

|Offered wire data (Mb/s)|Loss (%)|Timely/all|Late|Missed|P95 (ms)|
|---:|---:|---:|---:|---:|---:|
|80|0.5|7/20|12|1|228.175|
|80|1|12/20|8|0|138.195|
|80|2|20/20|0|0|88.029|
|80|5|20/20|0|0|78.552|
|1000|0.5|20/20|0|0|72.461|
|1000|1|20/20|0|0|67.960|
|1000|2|20/20|0|0|69.225|
|1000|5|20/20|0|0|68.070|

Timely means the first correctly localized post-injection decision below 100 ms,
divided by all registered fault attempts. Nondetections remain in nearest-rank
p95 as infinity. All controls and pre-event/unaffected-path alarms count.
The 40 primary controls have 0 false alarm events over 24 simulated lifecycle
seconds (192 path-seconds). Fault trials have 0 pre-event/unaffected-path
alarms. Primary unavailable batch count is 0. The low/high measurements
are simulated times; they must not be pooled with M7 Linux wall-clock results.

A retrospective, scorer-assisted report-opportunity diagnostic finds that all
21 deadline failures have fewer than two reported deficits available by the
100 ms deadline: 13 at low 0.5% loss and eight at low 1% loss. None has two
available deficits but a late/missed rule decision. Every fault lifecycle has at
least two deficits over the full observation, including the one full-lifecycle
nondetection; cumulative evidence therefore is not equivalent to this resetting
rule. This diagnostic omits the rule's window/reset semantics and is not a
validated alternative detector or false-alarm evaluation. It identifies the
report/data opportunity budget as a constraint on this campaign's deadline.
One nondetection among 20 can remain above the nearest-rank p95; report the miss
column explicitly even when that p95 is finite.

## Stress: delay ambiguity and observation coverage

All 25 separately registered stress trials have exact final delivery/drop accounting.
Under the original loss-only scoring, 80 ms reordering triggers alarms in
5/5 trials; competing traffic at 160%
of link capacity triggers alarms in 5/5.
These ten controls have no permanent random loss and final source/receiver counts
match. They demonstrate guard-envelope violations, not confirmed permanent loss.
Do not discard or relabel them to pass the registered gate.

At 1 Mb/s sparse data with 0.5% loss, timely decisions are
0/5, with
5 nondetections.
Idle-across-fault has 0/5 timely,
1 late and
4 nondetections.
With 10% independent report loss and 0.5% data loss, timely is
0/5, with
2 late and
3 nondetections;
361 of 2000 scheduled batch pairs lack
one or both reports. The availability ledger counts also pairs with both reports
missing. These failures remain part of the observation-model boundary.

## Cost and model scale

Every lifecycle schedules 800 reports, or 51.2 KB of modeled control traffic. During
steady reporting, the eight paths offer 819.2 Kb/s, 81.92% of the 1 Mb/s collector budget.
Marking consumes 0.8% of each data wire packet. These are modeled byte/service costs,
not measured switch CPU/memory resources or real telemetry overhead.

At unchanged 10 ms batching, report offered load is 204.8 Kb/s per logical rank. Eight
ranks already exceed the declared 1 Mb/s FIFO service rate; 128 ranks would offer
26.2144 Mb/s. This is an algebraic scaling implication, not a 128-rank simulation.
The current result must not be extrapolated without redesigning that channel.

## Preserved setup failures and evidence

The initial broad builds were stopped and the new target moved into a separate
backend copy with minimal dependencies. Before isolation, the broad build
recompiled unchanged generic dependencies in the common build directory; do not
claim that every baseline build product was untouched. Archived baseline results
remain separate. A link failure exposed the modified
backend's SimpleSeqTsHeader/MTP dependencies. The first registered development
attempt then failed the wire audit: packets were 1512 bytes because the assumed
PPP header was two bytes while the pinned header is 14. Preserve that failed run
and its seven unrun registrations. Corrected development v2 passes all eight
packet-accounting gates; its low 0.5% decision is 159.608 ms. No result is selected
away to improve the final score.

Independent final replay checks all 179620 counter
reports across 225 lifecycles against actual recorded decisions and scores, plus
source/binary/shared-library/input hashes and final packet conservation. Complete
raw inputs and truth audits remain on otakotak scratch:
`/home/suliu/scratch/LIMER_WORK_2026-10-10/runs/m8_validation_v1` and `m8_stress_v1`.
Frozen code is `m8_source_frozen_v1`; final audit is `logs/m8_final_audit.json`.

## Implementation checks

The final full LIMER suite passes all 251 tests on otakotak host Python 3.12.3.
The backend image uses Python 3.8 and is unsuitable for the full existing suite;
its failed import attempt is documented in the review notes. No dependencies
were installed to hide that environment mismatch. Code remains uncommitted.

## Remaining research decision and work

The signal detects delivery deficits under a declared guard; it cannot generally
distinguish a packet that will arrive after the decision deadline from one that
never arrives. Define whether the operational target is delivery impairment that
triggers route-cost evaluation, or permanent-loss confirmation under a bounded
delay model. Preserve the original loss-only verdict and all stress evidence
regardless of that future decision. No automatic route-control integration has
been enabled. Next experiments must include the dynamic DAG, finite horizon,
observation/cutover costs and unfinished-work correctness.
