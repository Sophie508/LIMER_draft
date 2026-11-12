# Interpreting the frozen gray-gate results

Review date: 2026-11-12. The interim snapshot below is retained as a historical
interpretation note. The complete verified outcomes are in [RESULTS.md](../RESULTS.md)
and the separately qualified [terminal repair results](../TERMINAL_REPAIR_RESULTS.md).
The 50%-capacity condition still misses one affected path in every repaired arm;
execution validity is not detection acceptance. This note does not change the
simulator, frozen harness, cases, seeds or acceptance criteria.

## Three clocks and quantities that must not be mixed

1. The simulator starts useful business work at simulated **1 ms**. Consequently,
   `communication_ms = (job_done_ns - 1,000,000) / 1e6`. The same subtraction
   applies to every policy and its matched healthy reference. For example,
   healthy `job_done_ns = 64,965,513` means **63.965513 ms** of communication,
   not 64.965513 ms.
2. Detection latency starts at the **fault onset**, currently 24 or 40 ms. The
   reported all-path delay is the maximum first-alarm delay over every affected
   path in that trial. A missing path produces no finite all-path delay; it is
   not dropped from the detection denominator.
3. The observation horizon is simulated **250 ms**, or **249 ms after business
   launch**. Monitoring continues after business completion. An unfinished run
   is right-censored at this horizon, not an observed 249-ms completion. Invalid
   and unrun attempts have no performance time, including no horizon substitute.

With identical useful payload, healthy-normalized whole-job throughput is
`T_healthy / T_fault`, using policy-, seed-, workload- and topology-matched
healthy controls. It is not `T_fault / T_healthy`, an instantaneous B-prime link
rate, or steady-state post-recovery throughput. A 1-Gb/s-helper case needs its
own 1-Gb/s healthy control. Even when healthy arms happen to tie, the registered
matching rule should not be replaced by an arbitrary fastest healthy run.

## Valid, completed and timely are separate predicates

- **Valid** means the recorded run passed the required execution/observation
  checks and completed the monitoring horizon. It does not imply good detector
  performance or completed useful work.
- **Completed** means all registered useful communication work finished, with
  valid accounting. It does not imply a useful route switch or recovery gain.
- **Timely detection** requires every affected path to alarm strictly below
  100 ms, without pre-fault or unaffected-path alarms. Misses, late alarms,
  invalid runs and unrun registrations remain visible in the denominator.
- Healthy clear/false-alarm outcomes use the full healthy observation exposure,
  even after useful work has finished. They are not fault detection trials.

The display must not convert "11 valid attempts" into "11 successful methods".
Fault-type counts may be pooled to account for registrations, but not to claim a
common detection distribution or silently hide a failing condition.

## What the cost totals cover

`control_wire_bytes`, probe bytes, helper reports, releases and activation counts
are taken from the full observation trace. Control messages are charged when
enqueued; the logged arrival can be later than job completion. A byte total is
not automatically a causal latency overhead. Continuing monitoring traffic is
also included in probe-wire totals, so dividing that full total by the shorter
business completion time would mix measurement windows.

The report now partitions control bytes by enqueue time before versus at/after
job completion, and separately shows bytes scheduled to arrive after completion.
The latter overlaps the enqueue columns and must not be added to their sum.
For a valid unfinished run only the whole-horizon total is reported. Probe-wire
traffic cannot be split into pre/post-completion bytes from the compact scalar
alone; that requires the archived wire trace.

In the inspected pilot snapshot, candidate blackhole had **81,504** total
control bytes, all enqueued before completion, but **384** bytes scheduled to
arrive afterward. Sustained early slowdown had **12,480** total control bytes,
all enqueued before completion, with **192** bytes scheduled to arrive afterward.
Healthy candidate had zero control bytes but **282,816,000** probe-wire bytes
over the monitoring horizon. Thus “zero post-completion control sends” does not
mean all measurement activity stopped at business completion.

## Initial accepted snapshot: adverse outcomes must be retained

The first read inspected 11 completed and valid pilot-v2 attempts: four healthy,
four sustained-25%-early, two blackhole, and late-slowdown adaptive-only. All
fault attempts then present were classified timely; all four healthy arms were
clear. Later runs were still pending and must not be inferred from this snapshot.

| Condition | Adaptive | Direct | Old gate | Candidate | Candidate minus direct |
| --- | ---: | ---: | ---: | ---: | ---: |
| Healthy | 63.965513 | 63.965513 | 63.965513 | 63.965513 | 0 |
| Sustained 25%, early | 95.443573 | 82.403551 | 95.443573 | 95.443573 | +13.040022 |
| Blackhole | Not registered in this pilot subset | 84.230882 | Not registered in this pilot subset | 84.300279 | +0.069397 |

Times are milliseconds after business launch. Early slowdown's candidate equals
adaptive and the old gate, and completes no fresh B-prime chunks. Direct recovery
completes 724 fresh B-prime chunks and finishes sooner. Its healthy-normalized
ratio is **77.6247%**, versus the candidate's **67.0192%**. This is a negative
case for the current candidate, even though execution and detection both pass.
The slight blackhole regression is also retained; its size alone does not
establish statistical significance. No overall candidate benefit follows from
the partial snapshot.

## Current-phase forecast versus whole-job result

The candidate decides initial activation in each phase. Once configured, it
retains the helper pair during health refresh. Its model considers the source's
remaining work and reported helper work; it does not reconstruct every rank's
critical path or continuously optimize routes.

Whole-job completion remains the primary measured outcome because source and
helper effects propagate through later phase barriers. A favorable whole-job
pair is evidence about the complete candidate package, not proof that each
phase-level prediction was calibrated. Conversely, a forecasted benefit or
successful activation cannot replace the realized job-time comparison. Different
actions create different later states, so whole-run timing differences do not
provide exact stay/switch counterfactuals at every logged decision.

## Repeated attempts and verification scope

The v1 ledger retains one valid attempt, one invalid audit attempt and all
remaining registrations. V2 changed the audit and reused the same native binary
and deterministic conditions. These repeated attempts must not be counted as
new independent evidence. Four arms within one scene share the seed and injected
fault, so four timely alarms are not four independent fault draws. The fixed
confirmation seed introduces new randomness for weak loss; deterministic healthy,
rate-degradation and blackhole repeats may be numerically identical.

The local compact verifier checks files, registered source/build/tooling hashes,
run identity, status/metrics consistency, retained archive receipts and independent
summary regeneration. Root also added cross-checks of attempt/summary validity,
monitoring completion and exact `job_done_ns - 1 ms` arithmetic following this
review. Raw archive hashes were rechecked on otakotak during export; the local
compact check is not a new native simulation or a fresh replay of every packet
log. These limits should remain visible in the final verification statement.
