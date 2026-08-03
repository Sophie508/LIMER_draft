# Architecture

## Research target and prototype boundary

The intended LIMER loop has three stages: a resource-conscious switch signal,
an uncertainty-aware end-host decision, and coordinated collective adaptation
without checkpoint rollback. This CPU prototype makes those interfaces and
their event ordering executable with explicit proxies. It does not claim a
production switch algorithm or a GPU recovery path.

Two generations coexist intentionally:

- legacy CPU v0 uses a scalar route and coordinated whole-ring A-to-B failover;
- active-active v1 uses an immutable per-step route plan and localized recovery.

The legacy `results/` tree is preserved. New v1 evidence is written only to
`results_active_active/`.

## Emulated Dual-ToR network

`limer_v0.topology.build_topology()` creates four Mininet hosts (`w0`-`w3`) and
one or two standalone OVS bridges:

- `single`: Fabric A (`sA`) and one access link per worker;
- `dual`: independent Fabrics A (`sA`) and B (`sB`), with one access link per
  worker per fabric.

Every switch-facing interface receives a 100 Mbit/s, 1 ms `netem` profile. In
the v1 fault scenarios, only rank 2's worker-side Fabric A interface `w2-eth0`
changes to 20 Mbit/s. The switch-facing peer `sA-eth3` retains its baseline
qdisc and supplies the observed RX counter. Both endpoints must remain `UP`.
This placement gives causal separation: the detector cannot succeed by reading
the configured qdisc of the injector.

Persistent TCP rings exist on both fabrics in v1, and both carry ordinary
healthy traffic before a fault.

## Per-step active-active route plan

`limer_v0.route_plan.RoutePlan` maps each `(sender rank, collective step)` to a
fabric. It validates rank and step coverage, supported fabrics, world size, and
policy, then derives a canonical JSON representation and SHA-256 fingerprint.
The object is immutable once constructed.

The balanced healthy schedule selects Fabric A when:

```text
(sender_rank + step) % 2 == 0
```

and Fabric B otherwise. Four ranks execute six steps per round, so A and B both
carry traffic in every step. A localized rank-2/A recovery changes exactly the
three rank-2 slots that originally selected A. Other sender schedules remain
byte-for-byte identical. Global failover is available only through an explicit
comparison policy.

## Workload data path

`limer_v0.worker` creates persistent TCP rings for every available fabric. At
each step a worker:

1. sends on the fabric selected by its own route-plan entry; and
2. receives on the fabric selected for the predecessor rank at the same step.

This is why all ranks must install the same plan even when only one sender's
entries change. The protocol coordinates shared interpretation; it does not
imply that every worker reroutes.

Each worker sends one framed 2 MiB chunk per step. A frame carries round, step,
plan version, payload length, and CRC32 fields from `limer_v0.protocol`. These
fields support transport-integrity and mixed-plan checks. The bytes are not
reduced, so the checks do not prove numerical AllReduce correctness.

## Three-layer control sequence

### Layer 1: switch-counter management proxy

`limer_v0.sentinel.SentinelRule` calibrates a median RX-rate baseline from the
switch-facing peer. It emits `SWITCH_SUSPECT` after three consecutive samples
below 60% of baseline while the port is not down.
`limer_v0.orchestrator.SwitchSampler` targets a 20 ms polling interval.

The Python process runs in the root namespace. It demonstrates a switch-first
counter interface, not ASIC, switch-CPU, SONiC, gNMI, or P4 residency. No switch
resource budget is established.

### Layer 2: deterministic end-host gate

`limer_v0.refiner.HostRefiner` combines:

1. Layer 1 suspicion;
2. completed-round duration relative to a matched baseline threshold; and
3. health of the alternate path.

It returns `confirm`, `suppress`, or `defer`. The active-active persistent case
should confirm; the short transient should suppress. Neuro-fuzzy classification
and Gaussian-process uncertainty are not implemented.

### Layer 3: coordinated localized plan transition

`limer_v0.coordinator.RecoveryCoordinator` proposes a full target plan, its
fingerprint, a new version, and an effective future round. Every worker checks
the proposal through `limer_v0.state.RouteState` and replies `READY`. Commit
occurs only when all ranks echo the same version, fingerprint, and effective
round; otherwise the transition aborts and the current plan remains active.

For `AA3_LOCAL`, the target plan changes only worker 2's three baseline-A send
slots. Every rank still installs that plan at the same completed-round boundary
so each receiver opens the correct fabric for its predecessor.

This remains a route-state scaffold. It does not rebuild a PyTorch process
group or NCCL communicator, and its host confirmation still waits for a full
round.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `topology.py` | Build single/dual Mininet-OVS fabrics, assign interfaces, apply base qdiscs, and run ping tests |
| `faults.py` | Validate and apply `tc/netem` profiles and read interface/qdisc state |
| `qdisc.py` | Parse `tc -s -j` samples into typed counter records |
| `protocol.py` | Encode and validate framed TCP messages with CRC32 |
| `route_plan.py` | Build, validate, fingerprint, compare, and localize immutable per-step plans |
| `worker.py` | Maintain both rings, use asymmetric send/receive plan entries, and report per-fabric evidence |
| `sentinel.py` | Calibrate and evaluate the high-recall switch-counter proxy |
| `refiner.py` | Confirm, suppress, or defer recovery from impact and alternate-path health |
| `state.py` | Enforce prepared, committed, and aborted per-worker plan state |
| `coordinator.py` | Enforce all-rank prepare/READY/commit or abort with fingerprint agreement |
| `orchestrator.py` | Own lifecycle, sampling, faults, rounds, artifacts, correctness, and cleanup |
| `metrics.py` | Calculate interval throughput and matched-baseline retention |
| `report.py` | Validate schemas, re-evaluate gates, and generate CSV, JSON, README, and SVG reports |

## Artifact flow

```text
predeclared config JSON
        │
        ▼
orchestrator ── topology / workers / switch sampler
        │
        ├── inject directed worker-side qdisc impairment
        ├── receive SWITCH_SUSPECT
        ├── evaluate completed-round host gate
        ├── coordinate plan version + fingerprint
        └── write per-run JSON, JSONL, and CSV artifacts
                                  │
                                  ▼
                              report.py
                                  │
                                  ├── schema and gate evaluation
                                  ├── summary.csv
                                  ├── aggregate_summary.json
                                  └── SVG plots and results README
```

Per-run `correctness.json` separates framing, plan consistency, healthy
active-active use, and locality gates. `summary.json` records route-plan deltas,
matched-baseline retention, and separate switch, host, coordination,
commit-to-completion, and fault-to-restoration latency stages.
