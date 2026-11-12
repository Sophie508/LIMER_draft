# Confirmation failure: final-phase helper lease cleanup

The retained `sustained_50_early-candidate_gate-s111213033` attempt is invalid.
This is a real terminal admission-lease cleanup defect, not the earlier audit
confusion between a phase reset and physical transfer release. The business
completed, but the paid release callback never clears its still-held lease.

## Observed timeline

All times below are absolute simulator timestamps. The failed run completes
32,768 logical chunks / 2 GiB at 85.251871 ms (84.251871 ms after the fixed 1-ms
workload start). That is descriptive evidence from an invalid attempt, not an
accepted performance result.

| Time (ns) | Event | Identity / consequence |
| ---: | --- | --- |
| 81,265,360 | `LEND_ACTIVE` | Source 0, phase 3, lease 100500; helpers 1 and 5 |
| 81,300,000 | Probe reserved | Route 100713, 64 KiB, same helper pair |
| 81,360,070 | Final probe leg completes | Physical data transfer complete |
| 82,367,750 | Probe `RELEASE` | Probe reservation released after the paid health report |
| 84,390,790 | Gate rejects | `stay_no_slower`; two paid release messages are sent |
| 85,251,871 | Last business `DONE` | `FinalAck` advances `phase` from 3 to 4 and returns |
| 85,398,470 | TX release delivery due | Original phase-3 release remains charged |
| 85,406,150 | RX release delivery / callback due | `p=3 != phase=4`, so the callback returns immediately |
| 250,000,000 | Monitor ends | No `LEND_RELEASED` or terminal reset was recorded |

There is no relay business payload in this run. All seven probe reservations
have matching physical releases; the final probe was released 3.0384 ms before
the release callback was due. Therefore the missing lease closure cannot be
explained by a live relay or probe reservation. Monitoring continues to 250 ms;
service events extend beyond 249 ms, so this is not an early simulation stop.

The CSV records message arrival schedules at send time. The skipped release
callback itself is not logged. Its rejection and the remaining admission flags
are a deterministic inference from the frozen source and the recorded timeline,
not a claimed direct dump of runtime memory.

Earlier leases 49726 and 75113 cross ordinary phase boundaries. Those have actual
`RESET_TO_AB` records at 37,379,192 and 61,328,834 ns respectively, and the auditor
correctly accepts their admission closure. Lease 100500 has neither an explicit
release nor a following reset. The existing rejected-lease predicate singles it
out; no auditor relaxation is justified.

## Source path responsible

- `runtime/completion.h::FinalAck` increments the global phase before checking
  terminal completion. For the last phase it sets `jobDone` and returns without
  calling `StartPhase`.
- `recovery/proxy.h::ReleaseLendingDone` requires its saved phase to equal the
  global phase, even after terminal completion. Its callback consequently exits
  before clearing `plannedTx`, `plannedRx`, `loanTx`, `loanRx`, and binding state.
- `Tick` only inspects bindings while `phase < phases`, so it cannot repair this
  state after completion. `StartPhase` performs admission cleanup between normal
  phases, but no such call occurs at terminal completion.

The diagnostic JSON records hashes for the original failed files and verifies
the inspected native source against the build manifest. The original attempt,
audit and native logs remain unchanged.

## Isolated repair plan approved by root

Repair only the separate `project-terminal-fix` copy. Preserve `project`,
`project-v1`, the original invalid attempt, and all registered v2 evidence.

1. Before the final business completion increments the phase, call the existing
   charged release path for every still-held v2 lease. Already-releasing leases
   remain idempotent; no gate, detector, traffic rate or physical limit changes.
2. Permit the release callback to finish after that terminal phase increment
   only if `jobDone`, `phase == phases`, `saved_phase + 1 == phase`, and the
   binding phase, lease ID and releasing state all match. Retain the physical
   reservation drain check and the guards against ordinary next-phase and
   reacquired-lease callbacks.
3. If the paid lending request is still in transit at terminal completion, its
   delivery must still be recorded before the already queued paid release.
   Permit only the matching terminal-and-releasing lending callback, log its
   original phase, and never start new work or configuration from it. The FIFO
   ordering and both message costs stay intact.
4. Add production-callback C++ regressions for the exact post-job release,
   delayed physical probe ownership, a missing release scheduled by final
   completion, pending lending requests, and stale next-phase/reacquisition
   callbacks. Direct and legacy terminal behavior must remain unchanged.

The test should fail against the frozen pre-fix callback implementation and pass
against the isolated repair. Root will run the full suite, build, and separately
register the limited repair validation; these diagnostics do not turn the old
attempt into a valid result.

## Reproduce the read-only diagnosis

Run `confirmation_final_lease_extract.py` through `ssh otakotak python3 -` and
compare its JSON with `confirmation-final-lease-failure.json`. It reads only the
fixed failed run and frozen source. It does not execute native simulation or
write remote inputs/results.
