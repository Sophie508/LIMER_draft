# M9 scripted pending-flow execution results

## Task and the implementation choice

Sophie approved detecting severe slowdown as well as loss. An alarm should lead
to route-benefit evaluation, not unconditional switching. The first native SimAI
integration task was to make a runtime route change executable before feeding
an online detector into it. The original loss-only M8 verdict is retained.

The static replay had preposted all receives on their initial planes. Changing
only a sender would leave its receive on the wrong port. The separate M9 target
posts one matching receive immediately before each flow launch, records the
committed route version, and retains that ownership through send/receive
completion. Affected unlaunched A flows can move to B; launched flows cannot.

The management channel is an explicitly modeled, reliable, shared FIFO,
separate from the RDMA data network. Each PREPARE, READY and COMMIT is 64 bytes,
with 1 Gb/s serialization and 1 us propagation by default. All four ranks must
vote ready and receive COMMIT before common activation. This is charged modeled
communication, not packetized distributed agreement on the data fabric.

## Prospective registration and observed results

Before launch, `m9_execution_v1/registration.json` froze all nine cases, expected
route-change counts, source/binary/library hashes and container image. Inputs
were individually frozen before each invocation. The eight valid workloads
completed and drained their transport maps; the ninth rejected the deliberately
nonconsecutive version with the expected error. All nine engineering gates pass.

| Registered case | Changed pending flows | Activations | Modeled control bytes | Workload completion (us) | Full execution end (us) |
|---|---:|---:|---:|---:|---:|
| Ring, no control | 0 | 0 | 0 | 221.994 | 221.994 |
| Ring, pending switch | 2 | 1 | 768 | 222.678 | 222.678 |
| Ring, slow control | 0 | 1 | 768 | 221.994 | 759.609 |
| Ring, one missing READY | 0 | 0 | 448 | 221.994 | 1005.000 |
| Ring, two versions | 4 | 2 | 1536 | 223.352 | 223.352 |
| Same-source dependency chain | 1 | 1 | 768 | 50.265 | 50.265 |
| Destination dependency chain | 1 | 1 | 768 | 52.551 | 52.551 |
| Unequal-size join | 1 | 1 | 768 | 58.321 | 58.321 |
| Reject nonconsecutive version | Not a completed workload | 0 | Not scored | Not scored | Not scored |

The default transaction requested at 5 us activates at 13.145 us: 8.145 us of
modeled coordination. With 250 us propagation it activates at 759.609 us, after
the workload has finished, so no flow changes. The missing-READY case ends at
the registered 1 ms timeout after its 5 us request; workload completion alone
would hide that unresolved transaction. Equal-rate healthy planes provide no
expected performance benefit; the switched ring is slightly slower. These are
execution measurements, not adaptive-policy efficacy results.

The ring has four logical ranks, six steps, 24 transfers and 40 endpoint-aware
dependency edges, with 3 MiB logical workload volume and deterministic active
A/B placement. Both planes have 200 Gb/s access links and 500 ns propagation.
The micrographs separately exercise source completion, destination completion,
and an unequal-size join. No impairment was injected in this campaign.

## Verification and preserved attempts

Independent replay auditing reconstructs every flow's selected physical ports,
launch version, immutable completion ownership, correct endpoint dependency
release, exact control FIFO service, readiness, commit delivery and activation.
All 582 trace records across eight completed workloads pass. Frozen inputs,
source, binary and all 39 shared libraries still match registration. Negative
unit fixtures reject ownership changes, unmatched ports, premature dependency
release, duplicate completion, missing readiness, early activation and free
control service. The full Linux Python suite passes all 260 tests; the local
macOS suite passes with its three pre-existing Linux-specific skips.

An initial broad module build was deliberately stopped (exit 137) before the
minimal target build; its log/status are retained. The subsequent minimal build
and the registered execution campaign pass. No failed experiment was removed,
and no efficacy denominator was constructed from the build attempt.

Remote artifacts remain under
`/home/suliu/scratch/LIMER_WORK_2026-10-10/runs/m9_execution_v1/` and
`logs/m9_final_audit.json`. Thin local copies are under
`/Users/sophie/Documents/LIMER_WORK_2026-10-10/m9_validation/`.
The executable hash is
`313581e37c0a71b82c6005d23bc4fb8cbff5d0bf5697a189888fe90a12258ea2`;
source hash is
`2ab5b3431a6ab831fd934c0b38897dafdddc384d432c51147e2a68014c3625df`.

## Remaining constraints

Scripted requests are not detector output. This gate does not establish online
<100 ms detection, beneficial switching, fault recovery, numerical tensor
reduction, packet cancellation/replay or concurrent invocation isolation.
Severely stalled launched transfers remain on their old path. Reliable modeled
control and common activation are explicit assumptions; failures of the control
channel require a separate model. The next implementation must use causal
observations and a finite workload horizon with useful pending work after an
alarm, and preregister eligible slowdown severity and duration.
