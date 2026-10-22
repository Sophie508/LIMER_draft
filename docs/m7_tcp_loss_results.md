# M7 prospective passive host loss confirmation

Status: implementation, six V3 development lifecycles and all100frozen primary
validation attempts verified. All five stress and five observer-off references are also terminal. Bulk evidence stays on otakotak scratch. The primary100msgate FAILS.

## What changed and why

The user requested an implemented candidate for the unresolved <100ms gray-fault
target, with autonomous literature review and code repair. Reading RFC8985 and
the Linux TCP_INFO UAPI led to a passive host rule that uses transport feedback
rather than waiting for a complete collective step. This application-level rule
interprets Linux recovery state; it is not a new implementation of RACK-TLP.
SprayCheck's per-spine packet-spraying distribution is unavailable in the current
deterministic slot-routing topology, so that mechanism is not silently imported.

The worker samples every outgoing A/B connection continuously at a nominal5ms,
from startup. The sampler brackets each native TCP_INFO read, records its actual
completion timestamp, requires the independently checked224-byte Linux prefix,
and reports missing reads explicitly. Its candidate decision is timed separately
from the orchestrator's log receipt. Injector timestamps and known fault location
are used only for offline scoring, never to arm or feed the rule.

The frozen `tcp-loss-v3` rule requires at least two recent retransmitted segments
within100ms, outstanding data and first loss-evidence age>=30ms. A new DSACK or
reordering feedback event vetoes confirmation for100ms. Missing reads, sample gaps
>15ms, connection replacement, counter discontinuity or clock regression clear
evidence; idle connections and expired evidence cannot confirm. A repaired loss
gauge alone no longer clears evidence of repeated loss. There is at most one
alarm per connection generation. This property does not establish repeated
episode detection on a persistent connection; reset/rearm requires separate work.

The worker/config/CLI integration is opt-in and defaults off. High-rate observation
events are logged but excluded from command-response wait queues. Enabling this
experimental decision together with automated recovery is rejected. The payload,
framing and existing cutover semantics are not changed by this candidate.

## Development results and preserved forks

The original V1 scene monitors all eight outgoing connections but shapes only the
faulted worker-to-switch ingress, retaining the topology's switch-egress shaping.
The one1/2/5%loss development trial per level confirms at50.976/44.047/40.239ms.
However, nominal produces six false alarms, congestion one,10msreorder one and
40msreorder one. This broad gate fails; a few fast fault decisions are insufficient.

A separate symmetric scene adds100Mb/s,1ms,limit10000 post-segmentation ingress
shaping to all eight worker-to-switch paths, retaining switch-to-worker shaping.
All sixteen veth offloads are disabled. This changes the emulator model rather
than demonstrating an algorithm-only gain. The first attempted setup fails before
traffic because a noqueue root is removed; its other three trials remain unrun.
After correcting that setup, four fresh V1 lifecycles complete: nominal,congestion
and10msreorder have zero alarms and zero final netem drops;1%confirms at43.485ms.
Those observations do not prove the cause of the original unaffected-flow alarms.

V2 reduces the recent retransmission threshold to one while retaining a continuous
30ms lost gauge. Its0.5%decision is2488.867ms late because successful TCP repair
repeatedly clears the gauge;1%confirms at85.996ms. The0.5%transport integrity check
passes but the legacy rate-sentinel summary fails on a pre-event suspect timestamp.
V3 repairs reporting by retaining pre-event suspects and computing post-event
latency from the first post-event suspect. It does not clamp invalid stage times.
The old failed summary remains archived. V2 also produces a40msreorder false alarm.

V3 restores the threshold to two and allows repaired holes between repeated loss
events. All six development lifecycles complete with framed transport integrity:

| Condition | Correct path confirmation | False alarm events |
| --- | ---: | ---: |
|0.5%random loss|46.257ms|0|
|1%random loss|43.280ms|0|
|Nominal|not applicable|0|
|Paced B congestion|not applicable|0|
|10ms A reordering|not applicable|0|
|40ms A reordering stress|not applicable|1|

The40msfalse alarm occurs about40.165s after the pseudo-event, not during startup.
At decision time, total_retrans has advanced by two within the current evidence
window, with two kernel-lost packets and nine outstanding. DSACK/reorder counters
are not advancing at that time. Its final netem drop counters are zero. Suppressing
warmup alarms would not repair this failure. This result blocks a broad causal
fault-detection claim and automatic route-control integration.

## Registered acceptance and denominators

The frozen prospective campaign consists of20new lifecycles each at0.5/1/2/5%
random loss and5each nominal,50Mb/s B congestion,250ms round pause and10ms A
reordering. All paths are observed continuously. The workload has four ranks,
framed2MiB chunks,one warmup,two baseline andfour post-event rounds; recovery is
disabled. Launch order is shuffled with20261010, except the first nominal
infrastructure gate. This is an order seed, not a kernel loss seed. Kernel netem
draws are uncontrolled and trials are independent/unpaired.

The primary operational metric is correctly localized host confirmations below
100ms divided by **all80registered fault attempts**, accompanied by per-condition
miss/late counts and95%Wilson descriptive intervals. The timer starts when the
injector command completes and ends at the worker's actual decision. Target path
is rank2/A only for offline scoring; any alarm before injection or on another path
is counted as false. Control alarms anywhere in the full observation lifetime
count, including before their pseudo-event. Missing or failed attempts cannot be
removed from the success denominator. Incomplete observations must be identified
separately from verified zero-alarm controls.

P95 uses the nearest-rank order statistic `ceil(0.95*N)`, with nondetections as
infinite delay. Conditional finite delays are reported separately. Consequently,
95fast decisions and5misses in100fault trials can pass p95 while failing the
strict every-trial requirement. Both the timely fraction and the original strict
all-fault/<100ms/no-false-alarm verdict are reported; no hidden relaxation occurs.

Five fresh40msreorder trials are separately registered as stress tests, and five
healthy observer-off references compare timing descriptively with the five
nominal observer-on validation trials. Neither set enters the primary fault
denominator. The controls and stress results must all remain visible. No retuning
is allowed on these campaigns; a changed rule requires distinct validation.

## Completed prospective primary validation

All100registered attempts are terminal and complete with framed transport
integrity. There are80faults:72correctly localized confirmations below100ms,
eight late decisions and no missed detections. No fault-trial alarm occurs on
an unaffected path or before injection. All20primary controls have zero alarms.
Source,wrapper and image hashes are constant across the entire matrix.

| Configured loss | Timely / all trials | Late | Missed | P95 | Observed range |
| --- | ---: | ---: | ---: | ---: | ---: |
|0.5%|14/20|6|0|408.156ms|39.827–414.772ms|
|1%|19/20|1|0|85.219ms|41.669–105.319ms|
|2%|19/20|1|0|60.893ms|39.629–111.644ms|
|5%|20/20|0|0|48.995ms|40.072–73.071ms|

Pooled p95 across80faults is121.439ms. The all-trial gate isFAIL. The1/2%rows
illustrate why an empirical p95below100msdoes not mean every trial meets the
deadline. Zero missed detections over the completed observation lifetimes does
not erase late decisions. The0.5%timely rate is70%(95%Wilson interval48.1–85.5%);
1/2%are95%(76.4–99.1%);5%is100%(83.9–100%). Small samples do not prove a
universal deadline or true95%reliability.

## Stress, timing references and replay verification

All five separately registered40msreorder lifecycles complete with transport
integrity, but three produce one false confirmation each:3/5false-alarm runs
and three events over208.601observed lifecycle seconds(1665.668connection-seconds).
All final netem drop counters are zero. The20primary controls observe178.437
lifecycle seconds(1417.247connection-seconds) with zero alarm events and zero
final netem drops. Their zero observed false-alarm rate has a95%Wilson per-run
interval of0–16.1%, not proof of a zero true rate. Stress and primary controls
have different observation lifetimes and must not be compared as equal exposures.

The primary matrix has2,362,364available samples,zero unavailable reads and zero
sample gaps above15ms. At least one late trial does not show a new retransmission
or nonzero kernel-lost gauge until179.456ms; other late trials have first evidence
at21.7–94.8ms but fail to accumulate/sustain the frozen decision conditions soon
enough. No new DSACK/reordering-counter feedback precedes any of these eight late
decisions. This posthoc timing diagnosis does not retune the validation rule or
prove actual physical drop times. Faster polling alone cannot establish timely
confirmation from a required signal that arrives after the deadline.

All105primary-plus-stress traces are independently replayed from their archived
TCP sample inputs:2,679,256samples reproduce every actual worker decision exactly.
This verifies decision/log consistency, not physical fault accuracy. The sampler/
rule source hash is45b8d59994bb560674726228a924f87445bfdb1319a3691e30d544d4666f6f1a.

Five observer-off healthy references complete correctly. The median of five
independent per-run baseline round medians is1.105678s
with observation and1.106965swithout it, ratio
0.998837. These are descriptive unpaired timings, not a causal
CPU/logging overhead estimate or evidence that observation accelerates traffic.

## Evidence and scope

Linux frozen source passes232Python tests, including actual extended TCP_INFO
loopback reads, state discontinuities and the pre-event alarm reporting regression.
Local macOS execution passes232tests with three Linux-only skips. Unit/runtime
tests establish implementation behavior, not statistical fault-detection accuracy.

Server root: `/home/suliu/scratch/LIMER_WORK_2026-10-10`.
Frozen source: `limer_source_m7_tcp_v3`; prior V1/V2 sources are retained.
Inputs/statuses/configurations/wrapper and image hashes are under `logs/` and the
source's `configs/m7_*`; event traces and final switch/ingress qdisc audits are in
`mininet_results/m7_*`. The owned rootless diagnostic image is
`sha256:f4e2c4b035a76dd44ab1eea827464976ad3caf9210800e832c8169ea939ded2a`.
At most two fourCPU/fourGiB Mininet lifecycles run concurrently. NoGPU/RDMA result
or host hardware detection is represented by these measurements.

The candidate identifies a sender/fabric TCP path, not the physical hop or failure
cause. It does not detect an idle path with no packets, prove switch-resident
placement, guarantee arbitrary delayed/reordered traffic discrimination, detect
pure rate reduction through its loss predicate, or validate numerical AllReduce.
The broader100msgray-fault constraint, route-cost comparison and execution-proof
requirements remain separate research work. An empirical pass in a bounded
emulator cannot establish a universal guarantee.

Primary sources:
- https://www.rfc-editor.org/rfc/rfc8985.html
- https://raw.githubusercontent.com/torvalds/linux/v6.8/include/uapi/linux/tcp.h
- https://arxiv.org/html/2605.03702v1
- https://man7.org/linux/man-pages/man8/tc-netem.8.html
