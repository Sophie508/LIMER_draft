# Throughput revision review

Scope: the candidate source under `../project`. The preceding phase-integration
source under `../../2026-10-28-rdma/project` and its 41 recorded attempts are
preserved. `throughput-v2.patch` compares those two owned source trees. Sophie
authorized committing and pushing the reviewed revision on 2026-11-12.

## Why these changes

The previous blackhole job took 907.896469 ms against a healthy 480.178448 ms.
This is 52.9% of healthy whole-job useful throughput for equal payload. Two
observed bottlenecks motivated the revision: idle-only helpers became available
late in each phase, and physical relay credits stayed occupied during the final
notification's roughly 1-ms transit even after data had reached its destination.

## Changes to review

| Area | Behavior | Cost or invariant retained |
|---|---|---|
| Physical resource lifetime | `ReleaseDelivered` releases relay NIC/buffer reservations after the third data leg | Logical ownership and phase completion still wait for the charged final notification |
| Confirmation window | Up to 32 logical chunks can await completion rather than 8 | Four physical credits per NIC, four buffers per helper; additional logical state is explicit |
| Shared helpers | Paid requests let a helper lend one NIC admission credit while doing its own work | Owner admissions capped at 3; aggregate physical capacity remains 4, and all traffic shares existing links |
| Helper selection | v2 avoids giving a single GPU two helper roles at once | Does not add hardware or inspect fault-injection truth |
| Phase lifetime | Loan state and bindings reset at the next phase | Old callbacks are guarded by phase/version; prior phase's logical work must have finished |
| Audit | Reconstruct lending delivery, physical release, caps, final ACKs and phase boundaries | Packet-derived detector replay remains required |
| Archive | Compression level 1 instead of 6 | Same lossless member hashes checked before raw-log pruning; simulation inputs unchanged |

The helper change is a design extension. The collaborator's proposal waited
until a helper had finished its own phase traffic; the candidate can share a
busy helper's resources. It must be presented as this explicit extension.

The 32-chunk confirmation window has a simple capacity rationale: at 10 Gb/s,
roughly 20 chunks of 64 KiB can arrive during a 1-ms notification delay. The
window leaves room for those unconfirmed chunks plus bounded active transfers.
It is not an increase to the four physical credits. It covers up to 2 MiB of
unconfirmed logical payload per rank, versus 512 KiB before; these are payload
bounds, not measured simulator memory allocations.

## What is intentionally unchanged

The detector, fault definitions, 10-Gb/s access links, 2400-Gb/s intra-server
links, 64-KiB chunk geometry, health TTL, representative three-leg probe,
100-Mb/s control FIFO, 1-ms control propagation and final notification remain
unchanged. The shared candidate still needs a delivered health report and the
full PREPARE/READY/COMMIT sequence. Healthy controls check for denominator
inflation. The larger source window is an explicit protocol-state cost.

These throughput runs use `policy=always`: an alarm plus a validated route
triggers recovery. They do not validate the `benefit` estimator. Its earlier
weak-loss regression (975.894384 ms versus 694.962340 ms for direct recovery)
remains recorded in the preceding version. A tail-aware estimator requires a
separate design and independent policy replay before a benefit claim.

Two supplementary short runs check the existing gate on frozen v2. Blackhole
timing is unchanged, but weak loss worsens from 86.900553 to 98.789654 ms and
fresh B-prime completions fall from 277 to zero. Native decisions independently
replay as written. One recorded refusal predicts
288 remaining B bytes will finish in 572 ns, yet those bytes are still pending
6.1 ms later. See the retained policy log and gate counterexample diagnostic.
Lending admission state also remains active while a rejected gate waits to
retry, until the phase reset. Its actual cost is included in job timing but is
not separately represented in the estimator. The measured regression should
not be attributed exclusively to the tail estimate without another ablation.

## Evidence and negative results

`project-v1` freezes the first candidate. The 12-case v1 pilot includes an
all-local-B-links blackhole boundary that did not finish within 400 ms. That
condition, historically named `no_idle_helpers`, actually injects faults on all
four B access links of one server; shared lending cannot invent a healthy B
path. It is not evidence that the new code automatically falls back to A.

The v2 helper-selection change improved the blackhole pilot from 82.097659 to
78.614773 ms but slightly worsened the weak-loss pilot from 85.773350 to
86.900553 ms. All pilot attempts remain available. The seven full-workload
cases were registered before v2 pilot outcomes, including one fresh matched
seed and an idle-only control. See `../RESULTS.md` for their audited outcomes.

Correctness scope is simulated logical chunk accounting and transport/control
causality. No tensor reduction, real GPU kernel execution, or hardware
throughput is established. The small development cohort does not establish a
population-wide 95% detection guarantee.

## Validation entry points

```bash
cd versions/2026-11-12-throughput/project
python3 limer.py check --verbose
cd ..
python3 verify_compact.py
```

The compact verifier re-derives tables, checks frozen source and build
provenance, and verifies retained server archive receipts. Full packet logs
remain on otakotak. It does not pretend to replay absent raw packet logs on a
laptop.
