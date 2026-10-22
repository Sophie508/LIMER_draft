# Baseline and novelty audit (2026-10-10)

## Verification boundary

Read versioned full-text HTML introduction, core design, evaluation and conclusion
for Chameleon v4, OptCC v1 and SprayCheck v1. Archived HTML/text, SHA256 manifest,
VCCL checkout and OptCC ZIP live in the private work directory
`/Users/sophie/Documents/LIMER_WORK_2026-10-10/`.
The paper draft does not treat externally reported numbers as our experiments.

## Chameleon: real overlap, narrower decision space

Source: [arXiv 2508.21613v4](https://arxiv.org/html/2508.21613v4),
Sections III, IV-A/C and V. v1 HTML calls the system Odyssey; use current v4.

**Fact:** Chameleon selects data rerouting versus dynamic parallelism after node
failure. The signals include execution-time profiling, memory and parallel
configuration. It uses analytical formulas, dynamic programming, heuristic search
and cached plans; describing it as ML-based would be wrong. Its real deployment
uses 32 Ascend NPUs, while comparisons use a separate event-driven simulator.

**Implication:** Remove claims that LIMER is the first real-time adaptive
fault-tolerance selector, or that avoiding ML alone distinguishes it.

**Proposed distinction:** LIMER decides whether to move affected network send
slots between already-active planes while retaining workers and their training
configuration. Switch-facing counters estimate displaced demand and spare
capacity. This is a candidate distinction against the works inspected, not
proof of worldwide priority. Include Chameleon explicitly in Related Work.

## OptCC: artifact rescued, full reproduction incomplete

Source: [arXiv 2606.01680v1](https://arxiv.org/html/2606.01680v1),
Sections 2, 4 and 5; [anonymous artifact](https://anonymous.4open.science/r/OPTCC_NeurIPS2026-1E87/README.md).

**Fact:** The public artifact contains six files: three standalone C++ DAG
generators, one header, README and gitignore. The page says available until
2026-11-03. Full ZIP archived; three generators compile and four example cases
produce valid JSON with zero process exit codes. Internal validator messages
are inspected separately; successful process exit alone is not a theorem proof.
The README references a missing parent MockNcclGroup.cc and run_all_experiments.sh.

**Implication:** Algorithm schedules are executable locally. Published SimAI
performance is not reproduced. The artifact and arXiv titles differ; establish
which algorithm/version each reconstructed figure corresponds to.

**Comparison correction:** OptCC schedules collectives after surviving-NIC
failover leaves asymmetric bandwidth. It is not simply staying on a failed
physical link. Hold the collective algorithm fixed when comparing route choices;
then add an OptCC-schedule factor once its SimAI implementation is validated.
Bandwidth loss and packet loss are different fault models.

## SprayCheck: useful measurement principle, not a drop-in detector

Source: [arXiv 2605.03702v1](https://arxiv.org/html/2605.03702v1),
Sections 3.2/3.5, 4, 5.3 and 6.

**Fact:** It counts a selected flow's packets per arriving spine, tests the
distribution against an expected packet budget, and reserves a high-priority
queue to isolate the measurement flow. Minimal application support announces
flow size; this is more than passive aggregate port-rate observation.
The 1.5%/one-iteration and 0.5%/five-iteration results require a particular
64-spine configuration and sufficient sampled traffic; they are not millisecond
latencies. The evaluation adds selective-repeat RDMA and packet spraying to NS-3.
Section 6 explicitly says its core distribution method does not apply to access
links, which all paths share. LIMER's w2-to-A injection is such an access link.

**Decision:** Do not transplant the per-spine balance test into slot-based A/B
routing. The transferable idea is measuring loss evidence against a known
communication budget. For the existing TCP prototype, first evaluate host
retransmission telemetry; routing-distribution detection requires a new model.

## VCCL and Varuna: mechanism references

[VCCL repository](https://github.com/sii-research/VCCL), archived shallow checkout
at `583e314e7888f806202a7be17dfe9402c5a9db67`.
In `src/transport/net_ib.cc`, backup QPs and receiver restart positions appear
around lines 2787-2820; `ncclIbRePostFifoInTimeout` re-posts a FIFO work request
around lines 2824-2837. Receives use the backup QP when the primary device is
flagged. Track operation identity and completion state rather than blindly
repeating writes. This RDMA work-request protocol cannot be copied into a TCP
byte stream. Hardware performance remains untested here.

[Varuna: Enabling Failure-Type Aware RDMA Failover](https://arxiv.org/html/2603.28001v1)
is distinct from the training-parallelism Varuna. Introduction, design,
evaluation and conclusion were read from the archived v1 full text. It pairs
requester logs with responder completion records, extends CAS with a UID-based
two-stage protocol, and remaps virtual QPs onto cached DCQPs while rebuilding
RCQPs in the background. Section 3.2 explicitly retains a corner case: an
operation can execute before its following completion-log write fails. Its
CAS extension has a separate, stronger recovery argument; do not generalize
that argument to all verbs or to LIMER's framed TCP transport.

Section 4 uses configured primary/backup link order; Section 6 identifies
adaptive path selection/load balancing as future work. This motivates a
bounded cost-aware route-choice comparison, not a claim that adaptive fault
tolerance itself is new. Section 5 uses four dual-25-Gb/s RDMA servers,
one-sided microbenchmarks and Motor/TPC-C. Reported 52.2%/64.5% recovery-time
reductions and transaction correctness are author measurements, not our runs
or training throughput. The text mixes microsecond-level language with
millisecond resume descriptions; do not inherit a universal latency claim.

## Correcting two inherited mechanism claims

**Cutover failure:** The preserved M4b trace supports a duplicate-reader race:
rank 3 completes step 2, rank 2 remains at step 2 and buffers step 4. Two
deterministic socketpair regressions reproduce frame loss from an abandoned
receive result. The patch keeps one receive attempt across a send-side abort.
This establishes a real bug consistent with the trace, not unique causal proof
of the historical failure. Mininet reruns remain necessary.

**Low-loss latency:** Sparse rate symptoms are an empirical explanation under
the measured observer, workload and TCP stack. They are not a proved universal
information-theoretic lower bound. Zero observed pre-fault alarms is not a
general zero-false-positive guarantee. Report sample counts and confidence.

## Jev offline arm

Official [quick start](https://docs.typesafe.ai/introduction/quickstart) and
[model reference](https://docs.typesafe.ai/models) were checked and archived.
An official key is required; no TYPESAFE_API_KEY is present in this process.
No account action or inference call was performed. Pin `jev-1.13.0`, remove
policy verdicts/outcomes from inputs, and retain service errors in the denominator.
Six existing decisions are a descriptive pilot, not evidence of general policy
accuracy. Independent episode-cost counterfactuals are needed for labels.

## Paper claim ledger

| Claim | Evidence | Status |
|---|---|---|
| Adaptive strategy selection is new | Chameleon III/IV | Reject broad claim |
| Non-ML selection is new | Chameleon analytic estimator | Reject broad claim |
| Network-slot-level telemetry decision is distinct | Code + inspected works | Candidate, scope-bounded |
| Exactly-once AllReduce is proven | CRC/version + framed ring, no tensor reduction | Reject; use protocol validation |
| Re-send was lost twice in failed run | No packet/ACK proof; reader race reproduced | Unverified inherited cause |
| All 1-5% loss detected <100 ms | Archived M4c medians 382-387 ms | False |
| Exact OptCC paper performance reproduced | Missing author integration/configuration/raw values | Not achieved; independent matched packet reconstruction completed |
| Historical M4b outcomes | 6 decisions; 5/6 complete | Supported, narrow scenes |

## Decisions ready for review

Lead with the cost of displacing traffic onto an already-used alternate plane,
the local route delta and the explicit execution contract. Include related
adaptive selectors. Keep Mininet results, SimAI results and paper-reported
competitor results in separate tables. Make no SIGCOMM readiness claim before
shared-backend comparison and stronger correctness evidence exist.
