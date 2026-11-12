# Phase-aware service observations: read-only design review

Date: 2026-11-12. Status: diagnosis and proposed interfaces only. No frozen source,
registered condition, threshold, or raw result was changed; no simulation was
started for this review.

## Finding and scope

The current helper service estimate divides acknowledged bytes by a fixed 10 ms,
including time when that helper had already finished the previous phase and was
waiting at the collective barrier. It then applies that diluted rate to work in
the new phase. This mixes two different workloads. The source-side
`RecentService` has the same fixed-window convention, although the distortion is
not necessarily identical for a source that was still transmitting while the
helper waited.

A minimal causal candidate would restrict the observation interval to the
current locally known phase, while retaining every elapsed instant within that
interval. It would **not** measure only ACK-active time or begin at the first ACK.
Queueing, credit waits, startup, contention, loss-induced stalls, and processing
of already offered work must remain visible in the denominator.

This corrects an observation definition. It does not establish that the gate
will beat direct recovery: the source finish-time approximation, helper
interference model, finite credit effects, and one-time setup cost remain.

## Current executable definitions

| Quantity | Current observation | Phase behavior | Existing replay evidence |
| --- | --- | --- | --- |
| Source A/B service | Direct business `ACK_PROGRESS` increments from the last 10 ms, divided by 10 ms | ACK histories survive `StartPhase`; previous-phase samples can remain | `logical_events.csv`, direct epoch 0; `policy_replay.py` |
| Source fallback | A fresh completed canary if there are no recent business ACKs and no owned bytes on that lane | A still-fresh canary can cross a phase boundary | `service_events.csv`, charged submitted/completed canary |
| Helper own service | All own logical ACK increments, including direct and relayed business, divided by 10 ms | `helperOwnAckSamples` survives `StartPhase` | `logical_events.csv`; `audit_helper_reports` |
| Helper remaining work | Current phase unoffered bytes plus unacknowledged owned suffixes | Cohort and offered count reset at phase start | Current-phase allocations and ACK increments |
| Helper report availability | Sample after a paid helper query arrives; use only after paid reply arrives | Phase, binding version, lease ID and endpoint must match | `control_events.csv`, `helper_reports.jsonl`, decision metadata |
| Phase start | `phaseStart=PeerNow()` in `StartPhase`, before local `Pump` calls | A new phase follows completion of every previous-phase logical chunk | `phase_events.csv`, per-rank `RESET_TO_AB`, logical `DONE` |

Source locations:

- [`RecentService` and decision construction](../project/src/simulator/recovery/decision.h).
- [`SampleHelperSnapshot`](../project/src/simulator/recovery/proxy.h).
- [`Progress` ACK histories](../project/src/simulator/transport/rdma.h).
- [`StartPhase`](../project/src/simulator/scheduling/dispatcher.h) and
  [`FinalAck` phase completion](../project/src/simulator/runtime/completion.h).
- [`policy_replay.py`](../project/python/limerlab/policy_replay.py) and
  [`audit_helper_reports`](../project/python/limerlab/audit.py).

The source sample's `known` flag currently uses global simulation time
`now >= 20 ms`, not the age of the current phase. A phase-aware denominator does
not automatically provide a new statistical confidence guarantee. Introducing a
minimum new-phase observation length would be a separate, explicitly registered
policy choice, not a silent change in this repair.

## Concrete retained counterexample

Run: `pilot-v2/runs/sustained_25_early-candidate_gate-s111213001` under
`otakotak:/home/suliu/data/LIMER_GRAY_GATE_2026-11-12/results`.

The measured communication durations (`performance.communication_ms`) are
**95.443573 ms for the candidate** and **82.403551 ms for direct recovery**. Their
absolute simulator completion timestamps are respectively **96.443573 ms** and
**83.403551 ms**: workload phase 0 starts at the fixed timestamp 1 ms, which is
subtracted for the reported duration. These absolute timestamps must not be
presented as communication durations. The candidate has zero relayed business
chunks and 14 candidate probes. This review directly read both status files and
the candidate's compact phase log, paid helper report and policy decision.
The accompanying model audit provides the streamed logical-event completion
anchors; see `sustained25early-model-audit.md` when available.

At source 0's phase-2 decision at **44,606,556 ns**, helper 1's report `54566` has:

| Evidence | Value |
| --- | ---: |
| Current phase start | 40,066,695 ns |
| Snapshot sampled | 43,591,196 ns |
| Snapshot delivered | 44,598,876 ns |
| Own remaining bytes at sampling | 26,207,856 |
| Recorded own rate | 0.7346576 bytes/ns |
| Implied ACK numerator in the 10-ms window | 7,346,576 bytes |
| Current phase age at sampling | 3,524,501 ns |
| Pre-phase part of the fixed window | 6,475,499 ns |

The previous helper phase completed at 32,826,724 ns, before the fixed window
began at 33,591,196 ns. Thus the pre-phase part contributes barrier waiting and
no own ACK bytes in this example. Dividing the same numerator by the observed
current-phase interval gives **2.084430108 bytes/ns**, and remaining/rate becomes
**12.573151721 ms**, versus the recorded **35.673565481 ms**.

These are arithmetic diagnostics, not a new run or a validated counterfactual
completion. Time anchors must not be mixed: the reported actual helper phase-2
completion at 55,950,276 ns is **12.359080 ms after sampling**, **11.351400 ms after
report delivery**, and **11.343720 ms after the policy decision**. The report
still contains the sampling-time backlog after its paid transport delay; this
proposal does not silently extrapolate that backlog or erase report staleness.

## Why a phase boundary is causal here

The simulator's workload scheduler explicitly starts a phase for every rank and
records its timestamp before admitting that phase's traffic. A sender can know
its own local work-release time without consulting the fault injector or future
completion. The helper can likewise timestamp its own phase start locally.

The source must receive the helper's phase-start timestamp and window definition
inside the already paid report, or derive them from a documented locally shared
phase-start contract. The safer auditable interface is to include them in the
report: it does not give the source a new free read of remote helper state.

This statement relies on the current synchronized, scripted simulation
scheduler. It is not a claim that a deployed multi-GPU implementation has a free
perfect global clock or instantaneous barrier metadata. If ranks can begin
phases at different times in a later model, record and report each rank's own
release timestamp rather than reading one global timestamp remotely.

## Proposed interval and invariants

For a sample taken at `s`, current local phase start `p`, and the existing
`W = 10,000,000 ns` observation window:

```text
window_start = max(p, max(0, s - W))
window_ns = s - window_start
ack_bytes = observed logical ACK increments within this interval
rate = ack_bytes / window_ns, when window_ns > 0
```

Use the same documented inclusive/exclusive endpoint convention in native code
and replay. Existing replay already accepts a single causal ACK prefix when
separate files contain events with the same nanosecond timestamp. The window
numerator and remaining bytes must match the **same** prefix.

Required properties:

1. The interval starts at work release, not the first successful ACK. A queue
   stall immediately after phase start remains in elapsed time.
2. Mid-phase pauses, source-window saturation, physical credit waits, helper
   contention, and network slowdown are not subtracted.
3. If the phase is at least 10 ms old, the denominator is again 10 ms. Ordinary
   within-phase zero-progress windows retain their current meaning.
4. Previous-phase ACKs cannot increase the current-phase numerator. In the
   current barrier model all earlier business completes before new-phase work;
   timestamp clipping suffices. Phase-tagged samples would be needed if that
   invariant changes.
5. A zero-duration interval is unavailable evidence. A positive interval with
   outstanding work but no ACKs remains zero observed progress; it must not fall
   back to an assumed healthy service rate.
6. Report transit and collection are still charged. The report carries values
   frozen at sampling, not recomputed from newer helper state at delivery.
7. The denominator continues to include effects of the currently active helper
   loan. This proposal does not pretend that the helper was unencumbered or that
   a relay is a free extra physical link.

An alternative that divides by time with ACKs, or by first-ACK-to-last-ACK time,
would hide the queueing and stalled-tail costs we need to predict. It is outside
this proposal.

## Option A: helper-only observation correction

This is the smallest versioned change addressing the demonstrated mismatch.
Keep source `RecentService`, the pure benefit formula, detection thresholds,
margin, control costs, and registered scenes unchanged. Change only the helper's
local sampling interval and transport enough metadata to replay it.

Proposed helper evidence fields in addition to existing identity and timestamps:

- `service_observation_version` (or an equally explicit schema version).
- `phase_start_ns`.
- `window_start_ns` and `window_ns`.
- `ack_bytes`.
- `own_remaining_bytes` (existing).
- `own_bytes_per_ns` may be logged for convenience but must be derived from the
  transmitted integer numerator and duration.

The pure policy's `HelperSample` need not change if it still receives a validated
rate and freshness. `HelperSnapshot`, JSON report serialization, policy evidence
metadata, and independent helper replay would change. Legacy report versions
must retain their frozen fixed-10-ms semantics.

Wire-budget discipline: extra evidence must fit a declared charged layout or
increase the charged report size. One possible **model-level** 96-byte layout is
an 80-byte body plus 16-byte envelope: three 64-bit IDs; 16-bit source and helper
IDs plus 32-bit phase; and six 64-bit values for sampling time, phase start,
window start, duration, ACK bytes and remaining bytes. The source records its
receipt time locally; rate and known-state are derived, not extra serialized
fields. This is a proposed explicit budget for the simulator's abstract control
channel, not a claim about a real protocol header. Do not keep charging 96 bytes
merely because the existing helper function has that constant.

Audit additions:

- Match phase start to the recorded work-release event for the helper/phase.
- Reconstruct `max(phase_start, sampled - W)` and the integer duration.
- Reconstruct ACK increments from actual `ACK_PROGRESS`, including relay ACKs,
  using one causal prefix at same-timestamp events.
- Check numerator, rate, remaining bytes, identities, report arrival and charge
  together; retain the current stale-phase/version/lease rejection.
- Keep sampling and receipt timestamps distinct in the decision evidence.

This option does not address a contaminated source rate. It isolates the proven
helper-side cause and permits an interpretable next comparison, but it must not
be described as a complete phase-aware controller.

## Option B: source and helper observation correction

Apply Option A, and add a separately versioned source sampler for the new
candidate. Leave the existing `RecentService` implementation available to the
legacy policy. Source A/B numerators remain direct business ACK increments;
helper numerators remain all own logical ACK increments. They are intentionally
different populations and must be named explicitly in logs.

Additional local source evidence should expose, per lane:

- current local phase start, sampling time, interval start and duration;
- business ACK numerator and derived rate;
- origin (`business`, `observed_no_progress`, or `canary_fallback`);
- for canary fallback, the already charged completion identity/timing.

These are local source observations, so no extra remote message is needed.
`policy_replay.snapshot()` must use the decision's current phase rather than
indiscriminately retaining a fixed-window cross-phase rate. Existing canary
fallback eligibility and freshness must remain explicit: removing old-phase
business ACKs must not accidentally manufacture a healthy estimate for a lane
with owned unacknowledged work. A fresh canary may remain useful independent
probe evidence under its existing rules, but its provenance must be visible.

Compared with Option A, this changes both sides of the stay/switch comparison.
For a source that was still busy while the helper waited, excluding its old
phase is a different observation change, not automatically the same correction
in magnitude or direction. Evaluate and report this option separately; do not
attribute any resulting gain entirely to helper-cost accounting.

## Checks required before a future version can claim the correction

No new experiment is requested by this document. If implementation is approved,
state the exact observation change and expected trace before registering runs.
Useful correctness cases are:

- phase younger than 10 ms with the retained helper example;
- phase older than 10 ms, which should match the old within-phase estimator;
- queueing before first ACK, which must remain in the denominator;
- a mid-phase no-progress interval, which must not be clipped away;
- previous-phase ACKs close to the boundary, which must not enter new work's
  numerator;
- same-nanosecond report sampling before versus after an ACK, requiring a joint
  causal prefix rather than independently selectable remaining/rate values;
- zero-duration sampling, stale reports, wrong local phase timestamps, forged
  numerator/duration, unpaid additional fields, and canary provenance;
- unchanged legacy/direct observation and execution paths.

The expected diagnostic observation is a helper forecast no longer diluted by
known pre-phase barrier idle, while genuine within-phase contention and control
costs stay visible. Better whole-job completion is a separate empirical question.
A pure-policy recomputation on old observations is not a fresh end-to-end run:
changed decisions would alter subsequent queueing and helper behavior.

Preserve the slower sustained-25% candidate result and all earlier failures. A
new source/observation version, rather than editing the frozen candidate or
relabeling its results, is required for any implementation and validation.
