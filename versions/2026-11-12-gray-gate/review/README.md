# Review scope

Start with [current-implementation.diff](current-implementation.diff): the full
28-file source/test diff for `project-terminal-fix` against the prior throughput
release. It combines the gate revision and terminal cleanup repair.

The implementation diff is [implementation.diff](implementation.diff), relative
to the frozen `2026-11-12-throughput/project` at commit `191f4349`. It covers 25
changed or added source/test files, excluding unchanged vendored dependencies
and generated Python caches. The new version is an isolated complete snapshot.

The separate [terminal-fix.diff](terminal-fix.diff) adds the final cleanup repair
on top of that frozen candidate: two native files and three test files. It does
not change detection, gate estimates or audit rules. Its complete source is
`project-terminal-fix`; the original `project` continues to identify the main
50-attempt evidence. Tests increased from 209 to 216. The source/conditions and
the retained failed run are never silently replaced.

Root review scope also includes the repository README pointer, implementation
plan, research protocols, diagnostics, report/export/verification programs and
compact evidence. Raw large archives remain on otakotak, with paths and hashes.

## Changes to examine

| Area | Change | Reason |
| --- | --- | --- |
| Estimator | Explicit `benefit_v2`; stalled-tail persistence, distinct physical/confirmation windows, paid helper-work forecasts | The old heuristic could predict near-zero completion for a tail that was no longer progressing |
| Observations | Two charged queries and replies with phase/version/lease identity | Helper workload must be observed causally, not read as free simulator state |
| Lifecycle | Paid release for rejected/failed temporary loans and completed sources; 20-ms probe-only timeout | Prevent stranded helper reservations without deleting business transfers |
| Correctness | Independent report, lease, cancellation and policy replay; exact aborted-probe tombstones | Reproduce decisions and preserve late packet accounting |
| Configuration | Separate zero-loss `slowdown` family and guarded v2 mode | Keep historical `quarter` semantics and unsupported mode combinations explicit |
| Evaluation | Four paired LIMER arms; all invalid, unfinished and pending cases retained | Test actual whole-job benefit instead of trusting predicted gains |

## Verification before native experiments

- Initial candidate: 204 tests passed in 10.085 seconds.
- Audit-only correction: `python3 limer.py check`, 209 tests passed in 9.376 seconds.
- Native build on otakotak passed in 99.522 seconds. Binary SHA-256:
  `289d08e36084cff75d5a931a18aee8a6203609458ccddbaa36525235ddeacef4`.
- Pilot and confirmation conditions and seeds were fixed before execution.
- The prior throughput release and its evidence remain separate and unchanged.

These checks establish implementation/test consistency, not a performance gain.
Native observations must still pass independent execution and policy replay.
The [retained first native failure](../research/FAILED_ATTEMPTS.md) led to an
audit-only correction, without changing the native binary or the policy.

## Completed native verification

The main 50 attempts include 49 valid records (47 completed and two unfinished)
and one retained invalid terminal release. The isolated repair then passed all
ten selected native execution/observation audits. Its 326 compact files, ten
archives and exact source identities were verified; 20 intentionally unrun
repair registrations remain visible. See [repair results](../TERMINAL_REPAIR_RESULTS.md).

All ten repaired traces preserve original completion timestamps, policy/alarm
streams and precompletion control records. The original invalid run is still
invalid in its own campaign. The repair's binary SHA-256 is
`8fa663d4182044696b2bc1facc908a0ce4afc9de4bfca5d8aa4b70ce231e1741`.

The 50%-capacity condition still misses affected path 721 in every arm. Passing
execution audits does not make these detection trials successful. The gate's
sustained-slowdown regressions and this detector limitation remain unresolved.

## Boundaries for claims

The gate controls initial activation in each phase, not continuous rerouting.
Its forecast covers the affected source and two helpers' outgoing work, not all
ranks or tensor computation. Tail persistence and equal-byte helper opportunity
cost are modeling assumptions. A short paired campaign does not establish a
population-level 95%-within-100-ms detection guarantee. The four policies are
LIMER ablations, not a reproduced R2CC implementation.

The registered workload is four phases / 2 GiB. It is a short-workload gate
diagnostic, not reacceptance of the previous 30-phase / 15-GiB throughput release
or its 70%–80% target. Do not compare or pool their normalized ratios without
matching phase count, payload and fault onset.

The full diff was supplied for review. Sophie explicitly authorized committing
and publishing this revision on 2026-11-12, on branch
`codex/gray-fault-benefit-gate-2026-11-12`. Further changes require fresh review
and explicit push approval.
