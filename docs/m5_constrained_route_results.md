# Constrained-B fixed-route episode diagnostic results (2026-10-10)

Registered in constrained_b_counterfactual_prereg.md before launch. Three fresh
lifecycles per arm; detector/observer disabled; 25% A random loss, B access10Mb/s.
No failure replacement or deadline extension. Primary episode ends only after
eight post-fault rounds finish. Source and image hashes agree across all6.
Initial map, workload and fault recipe match; realized packet loss draws do not.

| Run | Status | Completed post rounds /8 | Finite episode completion s |
|---|---|---:|---:|
| m5_b10_fixed_stay_r01 | failed | 0 | not observed |
| m5_b10_fixed_stay_r02 | failed | 1 | not observed |
| m5_b10_fixed_stay_r03 | failed | 0 | not observed |
| m5_b10_fixed_switch_r01 | complete | 8 | 85.029435997 |
| m5_b10_fixed_switch_r02 | complete | 8 | 84.809261469 |
| m5_b10_fixed_switch_r03 | complete | 8 | 84.803559237 |

All switch traces have402653184post-fault bytes, zero checksum/version errors,
one agreed plan per round, and only rank2 three A send slots changed. Stay arms
exceed the120s round wait and retain failures, not fabricated finite costs.
Stay r02 completes one post round before failing; r01/r03 complete none.

This is fixed/oracle switching at a safe round boundary. Coordination is included;
detection delay and in-flight redo are excluded. It does not prove the runtime
adaptive controller selects correctly or estimate censored stay completion times.
It contradicts using the expected stay branch under low spare as an optimality
ground truth. Bandwidth-degradation static results and random-loss TCP results
are different fault models; their apparent different preferences are not inconsistent.

Bulk evidence: /home/suliu/scratch/LIMER_WORK_2026-10-10/mininet_results.
Thin verified accounting: server_summary/b10_counterfactual_analysis.json.
