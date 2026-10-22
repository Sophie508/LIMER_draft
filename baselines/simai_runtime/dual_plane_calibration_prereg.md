# Dual-plane packet-model calibration — 2026-10-10

Change/expectation: extend a separate network-only replay binary to give each
logical rank two physical ns-3 network endpoints on disjoint star planes. Logical
DAG dependencies and byte counts stay unchanged. Expect traffic/path isolation,
exact graph drain and monotonic slowdown under declared access bandwidth changes.
This is static calibration, not a runtime LIMER controller or hardware-GPU model.

Four logical ranks, 3-MiB ring, 500-ns links, 200-Gb/s access, MTU 9000, same serial
executor and repaired transport as the verified OptCC baseline. Two switch nodes;
physical endpoints r on A and r+p on B. The topology's GPU labels are adapter
endpoint placeholders, not eight physical GPUs. No inter-plane data link, NVLink,
packet loss or hidden source capacity oracle is used by an adaptive policy.
Ring step parity plus source-rank parity determines initial plane, matching the
prototype's balanced slot map. Static localized switch remaps only last-rank A
flows to B before launch. It has no detection, coordination or in-flight replay
cost; it must not be called measured LIMER recovery performance.

Six declared cases: healthy initial; last A at 50%/20%, each with static stay and
localized switch; last A at 20% with last B at 10% and localized switch. Keep
source hashes, both physical per-plane byte totals, logical dependency trace and
backend route evidence. Require every flow to have exactly one start/send/recv,
physical endpoints on its selected plane, empty transport maps, and total payload
2(p-1)N. The degraded unmodified arm should not beat healthy absent a justified
transport interaction. Failure blocks the larger route-choice matrix.

Later dynamic comparison needs measured or explicitly imposed detection/cutover
costs, background-flow pacing and finite horizons. No such evidence is created by
these six calibration cases. OptCC's plane-slot mapping must be separately
specified and byte-accounted before crossing scheduling and route-choice factors.

## Input-table amendment before new attempts

Three original 40/20-Gb/s cases abort before time advances: the official ECN
KMIN/KMAX/PMAX tables have no entries for those speeds. This is a configuration
failure, not latency evidence. Preserve all six original attempts. For new
`ecn_v1_` attempts, explicitly add 40-Gb/s entries (160,640,0.2) and 20-Gb/s
entries (80,320,0.2), scaling KMIN/KMAX from the supplied25-Gb/s (100,400,0.2)
row at constant propagation delay. Keep all existing rows unchanged and repeat
all six cases. This is a declared configuration choice, not recovered paper
parameters. Record final config hashes and the new ECN rows in every manifest.

## Matched constrained-B references before additional launches

The six ECN-amended calibrations drain and validate. The constrained-B switch
case cannot be compared to an unconstrained-B stay case as a route-choice result.
Add two separate attempts at last-B20Gb/s: healthy last-A200Gb/s stay reference
and last-A40Gb/s stay. Compare the latter only to the completed last-A40/last-B20
static-switch case with the same graph bytes, binary and ECN config. Hypothesis:
constrained B can reduce or reverse switching's benefit; retain either outcome.
