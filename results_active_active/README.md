# LIMER active-active v1 results

These results are generated from preserved run directories; failed repeats are not discarded.
Run-level experiment matrix: **NOT ALL PREDECLARED GATES PASS**; inspect the denominator, gate column, and raw run folders.
The numeric millisecond target is not formally specified; raw latency stages are reported without an invented threshold.
The impairment is worker 2's directed Fabric A egress while operstate remains UP.

| Scenario | Runs | Median selected retention | Gate pass |
|---|---:|---:|---:|
| AA0_HEALTHY Fault-free active-active | 3 | 1.000 | 3/3 |
| AA1_FAULT Persistent fault / no detector | 3 | 0.371 | 3/3 |
| AA2_DETECT Switch detection only | 3 | 0.371 | 3/3 |
| AA3_LOCAL Closed-loop localized recovery | 3 | 0.936 | 3/3 |
| AA3_GLOBAL Closed-loop global failover baseline | 3 | 0.961 | 2/3 |
| AA4_ORACLE Oracle localized recovery | 3 | 0.947 | 3/3 |
| AA5_TRANSIENT Transient suppression | 3 | 0.993 | 3/3 |

Observed gate failures:

- `aa3_global_rep02`: AA3_GLOBAL post-recovery retention must be at least 0.9 (selected retention 0.882).

Artifacts:

- `summary.csv`: one row per discovered formal run.
- `aggregate_summary.json`: scenario denominators, raw values, and gate accounting.
- `throughput.svg`: retention by scenario.
- `timeline.svg`: AA3_LOCAL event timing when the representative run is complete.

This remains a CPU framed-transport prototype, not numerical NCCL AllReduce.
