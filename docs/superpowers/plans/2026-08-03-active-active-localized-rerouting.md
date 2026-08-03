# LIMER Active-Active Localized Rerouting Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four-worker Dual-ToR prototype use both fabrics before a fault, reroute only worker 2's affected Fabric A send slots after confirmation, and produce auditable latency, performance, correctness, experiment, documentation, and website evidence.

**Architecture:** Represent routing as an immutable versioned sender-by-step `RoutePlan`. Workers derive both send and receive sockets from the same plan, while the existing all-rank prepare/READY/commit protocol atomically installs a localized plan at a completed-round boundary. Preserve archived v0 evidence and generate a separate active-active v1 result family.

**Tech Stack:** Python 3 standard library, Mininet, Open vSwitch, Linux `tc`, framed TCP sockets, JSON/JSONL/CSV, browser-native JavaScript modules, Node.js test runner, Python `unittest`, static GitHub Pages.

## Global Constraints

- Preserve `results/` and the existing six `configs/*.json` files as immutable legacy v0 evidence and reproduction inputs.
- Store new measured runs under `results_active_active/` and new configurations under `configs/active_active_v1/`.
- Healthy Dual-ToR routing uses both Fabric A and Fabric B in every collective step.
- The v1 injected fault is worker 2's directed egress toward Fabric A; do not describe it as a bidirectional cable failure.
- Localized recovery changes only worker 2's Fabric A send slots. Workers 0, 1, and 3 retain their sender schedules.
- All ranks prepare and commit the same plan version and fingerprint at a completed-round safe point.
- Do not claim GPU, NCCL, RDMA, switch-resident detection, trained uncertainty, numerical reduction, or millisecond end-to-end recovery.
- Do not invent v1 experiment values. Website values must resolve to complete raw artifacts.
- Failed repeats remain in the result tree and in report accounting.
- Use English for code, comments, file names, configuration intent, and commit messages.
- Do not commit during execution. Show the complete diff to Sophie first; commit requires a later explicit approval and push requires a separate explicit approval.

---

## File Responsibility Map

### New files

- `limer_v0/route_plan.py`: immutable plan construction, validation, serialization, fingerprints, and plan deltas.
- `tests/test_route_plan.py`: route-plan unit contract.
- `configs/active_active_v1/*.json`: seven predeclared v1 experiment scenarios.
- `results_active_active/`: generated real v1 evidence and reports; never hand-authored.

### Core files modified

- `limer_v0/state.py`: activate prepared plans by version and round.
- `limer_v0/coordinator.py`: coordinate complete plan fingerprints instead of one route string.
- `limer_v0/worker.py`: choose send and receive fabric per sender and step.
- `limer_v0/orchestrator.py`: validate v1 configuration, launch workers with the initial plan, propose localized/global plans, aggregate per-fabric records, and derive stage timestamps.
- `limer_v0/refiner.py`: rename standby-path inputs and reasons to alternate-path language.
- `limer_v0/metrics.py`: recovery-window and per-fabric KPI helpers.
- `limer_v0/report.py`: validate and summarize both legacy and active-active schemas without mixing result trees.

### Public artifact files modified

- `scripts/build_demo_data.py`: combine immutable legacy replay evidence with complete measured v1 evidence.
- `docs/assets/js/replay.js`: derive legacy-global and active-active-localized scenes.
- `docs/assets/js/app.js`: select and explain both replay families with accurate bilingual copy.
- `docs/assets/css/site.css`: style simultaneous A/B use and localized route changes.
- `docs/index.html`: rename the replay heading to include both evidence families.
- `README.md`, `docs/current_limitations.md`, and `results_active_active/README.md`: document current behavior, evidence, and boundaries.

---

### Task 1: Add the immutable route-plan model

**Files:**
- Create: `limer_v0/route_plan.py`
- Create: `tests/test_route_plan.py`

**Interfaces:**
- Produces: `RoutePlan`, `RoutePlan.single_fabric()`, `RoutePlan.balanced_active_active()`, `RoutePlan.localized_reroute()`, `RoutePlan.global_fabric()`, `RoutePlan.from_dict()`, `RoutePlan.route_for()`, `RoutePlan.changed_slots()`, `RoutePlan.to_dict()`, and `RoutePlan.fingerprint`.
- Consumes: no project modules; standard-library `dataclasses`, `hashlib`, `json`, and typing only.

- [ ] **Step 1: Write failing construction and routing tests**

Add tests with the exact four-rank expectations:

```python
class RoutePlanTest(unittest.TestCase):
    def test_balanced_plan_uses_both_fabrics_each_step(self):
        plan = RoutePlan.balanced_active_active(world_size=4)
        self.assertEqual(plan.steps, 6)
        self.assertEqual(plan.routes[0], ("A", "B", "A", "B", "A", "B"))
        self.assertEqual(plan.routes[1], ("B", "A", "B", "A", "B", "A"))
        for step in range(plan.steps):
            self.assertEqual(
                {plan.route_for(rank, step) for rank in range(4)},
                {"A", "B"},
            )

    def test_localized_reroute_changes_only_faulty_sender_a_slots(self):
        baseline = RoutePlan.balanced_active_active(4)
        recovered = baseline.localized_reroute(2, "A", "B")
        self.assertEqual(recovered.routes[2], ("B",) * 6)
        for rank in (0, 1, 3):
            self.assertEqual(recovered.routes[rank], baseline.routes[rank])
        self.assertEqual(len(baseline.changed_slots(recovered)), 3)
```

Also test a single-A plan, global-B plan, stable serialization round-trip,
stable fingerprint, rank/step bounds, unsupported fabric, incomplete plan,
identical localized reroute, and invalid world size.

- [ ] **Step 2: Run the focused test and confirm the intended failure**

Run:

```bash
python3 -m unittest tests.test_route_plan -v
```

Expected: import failure because `limer_v0.route_plan` does not yet exist.

- [ ] **Step 3: Implement the exact immutable data contract**

Use tuple-backed routes so committed plan content cannot be mutated:

```python
@dataclass(frozen=True)
class RoutePlan:
    world_size: int
    policy: str
    routes: Tuple[Tuple[str, ...], ...]

    @property
    def steps(self) -> int:
        return 2 * (self.world_size - 1)

    @classmethod
    def balanced_active_active(cls, world_size: int) -> "RoutePlan":
        steps = 2 * (world_size - 1)
        routes = tuple(
            tuple("A" if (rank + step) % 2 == 0 else "B" for step in range(steps))
            for rank in range(world_size)
        )
        return cls(world_size, "balanced_active_active", routes)

    def route_for(self, sender_rank: int, step_id: int) -> str:
        return self.routes[sender_rank][step_id]
```

Validation runs in `__post_init__` and requires `world_size >= 2`, exactly
`world_size` sender tuples, exactly `2 * (world_size - 1)` steps per sender,
and only `A` or `B`. `to_dict()` returns lists for JSON. `from_dict()` accepts
only `world_size`, `policy`, and `routes`; it rejects missing or extra keys.
Canonical serialization is:

```python
json.dumps(self.to_dict(), sort_keys=True, separators=(",", ":"))
```

`fingerprint` is the lowercase SHA-256 hex digest of that UTF-8 string.
`changed_slots(target)` returns sorted dictionaries with `sender_rank`,
`step_id`, `old_route`, and `new_route`.

- [ ] **Step 4: Run route-plan tests and static compilation**

Run:

```bash
python3 -m unittest tests.test_route_plan -v
python3 -m py_compile limer_v0/route_plan.py
```

Expected: all route-plan tests pass and compilation exits 0.

- [ ] **Step 5: Record the no-commit checkpoint**

Run `git diff --check` and `git status --short`. Expected: only the approved
spec, this plan, `route_plan.py`, and its test are new; do not stage or commit.

---

### Task 2: Coordinate versioned plans safely

**Files:**
- Modify: `limer_v0/state.py`
- Modify: `limer_v0/coordinator.py`
- Modify: `tests/test_state.py`
- Modify: `tests/test_coordinator.py`

**Interfaces:**
- Consumes: `RoutePlan` from Task 1.
- Produces: `RouteState(initial_plan)`, `RouteState.plan_for(round_id)`, `TransitionProposal.plan`, `TransitionProposal.plan_fingerprint`, `TransitionDecision.plan`, and `RecoveryCoordinator(initial_plan)`.

- [ ] **Step 1: Replace route-string tests with plan activation tests**

The state contract becomes:

```python
baseline = RoutePlan.balanced_active_active(4)
recovered = baseline.localized_reroute(2, "A", "B")
state = RouteState(baseline)
state.prepare(version=1, plan=recovered, effective_round=5)
state.commit(1)
self.assertEqual(state.plan_for(4), (baseline, 0))
self.assertEqual(state.plan_for(5), (recovered, 1))
```

Retain tests for wrong next version, duplicate prepare, abort, commit without
prepare, wrong commit version, non-negative effective round, and no-op plan.

Coordinator tests use:

```python
coordinator = RecoveryCoordinator(baseline)
proposal = coordinator.propose(recovered, effective_round=4, current_round=3)
for rank in range(4):
    coordinator.record_ready(rank, proposal.version, proposal.plan_fingerprint)
decision = coordinator.commit_or_abort()
self.assertEqual(decision.action, "commit")
self.assertEqual(decision.plan_fingerprint, recovered.fingerprint)
self.assertEqual(len(decision.changed_slots), 3)
```

Add explicit mismatched-fingerprint and missing-rank abort tests.

- [ ] **Step 2: Run focused tests and confirm route-string APIs fail**

Run:

```bash
python3 -m unittest tests.test_state tests.test_coordinator -v
```

Expected: failures because current classes accept `route` strings.

- [ ] **Step 3: Implement plan-backed state**

Define:

```python
@dataclass
class PreparedTransition:
    version: int
    plan: RoutePlan
    effective_round: int
    committed: bool = False

class RouteState:
    def __init__(self, initial_plan: RoutePlan) -> None:
        self.active_plan = initial_plan
        self.active_version = 0
        self.prepared: Optional[PreparedTransition] = None
```

`prepare()` requires next version, different fingerprint, matching world size,
and non-negative future activation. `plan_for()` performs committed activation
at the first eligible round and returns `(active_plan, active_version)`.

- [ ] **Step 4: Implement plan-backed coordinator and decision serialization**

`TransitionProposal.to_dict()` and `TransitionDecision.to_dict()` include:

```python
{
    "version": version,
    "plan": plan.to_dict(),
    "plan_fingerprint": plan.fingerprint,
    "policy": plan.policy,
    "effective_round": effective_round,
    "changed_slots": changed_slots,
}
```

`record_ready(rank, version, plan_fingerprint)` rejects duplicate rank, wrong
version, wrong fingerprint, or out-of-range rank. Commit replaces the active
plan only after every rank is READY; abort preserves it.

- [ ] **Step 5: Run focused and regression tests**

Run:

```bash
python3 -m unittest tests.test_route_plan tests.test_state tests.test_coordinator -v
python3 -m py_compile limer_v0/state.py limer_v0/coordinator.py
```

Expected: all focused tests pass.

---

### Task 3: Route each worker step over the correct fabric

**Files:**
- Modify: `limer_v0/worker.py`
- Modify: `tests/test_worker_loopback.py`

**Interfaces:**
- Consumes: `RoutePlan`, plan-backed `RouteState`, and prepare commands with a full `plan` plus `plan_fingerprint`.
- Produces: worker `ROUND_DONE` fields `route_plan_fingerprint`, `send_routes`, `receive_routes`, per-fabric step counts, and per-fabric byte counts.

- [ ] **Step 1: Rewrite loopback expectations for simultaneous active-active use**

Launch workers with `--initial-routing-policy balanced_active_active`. For a
two-rank ring, assert round 0:

```python
self.assertEqual(events[0]["send_routes"], ["A", "B"])
self.assertEqual(events[1]["send_routes"], ["B", "A"])
self.assertEqual(events[0]["receive_routes"], ["B", "A"])
self.assertEqual(events[1]["receive_routes"], ["A", "B"])
```

Prepare the localized plan for rank 0. At the effective round assert rank 0's
send routes become `["B", "B"]`, rank 1's send routes remain `["B", "A"]`,
and rank 1's receive routes become `["B", "B"]`. Preserve checksum, byte,
frame, version, and pre-effective-round assertions.

- [ ] **Step 2: Run loopback test and confirm failure**

Run:

```bash
python3 -m unittest tests.test_worker_loopback -v
```

Expected: current CLI rejects `--initial-routing-policy` or current events lack
route arrays.

- [ ] **Step 3: Add initial-plan selection**

Add CLI choice `single_fabric` or `balanced_active_active`, defaulting to
`single_fabric` for legacy configs. Construct the initial plan after validating
the configured fabrics. Reject balanced active-active unless both A and B
sockets exist.

- [ ] **Step 4: Implement per-step send/receive selection**

At round start:

```python
plan, version = self.route_state.plan_for(round_id)
send_routes = []
receive_routes = []
for step_id in range(plan.steps):
    send_route = plan.route_for(self.rank, step_id)
    predecessor = (self.rank - 1) % self.world_size
    receive_route = plan.route_for(predecessor, step_id)
    send_sockets = self.sockets[send_route]
    receive_sockets = self.sockets[receive_route]
```

Start the receiver on `receive_sockets.incoming` and send on
`send_sockets.outgoing`. Record arrays plus dictionaries initialized for both A
and B, even when one count is zero. Keep frame `version` validation unchanged.

- [ ] **Step 5: Accept and verify full-plan prepare commands**

For `prepare`, construct `RoutePlan.from_dict(command["plan"])`, compare its
fingerprint with `command["plan_fingerprint"]`, call state `prepare`, and emit
READY with version, fingerprint, policy, and effective round. Never accept an
implicit global route string in the v1 command path.

- [ ] **Step 6: Run worker, protocol, state, and coordinator tests**

Run:

```bash
python3 -m unittest tests.test_protocol tests.test_route_plan tests.test_state tests.test_coordinator tests.test_worker_loopback -v
python3 -m py_compile limer_v0/worker.py
```

Expected: all pass, with no skipped loopback on a host that supports 127/8
aliases.

---

### Task 4: Extend orchestration and aggregation without changing legacy inputs

**Files:**
- Modify: `limer_v0/orchestrator.py`
- Modify: `tests/test_orchestrator_config.py`

**Interfaces:**
- Consumes: plan constructors, plan-based worker events, legacy configs without v1 fields, and v1 configs with explicit experiment/routing/recovery/fault fields.
- Produces: normalized config fields, per-fabric collective rows, and `_execute_handover(..., target_plan)`.

- [ ] **Step 1: Add failing normalization and strict-v1 tests**

Legacy config normalization must produce:

```python
{
    "experiment_family": "legacy_v0",
    "scenario_id": "C1",
    "routing_policy": "single_fabric",
    "recovery_policy": "global_failover",
    "fault_scope": {"rank": 2, "fabric": "A", "direction": "egress"},
}
```

For a v1 config, assert dual topology, balanced routing, explicit scenario ID,
and a recovery policy in `localized` or `global_failover`. Reject active-active
on `single`, localized recovery on a non-v1 config, wrong fault rank/fabric/
direction, blank scenario ID, and a recovery policy when recovery is false.

- [ ] **Step 2: Add failing active-active aggregate tests**

Construct four worker events with one common version/fingerprint but different
send routes. Assert aggregation accepts them and returns:

```python
{
    "route_plan_fingerprint": fingerprint,
    "fabric_steps_sent": {"A": 12, "B": 12},
    "fabric_bytes_sent": {"A": 12000, "B": 12000},
}
```

Retain rejection of missing ranks and split versions, and replace scalar-route
split rejection with fingerprint split rejection.

- [ ] **Step 3: Run the tests and confirm current behavior fails**

Run:

```bash
python3 -m unittest tests.test_orchestrator_config -v
```

Expected: missing normalized fields and current route-split rejection.

- [ ] **Step 4: Normalize legacy and v1 configuration**

Keep the existing required fields. Add optional normalized fields with legacy
defaults, but if `experiment_family == "active_active_v1"`, require all four
new inputs explicitly. Validate the exact policies and directed fault scope.
Pass `routing_policy` through `_launch_workers` as
`--initial-routing-policy`.

- [ ] **Step 5: Replace scalar route aggregation**

Update worker CSV fields with route arrays/fingerprints/per-fabric dictionaries.
Update collective CSV fields with common fingerprint and per-fabric totals.
Serialize array/dictionary fields as compact sorted JSON only at CSV write time;
keep native lists/dicts in memory and JSON summaries.

- [ ] **Step 6: Generalize handover to a target plan**

Change the signature to:

```python
def _execute_handover(
    handles: Sequence[WorkerHandle],
    event_log: EventLog,
    current_plan: RoutePlan,
    target_plan: RoutePlan,
    current_round: int,
    effective_round: int,
    prepare_timeout_s: float = 10.0,
) -> TransitionDecision:
```

Prepare commands carry full plan content and fingerprint. READY matching checks
version, fingerprint, and effective round. Recovery events record plan policy,
fingerprint, and changed slots. Keep `old_route_kept_open` as
`both_fabric_sockets_kept_open` in the safe-point contract.

- [ ] **Step 7: Select localized, global, and oracle target plans**

Construct the initial plan once from routing policy. On recovery:

```python
if config["recovery_policy"] == "localized":
    target = active_plan.localized_reroute(
        config["fault_scope"]["rank"],
        config["fault_scope"]["fabric"],
        "B",
    )
else:
    target = RoutePlan.global_fabric(WORLD_SIZE, "B")
```

Oracle uses the same constructor and coordinator without host refinement.
Change fault/post-recovery row classification from scalar route to plan version
and committed effective round.

- [ ] **Step 8: Run focused orchestration tests**

Run:

```bash
python3 -m unittest tests.test_orchestrator_config tests.test_state tests.test_coordinator tests.test_worker_loopback -v
python3 -m py_compile limer_v0/orchestrator.py
```

Expected: all pass.

---

### Task 5: Add KPI, correctness, and report contracts

**Files:**
- Modify: `limer_v0/metrics.py`
- Modify: `limer_v0/orchestrator.py`
- Modify: `limer_v0/report.py`
- Modify: `tests/test_metrics.py`
- Modify: `tests/test_report.py`

**Interfaces:**
- Consumes: v1 collective/worker rows and event timestamps.
- Produces: performance summaries, seven latency fields, active-active and locality correctness gates, and v1 report rows.

- [ ] **Step 1: Add failing recovery-window KPI tests**

Add `summarize_interval(rows, baseline_median_bps)` and test that it computes:

```python
total_bytes = sum(row["bytes_completed"] for row in rows)
total_duration_s = sum(row["duration_s"] for row in rows)
observed_bps = total_bytes * 8.0 / total_duration_s
retention = observed_bps / baseline_median_bps
```

Reject empty rows, non-positive durations/baseline, and negative bytes.

- [ ] **Step 2: Add failing correctness tests**

Create active-active baseline and localized recovered worker rows. Assert:

- both fabrics have non-zero baseline steps and bytes;
- one version/fingerprint exists per collective round;
- rank 2 changes exactly three A slots to B;
- ranks 0, 1, and 3 are unchanged;
- checksum/version errors are zero; and
- the report fails if any unaffected sender schedule changes.

- [ ] **Step 3: Add failing latency derivation tests**

Use synthetic nanosecond timestamps and assert:

```text
l_switch_ms = fault -> suspect
l_host_ms = suspect -> host confirm
l_detection_ms = fault -> host confirm
l_coordination_ms = host confirm/oracle trigger -> commit
l_fault_to_commit_ms = fault -> commit
l_commit_to_recovered_round_ms = commit -> recovered round end
l_fault_to_recovered_round_complete_ms = fault -> recovered round end
```

Oracle host and detection fields are null; no null becomes zero.

- [ ] **Step 4: Run focused tests and confirm failures**

Run:

```bash
python3 -m unittest tests.test_metrics tests.test_report -v
```

Expected: new helper and v1 gates do not yet exist.

- [ ] **Step 5: Implement the interval, latency, and correctness calculations**

Store latency values under `summary["latency"]`, while retaining the existing
legacy nested fields for backward readability. Add:

```python
"latency_target": {
    "unit": "ms",
    "numeric_target_ms": None,
    "status": "not_formally_specified",
    "source": "review feedback requests millisecond-level detection and recovery without a numeric threshold",
}
```

Always print the raw stage values. Do not infer a pass/fail threshold until the
project records an agreed numeric target.

- [ ] **Step 6: Extend report validation and grouping**

Detect schema by `manifest["experiment_family"]`. Legacy report behavior stays
unchanged for `results/`. V1 report groups by `scenario_id`, validates plan and
fabric-use fields, chooses post-recovery retention for localized/global/oracle,
and reports failed runs rather than discarding them. Use a representative
`aa3_local_rep01` timeline only when that complete run exists.

- [ ] **Step 7: Run metrics, report, and full Python unit tests**

Run:

```bash
python3 -m unittest tests.test_metrics tests.test_report -v
python3 -m unittest discover -s tests -p 'test_*.py' -v
```

Expected: all Python tests pass or only the environment-documented Mininet/
loopback test is skipped.

---

### Task 6: Predeclare the active-active experiment matrix

**Files:**
- Create: `configs/active_active_v1/aa0_healthy.json`
- Create: `configs/active_active_v1/aa1_fault.json`
- Create: `configs/active_active_v1/aa2_detect.json`
- Create: `configs/active_active_v1/aa3_local.json`
- Create: `configs/active_active_v1/aa3_global.json`
- Create: `configs/active_active_v1/aa4_oracle.json`
- Create: `configs/active_active_v1/aa5_transient.json`
- Modify: `tests/test_orchestrator_config.py`

**Interfaces:**
- Consumes: normalized v1 config schema from Task 4.
- Produces: seven auditable experiment intents with identical workload/fault settings except for declared condition toggles.

- [ ] **Step 1: Add a matrix-loading test**

Load every JSON file and validate it. Assert unique `scenario_id`,
`experiment_family == "active_active_v1"`, dual topology, balanced routing,
rank-2/A/egress fault scope, and non-empty `what_changes`/`expected`.

- [ ] **Step 2: Run the matrix test and confirm the directory is absent**

Run:

```bash
python3 -m unittest tests.test_orchestrator_config.ConfigValidationTest.test_active_active_matrix -v
```

Expected: failure because `configs/active_active_v1` does not exist.

- [ ] **Step 3: Add the seven configurations**

Use the existing chunk size, warmup, baseline, post-fault, 100-to-20 Mbit/s
rate-cap, and 0% added loss unless the legacy configs prove a different common
value. All files contain the four v1 fields from the design. Exact toggles:

| Scenario | condition | detector | recovery | oracle | recovery_policy | transient_ms |
| --- | --- | --- | --- | --- | --- | --- |
| AA0_HEALTHY | C0 | false | false | false | none | 0 |
| AA1_FAULT | C1 | false | false | false | none | 0 |
| AA2_DETECT | C2 | true | false | false | none | 0 |
| AA3_LOCAL | C3 | true | true | false | localized | 0 |
| AA3_GLOBAL | C3 | true | true | false | global_failover | 0 |
| AA4_ORACLE | C4 | false | true | true | localized | 0 |
| AA5_TRANSIENT | C5 | true | true | false | localized | copy C5 value |

Each `what_changes` states only the changed mechanism. Each `expected` predicts
both active fabrics at baseline and its condition-specific observation. Do not
predict an exact measured retention or latency.

- [ ] **Step 4: Validate JSON and matrix tests**

Run:

```bash
for file in configs/active_active_v1/*.json; do python3 -m json.tool "$file" >/dev/null; done
python3 -m unittest tests.test_orchestrator_config -v
```

Expected: all files parse and tests pass.

---

### Task 7: Add evidence-backed active-active website replay

**Files:**
- Modify: `scripts/build_demo_data.py`
- Modify: `tests/test_demo_data.py`
- Modify: `docs/assets/js/replay.js`
- Modify: `tests/test_replay_state.mjs`
- Modify: `docs/assets/js/app.js`
- Modify: `docs/assets/css/site.css`
- Modify: `docs/index.html`
- Modify: `tests/test_site_structure.py`
- Modify after real runs only: `docs/assets/data/demo-data.json`

**Interfaces:**
- Consumes: immutable legacy C3 artifacts and complete v1 AA3_LOCAL artifacts.
- Produces: `payload.replay_runs` entries with `mode` equal to `legacy_global` or `active_active_local`, plus a scene that keeps unaffected active edges unchanged.

- [ ] **Step 1: Add failing replay-state tests for both modes**

Keep the legacy assertion that commit moves all active links to B. Add an
active-active run and assert:

```javascript
const baseline = deriveScene(createReplayModel(activeRuns, "aa3_local_rep01"));
assert.equal(baseline.mode, "active_active_local");
assert.equal(baseline.edgeClasses.a0, "edge route-a");
assert.equal(baseline.edgeClasses.b0, "edge route-b");

const recovered = deriveScene(setState(
  createReplayModel(activeRuns, "aa3_local_rep01"), 4
));
assert.equal(recovered.edgeClasses.a2, "edge");
assert.equal(recovered.edgeClasses.b2, "edge route-b changed");
for (const id of ["a0", "a1", "a3", "b0", "b1", "b3"]) {
  assert.equal(recovered.edgeClasses[id], baseline.edgeClasses[id]);
}
```

- [ ] **Step 2: Add failing data-builder tests with a temporary v1 fixture**

Build a temporary complete AA3 summary/events/correctness trio and assert the
payload includes mode, plan fingerprints, changed-slot count 3, both-fabric
baseline totals, latency stages, artifact paths, and real retention. Add tests
that partial evidence and a changed-slot count other than 3 raise `ValueError`.

- [ ] **Step 3: Run focused JS/Python tests and confirm failures**

Run:

```bash
node --test tests/test_replay_state.mjs
python3 -m unittest tests.test_demo_data -v
```

Expected: current scene only supports global A-to-B and builder only supports
legacy `c3_runs`.

- [ ] **Step 4: Implement dual replay derivation**

`deriveScene()` branches on `run.mode`. Legacy output remains unchanged. For
active-active local mode, both A and B edges are active before the fault, only
`a2` receives `fault` during the fault phase, and at commit only `a2` loses its
active class while `b2` receives `changed`. Return `routeLabel` rather than
pretending one scalar active route exists.

- [ ] **Step 5: Build v1 payload only from complete evidence**

Refactor builder helpers to accept an explicit result root. Keep legacy counts
and paths unchanged. Scan `results_active_active/aa3_local_rep*`, require three
complete repeats for publication, and validate scenario, mode, correctness,
plan fingerprint, changed slots, both-fabric use, and required events. If the
directory does not exist, emit the legacy payload plus
`active_active_status: "not_measured"`; never fabricate a run.

- [ ] **Step 6: Update bilingual application copy and controls**

The run selector labels the family. Active-active text says both fabrics carry
normal traffic, the worker-2 A egress degrades, all ranks commit a localized
plan, and unaffected schedules stay unchanged. Legacy text explicitly says the
archived v0 moved the whole ring. Replace v1 `standby` wording with `alternate
fabric`; retain legacy wording only inside a visibly labeled legacy explanation.

- [ ] **Step 7: Update SVG/CSS for simultaneous use and localized change**

Allow `.edge.route-a` and `.edge.route-b` to be active simultaneously. Add
`.edge.changed` and a directional worker-2 egress label/arrow. Do not imply that
the whole physical link is bidirectionally failed. Ensure reduced-motion and
focus behavior remain intact.

- [ ] **Step 8: Run site-focused tests and syntax checks**

Run:

```bash
node --test tests/test_replay_state.mjs
node --check docs/assets/js/replay.js
node --check docs/assets/js/app.js
python3 -m unittest tests.test_demo_data tests.test_site_structure -v
```

Expected: all pass before real values are written.

---

### Task 8: Update public documentation without overstating completion

**Files:**
- Modify: `README.md`
- Modify: `docs/current_limitations.md`
- Create: `results_active_active/README.md` after report generation if the report does not create it.
- Modify: `tests/test_site_structure.py`

**Interfaces:**
- Consumes: implemented behavior and verified artifact paths.
- Produces: a reviewer-readable current-state narrative and reproduction commands.

- [ ] **Step 1: Add documentation boundary tests**

Assert public copy contains `active-active`, `localized`,
`results_active_active`, `directed egress`, and `all-rank coordination`, and
does not claim `millisecond end-to-end recovery achieved`. Retain the existing
privacy scan for names, contacts, internal workspace text, and branding.

- [ ] **Step 2: Run structure tests and confirm missing v1 language**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
```

Expected: new documentation assertions fail.

- [ ] **Step 3: Rewrite the README status narrative**

Lead with the concrete scene: four workers use A and B concurrently; worker 2's
A egress is rate-limited while UP; switch-facing evidence and host confirmation
produce a plan changing only three worker-2 slots; every rank safely installs
the same version. Separate:

- legacy v0 archived evidence;
- active-active v1 implementation and measured results;
- current CPU/proxy boundaries; and
- later SimAI up-to-128 and GPU/NCCL work.

Include exact local test commands, Linux/Mininet run commands, report generation,
demo-data generation, and website serving. Do not publish server credentials.

- [ ] **Step 4: Update limitations and next steps**

Replace standby-path variance as the primary next step. Keep the full-round host
confirmation bottleneck, directed-versus-bidirectional fault gap, management-
plane telemetry gap, numeric AllReduce gap, and GPU/NCCL gap. List SimAI up to
128 GPUs as a separate realism milestone rather than evidence from this CPU run.

- [ ] **Step 5: Run documentation and path checks**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
python3 scripts/build_demo_data.py --check
rg -n "standby-only|all workers switch|millisecond end-to-end recovery achieved" README.md docs
```

Expected: tests pass; the search returns no unsupported current-v1 claims.

---

### Task 9: Verify locally, run real Mininet experiments remotely, and audit completion

**Files:**
- Generate: `results_active_active/<run_id>/*`
- Generate: `results_active_active/summary.csv`
- Generate: `results_active_active/aggregate_summary.json`
- Generate: `results_active_active/throughput.svg`
- Generate: `results_active_active/timeline.svg`
- Modify from generated evidence: `docs/assets/data/demo-data.json`
- Modify as required by observed failures: core/tests/docs files from Tasks 1–8.

**Interfaces:**
- Consumes: all code, configs, tests, and the previously authorized Linux server.
- Produces: real three-repeat v1 evidence, generated website data, and a requirement-by-requirement verification record.

- [ ] **Step 1: Run the complete local static and unit suite**

Before running, record:

```text
Changed: routing and recovery semantics from global route strings to active-active localized plans.
Expected: all unit, loopback, schema, replay, and site tests pass; no test relies on fabricated v1 metrics.
```

Run:

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
node --test tests/test_replay_state.mjs
node --check docs/assets/js/replay.js
node --check docs/assets/js/app.js
python3 -m compileall -q limer_v0 scripts tests
git diff --check
```

Expected: all applicable tests pass. Investigate any skip and state whether the
remote Mininet run covers it.

- [ ] **Step 2: Verify remote prerequisites without exposing credentials**

Use the existing authorized SSH target through an interactive credential prompt
or local SSH configuration; never put the password in a command, log, file,
README, or report. Verify Python, Mininet, OVS, `tc`, and disk space. Do not
install or change system packages unless a missing prerequisite makes it
necessary and the prior blanket server authorization still applies.

- [ ] **Step 3: Transfer the uncommitted working tree without GitHub**

Create a temporary archive excluding `.git`, legacy results, caches, and secrets;
copy it to a new remote working directory. This avoids committing or pushing
before review. Verify remote SHA-256 hashes for `route_plan.py`, the v1 configs,
and the plan file match local hashes.

- [ ] **Step 4: Run one focused AA0 smoke test**

Before running, record:

```text
Changed: single-fabric baseline -> balanced active-active route plan; no fault or recovery.
Expected: every baseline round has non-zero A and B frames/bytes, one plan fingerprint, zero transport/version errors, and no recovery event.
```

Run one AA0 result. Inspect raw `worker_rounds.csv`, `aggregate_rounds.csv`,
`correctness.json`, and `summary.json` before proceeding.

- [ ] **Step 5: Run one focused AA3_LOCAL smoke test**

Before running, record:

```text
Changed: persistent worker-2 A-egress rate cap plus switch/host closed loop and localized recovery.
Expected: the interface remains UP, Layer 1 and Layer 2 trigger, all ranks commit one fingerprint, exactly three worker-2 A slots move to B, other sender schedules remain unchanged, and recovered throughput is measured against the active-active baseline.
```

Inspect raw events and schedule fields. If this invariant fails, stop the matrix,
fix code locally, transfer the patch, and repeat the smoke tests.

- [ ] **Step 6: Run the predeclared matrix with three repeats**

For each scenario, log `what_changes` and `expected` before the command. Use run
IDs `aa0_healthy_rep01` through `aa5_transient_rep03`, with
`aa3_local_rep01..03` and `aa3_global_rep01..03`. Preserve failed run folders.
Do not tune thresholds after viewing outcomes.

- [ ] **Step 7: Generate and inspect v1 reports remotely**

Run report generation against `results_active_active/`. Verify run counts,
failed-run accounting, scenario grouping, selected KPI semantics, locality
checks, and timeline event provenance. Copy the entire result tree back without
overwriting local legacy `results/`.

- [ ] **Step 8: Regenerate website data from copied raw evidence**

Run:

```bash
python3 scripts/build_demo_data.py --write
python3 scripts/build_demo_data.py --check
python3 -m unittest tests.test_demo_data tests.test_site_structure -v
node --test tests/test_replay_state.mjs
```

Expected: website data matches both evidence trees and shows three measured
AA3_LOCAL repeats.

- [ ] **Step 9: Serve and smoke-test the static site**

Run `python3 -m http.server 8000 --directory docs`, fetch `/`, CSS, JavaScript,
and data JSON with HTTP 200, and use the in-app browser only if available to
verify the replay selector, legacy/global scene, active-active scene, timeline,
language switch, keyboard navigation, and localized edge change.

- [ ] **Step 10: Perform the completion audit**

For every design acceptance criterion, record the authoritative file and exact
test or raw artifact that proves it. Treat missing real measurements, partial
evidence, a skipped uncovered invariant, or a stale website payload as not
complete. Do not mark the Goal complete until all objective requirements are
proved.

- [ ] **Step 11: Present the complete diff and verification evidence**

Run:

```bash
git status --short --branch
git diff --stat
git diff --check
git diff
```

Because new files are untracked, also show their paths and contents or use a
safe no-index diff for review. Summarize experimental outcomes without hiding
failed repeats. Ask Sophie to review the diff. Do not stage, commit, or push.
