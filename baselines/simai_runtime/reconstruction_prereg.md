# OptCC network-only reconstruction registration — 2026-10-10

Change: introduce a standalone DAG runner that uses the pinned SimAI
ASTRASimNetwork API and its original ns-3/RDMA transport, rather than modify the
native NCCL ring/tree executor to pretend it accepts arbitrary graphs. Expected:
all graph nodes complete exactly once, every dependency is released at its
specified endpoint, and converted byte totals agree with the disclosed formulas.
This is independent reconstruction; the author integration/configuration is absent.

Scope: network scheduling, not tensor reduction correctness or training latency.
No PacketBundle memory/reduction cost is modeled. The matched comparator is an
explicit ordinary reduce-scatter/all-gather ring DAG in this same runner. Run the
unmodified native SimAI AllReduce separately as an infrastructure/reference check.

First topology: one GPU per server, one nonblocking switch, 200 Gb/s healthy NIC,
100 Gb/s last-rank NIC for L=2, 500 ns per-link propagation. These are declared
choices, not recovered paper settings. Pin AS_SEND_LAT=3 microseconds, one network
QP per flow, CC_MODE=1, payload MTU=9000, PXN/NVLS disabled, packet loss zero.
Control payload=20 bytes; account for it separately. Initially use p=5,k=4,L=2
and N=1,048,576 bytes (divisible by k*(p-1)). Initial results are smoke/calibration
only; do not select k based on favorable observed timings.

Conversion: logical ranks 1..p map to 0..p-1. Reject duplicate IDs/dependencies,
cycles, invalid ranks, zero payload, missing parents and dependencies whose child
sender is neither parent endpoint. Release same-source edges on final send
serialization completion, destination-source edges on the backend's ACK-complete
receive notification. Register all receives before launching roots. Unique tags
are flow IDs within one invocation; forbid concurrent invocations in this runner.
The JSON omits bytes: use exact rational ideal sizes from generator formulas,
round half-up only when needed and publish exact/rounded per-flow values and error.
Rounding is a reconstruction choice, not evidence of tensor partition correctness.

Required gates before any performance claim: converter invariant/malformed-graph
checks; scheduler micrographs with mixed endpoint dependencies and unequal bytes;
transport sizes 20,8999,9000,9001,17999,18000,18001 and 1000-byte MTU variants;
one send/receive completion each, receive not before last serialization; graph
drain with empty transport maps; native ring reference; imported ring; 132-node
OptCC smoke with 255 dependencies validated from the timestamp trace.

Preserve stock transport gate failures before repairing a measured callback bug.
Any repair must apply identically to matched ring and OptCC and have a saved diff.
No interpolation or substituted latency for failed runs. Runtime timeouts remain
failed observations. Store source/config hashes, full invocation, exit code and
completion checks on otakotak scratch; keep thin summaries locally.
