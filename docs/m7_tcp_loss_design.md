# M7 passive TCP loss-confirmation candidate and experiment plan

**Goal:** Implement and prospectively test a host decision for the unresolved
<100 ms gray-failure target. Retain cost/execution work and all old evidence.
**Architecture:** Opt-in extended Linux TCP_INFO observation on every outgoing
worker connection. A connection-scoped state machine combines outstanding/lost
packets, retransmissions and reordering/DSACK feedback. It issues a host decision,
initially isolated from route control. No injector/capture data enters its inputs.
**Tech stack:** Python standard library, Linux TCP_INFO UAPI, existing Mininet and
owned rootless Docker on otakotak scratch. At most two four-CPU/four-GiB lifecycles.

## Research basis and alternatives

RFC 8985 RACK-TLP uses time/ACK evidence, with DSACK adaptation because reordering
can cause spurious retransmissions. We do not implement or claim to reproduce
RACK: Linux already provides transport recovery; this is an application-level
interpretation of exported state. SprayCheck's packet-spraying statistical model
is unavailable for our deterministic slot routing. Receiver sequence gaps are
useful timing observations but are confounded by reordering. Active probes could
cover idle periods, but at 0.5% independent loss approximately 598 probes are
needed for a 95% chance to see even one drop; probe overhead and delay ambiguity
would require separate design. Start with passive sender feedback.

Primary sources read:
- https://www.rfc-editor.org/rfc/rfc8985.html
- https://raw.githubusercontent.com/torvalds/linux/v6.8/include/uapi/linux/tcp.h
- https://arxiv.org/html/2605.03702v1

The actual server's native UAPI offsetof check verifies unacked=24, lost=32,
retrans=36, rtt=68, total_retrans=100, bytes_acked=120, bytes_sent=200,
dsack_dups=216, reord_seen=220. Require a complete 224-byte prefix, report missing
or unsupported reads rather than zero. Bracket each socket read with monotonic
timestamps; use read completion for the sample/decision time.

## Frozen first candidate, before development runs

Version `tcp-loss-v1`: sample each outgoing connection every 5 ms. A candidate
requires unacked>0, kernel lost>0, and at least two new total_retrans increments
in the trailing 100 ms. The lost/outstanding condition must persist for >=30 ms,
with no sample gap >15 ms. Any new DSACK/reordering event cancels the candidate
and vetoes confirmation for 100 ms. Idle/cleared loss, missing reads, connection
replacement, timestamp regression and counter discontinuities reset evidence.
One confirmation per connection generation; each records all supporting fields
and timing. These constants are exploratory design choices, not learned accuracy
or universal loss/delay guarantees. The rule cannot identify physical causes.

Candidate modules: `limer_v0/tcp_loss.py` (UAPI parsing, sampler, state machine),
worker lifecycle/CLI integration, orchestrator opt-in configuration/launch. Preserve
original retransmission observer and default behavior. Initially reject enabling
this candidate with automated recovery; add route-control consumption only after
independent validation and an explicit documented amendment.

## Implementation and checks

- [x] Add tests for delayed/spurious feedback, counter/read discontinuities,
  connection replacement, idle reset, missing fields and sustained evidence.
- [x] Implement extended sampler and state machine; test synthetic known UAPI
  offsets and Linux loopback reads. Sample duration/missing reads stay observable.
- [x] Wire worker/CLI/config without changing framed payload or receive ownership.
  Filter high-rate observation events out of command wait queues.
- [x] Run full Python suite on Linux frozen source before topology experiments.
- [x] Preserve a separate source snapshot, image/config/runtime hashes and diff.

## Development gate: eight exploratory lifecycles

Change: add opt-in passive detector; use offloads-disabled ingress-IFB recipe
from M6 so observed loss-stage IP lengths are MTU-sized. No recovery. 2 MiB,
1 warmup/2 baseline/4 post rounds, unchanged 100 Mb/s shaping and 1 ms base delay.
Expected: lost evidence could produce a decision around first signal+30 ms, while
DSACK/reordering vetoes short reorder cases. This is a hypothesis, not a promise.

One run each: nominal, 1/2/5% random loss, B congestion at 50 Mb/s, 250 ms round
pause, A reordering with 10 ms delay and a 40 ms-delay stress control. Every source
connection is monitored continuously from startup, not armed at fault time.
Keep no-loss controls and setup/measurement failures in the ledger. Observe the
actual candidate decision and any false alarm before or after the pseudo-event.
Development data may motivate a separately versioned rule, not final evidence.

## Prospective validation gate

Freeze the final candidate and configuration in a separate registration before
any validation run. Intended 20 fresh runs each at 1/2/5% loss plus 20 balanced
nominal/congestion/pause/10 ms reorder controls. Include all attempts and confirm
correct localization (rank 2 A) plus any alarms on unaffected connections.
If development exposes failure, document it and amend the candidate rather than
launch a nominally successful matrix or hide a stress-control failure.

Primary operational result: correctly localized confirmations within 100 ms /
all registered fault attempts. Timer: actual fault injection completed to actual
host confirmation; signal times are separate. Misses/late decisions remain in
the denominator. Report all delays, exact order-statistic p95 with misses as
infinite (never only among detections), conditional finite delays separately,
false alarms/control lifetime and completion/transport integrity.

Keep the original strict all-run/<100 ms/no-control-alarm gate as a secondary
binary verdict; do not silently relax it to p95. No universal guarantee follows
from an all-pass sample. Report empirical intervals and traffic/delay assumptions.

## Constraints and stop rules

No Git commit/push before Sophie's diff approval/explicit push permission.
User authorizes autonomous research/implementation, so no repeat design-approval
question or skill-requested commit is performed. No H20, GPU, host security/sysctl
changes or daemon interference. Keep failed infrastructure attempts separately
from scientific trials. Do not tune on prospective validation. Require a distinct
new validation if a failed frozen rule changes. Bounded passive observations cannot
guarantee low-loss detection during idle traffic or distinguish arbitrary packet
delay from permanent loss within 100 ms; preserve those scope limits.

## Measurement amendment: ingress shaping on every monitored path

Initial V1 development confirms 1/2/5% loss in 50.976/44.047/40.239 ms,
but nominal produces six alarms on unaffected flows, congestion one and 10 ms
reorder one. Nominal alarms occur around 2.7–2.9 seconds after the pseudo-event,
not just startup. Do not fix this by ignoring warmup, filtering to the known
faulted connection or deleting unaffected alarms. The first candidate fails.

A possible emulator confound is sender-egress netem shaping interacting with
TCP Small Queues; the tc-netem manual recommends receiver-ingress placement for
TCP tests. This is a hypothesis until checked. Register four new development
runs (nominal, 1% loss, B congestion, 10 ms reorder) using the same frozen rule,
but move worker-to-switch 100 Mb/s/1 ms shaping to post-segmentation ingress IFBs
for all eight monitored source paths. Remove only their owned host-egress qdiscs;
retain switch-to-worker shaping. Use limit10000 to hold a full framed burst.
Apply the event's loss/reorder to rank2/A IFB; all other IFBs stay zero-loss.
No detector configuration narrows to the known fault. Record all final qdisc
counters and exact commands offline; no host/global security/network settings
change. This is a distinct emulator recipe, not an algorithmic gain.

Expected: identify whether zero-configured-loss alarms remain when all monitored
paths have the same post-segmentation shaping recipe. If they remain, do not
claim this modeling correction solves false positives. Preserve original eight
runs and any ongoing 40 ms stress outcome before beginning the four new runs.

### Ingress setup correction V3

V2 nominal fails before traffic: the original topology gives base netem only to
switch egress; nonfaulted host egress is noqueue. Attempting to delete that root
fails. The other three V2 runs remain unrun. Preserve this setup failure; query
host qdisc state and only remove a real installed qdisc. V3 otherwise uses the
same four configurations and frozen TCP rule. Precisely, equal IFB shaping is
**added** to previously unshaped host-to-switch paths; it does not reproduce an
existing symmetric baseline. Record final switch and IFB drops to audit whether
configured no-loss controls contain queue-induced loss. A zero configured random
loss percentage alone is not proof of zero packet loss.

## Candidate V2 amendment: sparse-loss recall, before new runs

The four valid ingress-V3 development runs complete: nominal/congestion/10ms
reorder have zero alarms, 1% loss confirms at43.485ms. This does not establish
causality for the first recipe's unaffected alarms. The normalized ingress scene
is a distinct symmetric shaping recipe, not an unchanged remeasurement.

For 0.5% loss, demanding two retransmission events can miss a sparse early burst.
Freeze `tcp-loss-v2` before six new development runs: one retransmission event
(rather than two) is sufficient only with the same >=30ms continuous lost/unacked
state, <=15ms gaps and100ms DSACK/reordering veto. No persistence/veto constant
is fitted. Also repair generation reset after a missing read so a replacement
connection cannot inherit the prior connection's reordering veto. Preserve V1
source/config/runs. Tests verify a single event alone cannot bypass persistence.

New development: nominal,0.5/1%loss,congestion,10/40ms reorder, one each; same
four-rank normalized ingress recipe and all-connection monitoring. A40ms stress
false alarm is reported explicitly and is not made into a loss case. If the
primary development cases pass, freeze a prospective100-run campaign:20each
at0.5/1/2/5%loss plus20controls (5each nominal/congestion/pause/10msreorder).
Separately repeat40msstress5times; do not mix it into the declared bounded10ms
reordering population or conceal its result. No tuning on these new campaigns.
The strict all-fault/<100ms/all-control-zero gate is retained and reported.

A host outgoing-connection decision identifies a sender/fabric path, not which
physical access hop dropped a packet. Even if the CPU timing test passes, full
link localization, switch-side placement, idle coverage and realistic GPU/RDMA
validation remain unsolved requirements. Do not claim that all research constraints
are solved by these decisions.

## Candidate V3 amendment and reporting repair, before new runs

V2 development detects1% in85.996ms, but0.5% is late(2488.867ms). Its trace shows
lost=1 at33.9–49.5ms, clears by54.7ms after successful recovery, then another
loss episode appears at70.4ms. Requiring the *same hole* to persist30ms misses
repeated low-rate loss that TCP repairs promptly. Freeze `tcp-loss-v3`: require
at least two recent retransmitted segments within100ms, first evidence age>=30ms,
outstanding data, no feedback veto or sample discontinuity. A cleared lost gauge
alone no longer erases recent evidence; idle data or an expired event window does.
A new candidate begins only with current lost>0 and recent retransmission evidence.
This detects recurring delivery-loss feedback rather than one continuously lost
segment. Keep DSACK/reordering veto100ms and maximum sampling gap15ms unchanged.
It still cannot distinguish arbitrary delayed packets from loss within the deadline.

The0.5% workload's transport integrity passes, but its old rate-sentinel reporting
fails with negative latency because an earlier suspect precedes the pseudo-event.
Repair reporting by preserving all pre-event suspects separately and calculating
post-event latency from the first post-event suspect. Retain first-any timestamp
and total alarm counts. Do not clamp negative times to zero or erase false alarms.
The existing negative-stage-order guard remains for invalid actual sequences.
Preserve the original failed summary; reruns use a new frozen source snapshot.

V3 development repeats nominal,0.5/1%loss,congestion,10/40msreorder. If execution
and primary-control gates pass and loss decisions execute, proceed with the
predeclared100-run frozen validation to quantify sensitivity/tails, even if its
strict all-run gate can fail. This is prospective error measurement, not a claim
that development passed. No tuning or restart of the registered validation.


## Frozen V3 campaigns started

All six V3 development workloads complete with framed transport integrity.
The0.5/1% host decisions arrive at46.257/43.280ms with no other alarm.
Nominal,congestion and10msreorder have zero alarms and no final netem drops.
The40msreorder stress has one false alarm despite zero final netem drops;
the broad development gate fails. As predeclared, primary-control execution
passes and the separate100-run V3 validation starts without retuning.
Twenty independent runs at each0.5/1/2/5%loss and five each nominal/congestion/
pause/10msreorder are registered; five40msreorder stress trials follow.
The40msfailure is retained, not reclassified as a fault or omitted from the
claim boundary. Source,wrapper,image hashes and every attempt are archived.
Kernel netem randomness is uncontrolled; seed20261010 shuffles launch order
only. No paired loss-seed or hardware guarantee is claimed.

## Observer-cost reference registration, before execution

After the frozen detection matrix, run five fresh nominal lifecycles with
tcp_delivery_interval_s=0 and tcp_loss_detector=false, using the same V3source,
container,image,workload and symmetric ingress recipe. Compare completed-round
timing descriptively to the five nominal observer-on validation lifecycles.
These independent trials are unpaired and cannot isolate a causal CPU/logging
overhead. They are not detection trials and must not enter the fault/control
accuracy denominator. Retain any reference failures and raw timing vectors.

## Completed acceptance audit

All100frozen primary attempts complete correctly:72/80timely fault confirmations,
eight late,zero missed,zero other/pre-event fault alarms;20/20primary controls
have zero alarms. Per-loss p95 is408.156/85.219/60.893/48.995ms at0.5/1/2/5%.
The strict deadline gate fails. Five40msreorder stress lifecycles complete, but
three false alarms occur in three runs. Five observer-off healthy references
complete. Replaying2,679,256samples in all105detector-enabled validation/stress
traces exactly reproduces every worker decision. No rule is retuned on validation
and no automatic recovery is enabled. See m7_tcp_loss_results.md for denominators,
source hashes, descriptive timing references and unresolved scope.
