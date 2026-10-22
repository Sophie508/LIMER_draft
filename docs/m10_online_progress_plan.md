# M10 causal ACK-progress development plan

> Execute inline with executing-plans. Existing autonomous CPU implementation
> authorization applies; changes remain uncommitted for review.

**Goal:** Implement a native, causal, detection-only slowdown candidate before
connecting alarms to the validated pending-flow coordinator.
**Architecture:** Sample sender RDMA acknowledgment progress, deliver explicitly
charged reports, and evaluate the rule inside simulator callbacks. An independent
Python replay must reproduce the actual online alarms. Fault setup is a separate
input and never an argument to the detector. Build an isolated M10 target.
**Tech stack:** Existing pinned ns-3/SimAI C++17, Python 3.12 stdlib.

## Verified starting point and branch choice

The pinned `RdmaQueuePair::snd_una` advances on acknowledgments, while completed
queue pairs are deleted. `RdmaDriver::m_rdma->m_qpMap` exposes running pairs.
Accumulate completed flow bytes plus current acknowledged bytes to avoid a
counter decrease when a pair disappears. This is sender ACK progress, not an
instantaneous receiver-delivery or permanent-loss oracle.

Waiting for whole-flow completion loses within-flow progress. Two-ended UDP
batch marking would require new RDMA packet identity instrumentation. Start
with the existing ACK field instead, preserving M8 as a different model and
retaining weak-loss detection as unresolved. No claim that this heuristic is a
published method or a broadly validated detector is made.

## Registered development envelope

Use four logical ranks, active A/B slots, three consecutive 3-MiB ring graphs,
1-Gb/s accesses and 500-ns propagation. Join rounds using each rank's previous
local send and predecessor receive dependency. This is network scheduling, not
numerical reduction or GPU compute. Fault-free workload lasts long enough to
contain multiple reports; the actual horizon is measured, not assumed.

Sample all eight sender/plane paths every 2 ms. Reports occupy 64 bytes each on
a separate reliable 10-Mb/s FIFO with 1-ms propagation. The detector receives
path, cumulative acknowledged bytes, sample/arrival timestamps and whether a
current active pair spans the previous sampling boundary. Idle windows interrupt
evidence; absence of traffic cannot establish health.

Freeze the first four positive, fully busy service samples as the per-path
reference (median). After calibration, three consecutive fully busy windows
below half that reference emit one alarm per path. This is a development
hypothesis; it can miss brief/sporadic impairments, confound ACK delays with
delivery delay, and cannot calibrate a path that starts degraded or idle.

Prospectively register four development cases: healthy, persistent rank-2 A
egress reduction to 0.2 Gb/s at 50 ms, a 2-ms reduction then restoration, and
the same persistent reduction with 120-ms report propagation. Severity in this
development scene means an 80% injected directed service reduction persisting
at least 20 ms under queued demand; the short event is an ineligible control.
The long-report case is expected to expose the deadline cost, not earn a pass.
No formal recall/false-alarm population claim follows from four deterministic
development cases. Retain every observed alarm and late/missed localization.

**Development amendment after v1:** Device-only restoration left a queue pair
created during the 2-ms reduction capped at 0.2 Gb/s until completion. Its
31.563-ms transfer remained slow after the physical rate restored; it was not
a clean brief-delivery control. Preserve the original registered control alarm
and all v1 inputs/source/results. In v2, define rate events as a configured NIC
service change: change directed device serialization plus active DCQCN rate and
maximum/target caps at both reduction and restoration. This changes the fault
model, not the frozen decision rule. It cannot be described as an algorithm-only
gain. The observer still reads ACK progress only.

**What changes:** online ACK-progress observations and decision callbacks,
plus a separate directed rate injector; no route actuation yet.
**Expected observation:** persistent backlog causes a localized low-progress
alarm after delivered evidence; healthy/brief-delay scenes should not alarm.
Report propagation must delay the decision and can break <100 ms. These are
hypotheses to inspect, not required outcomes to relabel or tune away.

## Tasks

- [x] Implement an independent Python rule and tests for causality, startup,
  idle interruption, transient suppression and monotonic acknowledgment counts.
- [x] Add a separate native target and report FIFO; retain exactly matched
  receive ownership and final graph drain from M9. Keep injector metadata out of
  observer/decision interfaces.
- [x] Build in `m10_backend/simulation` and register source, binary, image,
  libraries and all four cases before launch. Use owned rootless Docker with
  four CPUs/four GiB; retain all failure/unrun ledgers.
- [x] Replay delivered reports independently, check exact final ACK byte totals
  against graph flow volume by physical sender, and report observed detection
  times without treating development as held-out validation.
- [x] Only after the signal and execution gates, connect route-benefit evaluation
  and preregister a fresh matched finite-horizon comparison. Pending-flow mode
  still cannot rescue permanently stalled launched work.
