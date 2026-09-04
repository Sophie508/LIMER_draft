# M3a results: the switch-vs-stay cost curve

Campaign per `docs/m3a_switch_cost_prereg.md`: 7 level directories × 2
measurement arms × 3 repeats = 42 runs, all complete, all correctness
gates passed, every level's report accepted. Retentions below are
recomputed from raw `aggregate_rounds.csv` (median of 3 repeats; raw
values preserved in `results_m3a_loss_sweep/`). Host: fresh 8-vCPU cloud
instance; the full test suite and a smoke run passed there before the
campaign, and all comparisons are within-run against matched baselines.

## Standard topology — surviving plane has headroom

| loss on w2→A egress | stay (retransmit) | switch (localized) | verdict |
|---:|---:|---:|---|
| 0.5% | 0.9921 | 0.9970 | switch (barely) |
| 1% | 0.9903 | 0.9980 | switch |
| 2% | 0.9848 | 0.9958 | switch |
| 5% | 0.9746 | 0.9979 | switch |
| 10% | 0.9212 | 1.0015 | switch |
| 25% | **0.1943** | 1.0004 | switch, by 5× |

Two findings. First, TCP absorbs light random loss remarkably well: at
0.5% loss, staying costs only ~0.8% of throughput, and even 5% loss costs
~2.5% — retransmissions are cheap while the loss stays sparse. Second,
there is a cliff: between 10% and 25% loss the stay arm collapses from
0.92 to 0.19 (retransmission storms and retransmitted packets being lost
again). The switch arm is flat at ~1.00 everywhere, because in this
topology Fabric B has free capacity for worker 2's displaced slots.

**Conclusion (standard topology): switching dominates at every measured
loss level** — the crossover, if any, lies below 0.5%, under this
campaign's measurement floor.

## Constrained variant — surviving plane capped (w2→B at 50 Mbit), 5% loss

| arm | retention |
|---|---:|
| stay on lossy A | **0.9637** |
| switch to constrained B | 0.6684 |

With no headroom on the surviving plane, the decision **inverts**: at 5%
loss, staying (0.96) clearly beats switching (0.67). Combining with the
standard table's 25% row (stay collapses to ~0.19, well below 0.67), the
constrained topology's crossover lies **between 5% and 25% loss** —
bounded but not pinpointed by this campaign; the interior points were not
run and we do not interpolate.

## What this answers, and what it does not

This is the empirical version of the review guidance "understand the
impact of the switch and decide whether it is worth it": the switch/stay
decision is not a function of loss rate alone — it is a function of
(loss rate, surviving-plane headroom). With headroom, switch always; the
policy is trivial. Without headroom, a real threshold appears, and a
practical policy needs an estimate of the surviving plane's spare
capacity, which the switch-side counters we already sample can provide.
Every run's decision context and outcome is preserved in the event logs —
the exact decision-versus-impact records that a future learned policy
(explicitly out of scope for now) would train on.

Not answered here: detector behavior on loss faults (both arms bypass
detection by design — the stay arm runs none, the switch arm is
oracle-triggered); finer resolution of the constrained-topology crossover;
loss on more than one link. All three are declared candidates for the
next campaign rather than silent gaps.
