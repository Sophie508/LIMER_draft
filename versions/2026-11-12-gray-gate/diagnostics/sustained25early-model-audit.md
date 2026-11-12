# Sustained 25% early slowdown: accepted pilot-v2 model audit

This is a read-only diagnosis of four registered development runs, not a new
policy or a confirmatory result. No frozen project source, condition, or run
record was modified. The observation timestamps below are simulation timestamps;
future completion events are used only for this offline audit, never as policy
inputs.

## Evidence and acceptance

Remote campaign: `otakotak:/home/suliu/data/LIMER_GRAY_GATE_2026-11-12/results/pilot-v2`.
Run names: `sustained_25_early-{adaptive,direct,legacy_gate,candidate_gate}-s111213001`.
All four `attempts/<run>.json` records were present with `valid=true`,
`status=completed`, `exit_code=0` before the accepted comparisons below were
written. Each record also reports valid, timely detection of both affected paths.

The matched condition is a sustained rate reduction to 25%, no configured loss,
fault at simulation timestamp 24 ms, four phases, 512 chunks/rank/phase,
64 KiB/chunk, 16 logical ranks, service detector, phase-scoped replacement,
pipelined completion and shared helpers. This is a CPU network simulation,
not numerical AllReduce or GPU hardware evidence.

**Whole-job communication duration is `performance.communication_ms`.** The first
phase begins at timestamp 1 ms, so `job_done_ns / 1e6` is an absolute completion
timestamp and is 1 ms larger than the communication duration. Initial provisional
messages quoted the latter; the table here uses the correct duration.

| Accepted arm | Communication duration (ms) | New B-prime chunks | Full-route health probes | Control wire bytes |
|---|---:|---:|---:|---:|
| Adaptive allocation, no replacement (G10) | 95.443573 | 0 | 0 | 192 |
| Direct recovery (G11 / always) | 82.403551 | 724 | 6 | 80,640 |
| Legacy gate (G11 / benefit) | 95.443573 | 0 | 24 | 3,648 |
| Candidate gate (G11 / benefit_v2) | 95.443573 | 0 | 14 | 12,480 |

The candidate has **no communication-time gain** over adaptive or legacy gate,
and is **15.8246% slower** than direct recovery. Direct recovery saves 13.040022 ms
relative to candidate/adaptive. Candidate uses fewer route probes than legacy,
but more control bytes because its helper requests/reports and releases are
charged; this is not an unqualified overhead improvement.

All arms alarm at timestamps 31.065907 and 31.073587 ms on paths 13 and 721:
7.065907 and 7.073587 ms after the fault. Candidate logs 12 `stay_no_slower`
and 2 `benefit_below_margin` decisions, with no activation. All four run statuses
report zero retransmission wire bytes. The zero-loss configuration plus ongoing
positive B ACK service distinguishes this case from blackhole recovery.

Important source files in each run: `performance.json`, `run_status.json`,
`policy_decisions.jsonl`, `helper_reports.jsonl`, `phase_events.csv`, and
`control_events.csv`. Raw logical ACK/DONE events were streamed read-only from
the candidate archive after normal runner archival. Its SHA-256 was independently
recomputed and matches the accepted attempt:
`941bb4bcb7fc86ce18c017ec9d5c1d754929d655af27a0c7064bdd5c47d0cad2`.
Candidate policy-evidence SHA-256 from the accepted attempt:
`aa214804dbfef24317476214dd2b9f95a24f40baea3fb798a1560d715064df15`.

## Actual phase chronology

These are absolute simulation timestamps. Phase 0 is common to all arms.
Adaptive, legacy gate and candidate have identical phase boundaries in this run.

| Event | Candidate / adaptive / legacy (ms) | Direct recovery (ms) |
|---|---:|---:|
| Phase 0 starts | 1.000000 | 1.000000 |
| Phase 1 starts | 16.847750 | 16.847750 |
| Phase 2 starts | 40.066695 | 40.121307 |
| Phase 3 starts | 67.942089 | 61.639989 |
| Job completes | 96.443573 | 83.403551 |

Direct recovery does not improve the first fault-affected phase: phase 2 starts
54.612 microseconds later. Its advantage appears in the later long-work phases:
phase 2 is approximately 6.356712 ms shorter and phase 3 6.737922 ms shorter.
Because direct recovery changes earlier traffic and subsequent phase start times,
its whole-job result is not an exact counterfactual for a candidate decision made
at a different timestamp.

## First fault-affected phase: source stay forecast is optimistic

The candidate reaches its first decision only after a physical three-leg probe,
a paid health report, and paid helper request/reply exchanges. For source 0:

- Fault: 24.000000 ms; alarm: 31.065907 ms.
- Probe/health-report stage corresponding to the legacy decision: 33.407533 ms.
- Helper 1 sampled at 34.415213 ms, report delivered at 35.422893 ms.
- Helper 5 sampled at 34.422893 ms, report delivered at 35.430573 ms.
- Candidate decision: 35.430573 ms. Both helpers report zero own remaining work.
- Source 0 actually completes its own phase at 40.066694 ms while staying on AB.

| Candidate decision | B ACK service (bytes/ns) | Oldest unfinished B chunk without progress (ms) | Predicted source stay (ms) | Observed remaining own-phase duration (ms) | Underprediction (ms) | Predicted switch (ms) |
|---|---:|---:|---:|---:|---:|---:|
| Source 0, phase 1, timestamp 35.430573 ms | 0.1481664 | 0.291260 | 4.135556 | 4.636121 | 0.500565 | 5.410792 |
| Source 15, phase 1, timestamp 35.522026 ms | 0.2466256 | 0.631715 | 2.937192 | 3.636817 | 0.699625 | 5.923433 |

These are genuine moving gray paths: source 0 acknowledged 1,481,664 B bytes in
its preceding 10 ms; source 15 acknowledged 2,466,256 B bytes. Their last B ACKs
in those windows occurred at 35.421800 and 35.519386 ms respectively. Neither
invokes the 2 ms stalled-tail forecast.

**Supported:** the fluid source model underestimates remaining AB duration on
these two decisions. **Not established:** correcting those errors alone would
make switching beneficial. Even the observed stay duration is shorter than the
candidate's predicted switch duration here. Direct recovery's first affected
phase is also slightly slower than staying, so these early rejections cannot be
called experimentally wrong simply because direct wins the whole job.

The candidate's source-0 rate window starts at 25.430573 ms, after the 24 ms fault.
Thus pre-fault healthy samples do **not** explain its first-decision error.
The legacy source-0 decision at 33.407533 ms uses a window beginning at
23.407533 ms, which does include 0.592467 ms before the fault; do not conflate
these two policies' evidence windows. Finite chunk scheduling, evolving A/B
allocation and service-rate variation are competing explanations for the
candidate's residual fluid-model error; this trace does not isolate them.

## Next phase: helper forecast is dominated by a barrier-idle window

The first phase-2 source-0 decision is at **44.606556 ms**. The relevant helper-1
snapshot is report **54566**, binding version **52762**, lease **50881**.
All values were sent before the decision through the registered paid transport.

| Helper 1 event / observation | Absolute timestamp or value |
|---|---:|
| Finishes its own phase 1 work | 32.826724 ms |
| Start of the snapshot's fixed 10 ms ACK window | 33.591196 ms |
| Global phase 2 starts; helper allocates new work | 40.066695 ms |
| First helper-1 ACK in phase 2 | 40.071308 ms |
| Last ACK included in this snapshot | 43.590889 ms |
| Snapshot sampled | 43.591196 ms |
| Snapshot delivered | 44.598876 ms |
| Source makes the decision after both replies | 44.606556 ms |
| Helper 1 actually finishes its own phase 2 work | 55.950276 ms |
| Source 0 actually finishes its phase 2 work | 67.942088 ms |

The ACK numerator is exactly **7,346,576 bytes**. The fixed denominator is 10 ms,
so reported own service is **0.7346576 bytes/ns**. However, **6.475499 ms** of that
window precedes the new phase; helper 1 had already finished its previous own
work and was waiting at the collective phase boundary. Only **3.524501 ms** lies
between current-phase allocation and snapshot sampling. The snapshot contains
**26,207,856 bytes** of current-phase own remaining work.

The implementation divides that current-phase remaining work by the idle-diluted
rate, predicting **35.673565 ms** of helper stay time at the decision. Actual own
completion is **11.343720 ms** after the decision. The helper prediction is about
**3.145 times** the observed remaining own duration. Helper 5 shows the same
pattern: report 54567 sampled at 43.598876 ms; 7,413,232 acknowledged bytes,
0.7413232 bytes/ns; actual own completion at 55.984790 ms.

This dilution is directly visible in the event chronology, not inferred from
an unsuccessful performance result. The report also describes work as of its
sampling time, 1.015360 ms before the source's decision; the policy conservatively
does not deduct progress during delivery. That staleness is a separate source
of overprediction.

For illustration **only**, using the same observed numerator over the elapsed
current-phase interval gives 2.0844301 bytes/ns and a 12.573152 ms residual estimate
from the snapshot. Deducting its elapsed delivery age under a persistence
assumption gives 11.557792 ms at decision time. These are offline arithmetic
comparisons, not a deployed policy, a newly measured outcome, or proof that
this normalization is safe for every startup/idle/weak-loss condition.

The source and helper contributions at this decision must remain separate:

| Forecast component at 44.606556 ms | Stay (ms) | Switch (ms) |
|---|---:|---:|
| Affected source only | 24.014795 | 23.301908 |
| Maximum of the reported helpers | 35.673565 | 42.882692 |
| Local source/helper maximum used by the gate | 35.673565 | 42.882692 |

Actual source-0 remaining phase duration is 23.335532 ms, close to the source
stay forecast. The helper model reverses the sign of the small source-only gain,
but that **0.712887 ms** gain is already below the source-only 10% margin of
2.401479 ms. Therefore, repairing only the helper denominator is **not enough**
to explain or guarantee a switch at this decision.

Later in phase 2, at 53.960343 ms, source 0 predicts stay 13.813323 ms and switch
12.975914 ms. Helpers are no longer the predicted critical component. The
0.837409 ms gain is below both the 1 ms absolute and 10% relative requirements,
so the reason is `benefit_below_margin`. A helper-only fix cannot remove this
second rejection mechanism.

## Other supported observations and unresolved causes

1. **Probe duration depends strongly on concurrent load.** The first phase-2
   source-0 probe has network-leg duration 225,226 ns, giving the model a relay
   rate of 0.2909788 bytes/ns. At the later 63.140790 ms decision, the sampled
   network leg is 59,460 ns and the relay estimate is 1.1021863 bytes/ns. It is a
   fact that the observations differ; whether a single contended chunk's elapsed
   time systematically underestimates the future four-credit relay pipeline is
   still a hypothesis. The physical bottleneck and source-window corrections do
   not by themselves remove changing queueing or shared-service effects.
2. **Observation acquisition has a real opportunity cost.** Candidate's first
   decision is 2.023040 ms after the corresponding legacy probe-complete decision,
   due to paid helper exchanges. It sees less remaining work and different rates.
   The runtime charges this delay. This is not a free same-timestamp comparator,
   and removing the reports' cost to obtain a favorable result would be invalid.
3. **A report of own outgoing work is not a full helper cost model.** RX-helper
   incoming contention, A/B headroom, all other ranks and compute remain outside
   the local estimator, while actual simulator resource limits still enforce
   physical interference. The additive equal-byte helper penalty is a hypothesis.
4. **The phase boundary matters to opportunity.** Phase-1 helpers are already
   idle by the first candidate decision, leaving short source work; later phases
   offer much more work but start with a diluted helper-rate window. Neither
   issue alone explains all 14 rejected decisions.

## Falsifiable next-round tests, not changes to this accepted pilot

Freeze new source and register a separate diagnostic matrix before execution.
Keep the four accepted runs above and the earlier failed attempt unchanged.

| Question | Isolated change / comparison | Observation that would reject the explanation |
|---|---|---|
| Does barrier-idle dilution materially cause rejection? | Helper-only current-phase/backlogged observation interval; keep source model, probe, paid report delay, margin and resource handling fixed. Check prediction error first, then matched completion. | Helper prediction remains badly biased, or prediction improves but decisions/whole-job duration do not. The latter means this is a calibration issue, not sufficient performance cause. |
| Is the source fluid forecast too optimistic? | Evaluate source prediction error at matched decision prefixes while keeping helper model fixed; then a separately versioned source-only causal estimator. Use continued-progress short and long conditions. | Source prediction improves but the same no-benefit decisions remain; or changes harm negative/transient cases. |
| Is a contended single-chunk probe a poor pipeline-capacity estimator? | Compare its forecast with realized service in timestamp-matched forced-switch diagnostic branches, keeping the same paid setup. Any richer probe needs explicitly charged bytes/time. | Realized relay service agrees with the old prediction, or apparent gains vanish after including added probe cost/helper burden. |
| Is the helper penalty rather than its rate estimate too pessimistic? | Preserve the paid snapshots and alter only the declared sharing/opportunity-cost model; measure both helpers' actual finish times and the global phase finish. | A lower penalty moves the bottleneck to helpers or fails to improve the global phase/job. |
| Does information arrive too late to exploit useful work? | Compare an equal-information-cost direct arm with candidate; or a separately declared causal earlier/pipelined collection design with its cost retained. | Equal timing still produces the same performance gap, or earlier collection's overhead cancels its benefit. |

A forced-switch branch at a candidate decision is an offline counterfactual
experiment, not an online oracle baseline or a permissible deployment input.
Do not choose a policy by reading future fault duration or future completion.
The first changed policy that looks promising on this development seed still
requires the predeclared fresh confirmation seeds and all negative controls.

The accepted conclusion is narrow: **in this sustained, still-progressing 25%
rate case, direct recovery helps later phases; the current gate fails to realize
that gain. Both source and helper forecast errors are observed, and correcting
only one component is not yet demonstrated to solve the decision problem.**
