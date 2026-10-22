# Next dynamic simulation: approved impairment scope and design

**Status:** The first scripted pending-flow execution gate is implemented and
validated (eight completed workloads and one expected invalid-version rejection).
See [M9 results](m9_dynamic_execution_results.md). M10/M11 now implement causal ACK-progress alarms and a bounded observable
route-cost loop; see [online results](m10_m11_online_results.md). Broad detector
validation, launched-work replay and crossed ring/OptCC comparisons remain open.
Sophie resolved the operational definition: severe slowdown is also eligible for
detection, followed by a separate route-benefit decision. Loss-only M8 labels and
results remain unchanged. The first implementation gate uses externally scripted
control transactions to verify pending-flow ownership; it is not an online
detector or adaptive-policy efficacy campaign.

## Starting code and the concrete integration problem

The pinned `LimerDualPlaneReplay.cc` assigns each flow a static plane before
execution. It translates logical endpoints to physical plane ports, registers
all receives on those ports, and then launches graph roots. Send and receive
callbacks release dependencies at different endpoints. Its completion gate
requires every registered receive and several frontend maps to drain.

Changing a flow's plane at launch alone is therefore incorrect: its receive
would still be posted on the old destination port. Registering both planes
without explicit ownership/cancellation would instead leave unused receives and
invalidate completion. An in-flight transfer also cannot be moved by editing its
plane field. Keep the static replay intact and use a separate dynamic target.

## First execution boundary

Start with a declared **pending-flow cutover** model. Launched transfers retain
their attempt/plane ownership until both required completion events occur.
Only unlaunched affected sender slots take a committed new route version.
Post the matching receive before each launch, using the selected physical
endpoints and a process-unique flow tag. The current target executes one graph
per process; it does not establish concurrent invocation/attempt namespaces.

This model leaves severely stalled launched work on its old path. It is a
bounded first execution mode, not cancellation/replay of unfinished packets.
Report that boundary explicitly and retain timeout as failure. A later replay
mode requires acknowledged byte/segment ownership, stale-completion rejection
and duplicate suppression; whole-flow callbacks alone do not provide them.

The coordinator stages one monotonically increasing plan version, gathers
modeled readiness, charges serialized control messages and delay, and commits
the version at a common activation event. A graph event records version, flow,
logical endpoints and actual physical ports. Shared simulator state is an
implementation mechanism, not a free or instantaneous distributed agreement.

## Detector and remaining-work interfaces

Integrate observations into the event loop, rather than importing an alarm
computed with hindsight. The observer receives independent counters and modeled
arrival times only. Hidden injection settings remain in a separate scorer.
The eligible category includes severe slowdown. Each future efficacy registration
must operationalize severity and duration before launch, and distinguish an
alarm from a beneficial route change.

The policy reads only observable outstanding work, measured delivery/service
history, the staged route version and alternative-path observations. The oracle
arm may read ground truth but is explicitly labeled. Preserve missing telemetry
as unknown and define how an unknown alternative affects the policy before
validation. Do not infer healthy spare from the injector configuration.

An isolated static DAG may finish in a few milliseconds, whereas the detector
target permits almost 100 ms. A policy experiment therefore needs a registered
finite multi-round workload with work remaining after an alarm, and must count
the initial delay against total completion time. Do not compare a long detection
episode to an already-completed static collective as if their horizons matched.

## Gates and the next registered experiments

1. Validate registration and ownership on small micrographs: parent-send versus
   parent-receive release, unequal sizes, early receive, a join, and duplicate
   completion rejection. The first micrographs pass; concurrent invocation
   namespaces and replay attempts remain a later gate.
2. Commit a route change with queued and launched flows present. Check that only
   unlaunched affected slots change, every receive matches its launch ports,
   all dependencies consume their correct endpoint event once, and no unused
   receive remains. Test readiness failure, delayed control and stale versions.
3. Run four arms with identical workload, topology, observation channel and
   declared control costs: fixed stay, fixed localized switch, oracle switch,
   and observable candidate. Account for the reporting traffic in every arm;
   separately label any observer-off cost reference. Do not give the candidate
   ground-truth onset or loss probability.
4. Register both helpful and harmful alternatives and finite episode lengths.
   Measure total completion time from workload start, completion fraction,
   deadline/localization errors, control/data bytes and cutover ownership errors.
   Failed attempts remain in denominators. Use matched random draws where the
   simulator can preserve them, and disclose when changed traffic changes RNG
   consumption. Same seed alone is not a paired fault-realization guarantee.
5. Freeze after development; use fresh seed ranges and preserve setup failures.
   Increase rank count only after measured CPU/memory feasibility and reporting
   stability. Numerical tensor reduction and GPU throughput remain outside this
   network-DAG gate.

**Before launching:** state exactly what changed and which observation would
support or refute it. A successful graph drain does not establish an optimal
route policy, and an oracle benefit does not establish a working detector.
