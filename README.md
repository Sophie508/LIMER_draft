# LIMER CPU-Only Emulation Prototype

> **Interactive project demo:** [https://sophie508.github.io/LIMER_draft/](https://sophie508.github.io/LIMER_draft/)
>
> The site is a bilingual, evidence-driven stage review of the archived
> CPU/Mininet prototype. It is not a live hardware experiment.

LIMER stands for **Lightweight In-Network Monitoring with Efficient End-Host
Recovery**. The research target is to detect network gray failures near the
switch, confirm their impact at the end host, and adapt collective
communication without rolling training back to a checkpoint.

This repository is the first CPU-only emulation snapshot. It builds the
smallest useful "incident scene": four workers communicate through an emulated
switch, one worker access link remains operational but is rate-limited from
100 to 20 Mbit/s, and the collective-like workload slows down. The prototype
then exercises a switch-counter-first detection proxy, an end-host confirmation
gate, and a coordinated whole-ring move to a healthy second fabric.

> **Current verdict: NO-GO (16/18 predeclared run gates pass).** The minimum
> two-week demonstration and closed-loop scaffold are working, but the full
> LIMER system is not complete and C3 recovery passes its 0.9 performance gate
> in only one of three repeats.

## What the demo actually does

```text
                         switch-facing counter
                                  │
                                  ▼
 w0 ─┐                        ┌────────┐
 w1 ─┼── 100 Mbit/s links ───│  sA    │       Layer 1 proxy:
 w2 ─┼── 100 → 20 Mbit/s ────│        │───── persistent low RX rate
 w3 ─┘     link stays UP      └────────┘
                                  │
                      end-host round slowdown         Layer 2 gate
                                  │
                                  ▼
                  all ranks prepare / READY / commit  Layer 3 scaffold
                                  │
                                  ▼
                     healthy fabric B, route version 1
```

The fault is applied with Linux `tc/netem` to rank 2's worker-side interface
`w2-eth0`. The detector reads RX counters from the distinct switch-facing peer
`sA-eth3`; it cannot inspect the injector qdisc. Both interfaces remain `UP`.
The formal matrix configures **0% random loss**: the demonstrated gray failure
is persistent partial bandwidth degradation, not packet loss disguised as an
up link.

The traffic generator is a Python TCP ring with four namespace-isolated
workers. Each worker sends six framed 2 MiB chunks per round, mirroring the
volume and synchronization pressure of a four-rank ring collective. It does
not sum tensors, so it is described throughout as **AllReduce-like**, not as
NCCL or numerical AllReduce.

## Measured results

The denominator is 18 clean topology lifecycles: C0-C5, each repeated three
times. No failed repeat is discarded. All runs completed with zero checksum
and route-version errors, both access-link endpoints stayed up, and all 18
record the injector and detector as distinct observation points.

| Condition | What changes | Median selected retention | Gate result |
|---|---|---:|---:|
| C0 | Fault-free control | 1.001 | 3/3 |
| C1 | Rank 2 access link limited to 20 Mbit/s; no detector | 0.213 | 3/3 |
| C2 | Same fault; counter-proxy detection only | 0.212 | 3/3 |
| C3 | Counter trigger + host gate + versioned move to B | 0.865 post-recovery | 1/3 |
| C4 | Oracle-triggered move to B | 0.980 post-recovery | 3/3 |
| C5 | 100 ms transient degradation | 0.988 | 3/3 |

In C3, the single degraded round on fabric A retained a median `0.215` of the
matched pre-fault throughput. After all ranks committed to fabric B, median
retention rose to `0.865`; the three values were `0.971`, `0.853`, and `0.865`.
The fixed acceptance threshold is `0.9`, so repeats 02 and 03 remain failures.
The oracle recovery result (`0.980`) shows the current emulation's upper bound,
not a result achieved by the LIMER detector.

Median switch-counter detection latency was 46.30 ms in C2 and 51.94 ms in C3.
The C3 end-host gate then waited for the degraded collective round to complete,
giving a 5.27 s median host-confirmation delay; coordination after confirmation
took 0.63 ms median. This is not an end-to-end millisecond recovery result.

The authoritative aggregate is
[`results/aggregate_summary.json`](results/aggregate_summary.json). The raw
run-level table is [`results/summary.csv`](results/summary.csv); plots are
[`results/throughput.svg`](results/throughput.svg) and
[`results/timeline.svg`](results/timeline.svg). See
[`docs/experiment_design.md`](docs/experiment_design.md) for metric and gate
definitions, including an important `fault_period_retention` field-name caveat.

## Architecture status

| LIMER layer | Implemented here | Still required for the research system |
|---|---|---|
| Switch-side first signal | 20 ms target polling of a switch-facing Linux RX counter; three-sample high-recall rule | Switch-resident or production telemetry path, resource budget, broader symptoms |
| End-host refinement | Deterministic impact and standby-health gate | Neuro-fuzzy classification, calibrated GP uncertainty, NIC/NCCL signals |
| Recovery | Four-rank prepare/READY/commit at a completed-round boundary; A-to-B route version change | PyTorch/NCCL integration, real communicator rebuild, failure-safe production protocol |

The module-level design and control sequence are documented in
[`docs/architecture.md`](docs/architecture.md). Unsupported interpretations and
the next experiments are listed in
[`docs/current_limitations.md`](docs/current_limitations.md).

## Repository map

```text
limer_v0/       Python topology, traffic, detector, gate, coordinator and report code
configs/        Predeclared C0-C5 experiment configurations
tests/          51 unit and integration tests
results/        Valid 18-run raw evidence and generated summaries/plots
docs/           Architecture, experiment semantics, limitations and execution plan
environment_probe.txt
                Emulation-host software and capability snapshot
```

The superseded pre-audit result tree is deliberately absent because its first
detector version observed the same qdisc used by the injector. Proposal files,
sponsor documents, literature-review attachments, credentials, and temporary
archives are also outside this code artifact.

## Requirements

Run topology and experiments on Linux with:

- Python 3;
- Mininet 2.3 or compatible;
- Open vSwitch;
- `iproute2` with `tc/netem`;
- privileges to create network namespaces, links, qdiscs, and OVS bridges.

The archived run host used Debian 13, Python 3, Mininet 2.3.0, and Open vSwitch
3.5.0. Exact probe output is in
[`environment_probe.txt`](environment_probe.txt). A GPU is not required for
this version.

## Verify the code

From the repository root:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile limer_v0/*.py tests/*.py
```

The test suite contains 51 tests. On a restricted macOS sandbox, the loopback
socket integration test can be skipped because local bind is denied; the full
suite passed on the Debian emulation host.

On a prepared Linux host, verify both topologies:

```bash
sudo python3 -m limer_v0.topology --kind single
sudo python3 -m limer_v0.topology --kind dual
```

The expected ping counts are 4/4 for the single fabric and 8/8 for the dual
fabric.

## Run one closed-loop experiment

Use a separate output directory so the archived evidence remains immutable:

```bash
mkdir -p scratch_results
sudo python3 -m limer_v0.orchestrator \
  --config configs/c3_full.json \
  --results-dir scratch_results \
  --workdir "$PWD" \
  --run-id c3_rep01
python3 -m json.tool scratch_results/c3_rep01/summary.json
```

Each run emits a manifest, immutable JSONL events, switch and worker CSVs,
correctness evidence, a summary, and worker stderr logs.

`limer_v0.report` is an aggregate formal-matrix reporter rather than a
single-run viewer. Run it only after the output directory contains all 18
predeclared C0-C5 repeats; it returns a non-zero status when overall acceptance
is false.

## Immediate next experiment

The first follow-up should keep the C3 `>= 0.9` gate fixed and compare three
standby-B treatments: idle, low-rate keepalive, and a matched pre-fault B
baseline. That isolates whether the two failed C3 repeats came from a cold TCP
path. In parallel, step-level host evidence should replace whole-round waiting
to reduce the current 5.27 s confirmation bottleneck. Numerical reduction and
GPU `nccl-tests` should follow only after those CPU controls are understood.
