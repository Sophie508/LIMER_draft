# Constrained-B fixed-route episode diagnostics — 2026-10-10

Change/expectation: compare fixed stay and an immediate safe-boundary localized
switch under the same 25% A rank-2 egress loss and B rank-2 access10Mbit profile,
using the guarded source snapshot but neither adaptive heuristic nor the new
signal trigger. The guarded stay pilot conforms to its expected branch yet times
out. The fixed switch may still finish, showing why a branch expectation is not
an episode-cost optimality label; retain the opposite outcome as well.

Three fresh lifecycles per arm, unchanged2MiB/1warmup/2baseline/8post-round work,
step timeout300s, inherited collective wait120s and wall1800s. Both fixed arms
keep detector off, TCP observer off, identical initial slot map and fault recipe.
Switch uses existing C4 oracle at the next safe round; its coordination cost is
included, but detection delay/in-flight cutover are omitted. Stay uses C1/AA9.
Do not call this a real-time LIMER or independent paired optimal-arm ground truth
for unobserved states. tc/netem realized loss streams are not shared across the
processes; the pairing is by workload/configuration, not identical packet draws.

At most two task Mininet lifecycles; launch after all33 signal pilots finish.
Record every attempt/status/fault recipe/source hash and exact clock timestamps.
Primary diagnostics: completed post rounds and elapsed fault-to-last-post-round
completion, with failed arms retaining no finite completion value. Also retain
baseline throughput and overall correctness/route delta. A successful switch
must change only rank2's three A slots. No retry replaces a failed attempt.
