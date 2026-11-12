# Phase-scoped recovery integration — 2026-11-12

This working revision follows the collaborator meeting transcript. The source
remains in [the existing project directory](../2026-10-28-rdma/project/) to keep
the code diff reviewable. The directory's date identifies its origin, not a new
frozen validation claim. The immutable previous release is
[501a0f50](https://github.com/Sophie508/LIMER_draft/tree/501a0f50f51fd90c9ea9d3582b08e17fee4590ab/versions/2026-10-28-rdma).
Its source-hash verifier deliberately does not certify these changed files.

## Meeting diagnosis

- `StartPhase` cleared readiness but retained `binding.disabled/configured`.
  Consequently the original B was permanently excluded after first activation,
  and subsequent phases did not receive a new benefit authorization. The
  supplied original ZIP has the same dispatcher hash as the October release:
  this behavior predates the benefit gate.
- A short phase can legitimately drain all unallocated work on A while waiting
  for idle helpers, a full probe, its health report and coordination. An
  activated proxy can then rescue old B suffixes without receiving new chunks.
  This is a workload/opportunity constraint as well as a lifecycle question.
- `<100 ms` is the impairment detection deadline, not the job horizon. The
  previous formal matrix used 400 ms, and a separate slow-helper boundary
  used 800 ms. New development horizons are recorded in registration.
- Adaptive splitting assigns 64 KiB chunks. The ns-3 backend transports packets
  within each chunk; using a packet backend does not make the splitting policy
  a per-packet routing algorithm.

## Implemented change and observation points

`--replacement-lifetime phase` resets the route binding at each existing
scheduler phase barrier; the first original-lane allocations are explored again.
A new version rejects stale callbacks. Helpers must finish their current own
work and every new phase pays the probe, delivered health report and full
PREPARE/READY/COMMIT exchange. Benefit authorization is checked again.

The reset does not heal B, erase fault truth or clear a previously received
path alarm. A persistent physical impairment remains known. The implementation
still does not model a separate distributed observation-exchange protocol.
`--replacement-lifetime persistent` keeps the old behavior as an explicit
comparison. `A_ONLY` uses A for all business while retaining the same two-plane
topology and detector traffic.

`phase_route_lifecycles` records per-phase original B allocations, reset and
activation times, unallocated bytes at activation, and fresh B-prime
completions. Fresh data is distinguished from rescued suffixes. Logical DONE
means that the final modeled receiver leg and required source notification
finished; phase completion waits for all 16 workers' declared chunk transfers.
It is not numerical AllReduce or GPU gradient computation.

## What the ablations mean

G00 fixes original A/B ownership and disables detection-driven recovery; G10
uses adaptive allocation without recovery. G01 fixes ownership and permits
proxy recovery; G11 combines adaptive allocation with recovery. Both G11
policies measure the same full helper route; only the benefit policy can
reject the replacement. The detector runs in shadow in disabled-recovery
arms so observation cost is held constant. These are not zero-detector-cost
arms, external-system reproductions or a proof that external systems are
incomparable.

A_ONLY is a business single-plane control, not a topology with B removed.
Faults, observation traffic and link costs remain registered identically.
Do not compare completion times across different chunk counts/phase counts;
the short and long pilots explain opportunity, while each method comparison
uses exactly matched workloads.

## Development protocol

The plan declares 38 cases before execution: four lifecycle/opportunity pilots,
30 matched internal ablations and four full 30-phase ring checks. The 4-phase
matrix is a development diagnostic; the public default remains 30 phases per
round. All cases use the unchanged detector, representative probe and charged
control costs. No A traffic is deliberately held back to create B-prime work.

Source/build hashes, exact conditions and every attempt are registered before
execution. Completed communication, unfinished tasks, alarms, new B-prime
traffic and recovery speed are separate outcomes. This matrix is not a new
independent 95% acceptance study or an external-system head-to-head comparison.

```bash
cd versions/2026-10-28-rdma/project
python3 limer.py check --verbose
python3 limer.py build --out /work/integration-build --jobs 8
python3 tools/integration_campaign.py plan --out /work/integration-plan.json
python3 tools/integration_campaign.py register --build /work/integration-build --out /work/integration-development
python3 tools/integration_campaign.py execute --out /work/integration-development --workers 2
```

## Verified results and present recommendation

The original 38-case registration and two separately registered follow-ups
(1 lifetime control and 2 full-ring weak-loss cases) are complete. All 41 runs
passed execution and observation audits; 36 communication jobs completed and
five remained unfinished. Policy replay is also checked where the gate runs.

- [All comparison tables and limitations](results/RESULTS.md)
- [Main registered trial table](results/development-v1/trials.csv)
- [Full-ring lifetime control](results/lifetime-full-v1/trials.csv)
- [Full-ring weak-loss pair](results/gray-full-v1/trials.csv)
- [Compact execution evidence and archive receipts](evidence/)

In the 30-phase blackhole case, repaired phase mode completed 762 new B-prime
chunks over 28 phases: 907.90 ms versus A-only's 959.85 ms and healthy
active-active's 480.18 ms. The integration is functional; healthy dual-plane
throughput has not been restored. The short phase still has zero fresh
B-prime completions and a reset/coordination cost.

Use service detection + adaptive allocation + direct recovery (`G11`,
`service/always`, `phase`) as the demonstrated integration reference for the
meeting. Keep the benefit gate as an experimental option: the full weak-loss
pair takes 975.89 ms gated versus 694.96 ms direct, despite more fresh B-prime
chunks under gating. The gated run made 132 candidate probes versus 56;
this is an observed cost difference, not a proven causal explanation of the
entire slowdown. The short ACK-service predictor and repeated-probe strategy
need further analysis before claiming a successful switching-benefit policy.

All 34 fault-arm checks in these related development runs were timely and
correctly localized; the seven related healthy controls were clear. This is
not a new independent 95% acceptance study. The original October evidence and
all short/unfinished/negative outcomes remain available.

For one full-ring blackhole case with the registered comparison seed:

```bash
python3 limer.py run --build /work/integration-build --out /work/full-ring-check \
  --method G11 --scenario blackhole --rounds 1 --chunks 512 \
  --detector service --policy benefit --replacement-lifetime phase \
  --phases-per-round 30 --horizon-ms 2000 --fault-ms 40 --seed 111210016
```

Read `performance.json`'s `new_Bprime_completions` for delivered fresh chunks;
the historical CLI `fresh_proxy` field reports launches. The supplemental
full-ring weak-loss pair uses the separate registered seed 111210016. Compare
policies within that pair; the short/full weak-loss difference is not a
single-variable causal test of phase count.


For portable compact integrity and table re-derivation from the repository root:

```bash
python3 versions/2026-11-12-integration/verify_compact.py
```

This checks all compact member hashes, the native source/build linkage, case
parameters and regenerated tables. The independent raw packet replay and final
41-archive hash verification were executed on otakotak; their receipts are
included. It does not claim to rerun raw packet replay on a laptop.
