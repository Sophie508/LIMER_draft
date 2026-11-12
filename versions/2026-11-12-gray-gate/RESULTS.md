# Gray-fault gate: registered simulation results

Workload: 16 logical GPUs × 512 chunks × 64 KiB × four phases = 2 GiB
of useful payload per case, in the native CPU network simulator. Each GPU
has two 10-Gb/s access paths. Helper-local links are 2400 Gb/s except for
the explicitly labelled 1-Gb/s boundary controls. See the fixed
`research/EXPERIMENT_PROTOCOL.md` in this version for conditions and seeds.

This four-phase / 2-GiB diagnostic does not revalidate the earlier
30-phase / 15-GiB throughput release or its 70%–80% retention target.
Ratios from those workloads must not be compared or pooled: phase count,
payload and fault onset must match for a direct performance comparison.

All values below come from the registered summaries. Times are whole-job
communication completion in milliseconds: `(job_done_ns - 1,000,000) / 1e6`.
The fixed 1-ms launch offset is removed from every arm and healthy control.
Each case sends the same useful payload. Invalid and unrun cases
have no performance value; an unfinished horizon is not an exact finish.

The 250-ms simulated observation horizon corresponds to 249 ms after job
launch. Monitoring continues after useful work finishes. Whole-horizon
control/probe totals therefore include activity that did not delay this
job. Detection delay instead starts at the configured fault onset.

These are four LIMER ablations, not a reproduction of R2CC or a hardware
comparison. The candidate changes its estimator, paid observations and
resource lifecycle together. It is not an estimator-only ablation.

The first v1 campaign stopped after an audit false positive. Its one valid
and one invalid attempt, plus all unrun registrations, remain separately
preserved in `evidence-v1`; they are not silently replaced or pooled here.

## pilot-v2

Registered: 20; attempted: 20; valid: 20; completed: 20.

| Condition | Adaptive only | Direct recovery | Old gate | Candidate gate | Candidate − direct |
| --- | ---: | ---: | ---: | ---: | ---: |
| healthy | 63.966 | 63.966 | 63.966 | 63.966 | 0.000 |
| sustained_25_early | 95.444 | 82.404 | 95.444 | 95.444 | 13.040 |
| sustained_25_late | 83.008 | 77.172 | 83.008 | 83.008 | 5.836 |
| transient_25_20ms | 72.619 | 80.313 | 72.661 | 72.675 | -7.638 |
| blackhole | not registered | 84.231 | not registered | 84.300 | 0.069 |
| weak_loss | not registered | 112.972 | not registered | 116.883 | 3.911 |

Negative difference means the candidate finished sooner. A blank
difference means that two valid completed runs are unavailable.

### Candidate behavior and detection

| Condition | Completion / detection class | Healthy-normalized useful throughput | Worst affected-path alarm delay from onset, ms | Initial/refresh activations | Fresh relay chunks | Released leases |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| healthy | completed / healthy_clear | 100.00% | — | 0 | 0 | 0 |
| sustained_25_early | completed / timely | 67.02% | 7.074 | 0 | 0 | 14 |
| sustained_25_late | completed / timely | 77.06% | 11.057 | 0 | 0 | 7 |
| transient_25_20ms | completed / timely | 88.02% | 7.074 | 0 | 0 | 10 |
| blackhole | completed / timely | 75.88% | 8.015 | 6 | 701 | 0 |
| weak_loss | completed / timely | 54.73% | 42.008 | 6 | 104 | 5 |

The throughput ratio is matched healthy completion time divided by fault
completion time for identical useful bytes. It is not instantaneous
post-recovery link bandwidth. Activation count includes health refreshes.
Fresh relay work alone does not prove a net time saving.

Detection delay is the maximum over affected paths within one case.
A miss has no finite all-path delay; it remains in the denominator.
A valid trace can contain a late/missed/false alarm, and a timely
alarm does not imply task completion or a beneficial route change.
Paired arms and deterministic repeats are not independent detection
trials. This matrix does not establish a population-level 95% target.

### Detection accounting for every registered attempt

| Arm | Fault cases registered | Timely | Late | Miss | Other fault outcomes | Healthy clear / registered | Healthy false alarms |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Adaptive only | 3 | 3 | 0 | 0 | none | 1/1 | 0 |
| Direct recovery | 5 | 5 | 0 | 0 | none | 1/1 | 0 |
| Old gate | 3 | 3 | 0 | 0 | none | 1/1 | 0 |
| Candidate gate | 5 | 5 | 0 | 0 | none | 1/1 | 0 |

Counts pool heterogeneous conditions only to account for registered
attempts; they are not a pooled acceptance rate or independent
sample count. Condition-level classifications remain above and in
`trials.csv`. Error and not-run outcomes are never removed.

### Candidate control cost over the observation horizon

| Condition | Bytes enqueued before job completion | Bytes enqueued at/after completion | Bytes scheduled to arrive after completion | Total logged bytes |
| --- | ---: | ---: | ---: | ---: |
| healthy | 0 | 0 | 0 | 0 |
| sustained_25_early | 12480 | 0 | 192 | 12480 |
| sustained_25_late | 7104 | 0 | 0 | 7104 |
| transient_25_20ms | 8832 | 0 | 0 | 8832 |
| blackhole | 81504 | 0 | 384 | 81504 |
| weak_loss | 27072 | 0 | 192 | 27072 |

The first two columns partition by enqueue time. The arrival column
can overlap them and must not be added to their sum. It does not convert
bytes into a causal latency penalty. For unfinished work only the
whole-horizon total is available. Relay/probe wire-byte totals and
lease counts in `report.json` also span the observation horizon.

### Completed candidate pairs: adverse and unresolved outcomes

- `blackhole-s111213001` versus `direct`: candidate slower by **0.069397 ms**.
- `sustained_25_early-s111213001` versus `direct`: candidate slower by **13.040022 ms**.
- `sustained_25_late-s111213001` versus `direct`: candidate slower by **5.836397 ms**.
- `transient_25_20ms-s111213001` versus `adaptive`: candidate slower by **0.056523 ms**.
- `transient_25_20ms-s111213001` versus `legacy_gate`: candidate slower by **0.014212 ms**.
- `weak_loss-s111213001` versus `direct`: candidate slower by **3.910860 ms**.

Exact ties and tiny differences are descriptive; this matrix supplies
no statistical significance test. An incomplete campaign cannot
support a final overall gain claim.

## confirmation-v2

Registered: 30; attempted: 30; valid: 29; completed: 27.

| Condition | Adaptive only | Direct recovery | Old gate | Candidate gate | Candidate − direct |
| --- | ---: | ---: | ---: | ---: | ---: |
| healthy | 63.966 | 63.966 | 63.966 | 63.966 | 0.000 |
| sustained_25_early | 95.444 | 82.404 | 95.444 | 95.444 | 13.040 |
| sustained_25_late | 83.008 | 77.172 | 83.008 | 83.008 | 5.836 |
| transient_25_20ms | 72.619 | 80.313 | 72.661 | 72.675 | -7.638 |
| blackhole | not registered | 84.231 | not registered | 84.300 | 0.069 |
| weak_loss | not registered | 88.572 | not registered | 91.503 | 2.931 |
| sustained_50_early | 84.494 | 78.713 | 84.247 | invalid | — |
| no_healthy_helper | not registered | unfinished after 249 ms | not registered | unfinished after 249 ms | — |
| healthy_local_1gbps | not registered | 63.966 | not registered | 63.966 | 0.000 |
| slow_helper_25 | not registered | 109.149 | not registered | 95.444 | -13.705 |

Negative difference means the candidate finished sooner. A blank
difference means that two valid completed runs are unavailable.

### Candidate behavior and detection

| Condition | Completion / detection class | Healthy-normalized useful throughput | Worst affected-path alarm delay from onset, ms | Initial/refresh activations | Fresh relay chunks | Released leases |
| --- | --- | ---: | ---: | ---: | ---: | ---: |
| healthy | completed / healthy_clear | 100.00% | — | 0 | 0 | 0 |
| sustained_25_early | completed / timely | 67.02% | 7.074 | 0 | 0 | 14 |
| sustained_25_late | completed / timely | 77.06% | 11.057 | 0 | 0 | 7 |
| transient_25_20ms | completed / timely | 88.02% | 7.074 | 0 | 0 | 10 |
| blackhole | completed / timely | 75.88% | 8.015 | 6 | 701 | 0 |
| weak_loss | completed / timely | 69.91% | 40.025 | 4 | 1 | 4 |
| sustained_50_early | invalid / error | — | — | — | — | — |
| no_healthy_helper | unfinished / timely | — | 8.061 | 0 | 0 | 0 |
| healthy_local_1gbps | completed / healthy_clear | 100.00% | — | 0 | 0 | 0 |
| slow_helper_25 | completed / timely | 67.02% | 7.074 | 0 | 0 | 14 |

The throughput ratio is matched healthy completion time divided by fault
completion time for identical useful bytes. It is not instantaneous
post-recovery link bandwidth. Activation count includes health refreshes.
Fresh relay work alone does not prove a net time saving.

Detection delay is the maximum over affected paths within one case.
A miss has no finite all-path delay; it remains in the denominator.
A valid trace can contain a late/missed/false alarm, and a timely
alarm does not imply task completion or a beneficial route change.
Paired arms and deterministic repeats are not independent detection
trials. This matrix does not establish a population-level 95% target.

### Detection accounting for every registered attempt

| Arm | Fault cases registered | Timely | Late | Miss | Other fault outcomes | Healthy clear / registered | Healthy false alarms |
| --- | ---: | ---: | ---: | ---: | --- | ---: | ---: |
| Adaptive only | 4 | 3 | 0 | 1 | none | 1/1 | 0 |
| Direct recovery | 8 | 7 | 0 | 1 | none | 2/2 | 0 |
| Old gate | 4 | 3 | 0 | 1 | none | 1/1 | 0 |
| Candidate gate | 8 | 7 | 0 | 0 | error: 1 | 2/2 | 0 |

Counts pool heterogeneous conditions only to account for registered
attempts; they are not a pooled acceptance rate or independent
sample count. Condition-level classifications remain above and in
`trials.csv`. Error and not-run outcomes are never removed.

### Candidate control cost over the observation horizon

| Condition | Bytes enqueued before job completion | Bytes enqueued at/after completion | Bytes scheduled to arrive after completion | Total logged bytes |
| --- | ---: | ---: | ---: | ---: |
| healthy | 0 | 0 | 0 | 0 |
| sustained_25_early | 12480 | 0 | 192 | 12480 |
| sustained_25_late | 7104 | 0 | 0 | 7104 |
| transient_25_20ms | 8832 | 0 | 0 | 8832 |
| blackhole | 81504 | 0 | 384 | 81504 |
| weak_loss | 11904 | 0 | 192 | 11904 |
| sustained_50_early | — | — | — | — |
| no_healthy_helper | — | — | — | 1536 |
| healthy_local_1gbps | 0 | 0 | 0 | 0 |
| slow_helper_25 | 12288 | 0 | 0 | 12288 |

The first two columns partition by enqueue time. The arrival column
can overlap them and must not be added to their sum. It does not convert
bytes into a causal latency penalty. For unfinished work only the
whole-horizon total is available. Relay/probe wire-byte totals and
lease counts in `report.json` also span the observation horizon.

### Completed candidate pairs: adverse and unresolved outcomes

- `blackhole-s111213033` versus `direct`: candidate slower by **0.069397 ms**.
- `sustained_25_early-s111213033` versus `direct`: candidate slower by **13.040022 ms**.
- `sustained_25_late-s111213033` versus `direct`: candidate slower by **5.836397 ms**.
- `transient_25_20ms-s111213033` versus `adaptive`: candidate slower by **0.056523 ms**.
- `transient_25_20ms-s111213033` versus `legacy_gate`: candidate slower by **0.014212 ms**.
- `weak_loss-s111213033` versus `direct`: candidate slower by **2.930540 ms**.

Unresolved registrations (including other arms):
- `sustained_50_early-candidate_gate-s111213033`: invalid; detection `error`.
- `no_healthy_helper-direct-s111213033`: unfinished after 249 ms; detection `timely`.
- `no_healthy_helper-candidate_gate-s111213033`: unfinished after 249 ms; detection `timely`.

Exact ties and tiny differences are descriptive; this matrix supplies
no statistical significance test. An incomplete campaign cannot
support a final overall gain claim.

## Retained limits

- The gate controls only initial activation per phase.
- A current-phase forecast is evaluated using whole-job completion.
  Whole-job gain is not a direct measurement of each decision forecast;
  later phases and helper contention can change the result.
- Helper forecasts use outgoing work and recent ACK service; incoming
  competition and other ranks are not separately predicted.
- Stalled-tail persistence and equal-byte helper opportunity cost are
  heuristics, not counterfactual or future-fault information.
- Four phases, one placement, fixed onsets and a small set of rates
  do not establish generality or training-scale performance.
- Only weak-loss repetitions use new random fault streams; repeated
  deterministic scenarios do not add independent statistical evidence.
- See `research/NOVELTY_AUDIT.md` before making novelty claims.
