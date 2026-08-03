# SimAI plan: realistic simulation up to 128 GPUs

Advisor guidance: stay at a small scale (at most 128 GPUs) and use the
realistic SimAI model first; larger systems only if time remains. This plan
is drafted from first-party sources only: the official repository
(https://github.com/aliyun/SimAI, Apache-2.0) and the NSDI '25 paper
(https://www.usenix.org/conference/nsdi25/presentation/wang-xizheng-simai).

## What SimAI provides

Components: AICB (workload generation), SimCCL (collective decomposition),
astra-sim-alibabacloud (core simulator with NCCL algorithm integration), and
ns-3-alibabacloud (packet-level network backend). Two modes matter here:
SimAI-Analytical (fast, bus-bandwidth abstraction) and SimAI-Simulation
(full ns-3 stack). Topology generation and GPU count are configured via
`gen_Topo_Template.py -topo <template> -g <gpus>`.

Two constraints to state up front:

1. **The official repository ships no fault injection.** Gray-fault
   experiments require a patch at the ns-3 level (changing link DataRate,
   attaching an error model, or adjusting queues at a chosen time), which is
   a development item, not a configuration item.
2. **The simulator does not contain this project's detector or coordinator.**
   Phase one therefore answers fault impact and rerouting benefit at scale;
   it does not measure detection latency. Reproducing the detection loop
   inside the simulator is possible but roughly triples the work and needs an
   explicit decision.

## Calibration against the Mininet evidence (never mixed in one table)

Absolute times are not comparable between a CPU/TCP emulation and an
NCCL-model simulation, so calibration uses dimensionless ratios, produced
independently on each side at 4 GPUs / 4 workers:

- R0: healthy active-active round time vs. the theoretical optimum;
- R1: retention under a 20% rate cap without recovery (Mininet: 0.371);
- R2: retention after localized reroute (Mininet steady state: ~1.00).

Acceptance: SimAI-Simulation at 4 GPUs matches R1 and R2 within 15% before
any upscaling. SimAI outputs are always presented in their own section and
never merged with Mininet packet or counter evidence.

## Proposed sweep

- Scale ladder: 4 / 8 / 16 / 32 / 64 / 128 GPUs (8 GPUs per server).
- Workloads: AllReduce microbenchmarks (message sizes 2 MiB to 256 MiB),
  then one small GPT-style training workload generated with AICB.
- Fault profiles: FP-R20-equivalent (20% rate cap on one GPU-to-ToR uplink),
  FP-L1 (1% loss), FP-T100 (100 ms transient), matching the names in
  `docs/fault_profile_matrix.md`.
- Arms per point: healthy / fault-no-reroute / fault-localized-reroute /
  fault-global-reroute (reroute arms use static route changes, i.e. the
  post-recovery steady state).
- KPIs: per-iteration time series, collective completion time distribution,
  retention (same definition as the Mininet evidence), per-GPU traffic split.
- Outputs: one directory per run with `iterations.csv` and `summary.json`,
  field names aligned with the existing results schema so the same audit
  tooling can recompute everything.

## Milestones

1. S0 feasibility spike: build SimAI, run a 4-GPU AllReduce microbenchmark,
   confirm a dual-plane topology is expressible (1-2 days).
2. S1 calibration at 4 GPUs with a written pass/fail report (3-5 days).
3. S2 ns-3 fault-injection patch with unit tests (3-5 days).
4. S3 the sweep itself (machine time dominated).

Execution waits on the open decisions listed on the project site: whether the
detection loop must be simulated, the topology form (dual-ToR dual-plane vs
rail-optimized), and the compute budget for packet-level runs at 128 GPUs.
