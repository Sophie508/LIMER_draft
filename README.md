# LIMER CPU-Only Emulation Prototype

> **Interactive project demo:** [https://sophie508.github.io/LIMER_draft/](https://sophie508.github.io/LIMER_draft/)
>
> The page is a bilingual, evidence-driven stage review. It replays archived
> measurements; it is not a live hardware experiment.

LIMER stands for **Lightweight In-Network Monitoring with Efficient End-Host
Recovery**. The research goal is to notice a network gray failure close to the
switch, confirm that it is harming collective communication at the end host,
and adapt communication without rolling training back to a checkpoint.

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

| LIMER layer | Executable CPU prototype | Still required for the research system |
|---|---|---|
| Switch-side first signal | 20 ms target polling of an isolated switch-facing Linux RX counter; persistent high-recall rule | Switch-resident or production streaming telemetry, resource budget, broader symptoms |
| End-host refinement | Deterministic impact and alternate-path health gate | Neuro-fuzzy classifier, calibrated GP uncertainty, NIC/NCCL signals |
| Recovery | Immutable per-step route plans; all-rank prepare/READY/commit; localized worker-2 delta | PyTorch/NCCL integration, real communicator adaptation, production failure handling |

The current latency path still waits for a completed round before host
confirmation. Raw v1 latency stages are recorded in milliseconds, but no
formal numeric target was supplied and this repository does not claim that
millisecond end-to-end recovery has been achieved.

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
studies up to 128 simulated GPUs. Real GPU/NCCL communicator recovery remains a
later systems milestone and is not claimed by this repository.
