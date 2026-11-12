# Helper-window-only shadow on accepted sustained 25% early slowdown

**Result: none of the 14 decisions flips.** The original model switches zero times; the helper-window-only shadow also switches zero times. Three rejection reasons change from `stay_no_slower` to `benefit_below_margin`. This rejects the claim that this helper-window correction, by itself and with the existing thresholds, is a sufficient route-decision fix on this realized trajectory.

## Scope and evidence

This is an offline prediction shadow over the same already accepted trajectory. It is not a new native experiment, an implemented online policy, an intervention trajectory, or a measured performance improvement. No frozen source, condition, threshold, raw result, or attempt record was changed.

Run: `sustained_25_early-candidate_gate-s111213001`, accepted `attempt.valid=true`, under `otakotak:/home/suliu/data/LIMER_GRAY_GATE_2026-11-12/results/pilot-v2`. Original native/Python predictions were checked before recomputing each decision.

Raw logical ACK events were streamed from the existing archive, with archive SHA-256 independently recomputed against the accepted attempt:

`941bb4bcb7fc86ce18c017ec9d5c1d754929d655af27a0c7064bdd5c47d0cad2`

Original policy evidence SHA-256:

`aa214804dbfef24317476214dd2b9f95a24f40baea3fb798a1560d715064df15`

Frozen Python policy source SHA-256:

`44176b99aaff915230cd8252e774a30a032781a18d52b6d22c78ffcb8facec43`

[Machine-readable inputs, report windows and both prediction sets](helper-window-shadow.json) retain all 14 decisions and 28 paid helper snapshots. See [the prior model audit](sustained25early-model-audit.md) for accepted whole-job performance and actual phase completion.

## Exact isolated change

For each paid helper report, let `s` be its original sample timestamp and `p` its current phase start. The shadow computes:

```text
start = max(s - 10 ms, p)
bytes = sum of logical ACK increments from this helper and this phase
        whose timestamps are in [start, s], inclusive
window = max(1 ns, s - start)
helper own service = bytes / window
```

The numerator was reconstructed from cumulative-prefix differences in `logical_events.csv`, including the original direct/relay logical accounting. It was not assumed unchanged. Each original fixed-10-ms numerator was also reconstructed and checked against its paid report.

Only `input.helpers[i].own_bytes_per_ns` changes. The report's remaining workload, age, identity and delivery time are retained; **no report-delay progress is subtracted**. Source A/B rates and workload, source tail forecast, physical probe, setup/ACK cost, helper readiness, source window and all thresholds remain identical. A deep comparison verifies every other input is unchanged. The evaluator is imported from the frozen `pilot-v2/tooling/python` copy.

Fixed thresholds: the gain must exceed both 1 ms and 10% of predicted stay time, i.e. `gain > max(1 ms, 0.10 * predicted_stay)`; maximum evidence age 20 ms; tail debounce 2 ms.

## All 14 decisions

Event time is an **absolute simulation timestamp**, while predicted stay/switch/gain/margin columns are **remaining durations**. This table does not use `job_done_ns` as a communication duration. Every original and shadow decision is **stay**.

| Index | Time (ms) | Source | Phase | Original reason | Shadow reason | Shadow stay (ms) | Shadow switch (ms) | Shadow gain (ms) | Required margin (ms) | Flipped? |
|---:|---:|---:|---:|---|---|---:|---:|---:|---:|---|
| 0 | 35.430573 | 0 | 1 | `stay_no_slower` | `stay_no_slower` | 4.135556 | 5.410792 | -1.275237 | 1.000000 | No |
| 1 | 35.522026 | 15 | 1 | `stay_no_slower` | `stay_no_slower` | 2.937192 | 5.923433 | -2.986241 | 1.000000 | No |
| 2 | 44.606556 | 0 | 2 | `stay_no_slower` | `benefit_below_margin` | 24.014795 | 23.301908 | 0.712887 | 2.401479 | No |
| 3 | 44.630398 | 15 | 2 | `stay_no_slower` | `stay_no_slower` | 25.399886 | 25.753587 | -0.353701 | 2.539989 | No |
| 4 | 53.960343 | 0 | 2 | `benefit_below_margin` | `benefit_below_margin` | 13.813323 | 12.975914 | 0.837409 | 1.381332 | No |
| 5 | 54.030475 | 15 | 2 | `stay_no_slower` | `stay_no_slower` | 11.697837 | 12.225678 | -0.527842 | 1.169784 | No |
| 6 | 63.140790 | 0 | 2 | `stay_no_slower` | `stay_no_slower` | 4.910824 | 5.338288 | -0.427464 | 1.000000 | No |
| 7 | 63.192834 | 15 | 2 | `stay_no_slower` | `stay_no_slower` | 2.617113 | 5.308910 | -2.691797 | 1.000000 | No |
| 8 | 72.481389 | 0 | 3 | `stay_no_slower` | `benefit_below_margin` | 22.899330 | 22.439730 | 0.459600 | 2.289933 | No |
| 9 | 72.524542 | 15 | 3 | `stay_no_slower` | `benefit_below_margin` | 26.999875 | 26.878961 | 0.120914 | 2.699987 | No |
| 10 | 81.873546 | 0 | 3 | `benefit_below_margin` | `benefit_below_margin` | 14.235279 | 13.310817 | 0.924462 | 1.423528 | No |
| 11 | 81.922757 | 15 | 3 | `stay_no_slower` | `stay_no_slower` | 11.717825 | 12.547888 | -0.830063 | 1.171782 | No |
| 12 | 91.040790 | 0 | 3 | `stay_no_slower` | `stay_no_slower` | 5.155674 | 5.445234 | -0.289559 | 1.000000 | No |
| 13 | 91.092834 | 15 | 3 | `stay_no_slower` | `stay_no_slower` | 2.546432 | 5.286927 | -2.740495 | 1.000000 | No |

## Window reconstruction checks

All **28** paid helper reports match their original raw-ACK numerators. **Eight** windows are shortened by the current-phase boundary. After reconstructing both old and clipped numerators, **zero windows discard any ACK bytes** in this specific case: the clipped intervals contain actual barrier-idle time, not previous-phase ACK traffic. That observation is a result of the raw-event check, not an assumption used to change only the denominator.

| Decision index | Helper | Report ID | Phase start (ms) | Sample (ms) | New window (ms) | Original ACK bytes | Rebuilt ACK bytes | Old rate (B/ns) | Shadow rate (B/ns) |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 2 | 1 | 54566 | 40.066695 | 43.591196 | 3.524501 | 7,346,576 | 7,346,576 | 0.734657600 | 2.084430108 |
| 2 | 5 | 54567 | 40.066695 | 43.598876 | 3.532181 | 7,413,232 | 7,413,232 | 0.741323200 | 2.098769004 |
| 3 | 12 | 54583 | 40.066695 | 43.615038 | 3.548343 | 7,299,728 | 7,299,728 | 0.729972800 | 2.057221638 |
| 3 | 2 | 54584 | 40.066695 | 43.622718 | 3.556023 | 7,460,080 | 7,460,080 | 0.746008000 | 2.097871695 |
| 8 | 1 | 80096 | 67.942089 | 71.466029 | 3.523940 | 7,332,912 | 7,332,912 | 0.733291200 | 2.080884465 |
| 8 | 5 | 80097 | 67.942089 | 71.473709 | 3.531620 | 7,393,712 | 7,393,712 | 0.739371200 | 2.093575186 |
| 9 | 12 | 80107 | 67.942089 | 71.509182 | 3.567093 | 7,343,648 | 7,343,648 | 0.734364800 | 2.058720645 |
| 9 | 2 | 80108 | 67.942089 | 71.516862 | 3.574773 | 7,504,976 | 7,504,976 | 0.750497600 | 2.099427292 |

## Why better helper estimates do not flip the decision

- At **44.606556 ms**, source 0's local source/helper stay forecast falls from **35.673565** to **24.014795 ms**, and switch falls to **23.301908 ms**. The sign of the gain becomes positive, but **0.712887 ms** remains below the **2.401479 ms** margin.
- At **72.481389 ms**, source 0's gain becomes **0.459600 ms**, below **2.289933 ms**.
- At **72.524542 ms**, source 15's gain becomes **0.120914 ms**, below **2.699987 ms**.
- For the other affected-window decision, source 15 at **44.630398 ms**, switch remains predicted slower even after removing barrier-idle dilution. The remaining ten decisions keep the same prediction/reason.

The shadow makes an observed helper calibration error smaller, but offers no changed route action on any of the 14 observed decisions. It therefore does not justify launching a helper-only revision as if it already solved the performance deficit. Source completion forecasts, relay capacity under concurrent load, paid information delay and the meaning of the existing margin remain separate explanations to examine. This result is not permission to lower margins after seeing the outcome.

A future revision must be separately frozen and preregistered, with matched negative/transient controls and fresh confirmation. The accepted original performance remains unchanged: candidate/adaptive/legacy communication duration **95.443573 ms**, direct recovery **82.403551 ms**. No duration is assigned to this shadow.
