# M9 pending-flow dynamic execution implementation plan

> Execute inline with executing-plans. Sophie authorized autonomous development;
> keep changes uncommitted for review and obtain permission before any push.

**Goal:** Verify runtime route-version commits and matching receive registration
in the existing pinned SimAI RDMA network-DAG reconstruction.
**Architecture:** Copy the static dual-plane runner into a separate target. At
launch, select ports from the committed plan, post exactly one matching receive,
and retain that ownership through both completion callbacks. A serialized modeled
management channel prepares, gathers readiness and delivers a common activation
version. Independent Python trace auditing verifies all endpoint/dependency and
control invariants. No online detector or policy gain is inferred from this gate.
**Tech stack:** Pinned ns-3/SimAI C++17 backend and Python 3.12 stdlib.

## Constraints and branch choice

Severe slowdown is now eligible for detection; an alarm triggers route-cost
evaluation, not unconditional switching. Original M8 classifications stay intact.
Use CPU scratch on otakotak, owned rootless Docker, at most four CPUs/four GiB per
container. Keep the static replay and all prior binaries/results intact by
building in `m9_backend/simulation`. No GPU, host/security changes, commit or push.

Moving only pending flows avoids ambiguous cancellation and duplicate ownership.
Moving launched RDMA transfers would require byte/attempt replay semantics absent
from the whole-flow adapter. Duplicating receives on both planes leaves unused
registrations. Thus the first gate posts one receive on the selected plane before
each launch. It cannot rescue a launched transfer stuck forever on its old plane.

## Task 1: Independent audit

Files: `simulation/audit_dynamic_dag.py`, `tests/test_dynamic_dag_audit.py`.
Interface: `audit_dynamic(graph, records, requests, control_model)` returns flow
count, dependency count, route-change counts, modeled control bytes and makespan.
It rejects missing/duplicate start/send/receive, altered launch ownership,
incorrect physical ports, early dependency release, inactive versions, nonlocal
changes, missing readiness/commit delivery and insufficient serialization delay.
Write negative fixtures for each invariant and verify missing-module failure,
then implement and run the focused suite.

## Task 2: Runtime pending-flow target

File: `simulation/LimerDynamicDagReplay.cc`. Reuse the static adapter's graph
parser, source/destination dependency release and transport drain checks.
Replace unconditional receive preposting with per-launch ownership; attach plan
version to each flow event. Control requests are a separate scripted input file:
`capacity_bps propagation_ns timeout_ns request_count`, then
`version request_ns affected_rank unavailable_rank`. Only consecutive versions
are accepted. Each PREPARE, READY and COMMIT occupies 64 bytes on one FIFO;
propagation applies to every delivered message. All ranks must receive COMMIT
before common activation. A missing ready vote times out without activation.
Include monotonically increasing event order for equal-time causal auditing.

## Task 3: Build and registered engineering campaign

Files: `simulation/build_dynamic_dag.py`, `simulation/run_dynamic_dag_gates.py`.
Build a separate scratch executable against the same pinned backend. Record source,
binary, image and library hashes before all attempts. Gate inputs retain the
existing dual-plane topology/configuration (including explicit ECN rows); they
are not a new scientific loss/slowdown benchmark.

Register: zero-control ring, commit during launched and pending work, long
propagation, missing readiness, multiple consecutive plans, and invalid version
rejection; add unequal-size same-source/destination/join micrographs. For every
case, state expected ownership and process result in registration before launch.
Successful cases must drain exactly and pass independent trace reconstruction.
Invalid-version rejection is an expected-error engineering case, not a successful
workload completion. Preserve every setup failure and unrun registration.

**What changes:** receive registration and route selection happen at runtime,
with versioned control delay and preserved ownership of launched work.
**Expected observation:** pending affected A flows use B only after activation;
launched and unaffected flows retain matching ports. Missing readiness never
activates. Every completed graph retains endpoint-aware dependency ordering.

## Task 4: Report and continue

Run focused and full suites on the Linux host, audit frozen campaign inputs, and
produce an uncommitted review diff and results note. Update the existing paper
with the user-approved detection category, retaining M8 failure classifications.
Online observation/controller integration and finite-horizon stay/switch efficacy
remain the next implementation gate; scripted requests are not detector output.
