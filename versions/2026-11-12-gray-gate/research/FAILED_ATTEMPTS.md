# Retained failed native validations

Two distinct failures are retained. The first was an audit-model error; the
later confirmation failure was a real terminal resource-cleanup defect. They
must not be combined or both described as false positives.

## Initial v1 failure

The first native smoke selection used the frozen `project-v1` and the registered
`pilot-v1` blackhole pair. The direct arm passed. The candidate completed the
simulated business workload, but its execution audit returned two errors:
`lease release erased live relay ownership`. The runner therefore marked that
attempt invalid and did not produce an accepted performance result. Its original
audit remains failed; no file was overwritten to turn that attempt into a pass.

| Original campaign | Registered | Attempted | Valid | Invalid | Not run |
| --- | ---: | ---: | ---: | ---: | ---: |
| pilot-v1 | 20 | 2 | 1 | 1 | 18 |
| confirmation-v1 | 30 | 0 | 0 | 0 | 30 |

Execution stopped before further cases. All unrun registrations are retained.
Compact files and hashes of the retained remote raw failure are in
[`evidence-v1`](../evidence-v1/COMPACT_MANIFEST.json).

## Root cause

Two phase-2 health probes had finished their data legs but were waiting for the
already charged health report to arrive. The next scheduler phase started first.
The auditor treated that admission reset as if it were a physical resource release.

| Event, in ns | Source 0 | Source 15 |
| --- | ---: | ---: |
| Lease identity | 50981 | 50982 |
| Probe route | 76618 | 76623 |
| Physical reservation | 63,100,000 | 63,200,000 |
| Third data leg completed | 63,160,070 | 63,262,114 |
| Next phase began | 63,637,881 | 63,637,881 |
| Paid health report arrived | 64,167,750 | 64,269,794 |
| Actual physical RELEASE | 64,167,750 | 64,269,794 |

Neither lease had an explicit `LEND_RELEASED` event. The original physical
reservations remained counted across the phase boundary and were released at
the actual report arrivals. The physical credit and helper-buffer maximums were
both four. The failure is an audit model error, not evidence that the physical
resources were prematurely cleared.

## Corrected revision

The current `project` differs from `project-v1` in exactly three files:

- `python/limerlab/audit.py`: require drained reservations at actual explicit
  `LEND_RELEASED` events; continue replaying physical resources across phases.
- `tests/test_helper_phase_drain_audit.py`: five regressions, including the
  observed timeline and adversarial early release of live probe/business work.
- `tests/test_helper_selection.py`: identify the original throughput-v1 negative
  control explicitly, rather than mistaking this new sibling `project-v1` for it.

All 209 tests pass. The native simulator and policy files are byte-identical;
both revisions use native binary SHA-256
`289d08e36084cff75d5a931a18aee8a6203609458ccddbaa36525235ddeacef4`.
The conditions and seeds were not tuned. Separate `pilot-v2` and
`confirmation-v2` registrations freeze the corrected audit before new attempts.
Read-only diagnostic replays of the old raw files are explanatory and do not
replace the original invalid attempt or supply an accepted performance result.

## Confirmation v2: real final-phase lease leak

The complete v2 campaign has 50 attempts: 49 valid (47 completed and two
unfinished no-helper cases), and one invalid candidate at sustained 50%
capacity. That attempt fails with `rejected helper lease leaked after delivered
release`. Its business completion does not make it a valid performance result.

The last business ACK advances to the terminal phase before the paid release
arrives. The old callback rejects the original phase, and no next-phase reset
or periodic work loop remains to clean up that lease. All physical probes had
already drained in this trace, so the auditor correctly identifies the leak.

See the [exact timeline and source diagnosis](../diagnostics/confirmation-final-lease-failure.md).
Original compact records and the remote raw-file hashes remain in
[`evidence`](../evidence/COMPACT_MANIFEST.json); the failed attempt stays invalid.

The separate `project-terminal-fix` snapshot repairs terminal paid cleanup while
retaining the policy and auditor. Its [targeted regression protocol](TERMINAL_REPAIR_PROTOCOL.md)
does not replace the original campaign or qualify the repaired version across
all gray-fault conditions.
