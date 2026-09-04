# Pre-registration: M3a switch-cost curve (loss sweep)

Registered before any formal run. Motivated by the 2026-08-27 review
discussion: for a gray fault expressed as packet loss, the system must
choose between staying on the lossy link (paying retransmissions) and
switching the affected traffic to the other plane (paying displacement).
Whether switching is worth it depends on the loss rate and on how loaded
the surviving plane is — and that trade-off has never been measured here.
A learning-based switching policy was explicitly deferred as out of scope;
this campaign produces the empirical decision curve (and, incidentally, the
kind of decision-versus-impact data any future learned policy would train
on).

## Design

Two measurement arms per loss level, three repeats each, in the standard
two-fabric four-worker emulation (per the review guidance to stay on the
simple structure):

- **AA9_STAY**: worker 2's Fabric A egress drops L% of packets (full rate,
  link up); no detection, no recovery. Measured quantity: fault-period
  retention = the cost of staying.
- **AA10_SWITCH**: the same fault, with an oracle committing the localized
  reroute immediately. Measured quantity: post-recovery retention = the
  cost of switching. The oracle isolates the routing question from detector
  behavior on loss faults (the burst rule has only been validated against
  rate caps — that generalization is a separate question, deliberately not
  mixed into this measurement).

Loss levels: 0.5, 1, 2, 5, 10, 25 percent. Above that, TCP over the lossy
link approaches stall and the decision is trivial; 50% is discussed
analytically, not run.

**Constrained-B variant** (`cb50_l5`): one level (5%) repeated with worker
2's Fabric B access capped to 50 Mbit before any round runs — baseline and
fault phase share the cap, so the matched-baseline retention semantics
hold. Expectation stated in advance: in the standard topology the surviving
plane has headroom, so switching should be near-free and dominate at every
measured loss level; the constrained variant exists to show the crossover
that appears when that headroom is gone. If the standard-topology switch
arm is *not* near-free, that is a finding, not a failure.

## Gates (measurement campaign: correctness gates only)

Both arms: run complete; correctness pass (zero checksum/version errors);
AA9 must neither detect nor commit; AA10 must commit exactly worker 2's
three Fabric-A slots. **No retention bounds** — retention is the measured
output, and binding it would presuppose the answer.

## Outputs

Per level: stay-retention and switch-retention (median of 3, raw values
preserved). Deliverable: the two curves over loss level, their crossover
(if any), the constrained-B comparison point, and the raw per-run evidence
under `results_m3a_loss_sweep/<level>/`. Failed repeats are preserved, as
always.

## Environment note

This campaign runs on a fresh 8-vCPU cloud host rather than the machine
used for v1–v3. Before any formal run, the full test suite and a smoke run
execute there, and an AA0-style baseline confirms round timing is
comparable; the report states the host change explicitly. Cross-campaign
comparisons remain within-run (matched baseline), which is robust to host
differences.
