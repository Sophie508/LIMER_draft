# LIMER Active-Active Localized Rerouting Design

## Purpose

Revise the CPU/Mininet prototype so the healthy Dual-ToR topology uses both
fabrics during normal collective communication and a gray degradation on one
worker-facing path causes only the affected communication slots to move. Keep
the existing all-rank safe-point coordination, but coordinate a versioned route
plan rather than one global `A` or `B` route.

The revision is evaluated against two primary outcomes:

1. measure detection and recovery latency as separate, auditable stages; and
2. retain collective throughput as close as possible to the matched
   fault-free active-active baseline.

This design supersedes whole-ring failover as the main prototype behavior.
Archived CPU v0 results remain immutable and are retained as a legacy global
failover baseline.

## Feedback-to-Implementation Mapping

| Review requirement | Design response |
| --- | --- |
| Fabric B must carry normal traffic, not wait idle as a backup. | Use a rank-offset A/B schedule so both fabrics carry worker edges in every normal step. |
| An impairment on worker 2's Fabric A path must not move every worker to Fabric B. | Change only worker 2's affected Fabric A send slots; all unaffected worker schedules remain byte-for-byte identical. |
| Detection and recovery should target millisecond timescales. | Record switch detection, host decision, coordination, commit, and service-restoration latency separately; do not hide the current full-round host-confirmation delay. |
| Failure-period performance must be compared with fault-free training. | Compare each run with its own pre-fault active-active baseline and report fault-window and post-recovery retention. |
| Small scale is acceptable and realistic simulation should precede larger scale. | Keep the executable CPU prototype at four workers; treat SimAI validation up to 128 GPUs as a separate follow-on milestone. |
| The term “gray-loss matrix” was unclear. | Remove it from reader-facing milestones and use concrete fault profiles such as rate cap, loss rate, and duration. |

## Scope and Non-Goals

### In scope

- four-worker framed ring traffic over two Mininet/Open vSwitch fabrics;
- normal traffic on both fabrics;
- controlled, still-UP degradation of worker 2's Fabric A egress;
- switch-facing high-recall suspicion and deterministic host confirmation;
- versioned, all-rank prepare/READY/commit of a localized route plan;
- active-active experiment configurations, raw evidence, reports, tests, and
  an evidence-backed website replay;
- explicit latency and performance KPI boundaries.

### Out of scope for this revision

- real GPU, NCCL, RDMA, or communicator reconstruction;
- neuro-fuzzy training, Gaussian Process uncertainty, or online evolution;
- a switch-resident/P4 detector or a proved switch resource budget;
- claiming millisecond end-to-end recovery before measurements support it;
- SimAI integration or experiments above four emulated workers;
- bidirectional physical-link impairment. The existing injection point is a
  directed worker-2-to-Fabric-A egress qdisc, so the v1 result must be described
  as a directed gray degradation rather than a complete cable failure.

## Routing Model

### Unit of control

The current implementation stores one route for an entire collective round.
The revised unit is a sender-and-step slot:

```text
route_plan[sender_rank][step_id] -> "A" or "B"
```

For a four-worker ring there are six steps per round. A worker sends on its own
slot route and receives on the route selected by its predecessor:

```text
send_route(rank, step) = route_plan[rank][step]
receive_route(rank, step) = route_plan[(rank - 1) mod world_size][step]
```

The receiver route is derived, never independently configured. This prevents a
sender from transmitting on one fabric while its receiver waits on another.

### Fault-free active-active plan

The default Dual-ToR plan uses:

```text
route(rank, step) = A when (rank + step) is even, otherwise B
```

For four ranks and six steps, the plan is:

| Sender | Step 0 | Step 1 | Step 2 | Step 3 | Step 4 | Step 5 |
| --- | --- | --- | --- | --- | --- | --- |
| w0 | A | B | A | B | A | B |
| w1 | B | A | B | A | B | A |
| w2 | A | B | A | B | A | B |
| w3 | B | A | B | A | B | A |

Every normal step therefore has two sender edges on Fabric A and two on Fabric
B. This is concurrent active-active use, not a standby probe and not merely
alternating the whole ring between fabrics.

### Localized recovery plan

The injected v1 fault is worker 2's egress toward Fabric A. Localized recovery
replaces only worker 2's `A` slots with `B`:

| Sender | Step 0 | Step 1 | Step 2 | Step 3 | Step 4 | Step 5 |
| --- | --- | --- | --- | --- | --- | --- |
| w0 | A | B | A | B | A | B |
| w1 | B | A | B | A | B | A |
| w2 | **B** | B | **B** | B | **B** | B |
| w3 | B | A | B | A | B | A |

The bold slots are the only changed slots. Workers 0, 1, and 3 retain their
complete fault-free schedules. The model supports a future bidirectional access
link scope by selecting every sender slot whose path enters or leaves the
affected worker, but that broader scope is not enabled or claimed in this
revision.

### Global-failover comparison

A separate comparison policy maps every slot to Fabric B after confirmation.
It exists only as a baseline for measuring the cost of the previous behavior.
It is not the default recovery policy and must be labeled `global_failover` in
configuration, artifacts, reports, and the website.

## Components and Interfaces

### 1. Route plan

Add a focused route-plan module with an immutable `RoutePlan` value object.
It owns:

- world size, step count, policy name, and sender-to-step routes;
- construction of single-fabric, balanced active-active, localized, and global
  plans;
- validation of complete rank and step coverage and supported fabrics;
- canonical JSON serialization; and
- a SHA-256 fingerprint over canonical content.

The fingerprint identifies plan content independently of its version. No
worker may acknowledge a transition whose computed fingerprint differs from
the proposal.

### 2. Versioned worker state

Replace `RouteState`'s single `active_route` with an active `RoutePlan` and one
prepared plan. The existing timing contract remains:

- prepare version `n + 1` for a future round;
- commit only after every worker reports READY;
- activate atomically when `round_id >= effective_round`;
- keep both fabric sockets open; and
- abort before the effective round if coordination fails.

`plan_for(round_id)` returns the immutable plan and version. A transition to
identical plan content is rejected as a no-op.

### 3. Worker data path

For each step, the worker:

1. obtains its send route and predecessor's receive route from the same active
   plan;
2. starts the receive on `sockets[receive_route].incoming`;
3. sends the framed payload on `sockets[send_route].outgoing`;
4. validates round, step, plan version, payload size, and checksum; and
5. records send route, receive route, duration, and bytes by fabric.

The frame's existing `version` field continues to detect a mixed plan. Worker
round records add:

- `route_plan_fingerprint`;
- `send_routes` and `receive_routes` arrays;
- `send_steps_by_fabric` and `receive_steps_by_fabric`; and
- `bytes_sent_by_fabric` and `bytes_received_by_fabric`.

The old scalar `route` field is not used for active-active rounds. Legacy raw
artifacts keep their original schema.

### 4. Recovery coordination

The coordinator proposal contains the full canonical route plan, its
fingerprint, next version, effective round, and change summary. The change
summary names each altered sender/step slot and is evidence, not the source of
truth.

All ranks still participate in prepare/READY/commit even when only worker 2's
data path changes. This is intentional: “localized rerouting” describes the
data-path delta, while all-rank coordination ensures every receiver interprets
the same sender plan at the same safe round boundary.

READY must echo the version, fingerprint, and effective round. A missing rank,
wrong fingerprint, wrong version, or wrong effective round causes abort. A
commit acknowledgement failure before activation invokes the existing rollback
path and records every rollback failure.

### 5. Detector and host gate

Layer 1 continues to sample the switch-facing peer counter rather than the
fault-injection qdisc. The target poll interval remains 20 ms and the evidence
must preserve interface separation and operstate-UP checks.

Layer 2 keeps the deterministic prototype gate. Terminology changes from
`standby` to `alternate path`, because Fabric B already carries normal traffic.
Its safety check probes Fabric B against the pre-fault Fabric B health baseline.
This revision does not claim that the deterministic gate is the proposed
neuro-fuzzy/GP model.

The current gate waits for a completed degraded round. That limitation remains
visible in the latency report. Step-streamed confirmation is a subsequent
optimization, not a result to be inferred from the 20 ms switch poll.

## Data Flow

```text
balanced active-active round plan
        |
        v
worker framed ring traffic on A and B
        |
worker-2 A egress rate cap, interface remains UP
        |
switch-facing counter suspicion (Layer 1)
        |
completed-round impact + alternate-path health (Layer 2)
        |
localized RoutePlan proposal, version n+1
        |
all ranks PREPARE -> READY -> COMMIT at next round boundary
        |
only worker-2 A send slots move to B
        |
post-recovery throughput, latency, fabric-use, and correctness evidence
```

The oracle condition skips Layer 1 and Layer 2 but uses the same route-plan
coordinator. The detect-only condition records suspicion without proposing a
plan. The global-failover comparison uses the same confirmation event but a
different plan constructor.

## Configuration and Experiment Family

Preserve all existing `configs/*.json` files and `results/` artifacts as the
legacy CPU v0 experiment family. Add `configs/active_active_v1/` with explicit
fields:

```json
{
  "experiment_family": "active_active_v1",
  "scenario_id": "AA3_LOCAL",
  "routing_policy": "balanced_active_active",
  "recovery_policy": "localized",
  "fault_scope": {
    "rank": 2,
    "fabric": "A",
    "direction": "egress"
  }
}
```

The v1 matrix is:

| Scenario | Fault | Detector | Recovery | Purpose |
| --- | --- | --- | --- | --- |
| `AA0_HEALTHY` | no | no | no | matched fault-free active-active control |
| `AA1_FAULT` | persistent | no | no | unrecovered performance loss |
| `AA2_DETECT` | persistent | yes | no | switch-first detection only |
| `AA3_LOCAL` | persistent | yes | localized | main closed-loop design |
| `AA3_GLOBAL` | persistent | yes | global | previous whole-ring behavior baseline |
| `AA4_ORACLE` | persistent | oracle | localized | recovery performance upper bound |
| `AA5_TRANSIENT` | transient | yes | suppress | false-trigger behavior |

Write new measured artifacts to `results_active_active/`, never into or over
the legacy `results/` tree. Run identifiers include the scenario and repeat,
for example `aa3_local_rep01`. Failed repeats remain in place and are included
in accounting.

## Measurements and KPI Contract

### Performance

Every v1 run uses its own pre-fault balanced active-active rounds as the matched
baseline. Report:

- baseline median aggregate throughput;
- fault-window retention;
- post-recovery retention;
- time-weighted fault-to-restoration retention;
- per-fabric frames and application bytes before and after the fault; and
- localized versus global recovery delta.

The primary performance gate remains `post_recovery_retention >= 0.90`, but an
observed miss is retained and reported rather than deleted or relabeled. The
metric remains an aggregate framed-wire-volume proxy, not unique reduced tensor
bytes.

### Latency

Record timestamps and derived durations for:

| Metric | Start | End |
| --- | --- | --- |
| `l_switch_ms` | fault applied | first switch suspicion |
| `l_host_ms` | first switch suspicion | host confirm/suppress/defer |
| `l_detection_ms` | fault applied | host confirmation |
| `l_coordination_ms` | host confirmation or oracle trigger | all-rank commit acknowledgement |
| `l_fault_to_commit_ms` | fault applied | all-rank commit acknowledgement |
| `l_commit_to_recovered_round_ms` | commit acknowledgement | first recovered collective completes |
| `l_fault_to_recovered_round_complete_ms` | fault applied | first recovered collective completes |

Oracle runs use `oracle_trigger -> commit` for coordination and leave host
latency null. A null stage is not converted to zero. Reports must show the
actual value and state that the formal numeric target is not yet specified;
they must not invent a pass threshold or claim end-to-end millisecond recovery
from switch detection alone.

### Locality and consistency

Add explicit correctness gates:

- both fabrics carry non-zero frames and bytes during healthy dual-fabric
  rounds;
- every rank observes one plan version and fingerprint per round;
- worker 2's three affected A slots change to B after localized recovery;
- workers 0, 1, and 3 retain exactly their pre-fault schedules;
- global failover changes all eligible slots and is labeled as a baseline;
- checksum errors, version errors, and incomplete ranks remain zero; and
- the degraded interface remains operationally UP.

## Artifact Schema

New v1 run directories keep the existing evidence types and extend them:

- `manifest.json`: experiment family, routing and recovery policies, fault
  scope, baseline and recovered plan fingerprints;
- `events.jsonl`: proposal plan, change summary, READY fingerprints, decisions,
  and stage timestamps;
- `worker_rounds.csv`: route arrays, plan fingerprint, and per-fabric counts;
- `aggregate_rounds.csv`: common version/fingerprint, per-fabric totals, and
  collective duration;
- `switch_timeseries.csv`: unchanged switch-facing counter evidence;
- `version_commits.csv`: version, fingerprint, effective round, policy, and
  changed-slot count;
- `correctness.json`: transport, plan consistency, active-active use, and
  locality gates;
- `summary.json`: performance, latency, locality, and interpretation boundary;
  and
- generated `summary.csv`, `aggregate_summary.json`, and plots for the v1
  results tree.

JSON-valued CSV fields use canonical compact JSON. Reports must validate the
declared schema before including a run.

## Website and Documentation

The public page distinguishes evidence from design:

1. label the existing C3 replay `Legacy CPU v0: global failover` and preserve
   every archived number and source link;
2. add a v1 active-active replay only from complete
   `results_active_active/aa3_local_rep*` artifacts;
3. show both fabrics carrying traffic in the healthy v1 scene;
4. show the directed worker-2 Fabric A egress as degraded;
5. after commit, change only worker 2's affected send slots and keep the other
   worker schedules visually unchanged;
6. replace `standby fabric` wording with `alternate fabric` for v1; and
7. state that all-rank agreement coordinates a localized plan—it does not move
   every worker.

If measured v1 artifacts are unavailable, the page may show the approved
architecture as `planned` but may not display invented performance or latency
numbers. The data builder fails on partial or schema-invalid v1 evidence rather
than silently mixing it with v0.

README and limitations documentation explain:

- what changed from global to localized recovery;
- why both fabrics are active before the fault;
- why all ranks still coordinate;
- the directed-fault boundary;
- the current whole-round host-confirmation latency; and
- the later SimAI/NCCL milestones.

## Error Handling

- Reject route plans with missing or extra ranks, missing or extra steps,
  unsupported fabrics, invalid world size, or a mismatched fingerprint.
- Reject active-active routing on a single-fabric topology.
- Reject localized recovery whose fault scope identifies no affected slot.
- Abort a transition when any rank is missing or echoes a different version,
  fingerprint, or effective round.
- Preserve the active plan after abort and record the exact failure stage.
- Defer recovery when the alternate path health check fails.
- Fail a round on frame version, round, step, payload, or checksum mismatch.
- Keep failed experiment directories and write the output contract with a
  machine-readable failure record.
- Never fall back from localized to global failover implicitly. A global plan
  requires an explicit configuration policy.

## Testing Strategy

### Unit tests

- balanced-plan construction and exact route table;
- localized and global plan deltas;
- canonical serialization and stable fingerprinting;
- invalid plan and fault-scope rejection;
- prepared/committed/aborted plan-state transitions;
- coordinator READY fingerprint agreement and abort paths;
- configuration defaults for legacy files and strict v1 fields;
- active-active aggregate metrics and locality gates; and
- latency derivation with null-safe oracle behavior.

### Worker loopback tests

Run four local workers with both fabrics and verify asymmetric send/receive
routes for every step, transition at the effective round, schedule preservation
for unaffected workers, byte totals, and zero transport/version errors.

### Site tests

- legacy replay remains traceable to unchanged v0 evidence;
- healthy v1 state activates both fabrics;
- v1 recovery changes only the affected worker-2 send slots;
- bilingual copy avoids standby-only and whole-ring claims for v1;
- every displayed metric resolves to a real artifact; and
- no internal contacts or private collaboration text appears publicly.

### Linux/Mininet integration

For each v1 scenario and repeat, record before running:

- what changed relative to the previous condition; and
- the expected observation.

Then verify topology health, both-fabric baseline use, still-UP fault injection,
detection events, route-plan coordination, correctness gates, and report
generation. The full matrix is run only after focused unit and loopback tests
pass.

## Acceptance Criteria

The revision is ready for diff review only when:

1. the v1 healthy run proves non-zero normal traffic on both fabrics;
2. the v1 localized run changes only worker 2's affected send slots;
3. all ranks use one committed plan fingerprint at the safe round boundary;
4. the active interface stays UP and switch observation remains isolated from
   the injection qdisc;
5. latency stages and retention against the matched active-active baseline are
   present without unsupported millisecond claims;
6. localized, global, oracle, detect-only, and transient semantics are explicit
   in configuration and artifacts;
7. failed repeats and legacy v0 evidence are preserved;
8. Python, Node, schema, report, and site tests pass;
9. the complete working-tree diff is shown to Sophie; and
10. no commit or push occurs before separate explicit approvals under the
    repository rules.
