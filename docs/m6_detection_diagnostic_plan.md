# Fast gray-failure detection diagnostic implementation plan (2026-10-10)

**Goal:** Keep <100-ms gray-failure detection as the primary research target,
with route-choice cost and execution correctness as accompanying questions.
Current fast detection remains unresolved; no result is relabeled as passing.

**Architecture:** First explain existing signal latency without modifying the
controller. Then record header-only packet observations and segmentation state
in isolated Mininet lifecycles. Compare the original segmentation setting with
an explicitly disabled offload variant. Only observation and emulator settings
change; no packet-derived trigger or injected truth enters the policy.

**Tech stack:** Existing Python/Mininet source snapshot, dedicated rootless Docker,
Linux tcpdump/ethtool from official Ubuntu packages, read-only trace analysis.

## User decision and constraints

Sophie selected detection as the core on2026-10-10, while retaining cost/correctness
research and explicit unsolved status. Continue within existing authorization.
No commit/push; preserve prior logs. otakotak scratch only; no H20 or GPU access.
At most two isolated Mininet lifecycles, four CPUs and four GiB per lifecycle.

## Alternatives assessed

1. Earlier host/socket information: low intrusion, but loss evidence can be sparse
   and retransmission/SACK can respond to reorder or congestion. Explore first.
2. Slot-aligned receiver/port observations: matches the current routing model;
   requires activity and packet granularity accounting. Explore alongside1.
3. Dedicated probes: could provide observations during idle periods, but add load
   and may differ from application traffic. Do not assume they satisfy100ms.

SprayCheck's packet-spraying distribution is unavailable in our deterministic
plane slots. The idea of predictable traffic is useful, but its detector cannot
be transplanted or claimed as reproduced here.

## Step1: Existing timing decomposition

- [x] Analyze all18configured-loss runs. Infer rank2/A step start as STEP_DONE
  timestamp minus duration; label this reconstruction approximate.
- [x] Record first positive counter sample, actual poll interval and host log
  receipt delay. Report injection-to-signal and active-step-to-signal separately;
  keep injection timing primary. Existing traces have no per-packet first-drop
  truth, so absence of retransmission is not proof of absence of packet loss.
- [x] Compare first100ms switch RX byte/packet counts against declared MTU only
  as a clue. Large counted packets suggest batching, not proven fault causality.

## Step2: One topology-only inventory

Change: inventory MTU, offload features, exact Mininet/kernel version and qdiscs.
Expectation: identify whether veth segmentation can change emulator loss units.
Do not alter settings. No traffic efficacy experiment or detector claim.

## Step3: Header-only diagnostic replay, not formal validation

Change: eight exploratory lifecycles, one each for healthy/0.5/1/2%loss under
original settings and tso/gso/gro disabled on all16host/switch veth endpoints.
Use original100Mb/s,2MiB,1warmup/2baseline/8post workload and20mscounter observer;
healthy cases use the matched zero-loss C2 recipe, not the shorter C0 reference.
Recovery remains disabled. No threshold is selected or fitted.

Record tcpdump headers (snaplen128) at w2/A egress and its switch peer, filtered
only to the rank2->rank3 TCP connection. Capture both data/ACK directions. Snapshot
qdisc/feature/capture-drop statistics for offline ground truth; never feed injector
stats to detection. Anchor capture realtime to monotonic with bracketed clocks.
Snaplen128 may retain a bounded prefix of the generated synthetic payload.
No user traffic or unrelated interfaces are captured; analysis uses headers only.

Expected: establish actual observed packet sizes, first receive sequence gap,
retransmitted sequence ranges and counter delay; distinguish no early informative
packet event from slow polling. Healthy comparisons quantify capture/offload costs.
Missing capture, startup errors, truncated headers or kernel drops invalidate the
corresponding diagnostic and are preserved, not treated as zero loss.

## Stop rules and claim gates

- Do not call an earlier receiver gap a detector: reorder/congestion and delayed
  packets can create it. A frozen prospective rule and independent controls remain
  mandatory before formal1/2/5%loss validation.
- Offload changes define a different emulator configuration. They cannot silently
  replace prior outcomes or be represented as a new detection algorithm.
- Do not change the latency origin to first activity in the main100ms result.
  Report conditional activity timing in addition to injection timing.
- Random losses have finite observation probability; all-run empirical100ms gates
  are not universal guarantees. Detection probability and false alarm rate need
  explicit denominators and traffic assumptions.
- If no useful signal exists within100ms in the corrected model, report the failed
  target and prepare the smallest additional measurement/placement requirement.

## Deliverables

Private runtime scripts, exact image/source/config hashes, raw pcaps and failures
on otakotak; thin timing and packet summaries locally. Update paper positioning
and experiment status without rewriting prior evidence. Cost/execution work stays
on its separately registered path; its dynamic three-arm matrix remains unrun.

## Capture startup amendment v2

The first eight launches fail before topology/workload execution: the wrapper
creates the result directory before the orchestrator's exclusive creation.
These are eight infrastructure failures, not eight completed diagnostics. Preserve
all statuses/logs. Fix only directory ownership in the capture wrapper: let the
orchestrator create it. Use a separately named v2 wrapper and registration. Keep
tcpdump at root inside the isolated rootless container to write its mounted task
output; no host account permissions change. Capture/offload settings and loss
recipes remain as registered. No efficacy conclusion follows from this repair.

## Capture lifecycle amendment v3

V2 workloads finish, but terminating tcpdump raises a permission error inside the
rootless environment; capture statistics are unavailable, so those diagnostics
fail the capture-completeness gate. Preserve workload status, nonzero process
exits and raw partial captures. Do not disable host security or change accounts.
Replace only capture lifecycle with a Python AF_PACKET observer on the same two
veths, retaining IPv4/TCP metadata, kernel receive timestamps and packet-socket
drop counts. A shared stop file ends capture cooperatively. No payload is saved.
Record final injector qdisc statistics only as offline diagnostic ground truth.
Use new v3 source/config/run names, and wait for v2 to end before launch. The
controller/source snapshot and loss/offload protocol remain unchanged.

## Capture completeness amendment v4

V3 cooperative observers finish but packet-socket statistics show kernel capture
loss. Reject those traces for loss/sequence-gap inference, retaining their terminal
workload states and settings. Restore libpcap-based tcpdump with an internal
8-second capture window (-G8 -W1), ending without external signals. This includes
warmup/calibration and must be checked to cover the first100ms after injection;
it does not cover the entire post-fault workload. Require zero capture drops,
complete TCP headers and startup SYN, and verify independent decoder agreement.
Run one healthy v4 pilot before expanding the remaining seven. Record v4 status
and original/disabled recipes separately. No security profile is disabled.

## Packet-granularity amendment v5: ingress diagnostic

V4 provides zero-drop capture windows. Original-settings observed IP lengths reach
37,700bytes; disabling TSO/GSO/GRO makes observed IP lengths <=1500 but does not
remove the slow first-gap cases. One disabled0.5%case has firstgap1253.7ms and
firstretranssample1268.3ms. This is not a successful new detection method.

Upstream Linux6.8 netem makes its loss decision on enqueued skbs; device transmit
validation may segment after qdisc dequeue. Thus offload settings alone do not
prove a per-MTU Bernoulli loss model. This is a source-backed mechanism hypothesis,
not a trace of the Ubuntu kernel's internal skb sizes.

The owned rootless namespace supports IFB creation without host account/module
changes. Register four exploratory v5 runs: healthy/0.5/1/2%loss, one each. Disable
host/switch TSO/GSO/GRO as before. Keep host/switch100Mb/s shaping and1ms base delay.
Redirect sA-eth3 ingress to a task IFB; apply loss there after sender segmentation,
with no additional rate/delay. This changes injector placement and packet model;
retain it as a distinct diagnostic, not a replacement of prior evidence.

Capture sender and receiver-w3 A headers and IFB-egress headers with timed libpcap;
verify IP lengths <=1500 at the loss-stage egress, capture drop counters, startup
SYN and coverage of the first100ms after injection. Record actual IFB netem setup
and timestamps plus final counters only for offline audit. Controller consumes
no IFB/qdisc/capture data. One healthy pilot precedes the remaining three; failures
remain explicit. The old upstream rate-counter input remains unchanged and is not
claimed to localize this alternative injection position.

Expected: resolve measurement granularity and then assess when packet sequence
holes become observable. No fitted threshold, false-alarm guarantee, physical
hardware claim or validated100msdetector follows from these four launches.

Primary mechanism sources:
https://raw.githubusercontent.com/torvalds/linux/v6.8/net/sched/sch_netem.c
https://raw.githubusercontent.com/torvalds/linux/v6.8/net/sched/sch_generic.c
https://raw.githubusercontent.com/torvalds/linux/v6.8/net/core/dev.c

## Verification result

See m6_detection_diagnostic_results.md for all terminal states, valid capture
windows, decoder checks and unresolved interpretation boundaries. Twelve valid
exploratory workloads finish (eight V4, four V5); no formal detection claim passes.
The statistical acceptance criterion awaits human choice.
