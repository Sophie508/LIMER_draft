# Targeted terminal-lease cleanup regression

Status: declared before building or running the repair. This is a post-failure
correctness regression, not a new performance-policy confirmation.

## What changes

The original `confirmation-v2` sustained-50%-capacity candidate failed its
independent audit with `rejected helper lease leaked after delivered release`.
The last business ACK advanced the global phase to the terminal state before an
already paid release arrived. The callback rejected the old phase, and the
periodic scheduler no longer cleaned up completed sources.

The separate `project-terminal-fix` snapshot will:

1. Send paid releases for still-held v2 helper leases at final business
   completion, while the original phase identity is still available.
2. Allow a strictly matching last-phase lease's paid cleanup to complete after
   terminal transition, including a previously paid LEND still in flight.
3. Retain every physical reservation until its actual drain or existing bounded
   probe cancellation. Keep phase/lease ownership and stale-callback protection.

The policy formula, detector, thresholds, input observations, traffic, physical
limits and existing audits must not be relaxed. Direct and legacy behavior must
remain unchanged. Original source and failed attempts stay frozen.

## Expected observations and acceptance

- The exact sustained-50% failure has a paid release event with its original
  lease/phase identity and passes the unchanged native audit and policy replay.
- Its job completion timestamp and policy-decision stream remain identical to
  the original trace. This comparison checks repair locality; the old invalid
  attempt still has no accepted performance value.
- Healthy and blackhole controls pass. No new business traffic is admitted after
  job completion; pending physical probe work is not erased early.
- Targeted production-callback tests cover delayed release after terminal state,
  pending LEND, physical-drain waiting, last-completion release initiation, and
  stale next-phase / replacement-lease rejection.

## Frozen execution scope

Use the existing confirmation definitions and seed `111213033`, separately
registered against the new source and freshly built binary. Run exactly these
three preselected conditions: `healthy` (four arms), `sustained_50_early` (four
arms), and `blackhole` (direct and candidate), for **10 attempted cases**.

The existing registration contains all 30 confirmation definitions. The other
20 remain explicitly unrun in this targeted campaign; they are not silently
removed, and this is not full repair-version performance qualification. Do not
pool the repair's deterministic repeats with previous detection trials.

Only root launches native runs on otakotak. Recheck user quota before launch.
Use at most two workers and retain original failure files. If this regression
fails, retain its attempt rather than replacing or relabelling it as success.

The full `pilot-v2` and `confirmation-v2` tables continue to describe the original
frozen candidate. Report the terminal fix and its targeted evidence separately.
