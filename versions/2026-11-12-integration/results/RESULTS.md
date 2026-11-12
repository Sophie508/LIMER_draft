# Integration development results — 2026-11-12

These are declared development comparisons, with one shared physical input/seed per matched row. They are not independent repeat cohorts, statistical evidence of a general 95% guarantee, an external-system comparison or numerical AllReduce validation.

Registered 41 attempts; 41 passed execution audit and independent observation replay (plus policy replay where applicable); 36 communication jobs completed. Valid execution does not mean the job completed.

## Matched four-phase module comparison

16 logical GPUs; 512 × 64 KiB chunks per rank per phase; four phases (2 GiB total logical payload), injection at 40 ms, 400 ms observation horizon. All values are communication ms from business launch, not detection latency. Unfinished jobs remain unfinished rather than receiving a fabricated completion time.

| Condition | G00 fixed | G10 adaptive | G01 fixed + recovery | G11 direct replacement | G11 benefit gate | A-only |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| healthy | 63.94 | 63.97 | 63.94 | 63.97 | 63.97 | 128.01 |
| blackhole | unfinished | unfinished | 252.73 | 87.78 | 87.78 | 128.01 |
| quarter | 191.19 | 83.01 | 200.55 | 84.20 | 82.76 | 128.01 |
| weak_loss | unfinished | unfinished | 85.36 | 94.57 | 106.69 | 128.01 |
| delay | unfinished | 359.49 | 257.30 | 87.78 | 87.78 | 128.01 |

## Full default 30-phase workload

Same 16-GPU model and 512-chunk phase size, 30 phases (15 GiB logical payload), injection at 40 ms and 2000 ms observation horizon. The separate lifetime and weak-loss follow-ups were registered before their execution; they are not replacements for short negative runs.

| Case | Completed | Communication ms | Fresh B-prime chunks completed | Phases with fresh B-prime | Fresh B-prime MiB |
| --- | --- | ---: | ---: | ---: | ---: |
| full-ring-healthy-G11-benefit | True | 480.18 | 0 | 0 | 0.00 |
| full-ring-blackhole-A_ONLY-always | True | 959.85 | 0 | 0 | 0.00 |
| full-ring-blackhole-G11-always | True | 907.90 | 762 | 28 | 47.62 |
| full-ring-blackhole-G11-benefit | True | 907.90 | 762 | 28 | 47.62 |
| full-ring-blackhole-G11-benefit-persistent | True | 920.65 | 1300 | 28 | 81.25 |
| full-ring-weak_loss-G11-always | True | 694.96 | 21 | 5 | 1.31 |
| full-ring-weak_loss-G11-benefit | True | 975.89 | 49 | 5 | 3.06 |

## Lifecycle/opportunity controls

| Chunks per phase | Phase count | Lifetime | Communication ms | Fresh B-prime completions |
| ---: | ---: | --- | ---: | ---: |
| 64 | 30 | persistent | 100.81 | 0 |
| 64 | 30 | phase | 158.31 | 0 |
| 512 | 4 | persistent | 88.65 | 52 |
| 512 | 4 | phase | 87.78 | 32 |

## Detection and interpretation

34/34 fault-arm checks met the strict all-affected-path <100 ms rule, with no pre-fault or off-path alarm. These checks share seeds and workloads across policy arms and must not be counted as independent statistical trials.
Healthy-arm classifications: healthy_clear (7 matched/related runs).

- Phase mode returns to original A/B eligibility at each existing scheduler barrier, retaining already observed physical-fault evidence. Original B is retired only within a committed phase binding.
- Fresh B-prime completions require new chunk allocation, all three physical legs and the modeled source notification. Rescued suffixes are counted separately. A phase barrier waits for all declared logical work; no gradient values are computed.
- The short control keeps zero fresh B-prime work and a lifecycle cost. Longer workloads create a genuine opportunity without holding A idle. More B-prime bytes alone are not evidence of better completion time.
- Gating can reject a slower route but also delay repair. These tables retain both outcomes. A shorter communication time in a matched case does not establish restored healthy dual-plane throughput.
- The v4 detection rules were unchanged. This is not a replacement for the October independent-cohort validation or a new general gray-fault coverage claim.
- Compact receipts include audits and archive hashes. Raw packet archives are retained on otakotak; recomputing raw replay requires those archives.
