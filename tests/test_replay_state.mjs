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
    fault_retention: 0.213,
    post_recovery_retention: 0.971,
    gate: "PASS",
  },
  {
    id: "c3_rep02",
    fault_retention: 0.215,
    post_recovery_retention: 0.853,
    gate: "FAIL",
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


test("run selection resets the timeline and preserves the failed gate", () => {
  const selected = selectRun(
    setState(createReplayModel(runs, "c3_rep01"), 5),
    "c3_rep02",
  );
  assert.equal(selected.stateIndex, 0);
  assert.equal(deriveScene(setState(selected, 5)).gate, "FAIL");
  assert.equal(deriveScene(setState(selected, 5)).retention, 0.853);
});
