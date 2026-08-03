# Active-Active v1 Verification Record

Status: **LINUX/MININET MATRIX COMPLETE; 20/21 PREDECLARED RUN GATES PASS**

Date: 2026-08-03

This record separates executable mechanism checks, measured emulator results,
and claims that remain outside the prototype. All v1 values below resolve to
raw artifacts under `results_active_active/`; no missing repeat was replaced and
no numeric millisecond target was invented.

## Change and expected observation

Changed:

- scalar whole-ring routing was replaced with immutable sender-by-step plans;
- the healthy Dual-ToR schedule uses Fabric A and Fabric B concurrently;
- the persistent impairment is worker 2's directed Fabric A egress;
- localized recovery changes only worker 2's baseline-A send slots; and
- every rank coordinates one version, fingerprint, and effective round.

Expected:

- healthy rounds use both fabrics and one version-0 fingerprint;
- a localized target contains exactly three worker-2 A-to-B changes;
- workers 0, 1, and 3 keep their sender schedules;
- sender and receiver route choices remain mutually compatible;
- failed repeats remain visible; and
- raw latency stages are reported without an invented pass threshold.

## Execution environment

The matrix ran in a privileged Ubuntu 24.04 container on a Fedora 44 x86-64
host. The host exposed Docker 29.6.2, `tc`, the Fedora Open vSwitch kernel
module, about 60 GiB RAM, and sufficient disk space. The local container image
contained Python, Mininet, Open vSwitch, `iproute2`, and `kmod`. A pre-experiment
`mn --test pingall` completed with 0% packet loss.

The uncommitted working tree was transferred without GitHub. The clean source
archive excluded `.git`, both result trees, caches, AppleDouble files, and
private files. Its local and remote SHA-256 was
`d4bf15cdf6f19b6f3d56216db5b45be495ac00e506f31baa5bd523595385ec61`.
Hashes for `route_plan.py`, all seven v1 configurations, and the implementation
plan also matched across hosts.

## Acceptance evidence

| Criterion | Authoritative evidence | Status |
|---|---|---|
| Healthy plan uses both fabrics | `aa0_healthy_rep01..03/correctness.json` and `aggregate_rounds.csv` | Pass 3/3 |
| Localized recovery changes only worker 2's three affected slots | `aa3_local_rep01..03/correctness.json` | Pass 3/3 |
| All ranks agree on version and fingerprint | `aa3_local_rep*/version_commits.csv` and worker rows | Pass 3/3 |
| Fault and detector endpoints remain UP and causally separate | Per-run summaries and manifests | Pass 21/21 |
| Retention uses each run's matched active-active baseline | Per-run summaries and report schema | Pass |
| Seven scenario semantics remain predeclared | `configs/active_active_v1/` | Pass |
| Failed repeats remain in the denominator | `summary.csv` retains `aa3_global_rep02` | Pass |
| Complete formal report has 21 runs and three per scenario | `aggregate_summary.json` | Pass |
| Website values resolve to three complete localized runs | `demo-data.json` source paths and builder tests | Pass |
| Commit and push controls | Feature-branch working tree remains uncommitted | Pass |

All 21 formal runs have status `complete`, correctness `pass`, zero checksum
errors, zero version errors, and empty worker stderr logs. The report contains
20 passing performance gates and one retained failure:

- `aa3_global_rep02`: post-recovery retention 0.882, below the fixed 0.9 gate.

This failure had a correct global plan, all-rank agreement, and no transport
error. The available evidence supports treating it as a valid performance
observation; it does not establish a specific causal explanation.

## Measured scenario summary

| Scenario | Median selected retention | Gate pass |
|---|---:|---:|
| AA0_HEALTHY | 1.000 | 3/3 |
| AA1_FAULT | 0.371 | 3/3 |
| AA2_DETECT | 0.371 | 3/3 |
| AA3_LOCAL | 0.936 | 3/3 |
| AA3_GLOBAL | 0.961 | 2/3 |
| AA4_ORACLE | 0.947 | 3/3 |
| AA5_TRANSIENT | 0.993 | 3/3 |

For `AA3_LOCAL`, the three-repeat median switch-suspicion latency was about
2777 ms, host refinement after suspicion about 91 ms, coordination about
0.55 ms, and fault-to-completed-recovered-round latency about 3958 ms. The
sub-millisecond coordination result does not make recovery end-to-end
millisecond-scale: the current detector waits for a degraded collective round.

## Verification commands

Local static and unit verification:

```bash
python3 -m unittest discover -s tests -p 'test_*.py'
node --test tests/test_replay_state.mjs
node --check docs/assets/js/replay.js
node --check docs/assets/js/app.js
python3 -m compileall -q limer_v0 scripts tests
python3 scripts/build_demo_data.py --check
git diff --check
```

Linux-specific focused verification executed 85 routing, protocol,
coordination, worker, configuration, correctness, latency, metric, and report
tests. It included the process-level worker loopback that macOS skips.

The result tree was independently audited after transfer: 21 formal run
directories, 21 report rows, seven scenarios with three repeats each, 21
complete/correct runs, 20 gate passes, one gate failure, and no missing required
artifact.

## Remaining research boundary

The completed evidence is still a four-worker CPU/Mininet framed-transport
prototype. It does not prove numerical AllReduce, GPU/NCCL or RDMA recovery,
switch-resident implementation, switch resource bounds, learned neuro-fuzzy or
Gaussian-process decisions, broad fault coverage, publication-level
statistics, or millisecond end-to-end recovery. The immediate systems task is
step-level confirmation; the next scale track is separately calibrated SimAI
evaluation up to 128 simulated GPUs.
