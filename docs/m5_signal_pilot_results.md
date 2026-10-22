# M5 observation-only signal pilot results (2026-10-10)

## Protocol and denominator

Registered before execution: 18 configured-loss lifecycles (six levels, three
fresh lifecycles each), three short healthy references and 12 matched controls.
The counter never triggers a detector or changes a recovery plan. Source,
configuration hashes, raw events and failures live on otakotak scratch.

All 33 attempts completed their process lifecycle: 30 workloads complete and
three 25% loss workloads fail the inherited 120-second round wait. There are
615,998 HOST_RETRANS_SAMPLE records, zero unavailable counter reads. A run-level
completion failure remains in the latency observation ledger; it is not removed
because a retransmission was observed first.

## Raw signal availability

The metric is injection-end to first positive delta in rank 2's outgoing A
socket. It is NOT a validated detector latency, fault identity, final recovery
alarm, or guarantee. Each number range is three observed launches; no confidence
interval is inferred. Poll boundaries can overlap injection and are logged.

| Configured loss handle | Attempts | Workloads complete | First positive delta range ms |
|---|---:|---:|---:|
| l0p5 | 3 | 3 | 44.465–1158.146 |
| l1 | 3 | 3 | 59.382–157.443 |
| l2 | 3 | 3 | 59.869–152.596 |
| l5 | 3 | 3 | 47.718–62.696 |
| l10 | 3 | 3 | 51.925–100.594 |
| l25 | 3 | 0 | 40.710–43.727 |

The 0.5%, 1%, 2%, and 10% groups each have at least one observation exceeding
100 ms. This pilot rejects a uniform 100-ms observer claim under this recipe.
It does not estimate deployment p95 or establish an improved detector.

## Controls and interpretation

All three short healthy, three matched nominal and three pause controls have
zero positive deltas. Each congestion control has at least one positive delta
somewhere in the eight observed sockets; some occur before the nominal episode
boundary. Reordering controls produce 892,779,730 rank-2 A retransmissions.
50-Mb/s paced UDP has measured sender rates49.945,49.970,49.966Mb/s; actual receive
rates/drops and kernel queues remain distinct evidence. Controls configure no
random loss; actual queue drops are not independently ruled out. No claim that
a retransmission means a permanently faulty link is justified.

The existing rate-counter detector emits one or more SWITCH_SUSPECT events in
all12 matched controls (host refinement/recovery disabled). This is a symptom
false-positive diagnostic, not a final host-confirmed alarm-rate estimate.

## Stop gate

Do not feed any-positive-retransmission into the controller or launch the formal
loss/false-alarm campaign yet. Its prerequisite, a justified frozen trigger,
is unmet. Cause-aware evidence, or a decision objective tolerant of ambiguous
symptoms, is required. Stronger signals must be evaluated within the slot-based
routing model; SprayCheck's packet-spray distribution is not assumed available.

Bulk evidence root: /home/suliu/scratch/LIMER_WORK_2026-10-10/mininet_results.
Thin analysis: server_summary/signal_pilot_descriptive.json. This document is a
completed pilot result, superseding previous running-pilot status text.
