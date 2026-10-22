# First matched network replay measurements — 2026-10-10

Change: after all transport/scheduler/OptCC smoke gates pass, run the ordinary
ring and disclosed OptCC single-straggler DAG on the same repaired packet backend.
Expected: exact graph drain and dependency order; latency may favor either arm.
Failure to improve is retained. This checks reconstructed network makespan, not
the author's reported curve, GPU performance or numerical tensor correctness.

Frozen conditions: p=5 with N=5 and 20 MiB; p=16 with N=15 and 60 MiB. N is chosen
to divide exactly by both p and k*(p-1) for k=4, rather than chosen from observed
speedups. Single last-rank NIC is 100 Gb/s, all other NICs 200 Gb/s; L=2. One switch,
500 ns propagation per link, AS_SEND_LAT=3 us, controls=20 bytes, CC_MODE=1,
MTU=9000, no packet loss, no NVLink or PXN. Same runner/config/transport for both.

Three fresh process launches per arm/condition, fixed default simulator RNG seed
and one available route. These are deterministic repeatability checks, not three
independent stochastic samples; no confidence interval/error-bar claim. Latency is
the maximum send/ACK-complete receive timestamp across the full graph (origin 0),
validated by the trace checker. Publish graph sizes, payload/control totals and
every run status. A 120-second wall timeout is FAILED; never replace/interpolate.

Healthy ring references run once per condition on all 200-Gb/s NICs. These help
expose the bandwidth fault cost; they do not share the degraded physical condition.
After primary runs, a preregistered k=8/16 sensitivity at p=16,N=15 MiB,L=2 examines
the segmentation overhead. Do not pick the winning k as the new primary arm.

Write only validated timings to Overleaf with the independent-reconstruction and
network-only labels. Keep native SimAI NVLink reference measurements in a separate
infrastructure table. Treat scheduling completion as distinct from numerical
AllReduce correctness and route-switching effectiveness.

## Gate-driven amendment before performance execution

The MTP scheduler with one worker drained both OptCC graphs but violated seven
parent/child timestamp inequalities in the L2 smoke. Shared graph state observed
callbacks from different logical processes in a nonchronological order. Use
ns3::DefaultSimulatorImpl for the standalone runner so all dependency callbacks
execute in chronological order. This setting applies to both matched arms. Repeat
all transport and scheduler gates with new run names; retain the failed MTP runs.
Native SimAI's original MTP/NVLink run remains a separate infrastructure reference.
