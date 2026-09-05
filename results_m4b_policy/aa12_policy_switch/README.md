# LIMER active-active v1 results

These results are generated from preserved run directories; failed repeats are not discarded.
Run-level experiment matrix: **PASS**.
The numeric millisecond target is not formally specified; raw latency stages are reported without an invented threshold.
The impairment is worker 2's directed Fabric A egress while operstate remains UP.

| Scenario | Runs | Median selected retention | Gate pass |
|---|---:|---:|---:|
| AA0_HEALTHY Fault-free active-active | 0 | n/a | 0/0 |
| AA1_FAULT Persistent fault / no detector | 0 | n/a | 0/0 |
| AA2_DETECT Switch detection only | 0 | n/a | 0/0 |
| AA3_LOCAL Closed-loop localized recovery | 0 | n/a | 0/0 |
| AA3_GLOBAL Closed-loop global failover baseline | 0 | n/a | 0/0 |
| AA4_ORACLE Oracle localized recovery | 0 | n/a | 0/0 |
| AA5_TRANSIENT Transient suppression | 0 | n/a | 0/0 |
| AA6_STEPDETECT Step-level detection closed loop | 0 | n/a | 0/0 |
| AA7_HARD Hard link-down immediate failover | 0 | n/a | 0/0 |
| AA8_GRAYFAST Fast gray step-cutover recovery | 0 | n/a | 0/0 |
| AA9_STAY Loss fault, stay and retransmit (measurement arm) | 0 | n/a | 0/0 |
| AA10_SWITCH Loss fault, oracle localized switch (measurement arm) | 0 | n/a | 0/0 |
| AA11_LOSSDETECT Loss fault, detector armed (detectability measurement) | 0 | n/a | 0/0 |
| AA12_POLICY Loss fault, switch/stay policy decides (demonstration) | 3 | 0.235 | 3/3 |

Artifacts:

- `summary.csv`: one row per discovered formal run.
- `aggregate_summary.json`: scenario denominators, raw values, and gate accounting.
- `throughput.svg`: retention by scenario.
- `timeline.svg`: AA3_LOCAL event timing when the representative run is complete.

This remains a CPU framed-transport prototype, not numerical NCCL AllReduce.
