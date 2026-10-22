# M8 two-ended batch observation implementation plan

> Execute inline using executing-plans. Sophie's continuing autonomous research
> authorization supersedes repeated design approvals and skill-requested commits.

**Goal:** Implement and prospectively evaluate a simulation-only delivery-deficit
candidate with observable input separation and explicit telemetry cost.
**Architecture:** A new isolated ns-3 program in the pinned CPU backend emits
eight paced, one-hop UDP streams (rank/fabric labels only, not a collective).
Source acceptance and destination delivery counters are keyed by a serialized
batch ID. A shared serialized reporting channel delivers independent snapshots
to a Python candidate through timestamped input replay. This first stage measures
detection only, not route choice, application completion or execution correctness.
**Tech stack:** Existing pinned ns-3/SimAI CPU build, C++17 and Python stdlib.

## Research and choice

[Fact] RFC9341 describes matching two-ended counters for packet batches and
requires synchronization/guard intervals before comparison. Its observations
motivate this design, not a novel measurement method or an exact RFC implementation.
https://www.rfc-editor.org/rfc/rfc9341.html (Sections 3.1, 4.3, 5).

[Local fact] The pinned ns-3 backend exposes successful reception and transmission
traces. Existing DAG adapters report whole-flow completion only. Retuning M7 cannot
create feedback that arrives after its deadline. Probes add load. Use a separate
batch-counter signal experiment first, then integrate a successful bounded model
into the existing DAG; do not overwrite baseline binaries or imply integration.

## Frozen initial candidate and model

- Rule `batch-loss-v1`: pair TX/RX reports for the same path and batch. Require
  two missing packets summed across complete batches in the trailing 100 ms of
  report acceptance, with history cleared after two active zero-deficit batches.
  This conservative reset also occurs before confirmation, and can lose evidence
  of intermittent weak loss. Report an observed delivery deficit, not its physical cause.
- Batch period 10 ms; RX snapshot at batch end + 50 ms. TX snapshot at batch end.
  Report arrivals include a shared FIFO at 1 Mb/s, 64 serialized bytes per report,
  plus 5 ms propagation. There are 16 reports per batch across all eight paths.
  Charge every report, including idle/empty batches; observer budget is modeled,
  not measured switch resource consumption. Reporting uses a declared separate
  channel, not the affected data link. No free, instantaneous, reliable oracle.
- Source API observes successful UDP enqueue before device queues. Thus the guard
  includes queue, serialization, network and receiver delay. This does not isolate
  a physical access-hop cause. Positive sends and final sink deliveries are audited.
- Data wire size 1500 bytes: 12-byte batch/sequence header, 1446-byte user payload,
  UDP8/IP20/pinned-backend-PPP14. The 12-byte mark is charged in packet serialization. Shared ns-3
  clocks and complete local counters are declared assumptions; report loss/delay
  and queue/delay-envelope violations are separately tested.
- A report missing beyond 200 ms after batch end is unavailable. Never interpret
  absent RX telemetry as zero delivered packets. Reject conflicting duplicates,
  invalid times/counters, and RX>TX; deduplicate complete pairs. Missing or invalid
  batches interrupt persistence. Rearm after two complete, active, zero-deficit
  batches. Idle batches do not establish recovery. Preserve late arrivals.
- Report inputs contain no loss rate, fault time, fault path or drop callback.
  Hidden fault metadata is confined to separate scorer files. The candidate input
  API has an exact schema; compare actual report arrival times, not file order.

## Implementation tasks and checks

- [x] Add `limer_v0/batch_loss.py`: `BatchLossDetector.observe(report)` and
  `advance(now_ns)`; strict schema, pairing, bounded retention, rearm and missing
  semantics. Input fields: path, batch, side, count, sample_t_ns, arrival_t_ns.
- [x] Add `tests/test_batch_loss.py` for reordered reports/packets, no false alarm
  from missing reports, report expiry, duplicates/corruption, evidence expiry,
  separate paths, repeated episodes and decision timing after delayed telemetry.
  Verify a missing module first fails; then pass the focused and full suites.
- [x] Add `simulation/LimerBatchObservation.cc`: isolated ns-3 stream generator,
  serialized marking, source/sink snapshots, bounded FIFO reporting, timed fault/
  no-loss controls, independent assigned RNG streams and separate truth audit.
  A custom receive error model implements probabilistic permanent loss or timed
  deferred delivery/reordering; deferred arrivals bypass the hook once. Deferral
  is not a permanent drop even if a built-in PhyRxDrop hook fires internally.
- [x] Add `simulation/run_batch_observation.py`: launch manifests, process status,
  immutable registration before each campaign, replay exact reports, all-attempt
  per-condition scoring, p95 with nondetections infinity and strict verdict.
- [x] Build only the new scratch target in the existing owned rootless Docker.
  Preserve failed builds/development runs. Audit exact packet accounting for
  healthy/reorder, intentional drops for loss, and input/source/binary hashes.

## Experiments: what changes / what is expected

Development: replace passive TCP feedback with two-ended counter reports. Keep
the original M7 evidence untouched. Eight trials: low/high nominal, low/high 0.5%
loss, low 1% loss, low 40 ms reorder, low pause and low report loss. Expect reported
loss to become visible without TCP repair; 40 ms reordering should drain before
the 50 ms guard. Weak/sparse traffic may fail the deadline. Count every alarm and
unknown batch. Any change creates a new rule version and new development ledger.

After passing engineering gates, freeze the candidate before fresh validation:
20 independent seeds each at 0.5/1/2/5% loss in both traffic profiles, plus five
each nominal, paced congestion, source pause and 40 ms reorder per profile.
Low profile: 100 Mb/s capacity, 80 Mb/s offered data. High profile: 10 Gb/s
capacity, 1 Gb/s offered data. Base propagation 1 ms. Development fault/pseudo-event
at 50 ms; validation/stress phase independently registered uniformly in 50–60 ms;
traffic from 1 ms to 250 ms; observation through 600 ms. All eight paths observed
from startup. Reordering defers 25% of affected arrivals by 40 ms without loss.
Paced congestion adds 10% capacity (below overload); pause stops source traffic
for 60 ms. These are exact declared controls, not arbitrary benign delay.

Separate five-repeat stress groups: 80 ms reordering, overloaded competing
traffic, sparse 1 Mb/s data, idle-across-fault, and 10% telemetry report loss.
Stress is visible alongside primary results; it cannot be relabeled a detected
physical fault. Preserve nondetection and late decisions in the fault denominator.
Scoring targets rank2/A after injection but the detector observes all eight paths.

No automatic recovery integration follows from a conditional detection pass.
Next integration must include data dependencies, finite horizon, telemetry and
cutover costs, and unfinished-work correctness before any adaptive benefit claim.

## Development setup amendment before further launches

The first registered development attempt (low 1% loss) completed the simulator
but failed the wire-size audit: all transmitted packets were 1512 bytes, not the
declared 1500. Inspection verifies that this pinned backend's PPP header has
14 bytes (`PppHeader::GetStaticSize`), rather than the assumed two. Preserve the failed attempt and seven
unrun registrations. Correct user payload to 1446 bytes (1458 UDP payload including
the 12-byte mark) and competing UDP payload to 1458 bytes. Keep the detector
unchanged; repeat all eight development cases under tag v2 before any validation.

## Development terminal gate and prospective freeze

All eight corrected v2 development lifecycles pass exact packet/wire accounting.
Observed decisions: high 0.5% loss 69.608 ms, low 0.5% 159.608 ms, low 1% 99.608 ms.
No false alarms in these eight runs, including the 40 ms reorder development run.
Report-loss development is unavailable for some batches, not certified healthy.
The signal is implemented but the low-loss deadline already fails in development.
Freeze `batch-loss-v1` unchanged for the registered 200-run validation; this
campaign evaluates the failure boundary rather than declaring an achieved target.

## Constraints

Simulation-only; no GPU/H20, physical device access, daemon/host security changes,
commit or push. CPU data/results stay on otakotak scratch. One or two bounded
containers, each four CPUs/four GiB, independent of existing baseline artifacts.
