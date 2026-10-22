# M12 hybrid delivery detection: frozen results

**[Fact] Prospective empirical verdict: PASS.**
The goal is >=95% correctly localized alarms STRICTLY below 100 ms in EACH
registered eligible fault condition. The frozen primary ledger contains
740 lifecycles: 700 faults and
40 verified controls. There are
698/700 timely fault decisions;
control alarm events: 0; pre-event/unaffected-path alarm events: 0.
All registered late, missed and unverified faults remain in their condition's
denominator. The older all-trial/no-unavailable-report strict verdict is
FAIL; that gate is preserved separately, not rewritten.

## What changed and why

The archived M8 passive batch-counter candidate retained weak-loss, sparse,
idle and report-availability failures. M12 adds continuous same-path probes
and a separate early delivery-service lane. The mature lane retains the
10-ms batches, 50-ms receive guard and two-deficit rule. The early lane
compares adjacent cumulative accepted/delivered packet counts, with both sampled
at closure+10 ms; two consecutive windows with >=32 accepted packets and
delivery <=60% of accepted traffic alarm. Gaps/unknown pairs break evidence.
Neither lane reads injection time, identity, private drops or fault labels.
`missing_packets` in an early-lane alarm is a service-window count shortfall,
not a set of packets proven permanently lost.

All eight paths are monitored from startup. Data and 64-byte ON-WIRE probes
share the same UDP socket, queue, route, receiver and error hook. Main loss is
size-independent IID per packet; permanent loss and severe delay are separate
prospectively eligible causes. Report samples are independently lost copies
on a separate shared 10-Mb/s FIFO with 1-ms propagation. All three 64-byte
copies per sample consume service, including lost copies. A lost report is
unknown, never a zero received count. Alarms are generated natively at the
actual delivered-report events and independently reproduced from the seven
observable fields: path, batch, side, count, sample time, arrival time, guard.

## Frozen independent validation

| Registered eligible condition | Timely / all attempts | Late | Miss/unverified | P95 ms | Wilson 95% interval |
|---|---:|---:|---:|---:|---:|
| 80 Mb/s data, 0.5% loss | 60/60 | 0 | 0 | 78.522 | 93.98–100.00% |
| 80 Mb/s data, 1% loss | 60/60 | 0 | 0 | 70.519 | 93.98–100.00% |
| 80 Mb/s data, 2% loss | 60/60 | 0 | 0 | 64.763 | 93.98–100.00% |
| 80 Mb/s data, 5% loss | 60/60 | 0 | 0 | 62.767 | 93.98–100.00% |
| 1000 Mb/s data, 0.5% loss | 60/60 | 0 | 0 | 66.796 | 93.98–100.00% |
| 1000 Mb/s data, 1% loss | 60/60 | 0 | 0 | 64.030 | 93.98–100.00% |
| 1000 Mb/s data, 2% loss | 60/60 | 0 | 0 | 63.342 | 93.98–100.00% |
| 1000 Mb/s data, 5% loss | 60/60 | 0 | 0 | 62.355 | 93.98–100.00% |
| 1 Mb/s data, 0.5% loss | 60/60 | 0 | 0 | 79.502 | 93.98–100.00% |
| Data idle, 0.5% loss | 59/60 | 1 | 0 | 80.694 | 91.14–99.71% |
| 0.5% packet loss + 10% report loss | 59/60 | 1 | 0 | 77.687 | 91.14–99.71% |
| 80 ms extra delay on 25% of packets | 20/20 | 0 | 0 | 61.847 | 83.89–100.00% |
| 80%-capacity additional competing traffic | 20/20 | 0 | 0 | 34.040 | 83.89–100.00% |

Validation has fresh ns-3 run IDs 41000+, separate from development, seed
20261010 and hidden event phase in 50–60 ms. Code, native executable, library
hashes, image and schedules were frozen before launch. The fixed injected
path is 2/A; arbitrary fault locations or multiple episodes are not validated.
Primary data lasts 1–250 ms; the observation lifecycle is 600 ms. Nominal
repeat controls are deterministic implementation checks rather than estimates
of a stochastic field false-alarm distribution. Source pauses stop data,
while probes continue. Mild background adds 10% of link capacity: on the low
profile, data + probes + background offer 107.92% nominal load, so it must not
be described as below-capacity traffic.

Wilson intervals accompany empirical rates. Even 60/60 has a two-sided 95%
lower bound of 93.98%; 20/20 has 83.89%. An empirical >=95% acceptance pass
does not prove a population lower confidence bound >=95%, nor uniform fault
coverage. Detection times are simulated injection-to-decision intervals,
never pooled with Mininet wall-clock results.

## Costs and preserved limitations

Probe rate is 35,000 packets/s/path: 17.92 Mb/s/path (17.92% of a 100-Mb/s
access). The eight paths inject 69,720 probes/lifecycle, totaling 4,462,080
wire bytes. On the 80-Mb/s data profile, data + probes offer 97.92% nominal
capacity even without background. Collection costs 4,800 report copies,
307.2 KB/lifecycle; steady load is 4.9152 Mb/s, 49.152% of the modeled
collector capacity. These costs are material. Probe rate is the configured
nominal rate; actual nanosecond intervals are rounded up to 28,572 ns.
The separate collector does not share data-plane congestion in this model.

The 15 fresh boundary trials are deliberately reported apart
from the primary matrix, with original failures retained:

| Explicit boundary | Timely / registered | Late | Miss/unverified |
|---|---:|---:|---:|
| 120 ms report propagation | 0/5 | 5 | 0 |
| No-probe idle | 0/5 | 4 | 1 |
| Sparse, business-only size-selective loss | 0/5 | 0 | 5 |

The no-probe idle case has no active observations during idle. Report
propagation of 120 ms makes a <100-ms delivered-report decision impossible;
its lifecycle extends to 800 ms to drain reports. Size-selective loss applies
only to >128-byte packets, making 64-byte probes unrepresentative. Same path
alone does not guarantee probe representativeness. These results limit the
claim to the registered observation and fault envelope. In the sparse selective
boundary, 4/5 lifecycles realize ZERO business-packet drops;
these configured-fault outcomes cannot be presented as that many failures to
detect demonstrated business damage. Zero-damage trials remain registered.

A more informative matched supplement uses 20 fresh seeds 52000–52019,
reused deliberately across IID and size-selective arms at 80-Mb/s business
traffic. Both arms have EXACTLY matched business send/loss COUNTS (not a claim
of exported individual-loss identities): 123 drops in
EACH arm, 0 zero-damage pairs. IID has
20/20 timely decisions; selective has
5/20, 14
late and 1
missed decisions, with no false-alarm events. Selective probes have zero loss.
All 40 lifecycles and 192000 delivered report rows pass
independent accounting/native replay and registration-adapter provenance audit.
This is a direct observed representativeness failure at active business load,
not merely an idle/no-realized-loss example. It is a separate failed supplement,
never pooled into the size-independent primary pass. General fast gray-fault
coverage remains unresolved.

This is isolated one-hop UDP detection, not M11 RDMA collective integration,
tensor reduction correctness, recovery of launched transfers, optimal route
selection, or a matched OptCC/SprayCheck superiority result. Original M7/M8
strict FAILs and loss-only stress labels remain unchanged. The next required
joint experiment must charge these observation costs inside the collective
workload and evaluate detection, switch/stay and execution together.

## Development and verification ledger

Development v1: 57/57
engineering-complete, empirical verdict FAIL.
Sparse weak-loss tails and severe-overload delay were retained.
Development v2: 65/65
engineering-complete, empirical verdict FAIL.
Its early age-deficit lane false-alarmed under mild congestion; that complete
ledger is retained. Development v3 changed to delivery service rate BEFORE
fresh trials and passed 65 development lifecycles.
V3 then FAILED its first independent validation: source-pause controls produced
8 false alarm events.
V4 aligns both early samples at the SAME simulated time and rejects mismatched
sampling. Its corrected development ledger completes 137
lifecycles before fresh 41000+ validation. The original validation is retained,
not reclassified as a pass. Its observed failure informed v4 development; the
new validation's seeds and parameters were not tuned after launch.
The first v4 build/setup ledger retains eight FAILED and 129 UNRUN attempts;
it had copied stale native objects due to source/build clock differences.
Corrected v4b compilation uses the server clock and checks native rule strings,
and its fresh 34000+ development IDs do not reuse failed registrations. Each campaign uses at most eight single-core/1-GiB CPU containers; overlapping
old/new campaigns use at most sixteen, changing wall-clock throughput only.

Linux Python 3.12: 292 tests pass, no skips. Local macOS: 292 tests run,
289 pass and three preexisting Linux-specific tests skip. Native-vs-Python parity, all-attempt
denominators, missing reports, early service windows and FIFO tamper rejection
are covered. Earlier incomplete test-package/fixture failures are retained in
server logs; the complete fixture package was then tested successfully.

Final independent audit verifies 3523470 delivered primary
report rows and 51592800 injected primary probe packets,
registration/source/executable/library/input hashes, exact native alarm replay,
report FIFO serialization and packet/wire-byte conservation. Boundary audit
verifies 72000 report rows. A supplementary counter
audit checks early cumulative monotonicity, final bounds and exact source
prefix agreement over 1834 trials and
14672 path lifecycles; the 40 paired supplement
lifecycles have their own accounting and provenance audit.

Raw evidence stays on otakotak:
`/home/suliu/scratch/LIMER_WORK_2026-10-10/runs/m12_validation_v2`,
`runs/m12_boundary_v2`, archived `runs/m12_validation_v1` and
`runs/m12_boundary_v1`, `runs/m12_development_v1`–`v4b`;
frozen validation source: `m12_source_frozen_validation_v2`.
Thin local evidence, full registrations and audits:
`/Users/sophie/Documents/LIMER_WORK_2026-10-10/m12_evidence`.
Primary source hashes: `07267875d944e0da6c9f4834078dfdbe67e415c5a13b8e7e21501c4831dddf50` (native source),
`313e379bc736961072161863f6a5cb1729fb89bc326a8e4177d4eda0438e84df` (executable).

## Research interpretation

RFC 9341 motivates correlated two-ended counters and guards, while RFC 5357
motivates active test traffic; this custom batch/probe format implements
neither RFC protocol. SprayCheck uses packet spraying and sketches an access-link count/NACK
extension. No untouched-access-link novelty or iteration-to-100-ms comparison
is claimed. Probe representativeness is explicitly tested.

Sources: https://www.rfc-editor.org/rfc/rfc9341.html ;
https://www.rfc-editor.org/rfc/rfc5357.html ;
https://arxiv.org/html/2605.03702v1 .
