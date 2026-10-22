# M6 detection diagnostics: verified results (2026-10-10)

## Outcome and research status

Sophie selected **<100 ms gray-failure confirmation as the primary research
objective**, with route-choice cost and execution correctness retained. Fast
detection remains unresolved. This campaign changes measurement and injector
placement, not the worker/controller implementation; the TCP counter is still
observation-only. It does not produce a new validated trigger.

We first asked why the existing retransmission signal sometimes arrives more than
one second after injection. In all 18 configured-loss traces, reconstructed first
affected rank-2/A step activity starts 17.380–24.227 ms after injection. Idle
application traffic alone therefore does not explain those late signals. Polling
near the first positive sample remains about 20 ms. The step start is reconstructed
from STEP_DONE time minus duration; it is not a per-packet first-drop timestamp.

The interface inventory then finds MTU 1500 with TSO/GSO enabled and GRO disabled
on all 16 veth endpoints. Eight valid capture diagnostics compare original settings
and all-off settings. Original captured IP units reach 37,700 bytes. All-off bounds
observed lengths at 1500, yet the 0.5% run still has no receiver gap until 1253.666 ms.
Turning off device features alone does not establish a per-MTU injector loss model
or solve the latency constraint.

A separate four-run diagnostic redirects switch ingress through a task IFB and
applies loss there after sender segmentation. All-off IP lengths remain <=1500 at
all three captured points. The three loss runs show receiver gaps in 9.198–10.862 ms
and first positive TCP_INFO samples in 19.675–22.384 ms. The healthy run shows neither.
Each condition has only **one exploratory run**. No host confirmation rule executes,
so none is counted as a successful <100 ms detection trial.

## Exploratory observations

Times are injection-completion to first observation, in ms. V4 observes the switch
peer; V5 observes the actual receiver. Configured percentages are distinct recipes,
not measured physical wire-loss rates. V4 and V5 have different fault placements.

| Recipe | Max observed receive IP length (bytes) | First receive gap (ms) | First positive TCP counter (ms) |
|---|---:|---:|---:|
| v4_disabled_l0 | 1500 | none | none |
| v4_disabled_l0p5 | 1500 | 1253.666 | 1268.286 |
| v4_disabled_l1 | 1500 | 125.157 | 136.422 |
| v4_disabled_l2 | 1500 | 64.913 | 82.457 |
| v4_original_l0 | 37700 | none | none |
| v4_original_l0p5 | 37700 | 772.948 | 781.515 |
| v4_original_l1 | 37700 | 77.822 | 88.187 |
| v4_original_l2 | 37700 | 189.953 | 200.388 |
| v5_disabled_l0 | 1500 | none | none |
| v5_disabled_l0p5 | 1500 | 10.582 | 22.328 |
| v5_disabled_l1 | 1500 | 10.862 | 22.384 |
| v5_disabled_l2 | 1500 | 9.198 | 19.675 |

The original 33-run M5 observer results remain valid records of their original
recipe and are not overwritten. V4 is a segmentation diagnostic. V5 changes the
fault model: the original host qdisc keeps 100 Mb/s shaping and 1 ms delay with zero
random loss; switch-facing ingress is redirected to an IFB carrying the requested
loss, with no extra rate/delay. Fault timestamps bracket the actual profile/IFB
setup. The old rate-counter input is upstream of this new injector and does not
localize its loss. Injector counters and packet captures are offline audit inputs;
the controller reads neither.

## Capture validation and preserved failures

- V1: eight process launches fail before topology/workload because of conflicting
  result-directory creation. These are infrastructure failures, not scientific
  workload trials.
- V2: eight workloads finish but capture termination returns a permission error;
  final capture statistics are absent. These traces are excluded from gap inference.
- V3: eight workloads finish with cooperative packet-socket capture, but kernel
  capture losses invalidate the intended loss/sequence-gap audit. No host security
  controls are weakened to fix capture.
- V4: eight workloads complete. Both capture points have startup SYN, complete TCP
  headers, zero kernel capture drops and coverage of the first 100 ms after injection.
- V5: four workloads complete. All three points pass the same checks; framed transport
  integrity and plan consistency pass with recovery disabled.

Captures use an internal eight-second timed window. Last observed packets extend
3.25–4.19 seconds beyond injection in V4 and 3.45–4.08 seconds in V5. Thus they cover
the stated early window, not the entire post-fault workload. Captured-record counts
and tcpdump's received-by-filter counts differ at window termination; zero kernel
drops is not a claim of complete full-workload recording.

The custom header parser is independently checked against native tcpdump over four
selected complete capture files (V4 original 0.5% sender/switch, V5 0.5% sender/receiver).
All 84,317 decoded records agree on timestamp, endpoints, IP length, TCP payload
length and absolute sequence when printed (52,889 sequence fields). This validates
field decoding, not a detection rule or general sequence-gap causality.

TCP_INFO increments precede the first overlapping sequence observed at the V5
sender capture: 19.7–22.4 ms versus 49.9–54.5 ms. Counter sampling and interface
observation measure different stages; the exact queue/attempt explanation is still
unverified. Do not call these two clocks interchangeable or use the difference as
proof of processing latency. V4 sender capture also occurs after its egress qdisc,
so a first dropped attempt may be absent from that capture.

## Mechanism hypothesis and boundaries

**Hypothesis:** netem can apply a loss decision to an enqueued skb before device
transmit validation segments it, so egress device-offload changes alone may leave
loss granularity different from the observed MTU-sized output. Basis: upstream
Linux 6.8 netem enqueue and transmit-validation paths. This is source inspection,
not instrumentation of Ubuntu's compiled kernel skb sizes.

Primary sources:
- https://raw.githubusercontent.com/torvalds/linux/v6.8/net/sched/sch_netem.c
- https://raw.githubusercontent.com/torvalds/linux/v6.8/net/sched/sch_generic.c
- https://raw.githubusercontent.com/torvalds/linux/v6.8/net/core/dev.c
- https://docs.kernel.org/networking/segmentation-offloads.html
- https://man7.org/linux/man-pages/man8/tc-netem.8.html

Do not infer a physical loss percentage from qdisc drop/packet-count ratios where
GSO segments and skbs may have different accounting units. Random-loss draws are
not paired across recipes. Reordering, queue drops, paused demand and clock/observer
costs still need independent controls. CPU/TCP emulation does not prove GPU/RDMA,
numerical reduction, switch-resident resource budgets or hardware latency.

## Next registered work and human decision

Before prospective validation, freeze the observable inputs, activity assumptions,
rule, hold time, startup handling and alarm suppression. Do not tune on held-out
runs or consume injector truth. Keep the primary timer **fault injection completed
→ host-confirmed decision**, and separately report first-signal and route-commit
latencies. Report all registered attempts, misses/censoring and false alarms with
observation-time denominators.

The statistical interpretation of <100 ms is pending a human decision: p95 with
explicit detection/miss rates, or every registered run. The original strict gate
is not silently relaxed. A percentile among only successful detections cannot hide
misses. The formal 20-each loss/control validation remains unrun; the dynamic route
cost matrix and numerical reduction validation also remain unrun.

## Artifact locations

Canonical remote root: `/home/suliu/scratch/LIMER_WORK_2026-10-10` on otakotak.
Raw captures/failures: `mininet_results/m6_packet_*` (server only).
Runtime/config/source hashes: per-run registrations/statuses in `logs/`;
worker/orchestrator/retrans source hashes match the frozen guarded-v1 snapshot.
Diagnostic image: `sha256:f4e2c4b035a76dd44ab1eea827464976ad3caf9210800e832c8169ea939ded2a`.
Private analysis scripts: `baselines/simai_runtime/analyze_m6_packet_audit_v6.py`
and `verify_m6_native_decode.py`; registrations preserve wrapper versions.
Thin local evidence: `/Users/sophie/Documents/LIMER_WORK_2026-10-10/server_summary/`
(`m6_packet_audit_v6.json`, `m6_native_decoder_agreement.json`,
`signal_timing_decomposition.json`, `m6_offload_inventory.json`, V4/V5 summaries).
No LIMER controller code changes in M6. No Git commit/push. No H20 or GPU access.
