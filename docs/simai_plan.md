# SimAI plan: realistic simulation up to 128 GPUs

## Scope amendment, 2026-10-10

Sophie confirmed that the project requires simulation implementation and
evaluation only. Real hardware access is not a prerequisite. The original
scale/calibration proposal below remains a plan, not a completion claim.

The detection loop is now explicitly in scope: correctly localized gray-fault
decisions below 100 ms are the core target, accompanied by switch/stay cost and
execution correctness. M7's CPU/TCP candidate does not yet meet that target.
An ns-3 loop must consume modeled endpoint/link observations with declared
observation delay and cost; the fault injector's time, loss configuration and
chosen path must not be passed to the detector. See
[simulation_scope.md](simulation_scope.md) for the continuation pipeline.

The existing OptCC CPU-compatible replay and static dual-plane calibration
provide separate starting artifacts. They do not constitute a completed
dynamic detection/cost/execution loop or exact published-figure reproduction.

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
   inside the simulator is a required next development phase under the scope
   amendment above. Static route changes remain a separate baseline.

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

Continue autonomously with the existing dual-plane model and small CPU runs.
Integrate and validate the detection/decision loop before expanding the scale
ladder. Larger runs require a measured runtime/memory feasibility gate; the
128-GPU endpoint is a proposed simulated scale, not a requirement for physical
GPUs. No additional hardware-platform decision is pending.
