# Observation pilot controls and execution — 2026-10-10

Change/expectation: run the registered 7 original TCP_INFO configurations three
times, plus four matched no-drop controls three times (33 lifecycles total).
Expect connection-scoped Linux counters with explicit unavailable samples;
low-loss separation is a hypothesis, not a preset latency result. No new trigger
threshold or recovery policy consumes this signal during the pilot.

Added controls share l1's 2-MiB, 1 warmup/2 baseline/8 post rounds and 100-Mbit/s
access profile, with fault_loss_pct=0 and detector enabled/recovery disabled:
nominal; 50-Mbit/s paced UDP on B from rank 2 to rank 3 starting before healthy
calibration; 250-ms inter-round pauses; A rank-2 egress reordering (10-ms delay,
25% reorder, 50% correlation) after calibration. The latter has no configured
packet-drop probability, but queue/congestion drops must still be counted.
Original C0 healthy is an additional infrastructure control, not the matched
false-alarm denominator alone. Do not infer burst timing robustness from a
payload-size change. Preserve actual UDP sent/received rate and scheduler gaps.

Controls are runtime wrappers around topology creation, environment injection and
round spacing. They do not modify worker/source detector logic or read injector
state into inference. Preserve wrapper/config hashes in every run. At most two
Mininet lifecycles across the task, with identical 4-CPU/4-GiB isolated containers.
A 1800-second wall guard remains an infrastructure failure. Before launching,
complete the two preserved original r01 lifecycles; then execute guarded pilot,
nine original v3 checks and this observation pilot. Only a successful guarded
branch/correctness pilot may expand to nine additional repetitions per branch.

Analyze raw new-counter detection times after this pilot; freeze a threshold in
a separate amendment before held-out validation. Missing readings, misses and
failed runs stay in their denominators. These 33 pilot observations cannot prove
a <100-ms bound or provide the final false-positive estimate.
