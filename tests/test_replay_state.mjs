import test from "node:test";
import assert from "node:assert/strict";

import {
  createReplayModel,
  deriveScene,
  selectRun,
  setState,
} from "../docs/assets/js/replay.js";


const runs = [
  {
    id: "c3_rep01",
    mode: "legacy_global",
    fault_retention: 0.213,
    post_recovery_retention: 0.971,
    gate: "PASS",
  },
  {
    id: "c3_rep02",
    mode: "legacy_global",
    fault_retention: 0.215,
    post_recovery_retention: 0.853,
    gate: "FAIL",
  },
];

const activeRuns = [
  {
    id: "aa3_local_rep01",
    mode: "active_active_local",
    fault_retention: 0.42,
    post_recovery_retention: 0.96,
    gate: "PASS",
  },
];


test("baseline uses Fabric A and matched retention", () => {
  const scene = deriveScene(createReplayModel(runs, "c3_rep01"));
  assert.equal(scene.route, "A");
  assert.equal(scene.version, 0);
  assert.equal(scene.retention, 1);
  assert.equal(scene.faultActive, false);
});


test("fault state marks only the degraded A edge", () => {
  const scene = deriveScene(
    setState(createReplayModel(runs, "c3_rep01"), 2),
  );
  assert.equal(scene.retention, 0.213);
  assert.equal(scene.edgeClasses.a2, "edge route-a fault");
  assert.equal(scene.edgeClasses.b2, "edge");
});


test("committed state moves every active edge to Fabric B", () => {
  const scene = deriveScene(
    setState(createReplayModel(runs, "c3_rep01"), 5),
  );
  assert.equal(scene.route, "B");
  assert.equal(scene.version, 1);
  assert.equal(scene.retention, 0.971);
  assert.equal(scene.edgeClasses.a2, "edge");
  assert.equal(scene.edgeClasses.b2, "edge route-b");
});


test("active-active baseline uses both fabrics concurrently", () => {
  const scene = deriveScene(
    createReplayModel(activeRuns, "aa3_local_rep01"),
  );
  assert.equal(scene.mode, "active_active_local");
  assert.equal(scene.route, "A+B");
  assert.equal(scene.routeLabel, "A+B active-active");
  assert.equal(scene.edgeClasses.a0, "edge route-a");
  assert.equal(scene.edgeClasses.b0, "edge route-b");
  assert.equal(scene.edgeClasses.a2, "edge route-a");
  assert.equal(scene.edgeClasses.b2, "edge route-b");
});


test("localized recovery changes only the affected worker two edge classes", () => {
  const model = createReplayModel(activeRuns, "aa3_local_rep01");
  const baseline = deriveScene(model);
  const fault = deriveScene(setState(model, 2));
  const recovered = deriveScene(setState(model, 5));

  assert.equal(fault.edgeClasses.a2, "edge route-a fault");
  assert.equal(recovered.route, "A+B");
  assert.equal(recovered.routeLabel, "A+B · w2 A slots rerouted to B");
  assert.equal(recovered.version, 1);
  assert.equal(recovered.edgeClasses.a2, "edge");
  assert.equal(recovered.edgeClasses.b2, "edge route-b changed");
  for (const id of ["a0", "a1", "a3", "b0", "b1", "b3"]) {
    assert.equal(recovered.edgeClasses[id], baseline.edgeClasses[id]);
  }
});


test("run selection resets the timeline and preserves the failed gate", () => {
  const selected = selectRun(
    setState(createReplayModel(runs, "c3_rep01"), 5),
    "c3_rep02",
  );
  assert.equal(selected.stateIndex, 0);
  assert.equal(deriveScene(setState(selected, 5)).gate, "FAIL");
  assert.equal(deriveScene(setState(selected, 5)).retention, 0.853);
});
