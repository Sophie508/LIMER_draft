# Gray-fault gate campaign protocol

## What changes and what should be observed

The explicit `benefit_v2` policy revises stalled-tail, pipeline and helper-burden
estimates for initial activation in each phase. Before activation, rejection,
expired initial health evidence, or a failed probe releases the unconfigured
temporary helper lease through charged messages. V2 bounds a health probe by a
20-ms timeout: it safely cancels that probe and preserves its elapsed costs and
unsuccessful outcome. Business completion must not be erased or credited by
probe cancellation.

After activation, a configured binding retains the same helper pair while
refreshing health; an expired sample or timed-out refresh does not replace the
helpers or rerun candidate optimization. A completed source releases its lease,
and the next phase resets binding eligibility. The gate therefore controls
initial activation per phase, not continuous route optimization. Legacy/direct
policies retain their existing probe lifecycle. Detector thresholds, physical
capacities, coordination costs and final logical ACK remain unchanged. The
hypothesis is that these changes may preserve useful recovery while avoiding
unprofitable initial switches and stranded temporary reservations; adverse
results are retained.

Primary metrics are paired whole-job completion time and useful throughput
relative to policy-matched healthy work. The useful-throughput ratio is
`healthy_completion_ms / fault_completion_ms`, because useful payload is fixed.
It is not a measurement of instantaneous network bandwidth.

## Fixed pilot and confirmation

All cases use 16 logical GPUs, 512 chunks per GPU per phase, four phases,
64-KiB chunks, two 10-Gb/s access planes, shared helpers, phase-scoped bindings,
and pipelined physical completion. Observation ends at 250 ms. The original
detector calibrates from 1 to 21 ms, so primary injection begins only afterward.

| Condition | Fault time / duration | Pilot arms |
| --- | --- | --- |
| Healthy | No injected fault | All four |
| Sustained 25% capacity, early | 24 ms / through horizon | All four |
| Sustained 25% capacity, late | 40 ms / through horizon | All four |
| Transient 25% capacity | 24 ms / 20 ms | All four |
| Blackhole | 24 ms / through horizon | Direct and candidate |
| Weak loss 0.5% | 24 ms / through horizon | Direct and candidate |

The pilot has 20 registered attempts, seed `111213001`. Early and late injection
change remaining work without changing the total payload. Each four-arm group
uses identical workload, placement, timing and seed. The arms are G10/always,
G11/always, G11/benefit and G11/benefit_v2.

Confirmation uses seed `111213033` and exactly the same 20 cases, plus:

- Sustained 50% capacity (`slowdown`, explicitly zero injected loss): four arms.
- No healthy helper (all four server B links blackholed): direct and candidate.
- Local links at 1 Gb/s: healthy and sustained 25% capacity, each direct/candidate.

Thus confirmation has 30 attempts. Its definitions are fixed before observing
pilot outcomes. For slow helpers, normalization uses its own 1-Gb/s healthy
control. A source change after viewing confirmation outcomes requires a new
labelled campaign and source registration; the old results remain intact.

## Registration and execution

`tools/gray_gate_campaign.py plan --preset pilot --out pilot-plan.json` and the
corresponding `--preset confirmation` generate deterministic definitions.
The `register` action freezes source, tooling, cases, binary and build hashes.
Use separate empty output directories for the two registrations. Registration
must happen after all source changes and before any native campaign attempt.

Only the root agent launches native work on otakotak. The default is one worker;
at most two are allowed. Root can enable the second only after measuring the
first attempt's raw/archive budget and confirming quota headroom for at least
two raw working sets plus 10 GiB. The runner verifies each raw archive before pruning duplicate large
logs. A failed attempt is retained and skipped by `--resume`; it is never
overwritten with a favorable rerun. An explicit repeat needs its own campaign.

The `summarize --out <campaign>` action works with partial campaigns. Missing,
invalid and unfinished attempts stay in the registered denominator. Only valid
unfinished runs receive the capped time `(horizon - 1 ms)`, marked as a cap,
never as exact completion. Invalid and unrun records have null performance
values. A capped pair difference requires both runs to be valid; exact time
differences and throughput ratios require valid completed runs.
`gray_gate_summary.json` is authoritative for this study. The runner also writes
`research_summary.json`, whose historical arm names and detection-acceptance
logic do not constitute gray-gate acceptance.

## Cost and decision interpretation

The summary records every policy decision reason, control-event and byte count,
probe routes/wire bytes, relay wire bytes, delivered helper snapshots, helper
activation/release counts, relay leg/final-notification costs, and fresh B-prime
payload. These are observations, not an inferred per-helper counterfactual.
Execution and policy replay audits are prerequisites for performance claims.

A switch with no fresh payload may still rescue in-flight work. Call a switching
arm harmful only from a valid paired completion-time comparison with adaptive
allocation alone, and retain the fact that this contrast includes all recovery
costs. A candidate-versus-direct comparison measures the revised decision and
resource behavior together; it is not an isolated estimator ablation.

Detection retains late/missing alarms, all affected paths, pre-fault/wrong-path
alarms, and healthy false alarms. This diagnostic sample is too small for a new
population-level 95% claim. The confirmation seed separates random loss draws;
deterministic rate and blackhole runs may repeat exactly and are not independent
stochastic evidence.

## Resource estimate and stopping boundary

The pilot simulates five seconds total across 20 independent horizons;
confirmation simulates 7.5 seconds. Wall time and storage are not inferred from
simulation time. Before extending the run selection, root measures the first
archive size and elapsed time and checks available quota. A disk limit may leave
registered cases pending; that is reported rather than silently reducing the
matrix. The default raw working set is one case; conditional parallel execution
has at most two. Parallelism changes wall time, not the simulated event clock.
