# Bounded novelty audit: current-phase activation under gray degradation

Checked 2026-11-12 while the registered native campaign was running. This note
does not change source, conditions, seeds, registration or acceptance criteria.
No campaign outcome was used to formulate the comparison below.

## Local evidence checked first

- `docs/m5_related_work_audit.md`: the October audit already rejected broad
  first-selector and non-ML-selector claims after reading Chameleon v4.
- `handoff/PAPER_MAP.md`: Chameleon and SprayCheck are mechanism references,
  not completed full-system head-to-head reproductions.
- `docs/m13_business_detection_results.md`: same-observation shadow comparisons
  already warned that changed measurement availability can drive target passes;
  a detection target alone is not evidence of algorithmic novelty.
- `research/R2CC_SCOPE.md`: pinned R2CC code and its transport/watchdog boundary.

The earlier handoff's title-only Chameleon warning was subsequently investigated;
it must not be presented as a still-unread paper.

## Three closest inspected works

| Primary source and exact location | Already-established feature | Consequence for LIMER wording |
| --- | --- | --- |
| [R2CC v2](https://arxiv.org/html/2512.25059v2), Section 4.3, Section 5.1, Section 7.4, Appendix C | In-flight repair, proxy forwarding, bandwidth-aware redistribution and model-based strategy choice; Appendix C identifies masked gray degradation and proposes observed-bandwidth adaptation. | Neither a GPU proxy nor predicting performance before choosing a strategy is sufficient novelty. |
| [Chameleon v4](https://arxiv.org/html/2508.21613v4), Section III equations (2)-(8), Section IV-A and IV-C | Models transition cost and post-recovery throughput; chooses between data rerouting and dynamic parallelism using analytical/profiling estimates and candidate-plan search. | The general tradeoff between recovery cost and later performance is already explicit. Non-ML selection is not a distinction. |
| [SprayCheck v1](https://arxiv.org/html/2605.03702v1), Sections 3.3-3.6, Section 6 "Detection of Access Link Faults" | Detects gray loss from predicted versus observed packet-spraying distributions; sketches access-link packet/NACK accounting. | Gray-fault detection or access-link counting alone is not a new category. Its packet-spray assumptions differ from our current routing model. |

Chameleon's action space changes training parallelism or reroutes micro-batches
after node failure. LIMER currently leaves workers and training configuration
fixed and acts on an in-flight communication phase. This is a narrower contrast,
not proof of worldwide priority. Chameleon's formulas explicitly consider
transition overhead, so "we account for switching cost" would still be too broad.

SprayCheck's core test requires packet spraying and known flow information;
its Section 6 access-link discussion is a sketched extension. Neither fact
establishes a drop-in baseline for our two-plane, chunk-assignment simulator.
No external paper percentage is used as a LIMER performance measurement.

For R2CC, also retain the code-level qualification: the inspected
[net.cc commit 51fa7ff, lines 288 and 2214-2238](https://github.com/r2cc-project/R2CC/blob/51fa7ff612b33b58ddbae64f386686dd38380fa6/src/transport/net.cc#L2214)
has a configurable no-progress watchdog. Continued degraded progress differs
from a stalled sender; its default timeout is not an intrinsic lower bound.

## Remaining hypothesis requiring evidence

**Hypothesis:** When B is still delivering but is slower, the work left in the
current phase may be too small to amortize relay setup and interference with
busy helpers. A decision based on delivered ACK/probe/helper observations may
choose useful initial activation and avoid a slower intervention.

This is a current-phase, initial-activation decision. After configuration the
implementation keeps its helper pair during health refresh. It is not continuous
route optimization. The estimate covers the source and two helpers, not the
complete distributed critical path. Tail persistence, relay overlap and helper
opportunity cost remain model assumptions whose errors must be measured.

Evidence needed before stating a contribution includes: observed continuing
progress in the rate-only condition; correct causal observations and execution;
both useful-switch and harmful-switch cases; and lower realized completion time
with all measurement, cancellation, release and contention costs included.
A predicted positive gain, an activation event, or fresh B-prime traffic alone
does not establish that benefit. The present small matrix can support bounded
examples; it cannot establish optimality or general gray-fault coverage.

## What the registered four-arm matrix can and cannot attribute

| Comparison | Defensible interpretation | Attribution it cannot make |
| --- | --- | --- |
| G11/direct versus G10/adaptive | Effect of adding the implemented recovery option and its costs to existing allocation | Proxy execution alone, isolated from alarm/probe/coordination costs |
| G11/legacy gate versus G11/direct | Whole-system effect of the preserved gate's behavior | Accurate counterfactual prediction at every individual decision |
| G11/candidate versus G11/legacy or direct | Combined effect of the revised decision model, paid helper observations, temporary-lease release and v2 probe-timeout lifecycle | Benefit from tail modeling, pipeline modeling, helper cost, or timeout individually |
| All arms with the same service detector | Recovery behavior under the frozen detector and matched scene | New detection-algorithm superiority or a new population 95% guarantee |

The candidate and direct arms pay different observation/lifecycle costs by
design. Their net difference is meaningful, but calling it a pure gate-estimator
ablation would be inaccurate. Separate component ablations would be future work,
not an interpretation imposed on this registration.

Whole-run paired timings also do not reveal the true stay/switch counterfactual
at each logged decision, because actions make later states diverge. Evaluating
decision calibration would require matched state forks or an explicitly
validated counterfactual replay. An oracle supplied future fault duration would
be a separate upper-bound experiment, never an online input.

All four arms are LIMER implementations. They cannot establish superiority to
R2CC, Chameleon or SprayCheck. Deterministic healthy/rate/blackhole repeats with
a changed seed do not add independent stochastic evidence. The fixed topology,
short phase count and helper assumptions also limit generalization.

## Safe provisional claim

We investigate whether a current-phase activation decision can avoid recovery
whose setup and shared-helper cost exceed its benefit under gray degradation.
The present implementation and paired simulation test that hypothesis; they do
not establish the first adaptive recovery selector or a globally optimal policy.
