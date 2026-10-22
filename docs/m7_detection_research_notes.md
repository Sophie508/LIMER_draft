# Detection research notes: mechanisms and transfer boundaries

Read on2026-10-10; facts from primary sources are separated from local proposals.
No candidate handles or search summaries are treated as implemented baselines.

## Sources and decisions

**[Fact] RACK-TLP, RFC8985:** TCP uses timestamp/ACK evidence for recovery and
adapts to reordering with DSACK feedback. Transport loss inference does not prove
which physical hop failed. **[Proposal implemented]** Interpret exported Linux
TCP_INFO at the application layer, require recent delivery-loss evidence and veto
new spurious/reordering feedback. This is the frozen M7 candidate, not a claimed
RACK implementation or novel transport algorithm.
https://www.rfc-editor.org/rfc/rfc8985.html

**[Fact] SprayCheck:** Its passive distribution signal depends on packet spraying
and adaptive routing. The existing LIMER slots select planes deterministically.
**[Decision]** Do not port its statistical test without its sampling assumptions;
iteration-based results cannot be substituted for injection-to-host milliseconds.
https://arxiv.org/html/2605.03702v1

**[Fact] R-Pingmesh:** The author PDF describes active service-path probes with
four timestamps to separate network RTT from endpoint processing. It uses ToR
probe structure to distinguish RNIC-related from switch-network anomalies. The
deployed analysis period is20seconds; the paper explicitly groups RNIC, its link
and the adjacent switch port because probes cannot directly distinguish those.
CPU processing delays caused initial false positives. **[Proposal, not implemented]**
If adding idle-path probes, include responder processing time and endpoint-health
corroboration; do not treat a missing echo alone as a link fault. The RNIC timestamp
and RDMA UD mechanisms require hardware absent from the current CPU/TCP experiment.
The20sanalysis is a mechanism reference, not evidence for our100ms target.
https://cs.stanford.edu/~keithw/sigcomm2024/sigcomm24-final858-acmpaginated.pdf

**[Fact] Minder:** The system detects faulty machines using similarity across
workers, persistence and separately denoised metrics. The reported3.6smean is the
time for a call to make an alert, including pulling/processing monitoring data;
it is not our fault-injection-to-link-confirmation metric. **[Proposal, not implemented]**
Cross-worker corroboration could distinguish endpoint stalls, but synchronous
ring dependencies and deterministic A/B slots prevent assuming equal per-port
activity. Its minute-scale fault persistence is not a100ms decision rule.
https://www.usenix.org/system/files/nsdi25-deng.pdf

**[Fact] tc-netem manual:** It recommends receiver-ingress placement for TCP
tests because of TCP Small Queues and lists emulation/timer limitations.
**[Local implementation]** M7 adds symmetric post-segmentation IFB shaping and
retains switch-to-worker shaping. This is a distinct emulator recipe; source
placement corrections and detector changes cannot be pooled as one causal gain.
https://man7.org/linux/man-pages/man8/tc-netem.8.html

## Why faster polling is insufficient

**[Assumption]** Independent random drops with probability0.005, perfect observation,
no delay ambiguity. At least598packets are needed for a95%chance of seeing one
drop, since `1-(1-p)^n>=0.95`. Seeing two distinct independent drops requires947
packets from `1-(1-p)^n-n*p*(1-p)^(n-1)>=0.95`. At100Mb/s and1500bytes each,
947packets need113.64ms even before confirmation overhead. This illustrates the
traffic/recall tradeoff, not a bound for M7: total_retrans can count repeated
transmissions of one segment, and actual packet sizes/activity/feedback vary.

An idle path supplies no passive evidence. A packet delayed beyond the decision
deadline and one permanently lost can produce the same observations before that
deadline. No threshold change can guarantee their physical distinction without
additional information or an explicit delay envelope. The40msreorder failure
provides an empirical reason to keep this boundary visible.

## Next research gate

After the frozen campaigns, diagnose timing tails without tuning the archived
rule. A new candidate needs a new registration and held-out evaluation. Prefer
independent two-ended/link telemetry or processing-aware probes when available,
rather than declaring retransmission a physical fault. Keep100ms as the unmet
target, and cost/execution correctness as connected but separate requirements.
Scope amendment (Sophie, 2026-10-10): the project requires simulation only.
Hardware telemetry access is therefore not a blocking input. Model observation
delay, availability, noise and any probe budget explicitly, and test sensitivity
to those assumptions. Do not substitute the injector's hidden state for an
observation or reinterpret the frozen M7 failure as a simulation success. Real
device validation is outside the agreed scope; see simulation_scope.md.
