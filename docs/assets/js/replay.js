export const PHASES = [
  "baseline",
  "fault",
  "detected",
  "confirmed",
  "committed",
  "recovered",
];


export function createReplayModel(runs, runId = runs[0]?.id) {
  if (!Array.isArray(runs) || runs.length === 0) {
    throw new Error("At least one replay run is required");
  }
  if (!runs.some((run) => run.id === runId)) {
    throw new Error(`Unknown run: ${runId}`);
  }
  return {
    runs,
    runId,
    stateIndex: 0,
    playing: false,
    speedMs: 1300,
  };
}


export function selectRun(model, runId) {
  if (!model.runs.some((run) => run.id === runId)) {
    throw new Error(`Unknown run: ${runId}`);
  }
  return {
    ...model,
    runId,
    stateIndex: 0,
    playing: false,
  };
}


export function setState(model, index) {
  if (!Number.isInteger(index) || index < 0 || index >= PHASES.length) {
    throw new RangeError(`Invalid replay state: ${index}`);
  }
  return {
    ...model,
    stateIndex: index,
  };
}


export function deriveScene(model) {
  const run = model.runs.find((candidate) => candidate.id === model.runId);
  const mode = run.mode || "legacy_global";
  const recovered = model.stateIndex >= 4;
  const faultActive = model.stateIndex >= 1 && !recovered;
  const edgeClasses = {};

  if (mode === "active_active_local") {
    for (const id of ["a0", "a1", "a2", "a3"]) {
      edgeClasses[id] = `edge${id === "a2" && recovered ? "" : " route-a"}${
        id === "a2" && faultActive ? " fault" : ""
      }`;
    }
    for (const id of ["b0", "b1", "b2", "b3"]) {
      edgeClasses[id] = `edge route-b${
        id === "b2" && recovered ? " changed" : ""
      }`;
    }
  } else {
    for (const id of ["a0", "a1", "a2", "a3"]) {
      edgeClasses[id] = `edge${recovered ? "" : " route-a"}${
        id === "a2" && faultActive ? " fault" : ""
      }`;
    }
    for (const id of ["b0", "b1", "b2", "b3"]) {
      edgeClasses[id] = `edge${recovered ? " route-b" : ""}`;
    }
  }

  return {
    phase: PHASES[model.stateIndex],
    retention:
      model.stateIndex === 0
        ? 1
        : model.stateIndex < 5
          ? run.fault_retention
          : run.post_recovery_retention,
    mode,
    route: mode === "active_active_local" ? "A+B" : recovered ? "B" : "A",
    routeLabel:
      mode === "active_active_local"
        ? recovered
          ? "A+B · w2 A slots rerouted to B"
          : "A+B active-active"
        : recovered
          ? "B global failover"
          : "A primary",
    version: recovered ? 1 : 0,
    gate: run.gate,
    faultActive,
    edgeClasses,
    run,
  };
}
