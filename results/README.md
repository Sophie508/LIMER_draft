# LIMER CPU v0 results

These results were generated from 18 immutable formal run directories (three per condition).
C0-C5 run-level acceptance: **NO-GO**; at least one predeclared run gate failed.
Gate scope: Implemented C0-C5 run-level gates only. This does not cover switch residency/resource budgets, C6/C7 ablations, numerical reduction, NCCL/RDMA semantics, or paper-level statistical sufficiency.
The workload is CPU/Mininet framed **AllReduce-like** traffic, not NCCL or RDMA.
The detector is an off-switch management-plane proxy reading switch-facing counters; it is not switch-resident logic.
The fault injector and detector are on opposite interfaces of the access link; the detector cannot read the injector qdisc.
C3 and C4 recovery results assume a healthy second fabric B.

| Condition | Runs | Median selected retention | IQR | Gate pass |
|---|---:|---:|---:|---:|
| C0 Fault-free | 3 | 1.001 | 0.019 | 3/3 |
| C1 Fault / no detector | 3 | 0.213 | 0.001 | 3/3 |
| C2 Detect only | 3 | 0.212 | 0.004 | 3/3 |
| C3 Full proxy closed loop | 3 | 0.865 | 0.059 | 1/3 |
| C4 Oracle recovery | 3 | 0.980 | 0.010 | 3/3 |
| C5 100 ms transient | 3 | 0.988 | 0.030 | 3/3 |

Failed formal gates:

- `c3_rep02`: C3 post-recovery retention must be at least 0.9 (selected retention 0.853).
- `c3_rep03`: C3 post-recovery retention must be at least 0.9 (selected retention 0.865).

Files:

- `summary.csv`: one row per formal run; no failed formal run is discarded.
- `aggregate_summary.json`: denominators, raw retention arrays, and acceptance gates.
- `throughput.svg`: median and raw selected retention by condition.
- `timeline.svg`: representative C3 event timeline.

No failed formal repeat is discarded or silently converted into a pass.
The measured C3 host-confirmation delay is dominated by waiting for a whole degraded round to finish. Streaming step-level host evidence is the next latency improvement.
