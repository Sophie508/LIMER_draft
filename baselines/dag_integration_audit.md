# Single-straggler OptCC DAG integration audit

Date: 2026-10-10. Read-only audit of SimAI commit `f5efb5a93ea9be7db25a8843f9f7ff54044f6062` and archived OptCC `single_straggler.cpp`, README, and `optcc_checks/single_L2/dag.json`. No simulator execution or code modifications were performed in this audit. Paths below are relative to `baselines/SimAI-official/` unless otherwise stated.

## Decision

An importer that merely turns JSON nodes into `SingleFlow` objects is insufficient. The stock `NcclTreeFlowModel` is an executor specialized to NCCL ring/tree dependencies and receive registration; it cannot execute this DAG faithfully without an explicit OptCC branch or dedicated algorithm executor. The missing author integration means a reconstructed runner must be labeled as our reconstruction, not the exact artifact used for the paper. Packet-level performance is not yet validated.

Recommended first integration: one DP group, one GPU per server, one network channel, single AllReduce, no PXN/NVLS, explicit workload N and k/L, positive control-message size, endpoint-aware dependency propagation, flow-specific receive tags, all receive events registered before launch. Preserve the unmodified official ring path for comparison.

## Source and rank mapping

The generator uses logical server IDs `1..p`, with server `p` the straggler; there are no ID-0 flows. Map logical ID i to `GroupInfo.Ranks[i-1]`, never blindly `i-1` for arbitrary noncontiguous DP groups. Require `p == group.nRanks == group.nNodes`, one GPU per node, all endpoints in the group, no self-flow, and actual topology wiring matching the chosen straggler rank. Slowdown L means degraded NIC bandwidth to approximately healthy/L, not packet loss.

The sample is p=5, k=4, L=2.0; 132 nodes, 40 sync nodes and 92 data nodes. Four DAG roots are IDs 1 (1->2), 4 (2->3), 7 (3->4), 13 (5->1). There are 255 deduplicated dependency edges: 128 incoming-parent edges and 127 same-sender-parent edges. No edge in this sample needs a notification at a third rank. Maximum indegree is 4. Recheck this invariant for every generated p/k/L, especially bubble cases.

`SingleFlow` is declared in `astra-sim/system/MockNcclChannel.h:25`, fields ordered: flow_id, src, dest, flow_size, prev, parent_flow_id, child_flow_id, channel_id, chunk_id, chunk_count, conn_type. `FlowModels` keys are `(channel_id, flow_id)` in `MockNcclGroup.h:38`. Create a bijection from generator IDs to newly allocated global `g_flow_id` IDs and apply it to every parent/child list. Compute children by reversing deps, deduplicate, and validate acyclicity. `MockNcclGroup.cc:281` caches by group/layer/loop state/op/data size; incorporate DAG mode and schedule parameters in a new cache key or guarantee one immutable mode per process. Reusing cached flow IDs across simultaneously live invocations needs an invocation-specific tag namespace.

## Bytes: JSON alone is not enough

`single_straggler.cpp:721-741` serializes p/k/L, id/src/dst/type/body/chain/deps, but no N and no `sz`. N must come from the actual workload and be written to a sidecar run manifest. The fourth command argument B is overwritten in main (`:763-772`). The generator computes base section bytes:

- L >= 2: s = N / [k(p-1)].
- 1 <= L < 2: s = NL / {k[(p-2)L+2]}.

The ideal type-dependent data sizes following `generateFlows` and `flowDuration` are:

| Node | Ideal payload |
|---|---:|
| Healthy ring, single label A1/C3 etc. | s |
| Healthy ring, merged label C1B1/D1B3 etc. | 2s |
| S2 up/down at head or tail | s |
| S2 up/down middle body, L >= 2 | s |
| S2 up/down middle body, L < 2 | 2s/L |
| bub_up / bub_dn | s(2-L)/L |
| sync | Explicit control bytes; see below |

These are payload bytes, not bandwidth-normalized durations. Do not multiply S2 bytes by L; the topology slowdown supplies that factor. The code's internal `sz` uses normalized 1000/2000 and truncates middle/bubble weights to integer for L<2, but critical-path analysis uses ideal floating expressions. Its JSON omits these weights, so the author integration's choice of scaling/rounding cannot be established from the archive.

For N=9000, p=5,k=4,L=2, s=562.5 bytes. Using literal normalized sz=1000 or interpreting CLI B=1000 as real bytes would simulate a different tensor size. Use a declared deterministic rounding/partition rule, report payload totals and rounding error; initially use exactly divisible synthetic N where possible. Avoid zero data edges for very small N or L approaching 2 from below. Merely rounding independent edges does not prove collective data semantics: tensor/segment provenance is absent from JSON. Completion of the dependency graph is a scheduling validation, not a proof that a real AllReduce reduces every element exactly once.

## Dependency notifications require two endpoint events

For dependency parent P -> child C, classify by C.src:

1. C.src == P.src: release on **parent send completion** (serialization/resource order).
2. C.src == P.dest: release on **parent receive completion** (data availability).
3. Otherwise: reject or add a specified explicit synchronization notification; never silently release at either endpoint.

At each endpoint callback, filter the reversed child list to children originating at that endpoint, verify the exact parent ID, consume each `(parent,child)` edge once, and enqueue a child only on transition indegree 1->0. Deduplicate sender and receiver completions separately. The sample's 127 same-sender edges include per-server send chains and parents of sync messages. They are not redundant: eliminating them changes the intended serialized NIC schedule.

Stock behavior in `collective/NcclTreeFlowModel.cc`:

- Constructor `:77-98` retains only flows touching this rank; a self-flow would violate its duplicate assertion.
- `init_indegree_mapping :131-139` indexes outgoing indegrees by flow ID alone, so IDs must be globally unique across channels.
- `PacketReceived :152-236` decrements children and asserts that the child is locally represented. Sending the entire unfiltered child vector to the receiver is invalid when children originate at the sender.
- `PacketSentFinshed :271-294` releases packet counters/QP queues but does not release DAG dependency children.
- `assert(flow_exist = true)` around :235 is an assignment, not a validation. An external graph/trace checker must catch absent children.

Implement source/destination propagation explicitly in an OptCC-only path, leaving the native ring semantics intact.

## Receives, tags, prev, and chunks

The native `prev` field is a vector of **rank IDs to receive from**, not a vector of predecessor flow IDs. Native `insert_packets :461-490` unconditionally reads `prev[0]`, including for roots; an empty vector crashes. Do not put same-sender parents into prev, which would create self receives. A harmless nonempty placeholder can satisfy native packet construction only if the entire native receive logic is bypassed; a dedicated executor avoids this workaround.

Native receive registration is not general DAG registration. `init_recv_ready :297-330` preposts receives only using outgoing chunk-0 flows' prev and parent lists. `recv_ready :333-363` uses the outgoing child's `flow_size`, which need not equal its parent's size. `ready :527-567` posts later receives using the current send packet size and NCCL chunk-dependent tags. With merged ring, S2 and sync edges these sizes differ. Prepost exactly one receive for **each incoming flow**, using that flow's source, own payload length, and unique tag. Register all incoming flows before any root sends. Buffering of early arrivals is supported by the frontend, but it stores only one pending flowTag per `(receiver,sender,tag)`; reused tags can overwrite flow identity.

In `ready :545-575`, native tags are `layer*chunk_count*m_channels + channel*chunk_count + chunk_id`, with an extra +1 for certain non-RING receive registrations. Marking conn_type RING avoids that +1 but does not solve collisions. All imported flows at chunk_id=0 in channel 0 share a tag, while using flow ID as chunk_id prevents native root launch (`StreamInit :244-266` starts only root chunk-0 flows). `chunk_id` also drives per-peer queue sequencing. The schedule's body index and chain pattern are not NCCL chunk IDs.

Recommended imported fields: one channel_id=0; flow_id globally unique; chunk metadata treated as importer metadata, not execution order (e.g. chunk_id=0,chunk_count=1 under a bypass branch); conn_type="OPTCC"; explicit per-flow tags and invocation ID independent of chunk values. Keep `m_channels=1` in the new constructor/path; normal ring's channels.size() must not accidentally override it. Alternatively assign each flow a channel and initialize m_channels accordingly, but that falsely models hundreds of channels/queue domains and is not recommended for faithful performance comparisons.

Both sim_send and sim_recv matching use tag + src/dest in `network_frontend/ns3/AstraSimNetwork.cc:107-205`. `sim_recv` specifically replaces the tag argument with callback ehd.flowTag.tag_id. Setting only request.tag or the sim_recv argument is insufficient. Initialize every required flowTag field for both callback objects. Copying the shared request flowTag to receive data incorrectly can turn current_flow_id from -1 before the frontend assertion; create receive placeholders with current_flow_id=-1 and let the transport fill the actual sender flowTag.

## Synthetic sync nodes and zero-byte danger

The generator creates sync nodes with `sz=20` (`single_straggler.cpp:386-482`), but assigns them zero analytic duration (`:554`). Therefore the source supports small control messages in an implementation and zero-cost synchronization in analytic accounting; the missing integration does not establish author-selected wire bytes.

Use an explicitly documented positive control payload (e.g. the generator's 20 bytes), with both sender and receiver expecting the identical value. Preserve sync dependencies and endpoints. These transmissions incur headers, serialization, routing, and AS_SEND_LAT; distinguish the resulting packet-level latency from the analytic zero-sync result and run a control-size sensitivity check. A separate zero-cost scheduler event is acceptable only as a labeled analytic/idealized mode, not a packet-level control-message reproduction.

Zero-byte sends are unsafe in this pinned backend. `network_frontend/ns3/entry.h:136` changes a zero per-QP payload to 1, while sentHash keeps original count 0. `send_finish :347-371` accumulates q.m_size=1; `notify_sender_sending_finished :239-276` requires exact equality, logs mismatch, and does not fire the callback. Thus the sender may never finish. The receive-side count arithmetic also no longer matches original sizes. A zero message is not an instantaneous synchronization primitive here.

## Backend callback issue that can invalidate same-sender dependencies

`ns-3-alibabacloud/simulation/src/point-to-point/model/qbb-net-device.cc:619-626` schedules SendCallback for packets with wire size <9000 and >60; the switch-as-host path repeats it at :666-673. `SendCallback :584-590` calls RdmaHw::SendPacketComplete with the packet header. `rdma-hw.cc:391-412` looks up the QP and triggers whole-flow send callback without checking `seq + payload == m_size`. `entry.h:347-371` then reports the entire QP size.

This approximates a last short packet under 9000-byte payload MTU. It can prematurely mark a long flow sent when smaller MTU makes every data packet short, and may omit the callback when a flow ends on a full-size packet. Default config has PACKET_PAYLOAD_SIZE=9000. This is a static-source risk, not a measured failure here. OptCC's same-sender chains make this timing especially consequential. Before performance runs, test exact MTU multiples and smaller MTU, and verify callbacks at the actual final packet serialization. Any fix should affect both baseline and OptCC equally and be documented as a simulator repair. Alternatively release same-sender edges on ACK-complete QP events in a explicitly labeled conservative mode, but that changes schedule overlap and is not equivalent to NIC send completion.

The receive notification is called from QpComplete after ACK processing (`rdma-hw.cc:528-536,630-644`, `entry.h:312-344`), so this backend's "receive completion" is not raw physical last-byte-arrival time. Match comparison policies to the same backend and report this modeling choice.

## Algorithm/protocol selectors and launch overhead

`Sys.cc:1171-1259` chooses NcclTreeFlowModel according to nccl_info.algorithm; RING and TREE share the executor. `MockNcclGroup.cc:2028-2101` currently chooses RING for ordinary DP AllReduce and sets protocol to NCCL_PROTO_UNDEF; it does not implement actual LL/LL128/Simple protocol selection. `SingleFlow.conn_type` controls internal tag behavior, not RDMA congestion control. AS_OPTCC_MODE and genAllReduceMyAlgoFlowModels appear only in the archived OptCC README; this SimAI commit does not contain them. Add a narrow explicit OptCC selector for the intended DP AllReduce only, fail closed on unsupported operations/modes, and log the selected algorithm plus imported DAG hash.

AS_PXN_ENABLE and AS_NVLS_ENABLE must be explicitly disabled for this single-GPU reproduction. CC_MODE in SimAI.conf selects network congestion control and must be shared with ring. `entry.h:130-135` parses AS_SEND_LAT as integer microseconds and multiplies by 1000 for simulator nanoseconds; default is 6000 microseconds (6 ms) per launched flow. The README example AS_SEND_LAT=3 means 3 microseconds, not 3 ns. OptCC's many sync flows make default overhead a dominant confound. Pin and report AS_SEND_LAT, topology latency, NIC bandwidth and slow NIC placement; never choose zero launch overhead simply because it yields the analytic expectation. Use identical backend configuration for ring and OptCC.

Native PacketBundle/insert_packets also toggles processing/send-back using ring counters rather than generator node type (`NcclTreeFlowModel.cc:451-507`, `PacketBundle.cc:95-110`). A custom direct-network branch removes this modeled memory/reduction overhead. If used, apply the same declared network-only scope to the comparator or provide a controlled native-ring plus imported-ring consistency check. Do not label such measurements end-to-end training latency.

## Required validation gates, in order

1. **Schema/identity**: reject absent N, mismatched p/group, L<1, k<4 or not multiple of 4, duplicate IDs/deps, absent parents, self edges, cycles and unsupported remote dependencies. Confirm complete rank permutation and globally unique runtime tags.
2. **Conversion**: golden 5/4/L2 sample keeps all 132 nodes, 40 syncs, 255 edges and four roots; each edge consumed once at the correct endpoint. Repeat p=3, larger p/k and L=1,1.5,2,4. Check ideal payload formulas against generator construction, report rounding/error, and total per-rank data/control bytes separately.
3. **Scheduler-only micrographs**: root->same-source child; root->destination child; mixed two-parent join; one parent with children at both endpoints; final receive-only rank; unequal parent/child sizes; sync chain; early receive; duplicate completion; two same-src/dst flows with unique tags; two concurrent collectives. Assert no early child launch and complete graph drain.
4. **Transport gates**: positive tiny sync, rejected zero sends, one-packet/multi-packet flow, exact 9000 and 18000 payloads and +/-1 bytes, alternate 1000-byte MTU, and final send vs ACK-complete timestamps. Require one sender and one receiver completion per flow, no missing expeRecvHash/sentHash/pending entries. No graph completion while incoming flows remain.
5. **Stock ring preservation**: run unmodified official ring first; importer disabled must reproduce its trace/output. Build an imported ordinary-ring graph with identical byte accounting and compare network-only timing to its declared counterpart. Test matching packet settings before OptCC.
6. **OptCC smoke**: p=5,k=4,L2 divisible-size workload; all 132 nodes start/finish; byte totals match; dependency inequalities verified on trace. Repeat bubble case and slowdown sweep. Capture original DAG, enriched manifest, converted graph, logs, hashes, compiler/version/seed/config and exit code. Wall-clock timeout is a failure, not a censored latency result.
7. **Performance gate**: require paper-settings match or explicitly identify deviations (missing author integration, rounding, sync bytes, callback repairs, channel count, memory costs). Only then use repeated matched ring/OptCC runs and write actual measured latency. Analytic critical path is a sanity bound/model reference, not a substitute measurement or proof of tensor correctness.

## What remains unknown

The author integration's exact byte scaling/rounding, control-message handling, channel assignment, NIC scheduling and memory overhead are absent from the six-file archive. The paper execution script is also missing. The proposed mapping reproduces the disclosed dependency graph with declared interpretation, and requires the validation gates above. This audit alone does not establish exact paper-number reproduction.
