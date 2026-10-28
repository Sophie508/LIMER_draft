# LIMER CPU-Only Emulation Prototype

> **Latest research version (2026-10-28):** Start at
> [the RDMA detector and switching-benefit release](versions/2026-10-28-rdma/README.md).
> It contains runnable source, collaborator-relative changes, all registered
> conditions, 640 new compact run records, the retained failed validation,
> results and the current paper snapshot. Earlier sections below keep their
> historical evidence scope.

> **Collaborator handoff (2026-10-22):** Start at
> [handoff/README.md](handoff/README.md) for implemented components, registered
> conditions, paper-to-code mappings, archived results and portable CPU/Docker
> entry points. The handoff is based on the last verified 2026-10-15 paper
> snapshot. Historical sections below retain their original evidence scope.

> **Interactive project demo:** [https://sophie508.github.io/LIMER_draft/](https://sophie508.github.io/LIMER_draft/)
>
> The page is a bilingual, evidence-driven stage review. It replays archived
> measurements; it is not a live hardware experiment.

LIMER stands for **Lightweight In-Network Monitoring with Efficient End-Host
Recovery**. The research goal is to notice a network gray failure close to the
switch, confirm that it is harming collective communication at the end host,
and adapt communication without rolling training back to a checkpoint.

## Current project scope: simulation and emulation

Sophie confirmed on 2026-10-10 that this project ends at an implemented and
evaluated simulation. Real switch/NIC access, GPU experiments and deployment
are not acceptance requirements. Mininet provides executable CPU/TCP emulation;
SimAI/ns-3 provides a separate packet-level simulation track. Their results and
time bases must remain separate.

The primary research target is a correctly localized gray-fault decision below
100 ms, with late/missed detections and false alarms retained. The project also
studies when localized rerouting pays off and whether coordinated execution is
correct. M7 implements a passive TCP candidate but does not meet that target:
72/80 fault trials were timely, and 3/5 long-reordering stress trials produced
false alarms. Simulation-only scope does not change this verdict.

See [the simulation scope and continuation pipeline](docs/simulation_scope.md)
and [the frozen M7 results](docs/m7_tcp_loss_results.md). Simulated observations
must have explicit delay, noise and availability assumptions; hidden injector
state is available to the scorer only.

M8 adds a costed two-ended batch-counter candidate in isolated ns-3 UDP
simulation. All 200 primary and 25 stress lifecycles pass packet accounting;
139/160 primary loss decisions are below 100 ms. The strict deadline gate still
fails: low offered-rate weak-loss cases retain late/missed decisions, and excess
delay/queue stress triggers no-permanent-loss alarms. This is not yet a dynamic
collective or route-controller result. See [M8 results](docs/m8_batch_observation_results.md)
and the [next dynamic simulation design](docs/m9_dynamic_simulation_design.md).

Severe slowdown is now also eligible for detection, followed by separate
route-benefit evaluation. M9 implements the first native SimAI pending-flow
cutover: eight scripted workloads drain correctly and one invalid-version case
is rejected as expected. Launched flows retain their ports; pending affected
flows can change after charged all-rank coordination. These engineering checks
do not yet establish online detection or adaptive-policy benefit. See
[M9 execution results](docs/m9_dynamic_execution_results.md).

M10/M11 now add native causal ACK-progress detection and an observable pending
route-cost decision. In the registered finite ring workload, candidate switching
reduces total completion from 1545.674 to 1339.485 ms with a faster alternative;
with a slower alternative it stays and completes in 3958.544 ms, whereas fixed
switching takes 5360.714 ms. These bounded configured-rate simulations retain
the unresolved weak-loss/idle/telemetry-delay constraints and do not establish
optimality or GPU throughput. See [online results and limitations](docs/m10_m11_online_results.md).

This repository now contains two clearly separated stages:

- **Legacy CPU v0 evidence** reproduces the minimum two-week demo and a first
  closed loop. Its recovery moves the whole four-worker ring from Fabric A to
  Fabric B. The archived 18 runs and their measured numbers remain unchanged.
- **Active-active v1** implements the corrected Dual-ToR model. Both fabrics
  carry normal traffic before a fault. A directed egress degradation on worker
  2's Fabric A path leads to a **localized** plan that changes only worker 2's
  three affected send slots. All ranks still coordinate one plan fingerprint
  so senders and receivers change consistently at the same round boundary.

The v1 data builder accepts replay data only when three complete `AA3_LOCAL`
artifacts exist under `results_active_active/`. The repository now contains
that measured three-repeat evidence, so the public replay resolves to raw
Linux/Mininet summaries, events, and correctness records rather than synthetic
values.

## Concrete v1 scene

```text
 Healthy round: A and B both carry ring steps

              ┌────────── Fabric A ──────────┐
 w0, w1, w2, w3                              │
              └────────── Fabric B ──────────┘

 Fault: only w2 -> Fabric A egress is rate-limited 100 -> 20 Mbit/s
        both endpoints remain UP

 switch-facing counter -> host confirmation -> all-rank coordination
                                             -> one localized route plan

 After commit: only w2 slots that previously used A move to B
               w0, w1, and w3 schedules remain unchanged
```

The healthy plan is deterministic: sender rank `r` uses Fabric A for step `s`
when `(r + s) % 2 == 0`, otherwise Fabric B. With four ranks and six ring steps,
both fabrics carry traffic in every step. The fault is injected with Linux
`tc/netem` on `w2-eth0`; the detector reads the distinct switch-facing peer
`sA-eth3` and cannot inspect the injector qdisc.

All-rank coordination does **not** mean that every worker reroutes. Each worker
must know the same immutable plan because a receiver has to listen on the
fabric selected by its predecessor for that step. The prepare/READY/commit
protocol therefore installs one version and fingerprint everywhere while the
plan delta remains local to worker 2.

## What the workload represents

The traffic generator is a Python TCP ring with four namespace-isolated
workers. Each worker sends six framed 2 MiB chunks per round, mirroring the
volume and synchronization pressure of a four-rank ring collective. Frames
carry round, step, plan version, payload length, and CRC32 fields.

It does not sum tensors, perform reduce-scatter, or all-gather. It is therefore
described as **AllReduce-like**, not as numerical AllReduce, NCCL, or RDMA.

## Preserved legacy v0 evidence

The existing denominator is 18 clean topology lifecycles: C0-C5, each repeated
three times. No failed repeat is discarded. All 18 completed with zero checksum
and route-version errors, and the injector and detector remained distinct.

| Condition | What changed in legacy v0 | Median selected retention | Gate result |
|---|---|---:|---:|
| C0 | Fault-free control | 1.001 | 3/3 |
| C1 | Rank 2 A link at 20 Mbit/s; no detector | 0.213 | 3/3 |
| C2 | Same fault; counter-proxy detection only | 0.212 | 3/3 |
| C3 | Detection + host gate + whole-ring move to B | 0.865 post-recovery | 1/3 |
| C4 | Oracle-triggered whole-ring move to B | 0.980 post-recovery | 3/3 |
| C5 | 100 ms transient degradation | 0.988 | 3/3 |

The legacy overall verdict remains **NO-GO: 16/18 predeclared run gates pass**.
C3 recovery passed its fixed `0.9` gate in only one of three repeats. Median
switch detection in C3 was 51.94 ms, but the completed-round host gate took a
median 5.27 s. Those values describe v0 and are not silently reused as v1
measurements.

The authoritative legacy aggregate is
[`results/aggregate_summary.json`](results/aggregate_summary.json), with raw
run rows in [`results/summary.csv`](results/summary.csv). Metric definitions
and the historical field-name caveat are in
[`docs/experiment_design.md`](docs/experiment_design.md).

## v1 scenario matrix

The seven predeclared v1 configurations hold the four-worker, 100-to-20 Mbit/s
scene constant while isolating control-loop behavior:

| Scenario | Detector | Recovery | Purpose |
|---|---|---|---|
| AA0_HEALTHY | Off | None | Prove healthy active-active A/B use |
| AA1_FAULT | Off | None | Measure the persistent fault without mitigation |
| AA2_DETECT | On | None | Show detection alone does not restore performance |
| AA3_LOCAL | On + host gate | Localized | Test the intended v1 closed loop |
| AA3_GLOBAL | On + host gate | Explicit global baseline | Compare against legacy-style global failover |
| AA4_ORACLE | Oracle | Localized | Estimate the emulation recovery upper bound |
| AA5_TRANSIENT | On + host gate | Suppressed | Check false-trigger suppression |

No policy silently falls back from localized to global recovery. The global
comparison has its own explicit configuration.

## Measured active-active v1 results

The formal v1 denominator is 21 clean topology lifecycles: seven scenarios,
each repeated three times. All 21 completed with correctness `pass`, zero
checksum errors, and zero route-version errors. The predeclared performance
gates pass in 20/21 runs, so the honest overall verdict is **NO-GO** rather than
an all-green claim.

| Scenario | Median selected retention | Gate result |
|---|---:|---:|
| AA0_HEALTHY | 1.000 | 3/3 |
| AA1_FAULT | 0.371 | 3/3 |
| AA2_DETECT | 0.371 | 3/3 |
| AA3_LOCAL | 0.936 post-recovery | 3/3 |
| AA3_GLOBAL | 0.961 post-recovery | 2/3 |
| AA4_ORACLE | 0.947 post-recovery | 3/3 |
| AA5_TRANSIENT | 0.993 | 3/3 |

`aa3_global_rep02` is the retained failure: its post-recovery retention was
0.882, below the fixed 0.9 gate, despite complete transport and plan
correctness. The intended localized policy passed all three repeats and changed
exactly worker 2's three affected slots each time. Its median switch-suspicion
latency was about 2.78 s, median host refinement after suspicion about 91 ms,
median coordination about 0.55 ms, and median fault-to-completed-recovered-round
latency about 3.96 s. These values expose the whole-round confirmation
bottleneck; they do not satisfy a millisecond end-to-end claim.

The authoritative v1 aggregate is
[`results_active_active/aggregate_summary.json`](results_active_active/aggregate_summary.json),
with one formal run per row in
[`results_active_active/summary.csv`](results_active_active/summary.csv).

## Architecture status

| LIMER layer | Executable CPU prototype | Remaining simulation work |
|---|---|---|
| Switch-side first signal | 20 ms target polling of an isolated switch-facing Linux RX counter; persistent high-recall rule | Independent simulated observations with explicit sampling delay, observation cost and broader fault/control profiles |
| End-host refinement | Deterministic impact and alternate-path health gate; opt-in M7 TCP loss candidate | A validated <100 ms gray-fault decision under declared traffic and delay assumptions; M7 fails the current gate |
| Recovery | Immutable per-step route plans; all-rank prepare/READY/commit; localized worker-2 delta | Cost-aware switch/stay comparison including detection, coordination and unfinished work; packet-level execution validation |

The current latency path still waits for a completed round before host
confirmation. Those archived v1 stages do not establish the current <100 ms
detection target, and detection time must remain separate from coordination and
completed-recovery time.

The current requirement-by-requirement evidence boundary is recorded in
[`docs/active_active_v1_verification.md`](docs/active_active_v1_verification.md).

## Repository map

```text
limer_v0/                  Topology, workload, detector, route plan, coordinator, reports
configs/                   Preserved legacy C0-C5 configurations
configs/active_active_v1/  Seven predeclared active-active scenarios
tests/                     Unit, schema, loopback, replay, and site checks
results/                   Immutable legacy v0 evidence
results_active_active/     Generated v1 evidence after Linux/Mininet execution
docs/                      Architecture, evidence semantics, limitations, and public site
```

Proposal files, collaboration contacts, credentials, and private research
archives are intentionally outside this code artifact.

## Requirements

Topology experiments require Linux with:

- Python 3;
- Mininet 2.3 or compatible;
- Open vSwitch;
- `iproute2` with `tc/netem`; and
- privileges to create namespaces, links, qdiscs, and OVS bridges.

A GPU is not required for this CPU prototype. The archived v0 host environment
is recorded in [`environment_probe.txt`](environment_probe.txt).

## Verify locally

From the repository root:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_replay_state.mjs
node --check docs/assets/js/replay.js
node --check docs/assets/js/app.js
python3 -m compileall -q limer_v0 scripts tests
python3 scripts/build_demo_data.py --check
git diff --check
```

The socket loopback integration test may skip on macOS when arbitrary `127/8`
aliases cannot be bound. The Linux/Mininet experiment is the authoritative
coverage for that path.

## Run focused v1 experiments

Use a separate results tree so legacy evidence stays immutable:

```bash
sudo python3 -m limer_v0.orchestrator \
  --config configs/active_active_v1/aa0_healthy.json \
  --results-dir results_active_active \
  --workdir "$PWD" \
  --run-id aa0_healthy_rep01

sudo python3 -m limer_v0.orchestrator \
  --config configs/active_active_v1/aa3_local.json \
  --results-dir results_active_active \
  --workdir "$PWD" \
  --run-id aa3_local_rep01
```

Inspect `correctness.json`, `worker_rounds.csv`, `aggregate_rounds.csv`,
`version_commits.csv`, and `summary.json` before running the full matrix. The
AA0 gate requires measured use of both fabrics. AA3_LOCAL requires exactly
three changed slots, all owned by sender rank 2, plus one committed fingerprint
across all ranks.

After three repeats of all seven scenarios:

```bash
python3 -m limer_v0.report --results-dir results_active_active
python3 scripts/build_demo_data.py --write
python3 scripts/build_demo_data.py --check
python3 -m http.server 8000 --directory docs
```

The reporter preserves failed repeats and can return non-zero when a
predeclared gate fails. A non-zero result is evidence to inspect, not a reason
to delete or retune a run.

## Next realism milestones

The immediate engineering bottleneck is step-level confirmation: the current
host gate waits for a whole slow round. Fault coverage must then expand from
the directed egress rate cap to bidirectional, low-loss, queue, and duration
profiles. SimAI is the next scale/collective-simulation milestone for realistic
studies up to 128 simulated GPUs. Simulating the detection and decision loop is
part of the current project; static post-reroute results alone do not implement
it. Real GPU/NCCL communicator recovery is outside the agreed project scope.

## M12 bounded hybrid detection result

The frozen one-hop UDP validation reaches the prospective empirical target:
698/700 correctly localized alarms are STRICTLY below 100 ms, and EACH of
13 registered fault conditions reaches at least 95%. The two late decisions
remain in their denominators; 40 negative controls have zero alarms. These
are simulated timings, independent of the archived Mininet wall-clock results.

Continuous same-path probes and aligned early service windows create this
result at a material cost: 17.92 Mb/s/path and 4.9152 Mb/s collection traffic.
It assumes size-independent packet faults and configured report service.
A matched business-only size-selective supplement reaches only 5/20 timely
alarms despite real business losses, so broader fast gray-fault coverage
remains unresolved. The hybrid detector has not been integrated with the
M11 collective route loop. Older strict FAIL verdicts remain unchanged.

See [the full results and failure ledgers](docs/m12_hybrid_detection_results.md),
[the prospective plan and amendments](docs/m12_hybrid_detection_plan.md), and
[the reproduction interface](simulation/README.md#hybrid-delivery-detection-m12).


## M13 representative business-delivery detection

The M13 candidate separates business/probe delivery counters and receiver
sequence gaps, preserving M12 as an independently scored fallback/shadow.
At the original 100 Mb/s, 17.92 Mb/s probe budget it retains FAIL: selective
16/20 and application loss 13/20 are timely. Workload-shaped probes at the
same nominal byte budget improve selective recall but retain application
and idle failures. These negative results stay in the released ledgers.

An explicitly changed 10 Gb/s, 420 Mb/s/path representative-probe envelope
passes fresh 460-case validation: 400/400 faults timely, 60 controls without
alarms, all independently audited. The same-report M12 baseline also meets
every condition's 95% gate (396/400 timely), so changed observations account
for most of the gain. This does not establish general gray-fault coverage
or joint collective recovery. A causal traffic-compensating policy passes fresh independent validation:
400/400 timely faults, 60 primary and 60 supplemental high-traffic
controls without alarms. Under the adaptive budget, the matched shadow
misses the idle target (55/60 timely versus candidate 60/60), whereas
both pass the constant high-budget envelope. At 1 Gb/s continuous business, actual lifecycle
probe cost falls to 10.843 Mb/s/path; sparse/idle traffic still needs substantial
probes. The result remains conditional on the same 10 Gb/s envelope.

See [M13 measured results, costs and retained failures](docs/m13_business_detection_results.md),
[the prospective amendments](docs/m13_business_detection_plan.md), and
[the reproduction interface](simulation/README.md#class-separated-business-observations-m13).
