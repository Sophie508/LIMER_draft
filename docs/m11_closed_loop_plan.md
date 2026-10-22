# M11 finite-horizon observable route-choice plan

> Execute inline with executing-plans under Sophie's autonomous simulation
> authorization. Keep changes uncommitted; request permission before any push.

**Goal:** Connect native causal slowdown alarms to cost evaluation and the M9
pending-flow coordinator, then compare finite completion costs in one backend.
**Architecture:** Keep the M10 decision rule unchanged. Reports additionally
carry local pending and unacknowledged launched bytes on both planes; charge
96 bytes per path report. At an A alarm, compare modeled remaining serialized
work using delivered observations. Unknown or stale B service selects stay.
Selected changes run the same all-rank PREPARE/READY/COMMIT transaction.
**Tech stack:** Pinned SimAI/ns-3 C++17 and independent Python auditing.

## Observable heuristic and limits

Let W_A/W_B be pending bytes and I_A/I_B launched unacknowledged bytes in the
delivered sender report. Let r_A be current observed ACK service and r_B the
minimum of B's calibrated and last positive fully busy service, no older than
20 ms at decision arrival. Unknown/zero service selects stay.

Estimated stay = max((I_A+W_A)/r_A, (I_B+W_B)/r_B).
Estimated switch = max(I_A/r_A, (I_B+W_B+W_A)/r_B) + 10 us.
Switch only when the latter is strictly smaller and pending A work exists.
The 10-us coordination budget conservatively exceeds the registered default
four-rank transaction. This is a sender-service heuristic, not a collective
critical-path optimizer. It assumes recent B service remains usable, and can
misjudge contention or future capacity changes. The report's queue state may
already be stale; actual execution only moves still-pending flows.

## Registered experiment before launch

Use fourteen consecutive four-rank 3-MiB ring graphs, with each round's roots
released no earlier than 0,100,...,1300 ms and endpoint-aware dependencies from
the previous round. Release times represent a prescribed workload schedule,
not detector knowledge of fault time. Each round remains network-only.

At 312 ms, reduce rank-2 A configured egress service from 1 to 0.2 Gb/s using
the explicit M10 v2 device/DCQCN model. Compare alternatives initially at 1
Gb/s (potentially helpful) and 0.1 Gb/s (potentially harmful). Other accesses
remain at 1 Gb/s. Carry identical reporting in all arms: 2-ms sampling, separate
10-Mb/s reliable FIFO, 1-ms propagation, 96 bytes per report. Detector receives
no injection metadata. Fixed/oracle identities and times are explicit baseline
inputs; the observable arm receives no scripted control request.

Register four arms in both conditions (eight runs): stay; fixed localized
switch requested at workload start; oracle switch at injection time; observable
candidate. All switches pay the modeled coordination cost and preserve launched
ownership. The oracle does not decide whether switching is beneficial: it is an
oracle timing arm, and may hurt when B is slow. No physical/numerical AllReduce
or OptCC superiority claim is allowed; this first loop uses the ordinary ring.

**What changes:** online alarm → observable cost estimate → staged route commit
in a finite multi-round workload, with declared queue-report cost.
**Expected observation:** useful B service should favor switching, slow B service
should favor staying; these are hypotheses. Report total makespan from workload
start, actual changes/control bytes, all alarms and failures. Scientific failures
do not stop or disappear; unexpected engineering failures stop expansion.

## Verification tasks

- [x] Test the independent cost estimator on helpful/harmful, already-launched,
  no-pending, unknown/stale and exact-tie cases.
- [x] Implement local queue summaries, prescribed release gates and causal
  policy callbacks in a separate M11 target/backend; preserve M9/M10 binaries.
- [x] Freeze all eight inputs/source/library/image versions before launching.
- [x] Independently reconstruct report service, detector output, queue-byte
  bounds, cost decisions, selected requests, release gates and launch ownership.
- [x] Compare measured finite-horizon arms without claiming the heuristic is
  optimal or the development measurements establish broad <100-ms detection.
