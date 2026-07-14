# Architecture

## Research target and v0 boundary

The intended LIMER control loop has three stages: a resource-conscious switch
signal, an uncertainty-aware end-host decision, and coordinated collective
adaptation without checkpoint rollback. CPU v0 implements the interfaces and
event ordering of that loop with explicit proxies. It does not claim that the
final switch algorithm or GPU recovery path exists.

## Emulated network

`limer_v0.topology.build_topology()` creates four Mininet hosts (`w0`-`w3`) and
one or two standalone OVS bridges:

- topology `single`: fabric A (`sA`) and four access links;
- topology `dual`: independent fabrics A (`sA`) and B (`sB`), with one access
  link per worker per fabric.

Each switch-facing access interface receives a 100 Mbit/s, 1 ms `netem`
profile. In fault conditions, only rank 2's worker-side A interface `w2-eth0`
changes to 20 Mbit/s. The switch-facing peer `sA-eth3` retains its baseline
qdisc and supplies the observed RX counter. This placement is the experiment's
causal separation: detection cannot succeed by reading the configured state of
the injector.

Fabric B is a stated redundancy assumption, not something the software invents
after a single-homed link fails. C0-C2 use the single topology; C3-C5 use the
dual topology.

## Workload path

`limer_v0.worker` creates persistent TCP rings for every available fabric. Four
ranks run six steps per round (`2 * (world_size - 1)`). At each step a worker
sends and receives one framed chunk. The default 2 MiB chunk therefore produces
12 MiB sent per rank and 48 MiB aggregate application payload per completed
round.

Each frame carries round, step, route version, payload length, and CRC32 fields
defined in `limer_v0.protocol`. This supports transport-integrity and
mixed-version checks. The payload is not reduced, so these checks do not prove
numerical AllReduce correctness.

## Three-layer control sequence

### Layer 1: switch-counter management proxy

`limer_v0.sentinel.SentinelRule` calibrates a median RX-rate baseline from the
switch-facing peer. After calibration, it emits `SWITCH_SUSPECT` when observed
rate stays below 60% of baseline for three consecutive samples while the port
is not down. `limer_v0.orchestrator.SwitchSampler` targets a 20 ms polling
interval.

The Python process runs in the root namespace. It demonstrates a switch-first
counter interface, but it is not resident in an ASIC, switch CPU, SONiC agent,
or P4 pipeline. No switch memory or RSS budget is enforced.

### Layer 2: deterministic end-host gate

`limer_v0.refiner.HostRefiner` consumes three pieces of evidence:

1. a Layer 1 suspicion;
2. completed-round duration relative to 1.5 times the matched baseline p95;
3. health of standby fabric B.

It returns `confirm`, `suppress`, or `defer`. C3 confirms a persistent impact;
C5 suppresses a short transient. The `confidence` and `calibration_version`
fields remain null because no neuro-fuzzy classifier or Gaussian process has
been trained. The deterministic rule is intentionally not presented as ML.

### Layer 3: versioned route transition

`limer_v0.coordinator.RecoveryCoordinator` proposes the next route version and
an effective future round. Every worker validates the proposal through
`limer_v0.state.RouteState`, replies `READY`, and applies the route only after a
commit. If any rank is missing, the coordinator aborts. In C3, the safe point is
the boundary after the degraded collective round; the first new-route round is
on fabric B with version 1.

This is a protocol scaffold. It does not rebuild a PyTorch process group or
NCCL communicator, and it assumes both TCP fabric rings were established before
the fault.

## Module responsibilities

| Module | Responsibility |
|---|---|
| `topology.py` | Build single/dual Mininet-OVS fabrics, assign interfaces, apply base qdiscs, and run ping smoke tests |
| `faults.py` | Validate and apply `tc/netem` profiles and read interface/qdisc state |
| `qdisc.py` | Parse `tc -s -j` samples into typed counter records |
| `protocol.py` | Encode and validate framed TCP messages with CRC32 |
| `worker.py` | Maintain per-fabric rings, execute rounds, and obey versioned control commands |
| `sentinel.py` | Calibrate and evaluate the high-recall switch-counter proxy rule |
| `refiner.py` | Confirm, suppress, or defer recovery from end-host impact and standby health |
| `state.py` | Enforce per-worker prepared and committed route state |
| `coordinator.py` | Enforce all-rank prepare/READY/commit or abort |
| `orchestrator.py` | Own experiment lifecycle, sampling, faults, rounds, artifacts, and cleanup |
| `metrics.py` | Calculate throughput distributions and matched-baseline retention |
| `report.py` | Re-evaluate run gates and generate aggregate CSV, JSON, README, and SVG reports |

## Artifact flow

```text
config JSON
    │
    ▼
orchestrator ── builds topology / launches workers / starts counter sampler
    │
    ├── injects worker-side qdisc fault
    ├── receives SWITCH_SUSPECT
    ├── evaluates host gate
    ├── coordinates route version (when confirmed or oracle-triggered)
    └── writes immutable per-run artifacts
                         │
                         ▼
                    report.py
                         │
                         ├── run gate evaluation
                         ├── summary.csv
                         ├── aggregate_summary.json
                         └── SVG plots and results README
```

The report selects post-recovery retention for C3/C4 and post-marker or
post-fault retention for C0/C1/C2/C5. Detailed definitions are in
[`experiment_design.md`](experiment_design.md).
