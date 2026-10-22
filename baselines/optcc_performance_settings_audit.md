# OptCC performance settings audit

Audit date: 2026-10-10. This report distinguishes verified source statements, artifact observations, and proposed reconstruction choices. No simulator experiment was run in this audit.

## Decision

**[FACT] Faithful reproduction of the published SimAI performance curves is not possible with the currently archived artifacts.** The six-file public artifact exposes schedule generators, but omits the author's SimAI integration, run script, topology files, simulator configuration, workload inputs, sweep parameters, and raw results. The arXiv TeX source contains manuscript and figure PDFs, not these missing experiment files. This is an artifact boundary, not a hardware boundary; CPU-only NS-3 experiments are still possible.

**[RECOMMENDATION] First finish the official SimAI build and healthy-ring smoke test, then independently reconstruct the simplest single-straggler setting.** Label all resulting packet-level timings “independent reconstruction using the public OptCC generator” until the original experiment configuration can be recovered. A successful reconstruction is useful baseline evidence but cannot be silently renamed paper performance reproduction.

## Sources and pinned versions

1. [OptCC arXiv v1](https://arxiv.org/html/2606.01680v1), title **Don't Let a Few Network Failures Slow the Entire AllReduce**. The arXiv record lists one version, submitted 2026-06-01 04:40:41 UTC. Local `sources/optcc.html` SHA256 `9ec168375af4c41cd44631a15772c57bde8e2561a1d8ec4f81ac7f68a5852013`.
2. [OptCC v1 TeX source](https://arxiv.org/src/2606.01680v1), downloaded during this audit to `sources/optcc_source_v1.tar`, safely extracted with Python tarfile `filter='data'` into `sources/optcc_source_v1/`. Hash and byte size are in `archive_manifest.json`; figure labels and hashes are in `figure_labels.json`.
3. [Anonymous public artifact](https://anonymous.4open.science/r/OPTCC_NeurIPS2026-1E87/), six-file ZIP already archived as `baselines/OPTCC_NeurIPS2026-1E87.zip`; source directory `baselines/optcc/`.
4. [Official SimAI](https://github.com/aliyun/SimAI), compatibility candidate checkout `baselines/SimAI-official`, HEAD `f5efb5a93ea9be7db25a8843f9f7ff54044f6062`. This checkout was read, not modified. The presence of an old `MockNcclGroup` interface is not proof it is the authors' simulator revision.
5. Paper baseline references: ICCL points to [arXiv 2510.00991](https://arxiv.org/abs/2510.00991), also represented locally by the VCCL repository; R2CCL points to [arXiv 2512.25059](https://arxiv.org/abs/2512.25059). SimAI points to the [NSDI 2025 paper](https://www.usenix.org/conference/nsdi25/presentation/wang-xizheng-simai). These citations do not supply OptCC's missing run configuration.

## What the paper fixes

**[FACT] Section 5:** A100 servers, eight GPUs and eight ConnectX-6 200 Gbps HDR InfiniBand NICs per physical server; NS-3-based SimAI; per-GPU ordering and P2P synchronization; reported completion time in milliseconds. The evaluation studies steady bandwidth asymmetry after local NIC pooling/failover, not packet-loss detection or failure-recovery downtime.

**[FACT] Mathematical notation:** `p` is total participating GPUs. With one GPU per server in the DP group, participating server count is also `p`; with `g` GPUs per participating server it is `p/g`. Physical GPUs per server are eight even where the DP subgroup has `g=1` or `g=4`. The artifact's multi-GPU driver uses `p` to mean server count, while the multi-straggler driver's `g` means healthy-server count. Do not pass paper `p/g` blindly across programs.

**[FACT] Slowdown:** `L = healthy effective bandwidth / degraded effective bandwidth`. Losing `d` out of eight pooled NICs implies `L=8/(8-d)`: one failure means `8/7≈1.142857`, two `4/3≈1.333333`, four `2`. Captions round the first two to 1.14/1.33. The unpublished run script is needed to know whether exact ratios or rounded values were used.

**[FACT] Theory:** `n` is the input vector length in elements, while experiments label `N` as bytes. Healthy NIC unit transmission time normalizes theoretical `n`; analytical makespan is not a measured wall-clock time. For multiple GPUs per server, the NVLink-rich model requires intra-server bandwidth at least `(g-1)` times NIC bandwidth; cited DGX A100 hardware has 2400 Gbps unidirectional aggregate NVLink per GPU versus 200 Gbps NIC. These hardware figures are not a disclosed simulator link topology.

## Exact panel targets recoverable from figure labels

The following facts combine Section 5 captions with the embedded PDF labels. Sweeps list fixed settings, not a verified complete input-bin list: there is no raw CSV or plotting script.

| Panel | DP layout | Swept variable | Fixed settings |
|---|---|---|---|
| 8a | one straggler, one GPU/server | `p` | `N=1 GiB`, `L=1.14` |
| 8b | same | `N` in MiB | `p=64`, `L=1.14` |
| 8c | same | `p` | `N=1 GiB`, `L=2` |
| 8d | same | `N` in MiB | `p=64`, `L=2` |
| 8e | same | `L` | `p=64`, `N=1 GiB` |
| 9a | two stragglers, one GPU/server | `p` | `N=1 GiB`, `L1=1.33`, `L2=1.14` |
| 9b | same | `N` in MiB | `p=64`, `L1=1.33`, `L2=1.14` |
| 9c | same | `p` | `N=1 GiB`, `L1=2`, `L2=1.33` |
| 9d | same | `N` in MiB | `p=64`, `L1=2`, `L2=1.33` |
| 9e | same | common `L1=L2` | `p=64`, `N=1 GiB` |
| 10a | one straggler server, four DP GPUs/server | `p` | `N=8 GiB`, `L=1.14` |
| 10b | same | `N` in GiB | `p=128`, `L=1.14` |
| 10c | same | `p` | `N=8 GiB`, `L=2` |
| 10d | same | `N` in GiB | `p=128`, `L=2` |
| 10e | same | `L` | `p=256`, `N=8 GiB` |
| 20a | one straggler, one GPU/server | `p` | `N=8 GiB`, `L=2` |
| 20b | same | message size | `p=64`, `L=2`; axis unit inconsistent, see below |
| 20c | same | `L` | `p=64`, `N=8 GiB` |
| 21a | two stragglers, one GPU/server | `p` | `N=8 GiB`, `{L1,L2}={2,1.5}` |
| 21b | same | message size | `p=64`, `{L1,L2}={2,1.5}`; axis unit inconsistent |
| 21c | same | common `L1=L2` | `p=64`, `N=8 GiB` |
| 22a | one straggler server, eight DP GPUs/server | `p` | `N=8 GiB`, `L=2` |
| 22b | same | message size | `p=128`, `L=2`; axis unit inconsistent |
| 22c | same | `L` | `p=512`, `N=8 GiB` |

**[FACT] No experiment table provides raw millisecond targets.** Tables 1–4 summarize theoretical bounds/complexity/optimality. Main-text prose reports 2–6% single-straggler overhead, 8.5% multi-straggler message-sweep gap, 4% multi-GPU gap, and stated baseline relative improvements; these are author claims, not independently recovered measurements.

**[DIGITIZATION LIMIT]** Figure 8c visually shows `p=16,32,...,256` markers. Near `p=64`, the graph is roughly 98–100 ms for healthy NCCL/OptCC, 147 ms for R2CCL and 238 ms for ICCL. These rough visual readings are for orientation only: they are neither exact numeric targets nor a pass/fail tolerance. Published vector PDFs permit a later explicit digitization file, but no digitized result should be called a raw measurement or used to reverse-engineer parameters until the comparison agrees.

## Version mismatches and mixed evidence

1. **[FACT] Artifact title mismatch:** README calls the submission “Bandwidth-Optimal AllReduce Under Network Failures”; arXiv v1 has the title above. README's Appendix sweep reference “Figs. 19–21” disagrees with v1: Figure 19 is a construction schematic, evaluation Figures are 20–22.
2. **[FACT] Main versus appendix settings differ:** Figure 10 uses `g=4`; Figure 22 uses `g=8`. Figure 10 axes have `N=8 GiB` rather than Figure 8/9's `1 GiB`. This cannot be collapsed into one common published experiment setting.
3. **[FACT] Figure 20 provenance:** its caption explicitly distinguishes filled measurements and open estimates, and says R2CCL is generated from a closed-form expression without measurements. The R2CCL line must not be described as a reproduction of that library's packet-level performance. Figures 21/22 do not clearly enumerate per-bin provenance.
4. **[FACT] Appendix units:** Figures 20b/21b/22b label the message axis GiB but show ticks 400/800/1200/1600/2000. Main message axes use MiB. The source supplies PDFs only, so whether these appendix values should be MiB or a rescaled coordinate is unresolved; do not silently fix the label and claim original settings.
5. **[FACT] Hidden source comment versus rendered prose:** `sections/experiments.tex:196-202` describes a sweep over nine `(p,N)` bins, five `L` values, seven `k` values, and a mean over `k`; it mentions one deterministic OPTCC failure at `P=64,k=56,L=1.25,N=2 GiB`, filled by interpolation, and a missing `results_summary.csv`. Rendered prose says one deterministic run per point/no error bars. **[UNCERTAINTY]** This could be a stale comment from a removed figure; there is no evidence tying it to each current panel. Either way the original `k`, failure accounting, and aggregation are not recoverable. Preserve failures in our results; never interpolate to obtain a passing point.
6. **[FACT] Multi-GPU artifact boundary:** the driver requires `L>=2` while Figure 10 includes `L=1.14` and slowdown sweeps below two. README's statement that the lower-`L` regime collapses to single-GPU bubble filling is not a released multi-GPU SimAI implementation of that regime.

## Missing parameters that block faithful timing reproduction

| Required parameter | Current evidence |
|---|---|
| Author SimAI commit/build dependencies | Unknown; citation and compatible interface do not pin them |
| `genAllReduceMyAlgoFlowModels()` integration | Referenced by README, absent from official checkout and six-file artifact |
| `run_all_experiments.sh`, raw CSV | Referenced, absent; arXiv source does not contain them |
| Network graph, switch counts, rail placement, oversubscription, link delays | Not specified in OptCC evaluation |
| NVSwitch representation, actual intra-server link rate/delay, concurrent DP groups | Not specified |
| Exact degradation implementation: pooled NIC share, reduced links, and direction | Caption describes physical NIC loss; simulator mapping not released |
| `k`, chunking, channel count, send/launch latency and cold-start model | Not specified for published curves |
| NS-3 congestion-control/PFC/ECN/QP/ACK/MTU settings | Not specified |
| Numerical mapping `n` elements to `N` bytes, rounding and payload budget | Not specified for original integration |
| ICCL/R2CCL simulator code and settings | Not released in six-file artifact; ring model and formula are not library replication |
| Exact bin list and aggregation, whether interpolated failures affect main graphs | Unresolved |

**[FACT, OFFICIAL SIMAI ONLY]** The candidate's `SimAI.conf` enables QCN/PFC, `CC_MODE=1` (DCQCN branch in `rdma-hw.cc`), payload 9000, `ERROR_RATE_PER_LINK=0`, `LINK_DOWN 0 0 0`, buffer 32, and rate-dependent ECN maps. Topology generator defaults are H100, 400 Gbps NIC, 2880 Gbps NVLink, 0.0005 ms NIC link delay and 0.000025 ms NVLink delay. None of these is confirmed as OptCC settings. In particular, running untouched defaults would contradict OptCC's A100/200 Gbps description.

## Public generator mapping and adapter risks

**[FACT]** Single: `single_straggler p k N B L`, with `p>=3`, `k>=4` divisible by four; `B` is recomputed as `N/[k(p-1)]` for `L>=2`, otherwise `N*L/[k((p-2)L+2)]`. Server `p` is degraded. Multi: `multi_straggler healthy_count k m N B L_list`; total participating `p=healthy_count+m`. Multi-GPU: `multi_gpu_per_server server_count k L ngpu ring_sz slow_sz`, not paper total GPU `p`.

**[FACT]** Single/multi JSON omit per-flow sizes and `N/B`. Single internally has canonical integer slot sizes 1000/2000, reduced-slot rounding below two, and 20-byte synchronization; its analytical `flowDuration` separately uses real-valued `B` formulas and zero sync time. Multi-GPU JSON retains `sz`. Thus the JSON alone is not sufficient to faithfully replay packet payloads; the original integration is consequential.

**[FACT]** The four existing example JSONs pass a separate Kahn topological traversal: 132/132, 157/157, 274/274, 198/198 flows reachable. This checks absence of dependency cycles in those four examples, not numerical AllReduce correctness or production-scale schedules.

**[RECOMMENDATION]** A reconstruction adapter must explicitly document rank indexing, type-to-payload mapping, rounding/residual allocation, fixed sync-byte handling, send/receive resource sharing, and endpoint completion dependencies. It must check byte budgets and reduction data provenance; successful JSON generation or schedule validation is insufficient. Use `L=2` first to avoid bubble-filling rounding ambiguities, then validate lower-`L` mapping separately.

## Actionable minimum target and gates

**[PROPOSED RECONSTRUCTION, NOT ORIGINAL SETTING]** Start from Figure 8c's simplest family: one participating GPU per server, `p=16`, `N=1 GiB`, last rank degraded to 50% (`L=2`), healthy effective NIC 200 Gbps. Freeze an explicit small topology, transport config, latencies and `k=4` for a smoke test. Then register a `k` sensitivity sweep before interpreting bandwidth efficiency; `k=4` is an executable generator example, not the paper's performance parameter. Add `p=64` only after correctness and resource checks. Compare healthy official SimAI ring, degraded official SimAI ring, and public-generator replay on the same chosen backend. Name the degraded baseline “SimAI ring under 50% bandwidth reduction”; do not call it native ICCL/VCCL. Report R2CCL theory separately if used.

Faithful-performance gate: recover author integration/config/topology/workloads/k and raw provenance, map to arXiv v1, validate byte budgets and baseline identities, then pre-register numeric comparisons and tolerance. This gate is currently closed.

Independent-reconstruction gate: pin every chosen value before running, preserve native/public sources and patch diff, validate DAG/data dependencies and payload accounting, preserve all failures, record raw FCT/event logs and compare matched configurations. This gate can be opened autonomously with the approved CPU server. A failed reconstructed timing comparison is evidence about our reconstruction until missing original settings are resolved, not evidence that the paper is wrong.
