# Recovery throughput development design

User authorization: improve the integrated simulation toward 70–80% of healthy
whole-job useful throughput. Previous diagnosis and the proposed resource,
helper-availability and tail-estimation investigation were accepted by the user.
The target is a research objective, not permission to change the denominator.

The immutable 41-case integration evidence and its original source remain in
their existing directories. A separate candidate project lives in
`versions/2026-11-12-throughput/project`. Its third_party symlink references the
identical repository-vendored dependency. No commit or push is authorized.

## Alternatives and selected sequence

1. Correct resource lifetime with idle-only helpers. Keep final notifications
   and logical completion, but release NIC/buffer reservations at delivery of
   the final relay leg. Allow a finite 32-chunk logical confirmation window
   instead of coupling it to the eight physical source slots. Four physical
   credits per NIC and four helper buffers remain enforced.
2. Explicit shared-helper extension. After a causal alarm, send charged lending
   requests to one helper in each endpoint server. Reserve at most one of four
   network credits for relay use while the helper's own traffic uses up to
   three; all traffic shares the same physical rate. Data still waits for a
   full representative probe, its report and full phase-local coordination.
   This changes the collaborator's whole-GPU-idle condition and is reported
   separately, not silently treated as the original model.
3. Tail-sensitive gate, only after the transport design works. Use observable
   per-chunk time without ACK progress in addition to recent average rate.
   A new estimator must have an independent causal replay before acceptance.

## Fixed constraints

16 logical GPUs, 4/server, two 10-Gb/s planes, 64-KiB chunks, 512 chunks/rank/phase,
30 phases for full evaluation, fault onset 40 ms, 2-s observation horizon,
unchanged fault profiles, detector v4, 2-ms/64-KiB canaries, 1-ms charged control
propagation and 100-Mb/s FIFO. Source/receiver identities, phase barriers,
exactly-once logical accounting and non-oracle decisions remain required.
Unfinished and invalid cases are retained. Original 480.178448-ms healthy result
is also reported alongside candidate-matched healthy controls to reveal any
artificial denominator inflation.

## Acceptance

Correctness and independently replayed detector decisions are prerequisites.
Report T_healthy/T_fault, payload completion, fresh/rescued B-prime volume,
phase timing, control/probe traffic, and resource maxima. Initial development
uses paired four-phase cases; full runs use the registered 30-phase workload.
Record source/build hashes and cases before execution. At least fresh matched
seeds must check the chosen design; a development success is not a general 95%
detection or throughput guarantee. No hidden fault state may guide recovery.

## Risks

Releasing physical credits cannot release logical ownership or skip the final
notification. Shared helpers can slow their own traffic; total phase completion
must include this cost. Confirmed phase reset must cancel stale lending/probe
callbacks. Shared-helper behavior remains an explicit architectural extension.
