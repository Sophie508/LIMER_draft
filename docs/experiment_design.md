# Experiment Design and Evidence Semantics

## Question addressed by v0

Can a controlled, partially degraded access link remain operational while
materially slowing a synchronized four-worker communication workload, and can
a switch-first/end-host-confirmed reroute scaffold restore most of the matched
fault-free throughput without mixed communication versions?

This is narrower than the final LIMER research question. It validates the
emulation scene and closed-loop interfaces before GPU/NCCL integration.

## Fixed setup

- Four Mininet worker namespaces.
- OVS standalone bridge per fabric.
- 100 Mbit/s and 1 ms baseline `netem` profile per switch-facing access link.
- Four-rank persistent TCP ring, six steps per round.
- 2 MiB per frame, 12 MiB sent per rank per round, and 48 MiB aggregate payload
  credited only after all four ranks complete.
- Two matched baseline rounds after one warmup round.
- Rank 2 fabric-A worker egress is the fault-injection point.
- `sA-eth3`, the opposite switch-facing endpoint, is the counter-observation
  point.
- Target counter polling interval: 20 ms.

The persistent fault uses 20 Mbit/s, 1 ms delay, and 0% configured random loss.
The transient condition applies that rate for 100 ms and restores 100 Mbit/s.
Both endpoints must remain `UP`.

## Conditions

| ID | Topology | Detector | Host gate | Recovery | Purpose |
|---|---|---|---|---|---|
| C0 | Single | Off | Off | Off | Stable fault-free control |
| C1 | Single | Off | Off | Off | Reproduce persistent gray-degradation damage |
| C2 | Single | On | Not used | Off | Show detection without recovery does not restore performance |
| C3 | Dual | On | On | Coordinated A-to-B | Exercise the full proxy closed loop |
| C4 | Dual | Oracle | B health only | Coordinated A-to-B | Estimate recovery upper bound without detection delay |
| C5 | Dual | On | On | Available but suppressed | Test false-trigger suppression for a short transient |

Each condition has three independent run directories matching
`^c([0-5])_rep([0-9]{2})$`. The formal denominator is therefore 18.

## Throughput and retention

One collective round duration is the maximum rank duration, so a slow rank
holds back the completed collective. Throughput is:

```text
sum(application payload bytes sent by all completed ranks) * 8 / round duration
```

This is a wire-volume proxy. The same logical bytes traverse multiple ring
steps, and no tensor reduction occurs, so the value must not be interpreted as
unique gradient throughput.

Every run uses its own pre-fault median as the denominator. `selected_retention`
uses:

- C0, C1, C2, C5: median post-marker/fault throughput divided by matched
  baseline;
- C3, C4: median post-recovery throughput divided by matched baseline.

## Gate definitions

`limer_v0.report.evaluate_run()` first requires every run to be complete, pass
framing correctness, keep both observed endpoints up, and prove that injector
and detector interfaces are distinct. It then applies:

- C0: selected retention in `[0.8, 1.2]`;
- C1: selected retention below `0.6`;
- C2: detector triggered and selected retention below `0.6`;
- C3: detector triggered, host action `confirm`, recovery committed, and
  post-recovery retention at least `0.9`;
- C4: oracle recovery committed and post-recovery retention at least `0.9`;
- C5: host action `suppress` and no recovery commit.

Overall acceptance additionally requires exactly three runs for each condition.
The observed outcome is 16/18 passing run gates and overall acceptance `false`.
C3 repeats 02 and 03 are retained as failures.

## C3 period semantics

Each C3 run contains one slow fabric-A round followed by three fabric-B rounds.
The raw per-run `summary.json` separates these as:

- `fault_window`: the one degraded A round;
- `post_recovery`: the three B rounds;
- `post_fault`: all four rounds after injection, including recovery.

The top-level field named `fault_period_retention` is currently copied from the
combined `post_fault` section. For C3 it therefore includes recovered B rounds
and must not be used as the pure gray-fault effect. The correct pure-fault value
is `summary.json -> fault_window -> fault_period_retention`; the three C3 values
are approximately `0.213`, `0.215`, and `0.216` (median `0.215`). The C3
acceptance gate correctly uses top-level `post_recovery_retention`, not the
ambiguous top-level fault field.

This is a reporting-name limitation, not a rewritten historical result. It is
recorded here so downstream analysis selects the intended nested field.

## Evidence hierarchy

Each run directory contains:

| Artifact | Role |
|---|---|
| `manifest.json` | Config, environment, topology, qdisc profiles, and declared expectations |
| `events.jsonl` | Ordered worker, detector, fault, host-gate, and recovery events |
| `switch_timeseries.csv` | Poll timing, qdisc state, queue fields, and interface counters |
| `worker_rounds.csv` | Rank-level routes, versions, durations, bytes, and error counts |
| `aggregate_rounds.csv` | One completed-collective row per round |
| `version_commits.csv` | Prepare/READY/commit history |
| `correctness.json` | Rank completeness, CRC, route, and version consistency checks |
| `summary.json` | Derived per-run metrics and boundary statements |
| `worker_*.stderr.log` | Process-level diagnostic output |

The repository-level hierarchy is:

1. raw per-run JSONL/CSV and manifests;
2. per-run `summary.json` values that can be traced to raw rows;
3. [`results/summary.csv`](../results/summary.csv), one formal run per row;
4. [`results/aggregate_summary.json`](../results/aggregate_summary.json), exact
   denominators, arrays, gate counts, and overall verdict;
5. plots and narrative summaries.

When a narrative and a field label appear to disagree, recompute from levels
1-2 rather than treating prose as evidence.
