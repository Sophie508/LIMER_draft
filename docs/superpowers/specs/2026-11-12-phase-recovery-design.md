# Phase-scoped recovery integration

The meeting asks for an executable integration repair, not an improved-looking retrospective table. Work on the supplied GitHub branch at parent 501a0f50. Preserve all historical runs and frozen snapshots. Do not commit or push before Sophie reviews the diff.

## Acceptance

1. Each scheduler phase starts with original A/B business eligibility and fresh bounded exploration. A committed helper route replaces B only within that phase. A physical fault is not healed by resetting the scheduler; detector evidence and fault injection retain their actual lifetimes.
2. Every new phase must pay full probe/report and PREPARE/READY/COMMIT costs before using new helpers. Pending callbacks are phase/version guarded. Existing phase work must finish before the barrier opens.
3. Distinguish old-chunk rescue from newly allocated B-prime chunks. Require real three-leg delivery and final source notification; count useful fresh B-prime completions across at least two phases for integration evidence. Do not hold A idle to manufacture helper traffic.
4. Detection deadline remains strictly below 100 ms from injection to controller receipt. It is independent of simulation horizon. Retain the old short workload as a negative/opportunity control and declare a longer per-phase workload prospectively.
5. Compare matched workloads: healthy G11, A-only business, G00/G10/G01/G11 and G11 benefit versus always. Keep equal observation costs. Report incomplete jobs, elapsed time, B-prime fresh/rescue bytes, phase resets and audit outcomes separately. Development runs are not a new 95% guarantee.

## Design choices

Use an explicit `replacement_lifetime` setting: `phase` for repaired integration and `persistent` for the old behavior comparison. Keep `phases_per_round=30` by default; allow smaller explicit values only for development diagnostics and label them as such. A phase is the existing global scheduler barrier, not a newly invented training iteration. Keep chunk-level adaptive allocation; ns-3 packet transport and detector observations operate below that layer.

At StartPhase, phase mode clears binding state, invalidates callback versions, resets lane launch/credit exploration state, and logs RESET_TO_AB for each source. Keep previously observed path alarms: a persistent physical fault remains known, and the helper search still requires real phase-idle workers. Every phase's first activation receives a new benefit decision and full coordination.

The short workload may legitimately finish pending work on A before a helper becomes available. Repair lifecycle first; use a larger declared cohort to test a real opportunity for new B-prime traffic. If the charged relay/ACK design remains slower than A, report that limit rather than suppressing A or fabricating restored healthy throughput.

## Risks and scope

Helpers can only forward after their own current-phase sends and receives finish. The 64 KiB chunk, four relay credits, per-chunk final notification and shared control FIFO may limit recovery throughput. No numerical AllReduce, GPU computation or universally fast gray-fault detection claim follows from these integration checks.

## Development follow-up after the pilots

Before any full-ring result is available, add one separately registered persistent-lifetime run, matched exactly to the declared full-ring blackhole G11 benefit case (including seed 111210016, 512 chunks, 30 phases and 2000 ms horizon). The short pilot shows a lifecycle cost, while the four-phase longer pilot differs little; this control isolates that cost over the default full workload. Keep its registration and denominator separate rather than silently rewriting the original 38-case registration.

The four-phase weak-loss runs then showed no fresh B-prime completions. Register two further development cases before execution: the full-ring G11 always and benefit inputs above, changing only the fault family to 0.5% weak loss. This tests whether subsequent phases supply a genuine post-diagnosis opportunity; it neither changes the detector nor replaces the short negative results. Keep the two-case registration separate.
