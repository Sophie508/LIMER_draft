# R2CC overlap and a falsifiable LIMER contrast

Checked on 2026-11-12. This is a source-based assessment, not a reproduction.

## What the primary sources establish

R2CC already combines live migration, bandwidth-aware traffic redistribution,
and collective schedule selection. Its topology-aware forwarding may use a proxy
GPU. Its alpha-beta model chooses communication strategies using latency,
bandwidth and message size. Therefore proxy recovery or cost prediction alone is
not a defensible LIMER novelty claim. Appendix C explicitly identifies gray
degradation masked by retransmission as a detection limitation and proposes
observed-bandwidth rebalancing as an extension.

Sources: [R2CC v2, Sections 4-5 and 7.4](https://arxiv.org/html/2512.25059v2),
[Appendix C](https://arxiv.org/html/2512.25059v2#A3).

The inspected public code is pinned to
`51fa7ff612b33b58ddbae64f386686dd38380fa6`. In `net.cc`, line 288 declares
`R2CC_FAILOVER_TIMEOUT_MS` with a 5000-ms default. Lines 2214-2238 implement a
sender no-progress timeout under additional state conditions. A configurable
timeout is not an intrinsic five-second detection lower bound. In particular,
continued delivery must be distinguished from a stalled sender.

Source: [pinned transport code](https://github.com/r2cc-project/R2CC/blob/51fa7ff612b33b58ddbae64f386686dd38380fa6/src/transport/net.cc#L2214).

## Proposed contrast, not yet an established contribution

LIMER asks whether a still-progressing but degraded path should keep receiving
its adaptively assigned work, or whether the remaining work warrants the paid
setup and shared-helper interference of a phase-scoped relay path. This is a
specific intervention and time horizon. It is not a claim that R2CC never reasons
about performance, nor a claim that all gray faults are new.

The candidate must show both useful recovery and avoided harmful switching.
Those outcomes are measured by paired whole-job completion time. A policy log
predicting a gain is not proof that the intervention delivered one. Likewise,
observing fresh relay data demonstrates execution, not positive net benefit.

## Comparisons that the present project can support

| Arm | Meaning | What a difference can establish |
| --- | --- | --- |
| G10 / always | Existing adaptive allocation, no relay replacement | Value of the full recovery option over allocation alone, including recovery overhead |
| G11 / always | Alarm, preparation and direct recovery | Value of the candidate decision policy and its additional observation/release costs |
| G11 / benefit | Preserved original gate | Whether the proposed estimator/lifecycle revision improves the old implementation |
| G11 / benefit_v2 | Candidate gate | Its behavior under identical injected conditions and workload |

These are LIMER ablations. None is a measured R2CC implementation. A future
R2CC comparison requires a runnable matched platform, exact commit/configuration,
comparable workload and fault semantics, and inclusion of its schedule optimizer.
Default-timeout-only comparisons or copying its paper's percentages into the
same performance table would not establish superiority.

## Limits that remain even if the pilot is favorable

- Four scheduler phases are a bounded diagnostic, not a training-scale result.
- Pure rate degradation does not guarantee continued observed progress; inspect
  actual service and ACK evidence before describing a run that way.
- Alarm timing relative to transient recovery is scored afterward. The online
  controller must not receive future duration or injector state.
- Paid helper reports describe observable work and recent progress; actual
  helper slowdown remains part of the measured job time.
- The small fixed matrix cannot establish a population-level 95% detection
  guarantee. It retains late, missed, invalid and false-alarm cases.
