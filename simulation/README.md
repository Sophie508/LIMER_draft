# Two-ended observation experiments

This directory contains an isolated ns-3 signal experiment for LIMER. It does
not run a collective or reroute traffic. Rank/fabric labels identify eight
independently monitored one-hop streams; they do not create a training topology.
The pinned modified ns-3 backend provides the packet network. Source UDP
acceptance includes subsequent queues in the observed delivery interval.

The serialized batch/sequence header occupies 12 bytes of each 1500-byte wire
packet. The backend's PPP header is 14 bytes. Counter reports use a separately
modeled FIFO with 64 bytes per report, 1 Mb/s service and 5 ms propagation;
they are not sent on the monitored data paths. Clock synchronization and
complete local counters are model assumptions. Report loss and excess delivery
delay are explicit stress cases. JSON files are an export of observations,
not their modeled wire encoding.

## Reproduce on the owned CPU server

Use `/home/suliu/scratch/LIMER_WORK_2026-10-10` as the private workspace root.
The existing pinned backend and `limer-simai-cpu:2026-10-10` image must already
be present. The rootless Docker socket is
`unix:///run/user/1005/limer-docker/docker.sock`.
Run the campaign driver and the full LIMER tests on the server's Python 3.12
host runtime. The backend image's Python 3.8 can execute the isolated observation
code, but cannot import several existing LIMER modules. The test suite uses
`unittest`; no pytest installation is required.

```bash
python3 simulation/build_batch_observation.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10

python3 simulation/run_batch_observation.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10 \
  --campaign development --tag reproduction
```

Build uses `m8_backend/simulation`, an isolated copy. The CMake amendment links
core, network, internet, point-to-point and MTP, plus the pinned
`simple-seq-ts-header.cc` required by the modified point-to-point library.
It does not require the original all-module scratch target dependencies.

The runner writes an immutable registration before launching any attempt and
refuses an existing output directory. Eight development, 200 primary validation
and 25 stress attempts are distinct ledgers. Tags prevent overwrite; tags alone
do not create fresh random realizations. The fixed seed ranges are 1000+ for
development, 10000+ for validation and 20000+ for stress. Reusing those ranges
is a reproduction, not new independent/held-out evidence. A changed candidate
requires newly registered seeds and its own frozen source.

## Audit and evidence

Every valid attempt has `reports.jsonl`, `truth.json`, `status.json` and a process
log. The detector consumes only `reports.jsonl` with the exact schema:
`path,batch,side,count,sample_t_ns,arrival_t_ns`. Fault rate, path and timing
exist only in scorer metadata. Counter pairing does not read error callbacks.

Process success is an engineering gate. The scientific gate additionally needs
all registered fault attempts below 100 ms, no counted control alarms and complete
valid reports. Nondetections remain in p95 as infinity. Scoring includes alarms
before injection and on every unaffected path. The fixed `batch-loss-v1` rule
clears accumulated history after two active zero-deficit batches, including
before confirmation; this conservative reset can impair sparse-loss recall.

The receive error hook can defer a selected packet and deliver its tagged copy
later. An internal PhyRxDrop callback can fire on that initial deferral; it does
not prove permanent loss. Audits instead verify final source/destination counts,
unique sequence identity, actual serialized packet lengths and explicit permanent
drop counts. Do not reuse this toy UDP conservation gate as a claim of tensor,
framed-TCP or coordinated-cutover correctness.

`audit_batch_campaign.py` recomputes decisions and scores from the frozen report
inputs after both primary and stress campaigns are complete. It checks archived
input, source, binary and shared-library hashes. See
[`../docs/m8_batch_observation_plan.md`](../docs/m8_batch_observation_plan.md)
for the prelaunch plan, development setup failure and model amendments.

## Scripted dynamic pending-flow gate (M9)

`LimerDynamicDagReplay.cc` uses the same pinned SimAI RDMA frontend but posts one
receive on the committed plane at flow launch. The flow retains its ports and
version until both completion events. Only affected unlaunched A flows can move
to B. Control requests are scripted; there is no online detector in this target.
Its reliable modeled management FIFO is separate from the data network and
charges PREPARE, READY and COMMIT bytes, serialization and propagation. Common
activation requires all ranks' readiness and commit delivery.

```bash
python3 simulation/build_dynamic_dag.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_dynamic_dag_gates.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --tag reproduction
```

The isolated `m9_backend/simulation` build preserves prior binaries. The runner
registers nine expected outcomes before launching, refuses an existing tag and
stops on the first unexpected outcome without discarding it. Eight completed
workloads and one expected invalid-version rejection pass the original `v1`
campaign. `audit_dynamic_dag.py` independently checks launch ownership,
endpoint-aware dependencies and charged control service. See
[M9 results](../docs/m9_dynamic_execution_results.md). Workload completion and the
full control lifecycle have separate timestamps; a late commit may change zero
flows. This gate does not validate numerical reduction or rescue of launched,
stalled work.

## Native online progress and route-choice loop (M10/M11)

`LimerProgressDagReplay.cc` samples sender ACK credit and evaluates the fixed
`AckProgressRule` inside report-delivery callbacks. It has no route actuation.
`LimerClosedLoopReplay.cc` adds charged queue summaries, prescribed workload
release times and an observable pending-work service heuristic. Its selected
requests use the same M9 transaction and immutable launched-flow ownership.
Unknown/stale B service selects stay. The rule and policy are independently
reconstructed by Python auditing, rather than importing an offline alarm.

```bash
python3 simulation/build_progress_dag.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_progress_development.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --tag reproduction
python3 simulation/build_closed_loop.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_closed_loop.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --tag reproduction
```

Builds use separate `m10_backend/simulation` and `m11_backend/simulation` copies.
The M10 current source implements the v2 configured-NIC/DCQCN restoration
model; its earlier device-only v1 source and control alarm remain archived.
M10 reports are 64 bytes; M11 additionally reports queue work and charges 96.
Both use separate reliable modeled management service, not packetized sharing
with the monitored network. These deterministic experiments include a 120-ms
report-delay deadline failure and harmful switching with a slow B alternative.
See [online results and full limitations](../docs/m10_m11_online_results.md).
No numerical reduction, weak-loss guarantee or rescue of launched stalls is
established by these gates. Do not rerun these tags as fresh held-out evidence.

## Hybrid delivery detection (M12)

`LimerHybridObservation.cc` adds continuous same-socket, same-queue 64-byte
wire probes and native delivered-report decisions to the isolated UDP model.
The mature lane keeps the M8 rule; the early lane compares two consecutive
10-ms delivery-service windows with BOTH cumulative endpoints sampled at
closure+10 ms. Exported `guard_ns` selects the configured lane. The exact
seven-field observable schema is
`path,batch,side,count,sample_t_ns,arrival_t_ns,guard_ns`. Fault truth is scorer-only.

The M12 collector is separate from data traffic: one 10-Mb/s FIFO, 1-ms
propagation, three independently lost 64-byte copies per sample. All copies
consume service, including lost copies. Probe cost is 17.92 Mb/s/path; reports
cost 307.2 KB/lifecycle and 4.9152 Mb/s steady collection traffic. These are
charged model costs, not zero-cost telemetry or a standardized RFC protocol.

```bash
python3 simulation/build_hybrid_observation.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_hybrid_observation.py \
  --root /home/suliu/scratch/LIMER_WORK_2026-10-10 \
  --campaign development --tag reproduction --workers 4
```

The corrected build uses an isolated `m12e_backend/simulation`, touches staged
source using the server clock and verifies native v4 rule strings. Existing
output tags are refused. The published v4 development uses 34000+, primary
validation 41000+, boundaries 51000+, and a separate matched selective-fault
supplement 52000+. Replaying those fixed ranges is reproduction, not fresh
held-out evidence. Register new ranges before changing or validating a candidate.

The final primary ledger has 740 complete/audited lifecycles: 698/700 timely
fault decisions, two late, no misses and 40 controls without alarms. Every
registered eligible condition passes the empirical >=95% target; the original
all-trial/no-unavailable-report strict gate separately remains FAIL. Report
loss is unknown, never a zero receiver count. Independent auditing checks
native replay, source/binary/library/input hashes, FIFO service and wire counts.

Size-independent IID fault coverage is a model assumption. Same-path probes
can still miss business-only damage: a 20-pair size-selective supplement gives
20/20 timely IID alarms versus 5/20 selective alarms with matched business-loss
counts. No-probe idle and slow-report boundaries also retain failures. This
is not an RDMA collective, route actuator, numerical reduction or validated
joint detection/switch/stay system. See [M12 results](../docs/m12_hybrid_detection_results.md).

## Class-separated business observations (M13)

M13 is a separate candidate. M12 source, binaries and published verdicts are
preserved. It adds independently counted business/probe progress and receiver
sequence-gap ages; a 40 ms gap guard complements the frozen M12 baseline and
business-only aligned early service windows. A gap starts when a higher packet
sequence actually arrives, and closes when its missing packet arrives. This
signal does not prove permanent loss.

Reports carry the seven M12 fields plus `data_count`, `probe_count`, `data_gaps`,
`probe_gaps`, `data_gap_age_ns`, `probe_gap_age_ns`. Native decisions and Python
replay accept only these observable fields. Payload encoding is audited as
68 bytes; the modeled collector charges 20 IPv4 + 8 UDP + 68 payload = 96 bytes
per copy, without a link-layer header. It is an abstract serialized collector,
not a second packet-network topology. With 4800 copies this costs 460.8 KB per
lifecycle and 7.3728 Mb/s at steady state. The eight monitored paths use 1500-byte business wire packets. Registered
probe interventions include 64-byte/35000-pps probes, 1500-byte probes at
the same nominal byte budget, constant 1500-byte/35000-pps probes and
causal traffic compensation. Every actual packet is charged.

`packet_events.csv` exports local source acceptance and actual application
receipts in event order. The audit independently reconstructs every sampled
class counter, sequence gap and gap age. Neither this audit export nor private
fault configuration/drop counters are detector inputs. Application-only loss
and delivery deferrals are separately modeled; small probes bypass that
application stage. A simulation does not establish GPU/RDMA or collective
recovery correctness.

```bash
python3 simulation/build_business_observation.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_business_observation.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --campaign development --tag reproduction --workers 8
```

The current builder uses isolated `m13e_backend/simulation` for the adaptive
policy; all earlier m13/m13b/m13c/m13d backends and immutable frozen sources
remain on otakotak. `probe_budget.h` computes each wave from the last CLOSED
10 ms accepted-business-TX count only, with a 25000-pps total target.
`probe_waves.csv` and actual packet events independently verify every causal
input and probe timestamp. After startup, high-rate business may require
no steady probes; a pause can temporarily increase probes, and its costs
are charged. Probe size/treatment and a 10 Gb/s capacity are explicit
assumptions, not repairs of the old low-budget failures.

```bash
python3 simulation/build_business_observation.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10
python3 simulation/run_business_observation.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --campaign adaptive_development --tag reproduction --workers 8
python3 simulation/run_business_observation.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --campaign adaptive_validation --tag reproduction --workers 8
python3 simulation/audit_business_campaign.py --root /home/suliu/scratch/LIMER_WORK_2026-10-10 --frozen m13_source_frozen_adaptive_validation_v1 --campaign m13_adaptive_validation_v1
```

Development must pass before unchanged-source held-out validation. For
published evidence, use the immutable source named by each registration,
not the current working tree. Adaptive primary validation is frozen before
adding the separate high-traffic control campaign option; detector, native
source, policy and binary remain identical. A new tag only avoids overwriting
output: fixed RNG ranges are reproductions, not fresh validation. Register
fresh IDs for another candidate or acceptance run.

Ranges: interrupted setup 60000+, corrected small-probe development 62000+
(failed, so its 63000+ validation was not launched), representative-byte
comparison 66000+, constant-budget development/validation 67000+/68000+,
adaptive development/validation 70000+/71000+, high-traffic controls 72000+.
The setup interruption retains the 80 ms delay mistakenly labeled sparse
40 ms. Corrected source exports actual parameters and rejects mismatches
against registration. See [measured outcomes and limits](../docs/m13_business_detection_results.md)
and [the plan](../docs/m13_business_detection_plan.md).
