# LIMER GitHub Pages Interactive Demo Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build and prepare a bilingual static GitHub Pages site that replays the archived LIMER C3 runs, exposes the complete C0-C5 evidence, explains the prototype boundary, and presents prioritized next experiments.

**Architecture:** A Python standard-library builder derives one compact JSON payload from immutable `results/` evidence. A zero-dependency HTML/CSS/ES-module frontend under `docs/` renders the bilingual narrative, SVG replay, and evidence explorer. A GitHub Pages workflow uploads only `docs/` and deploys it through the current official Pages actions.

**Tech Stack:** Python 3 standard library, semantic HTML5, CSS3, SVG, browser ES modules, Node built-in test runner, GitHub Actions Pages workflow.

## Global Constraints

- Do not modify, normalize, or regenerate any file under `results/`.
- Display archived evidence only; never label the replay as live simulation.
- Preserve the formal denominator of 18 runs and retain both failed C3 repeats.
- Use Chinese and English with a visible one-click toggle and bilingual accessibility labels.
- Use a clean academic visual style: white/light-gray surfaces, restrained blue, green for healthy/pass, red for fault/fail, blue for recovered Fabric B.
- Do not use organization-specific branding, organization names, or reviewer names.
- Do not claim switch residency, GPU, NCCL, RDMA, or numerical AllReduce validation.
- Respect `prefers-reduced-motion` and keyboard interaction.
- Before every commit, show the exact diff and obtain Sophie's explicit approval. Do not push without a separate explicit approval.
- Any approved commit uses Sophie alone as author/committer, with no AI attribution and no `Co-Authored-By` trailer.

## File Map

- Create `scripts/build_demo_data.py`: derive and validate the browser payload from archived JSON/JSONL.
- Create `tests/test_demo_data.py`: exact evidence and stale-payload tests.
- Create `docs/assets/data/demo-data.json`: generated, traceable website data.
- Create `docs/index.html`: semantic bilingual page shell and all section content.
- Create `docs/assets/css/site.css`: academic visual system, responsive layout, SVG topology, and reduced motion.
- Create `docs/assets/js/replay.js`: pure replay-state functions shared by browser code and Node tests.
- Create `docs/assets/js/app.js`: data loading, translations, DOM rendering, controls, evidence explorer, and visible error state.
- Create `package.json`: declare ES-module semantics and the dependency-free site test command.
- Create `tests/test_replay_state.mjs`: pure replay and run-switching tests.
- Create `tests/test_site_structure.py`: static HTML, CSS, wording, asset-path, and workflow checks.
- Create `.github/workflows/pages.yml`: official static Pages deployment from `docs/`.
- Modify `.gitignore`: ignore `.superpowers/` visual-companion artifacts.
- Modify `README.md`: add a website entry point and accurate Pages description.

---

### Task 1: Evidence-Derived Browser Payload

**Files:**
- Create: `scripts/build_demo_data.py`
- Create: `tests/test_demo_data.py`
- Create: `docs/assets/data/demo-data.json`

**Interfaces:**
- Consumes: repository root containing `results/aggregate_summary.json`, `results/c3_rep*/summary.json`, `results/c3_rep*/events.jsonl`, and `results/c3_rep*/correctness.json`.
- Produces: `build_payload(root: pathlib.Path) -> dict`, `render_payload(payload: dict) -> str`, and CLI modes `--write` and `--check`.
- Produces JSON keys: `meta`, `conditions`, `c3_runs`, `boundaries`, and `roadmap`.

- [ ] **Step 1: Write the failing evidence tests**

```python
# tests/test_demo_data.py
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location(
    "build_demo_data", ROOT / "scripts" / "build_demo_data.py"
)
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class DemoDataTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.payload = MODULE.build_payload(ROOT)

    def test_formal_denominator_and_gate_counts_are_exact(self):
        self.assertEqual(self.payload["meta"]["formal_run_count"], 18)
        self.assertEqual(self.payload["meta"]["gate_pass_count"], 16)
        self.assertFalse(self.payload["meta"]["overall_acceptance"])
        self.assertEqual(self.payload["conditions"]["C3"]["gate_pass_count"], 1)

    def test_c3_runs_preserve_all_repeats(self):
        runs = self.payload["c3_runs"]
        self.assertEqual([run["id"] for run in runs], ["c3_rep01", "c3_rep02", "c3_rep03"])
        self.assertEqual(
            [round(run["post_recovery_retention"], 3) for run in runs],
            [0.971, 0.853, 0.865],
        )
        self.assertEqual([run["gate"] for run in runs], ["PASS", "FAIL", "FAIL"])

    def test_c3_rep01_timing_and_fault_window_are_traceable(self):
        run = self.payload["c3_runs"][0]
        self.assertAlmostEqual(run["switch_detection_ms"], 39.905322)
        self.assertAlmostEqual(run["host_confirmation_ms"], 5283.694265)
        self.assertAlmostEqual(run["coordination_ms"], 0.625035)
        self.assertAlmostEqual(run["fault_retention"], 0.21297836608124676)
        self.assertEqual(run["source_summary"], "results/c3_rep01/summary.json")
        self.assertEqual(run["source_events"], "results/c3_rep01/events.jsonl")
        self.assertEqual(run["source_correctness"], "results/c3_rep01/correctness.json")

    def test_render_is_stable_and_committed_payload_matches(self):
        rendered = MODULE.render_payload(self.payload)
        committed = (ROOT / "docs/assets/data/demo-data.json").read_text(encoding="utf-8")
        self.assertEqual(committed, rendered)
        self.assertEqual(json.loads(rendered), self.payload)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the test and verify the builder is missing**

Run: `python3 -m unittest tests.test_demo_data -v`

Expected: FAIL while importing `scripts/build_demo_data.py` because the file does not exist.

- [ ] **Step 3: Implement the evidence builder**

```python
# scripts/build_demo_data.py
from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


EVENT_NAMES = (
    "FAULT_APPLIED",
    "SWITCH_SUSPECT",
    "HOST_CONFIRM",
    "RECOVERY_COMMIT",
)


def load_json(path: Path) -> dict[str, Any]:
    with path.open(encoding="utf-8") as handle:
        return json.load(handle)


def load_events(path: Path) -> list[dict[str, Any]]:
    with path.open(encoding="utf-8") as handle:
        return [json.loads(line) for line in handle if line.strip()]


def event_index(events: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    found = {event["event"]: event for event in events if event.get("event") in EVENT_NAMES}
    missing = sorted(set(EVENT_NAMES) - set(found))
    if missing:
        raise ValueError(f"Missing required C3 events: {', '.join(missing)}")
    return found


def build_c3_run(root: Path, run_id: str) -> dict[str, Any]:
    summary_rel = Path("results") / run_id / "summary.json"
    events_rel = Path("results") / run_id / "events.jsonl"
    correctness_rel = Path("results") / run_id / "correctness.json"
    summary = load_json(root / summary_rel)
    events = event_index(load_events(root / events_rel))
    correctness = load_json(root / correctness_rel)
    recovery = summary["recovery"]
    retention = float(summary["post_recovery_retention"])
    return {
        "id": run_id,
        "gate": "PASS" if retention >= 0.9 else "FAIL",
        "switch_detection_ms": float(summary["switch_detection"]["l_switch_ms"]),
        "host_confirmation_ms": float(summary["host_refinement"]["l_host_ms"]),
        "coordination_ms": float(recovery["l_coordination_ms"]),
        "fault_to_recovered_round_ms": float(recovery["l_fault_to_recovered_round_complete_ms"]),
        "fault_retention": float(summary["fault_window"]["fault_period_retention"]),
        "post_recovery_retention": retention,
        "checksum_errors": int(correctness["checksum_errors"]),
        "version_errors": int(correctness["version_errors"]),
        "events": [
            {"name": name, "t_monotonic_ns": events[name]["t_monotonic_ns"]}
            for name in EVENT_NAMES
        ],
        "source_summary": summary_rel.as_posix(),
        "source_events": events_rel.as_posix(),
        "source_correctness": correctness_rel.as_posix(),
    }


def build_payload(root: Path) -> dict[str, Any]:
    aggregate = load_json(root / "results/aggregate_summary.json")
    conditions = aggregate["conditions"]
    normalized_conditions = {
        condition_id: {
            "label": value["label"],
            "run_count": int(value["run_count"]),
            "median_retention": float(value["median_retention"]),
            "retention_values": [float(item) for item in value["retention_values"]],
            "gate_pass_count": int(value["gate_pass_count"]),
        }
        for condition_id, value in sorted(conditions.items())
    }
    run_count = sum(item["run_count"] for item in normalized_conditions.values())
    pass_count = sum(item["gate_pass_count"] for item in normalized_conditions.values())
    if run_count != 18 or pass_count != 16:
        raise ValueError(f"Unexpected aggregate counts: {pass_count}/{run_count}")
    return {
        "meta": {
            "title": "LIMER CPU-Only Emulation Prototype",
            "formal_run_count": run_count,
            "gate_pass_count": pass_count,
            "overall_acceptance": bool(aggregate["overall_acceptance"]),
            "source": "results/aggregate_summary.json",
        },
        "conditions": normalized_conditions,
        "c3_runs": [build_c3_run(root, f"c3_rep0{repeat}") for repeat in range(1, 4)],
        "boundaries": [
            "CPU/Mininet emulation",
            "AllReduce-like framed traffic",
            "Management-plane switch-counter proxy",
            "Healthy Fabric B assumed",
            "No GPU, NCCL, RDMA, or numerical reduction",
        ],
        "roadmap": ["standby_path", "step_level_confirmation", "orthogonal_loss_matrix"],
    }


def render_payload(payload: dict[str, Any]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser()
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--write", action="store_true")
    mode.add_argument("--check", action="store_true")
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[1]
    output = root / "docs/assets/data/demo-data.json"
    rendered = render_payload(build_payload(root))
    if args.write:
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(rendered, encoding="utf-8")
        return 0
    if not output.exists() or output.read_text(encoding="utf-8") != rendered:
        print("docs/assets/data/demo-data.json is stale")
        return 1
    print("demo-data.json matches archived evidence")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
```

- [ ] **Step 4: Generate the payload and run the tests**

Run:

```bash
python3 scripts/build_demo_data.py --write
python3 -m unittest tests.test_demo_data -v
python3 scripts/build_demo_data.py --check
```

Expected: four tests PASS and the final command prints `demo-data.json matches archived evidence`.

- [ ] **Step 5: Review the task diff and stop at the commit gate**

Run: `git diff -- scripts/build_demo_data.py tests/test_demo_data.py docs/assets/data/demo-data.json`

Expected: only the builder, its test, and the generated derived payload. Ask Sophie before running any commit command.

---

### Task 2: Semantic Bilingual Page Shell

**Files:**
- Create: `docs/index.html`
- Create: `tests/test_site_structure.py`
- Modify: `.gitignore`

**Interfaces:**
- Consumes: `docs/assets/data/demo-data.json` through `app.js`.
- Produces: stable DOM IDs `overview`, `demo`, `architecture`, `evidence`, `boundaries`, `roadmap`, and `feedback`.
- Produces: translatable nodes through `data-i18n` keys and the `#language-toggle` control.

- [ ] **Step 1: Write failing structure and wording tests**

```python
# tests/test_site_structure.py
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]


class SiteStructureTests(unittest.TestCase):
    def test_required_sections_and_assets_exist(self):
        html = (ROOT / "docs/index.html").read_text(encoding="utf-8")
        for section_id in ("overview", "demo", "architecture", "evidence", "boundaries", "roadmap", "feedback"):
            self.assertIn(f'id="{section_id}"', html)
        self.assertIn('id="language-toggle"', html)
        self.assertIn('src="assets/js/app.js"', html)
        self.assertIn('href="assets/css/site.css"', html)

    def test_copy_has_no_organization_specific_wording(self):
        site_files = [ROOT / "docs/index.html", ROOT / "docs/assets/js/app.js"]
        text = "\n".join(path.read_text(encoding="utf-8") for path in site_files)
        for forbidden in ("Huawei", "华为"):
            self.assertNotIn(forbidden, text)

    def test_visual_companion_output_is_ignored(self):
        lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
        self.assertIn(".superpowers/", lines)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the structure tests and verify they fail**

Run: `python3 -m unittest tests.test_site_structure -v`

Expected: FAIL because `docs/index.html` and `docs/assets/js/app.js` do not exist.

- [ ] **Step 3: Create the semantic page shell**

Create `docs/index.html` with the exact semantic structure below. Task 5 supplies the dynamic bilingual cards inside the named roots, so this shell contains no filler or duplicated narrative:

```html
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="LIMER CPU-only gray-failure detection and recovery prototype stage review">
  <title>LIMER · Interactive Stage Review</title>
  <link rel="stylesheet" href="assets/css/site.css">
</head>
<body>
  <a class="skip-link" href="#main">Skip to content / 跳至正文</a>
  <header class="site-header">
    <a class="brand" href="#overview">LIMER</a>
    <nav aria-label="Primary navigation">
      <a href="#demo" data-i18n="nav.demo">Demo</a>
      <a href="#evidence" data-i18n="nav.evidence">Evidence</a>
      <a href="#roadmap" data-i18n="nav.roadmap">Roadmap</a>
    </nav>
    <button id="language-toggle" type="button" aria-label="切换为中文">中</button>
  </header>
  <main id="main">
    <section id="overview" class="hero" aria-labelledby="hero-title">
      <p class="eyebrow" data-i18n="hero.eyebrow">Stage review · CPU/Mininet emulation</p>
      <h1 id="hero-title" data-i18n="hero.title">A link can stay UP while collective performance collapses.</h1>
      <p data-i18n="hero.body">LIMER detects a switch-facing signal, confirms end-host impact, and coordinates a move to a healthy fabric.</p>
      <a class="primary-action" href="#demo" data-i18n="hero.action">Replay the archived incident</a>
    </section>
    <section id="demo" aria-labelledby="demo-title"><h2 id="demo-title" data-i18n="demo.title">Archived C3 incident replay</h2><div id="replay-root"></div></section>
    <section id="architecture" aria-labelledby="architecture-title"><h2 id="architecture-title" data-i18n="architecture.title">What the CPU prototype implements</h2><div class="layer-grid" id="architecture-grid"></div></section>
    <section id="evidence" aria-labelledby="evidence-title"><h2 id="evidence-title" data-i18n="evidence.title">Evidence explorer</h2><div id="evidence-root"></div></section>
    <section id="boundaries" aria-labelledby="boundaries-title"><h2 id="boundaries-title" data-i18n="boundaries.title">Interpretation boundary</h2><div id="boundary-grid"></div></section>
    <section id="roadmap" aria-labelledby="roadmap-title"><h2 id="roadmap-title" data-i18n="roadmap.title">Prioritized next steps</h2><div id="roadmap-grid"></div></section>
    <section id="feedback" aria-labelledby="feedback-title"><h2 id="feedback-title" data-i18n="feedback.title">Feedback requested</h2><div id="feedback-grid"></div></section>
  </main>
  <div id="data-error" role="alert" hidden></div>
  <script type="module" src="assets/js/app.js"></script>
</body>
</html>
```

- [ ] **Step 4: Ignore companion artifacts without deleting them**

Append exactly this line to `.gitignore`:

```gitignore
.superpowers/
```

- [ ] **Step 5: Add the initial `app.js` module so static tests can read it**

```javascript
// docs/assets/js/app.js
import { createReplayModel, deriveScene } from "./replay.js";

const DATA_URL = "assets/data/demo-data.json";

export async function loadDemoData(fetchImpl = fetch) {
  const response = await fetchImpl(DATA_URL);
  if (!response.ok) throw new Error(`Demo data request failed: ${response.status}`);
  return response.json();
}
```

- [ ] **Step 6: Run the structure tests**

Run: `python3 -m unittest tests.test_site_structure -v`

Expected: all three tests PASS.

- [ ] **Step 7: Review the task diff and stop at the commit gate**

Run: `git diff -- .gitignore docs/index.html docs/assets/js/app.js tests/test_site_structure.py`

Expected: semantic shell, one ignored local-artifact directory, and no organization-specific wording. Ask Sophie before committing.

---

### Task 3: Academic Styling and Correct SVG Topology

**Files:**
- Create: `docs/assets/css/site.css`
- Modify: `tests/test_site_structure.py`

**Interfaces:**
- Consumes semantic class names and IDs from `docs/index.html` and state classes from `app.js`.
- Produces SVG edge classes `.route-a`, `.route-b`, and `.fault`; state tokens `--healthy`, `--fault`, and `--recovered`.

- [ ] **Step 1: Add failing CSS contract tests**

```python
def test_css_contains_accessible_motion_and_svg_routes(self):
    css = (ROOT / "docs/assets/css/site.css").read_text(encoding="utf-8")
    for required in (
        "prefers-reduced-motion",
        ".network-svg",
        ".edge.route-a",
        ".edge.route-b",
        ".edge.fault",
        ":focus-visible",
        "@media (max-width: 760px)",
    ):
        self.assertIn(required, css)
```

- [ ] **Step 2: Run the CSS contract test and verify it fails**

Run: `python3 -m unittest tests.test_site_structure.SiteStructureTests.test_css_contains_accessible_motion_and_svg_routes -v`

Expected: FAIL because `site.css` does not exist.

- [ ] **Step 3: Implement the visual system and anchored route paths**

Create `docs/assets/css/site.css` with the state rules below. In the same file, define `.site-header` as a sticky white navigation bar, `.hero` as a two-column white card, `.replay-layout` and `.evidence-layout` as `minmax(0, 1.2fr) minmax(18rem, .8fr)` grids, and `.layer-grid` and `.roadmap-grid` as three equal columns. Use `max-width: 72rem`, `border: 1px solid var(--line)`, `border-radius: 1rem`, section padding of `clamp(3rem, 8vw, 7rem)`, and the mobile stacking rule shown below:

```css
:root {
  --ink: #182338;
  --muted: #6f7b8f;
  --paper: #ffffff;
  --surface: #f5f7fb;
  --line: #dfe4ec;
  --primary: #4f69d6;
  --healthy: #3e9d74;
  --fault: #e55e6a;
  --recovered: #4f69d6;
}

* { box-sizing: border-box; }
html { scroll-behavior: smooth; }
body { margin: 0; color: var(--ink); background: var(--surface); font-family: Inter, ui-sans-serif, system-ui, sans-serif; }
button, select, input { font: inherit; }
:focus-visible { outline: 3px solid color-mix(in srgb, var(--primary) 55%, white); outline-offset: 3px; }
.network-svg { width: 100%; height: auto; overflow: visible; }
.edge { fill: none; stroke: #c3cad6; stroke-width: 3; stroke-linecap: round; stroke-linejoin: round; transition: stroke 240ms, stroke-width 240ms; }
.edge.route-a { stroke: var(--healthy); }
.edge.route-b { stroke: var(--recovered); }
.edge.fault { stroke: var(--fault); stroke-width: 5; stroke-dasharray: 10 8; animation: fault-flow 1s linear infinite; }
@keyframes fault-flow { to { stroke-dashoffset: -18; } }
@media (prefers-reduced-motion: reduce) {
  *, *::before, *::after { scroll-behavior: auto !important; animation-duration: 0.001ms !important; animation-iteration-count: 1 !important; transition-duration: 0.001ms !important; }
}
@media (max-width: 760px) {
  .site-header nav { display: none; }
  .replay-layout, .evidence-layout, .layer-grid, .roadmap-grid { grid-template-columns: 1fr; }
}
```

Use SVG paths in the replay markup with explicit endpoints rather than rotated HTML lines:

```html
<svg class="network-svg" viewBox="0 0 550 260" role="img" aria-labelledby="network-title network-desc">
  <title id="network-title">Four workers connected to Fabric A and Fabric B</title>
  <desc id="network-desc">The active route and degraded rank 2 access edge change during replay.</desc>
  <path data-edge="a0" class="edge route-a" d="M59 42 H178 Q207 42 227 48"></path>
  <path data-edge="a1" class="edge route-a" d="M59 218 H78 V103 Q78 92 90 92 H194 Q214 92 227 74"></path>
  <path data-edge="a2" class="edge route-a" d="M491 42 H372 Q343 42 323 48"></path>
  <path data-edge="a3" class="edge route-a" d="M491 218 H472 V103 Q472 92 460 92 H356 Q336 92 323 74"></path>
  <path data-edge="b0" class="edge" d="M59 42 H68 V157 Q68 168 80 168 H194 Q214 168 227 184"></path>
  <path data-edge="b1" class="edge" d="M59 218 H178 Q207 218 227 212"></path>
  <path data-edge="b2" class="edge" d="M491 42 H482 V157 Q482 168 470 168 H356 Q336 168 323 184"></path>
  <path data-edge="b3" class="edge" d="M491 218 H372 Q343 218 323 212"></path>
</svg>
```

- [ ] **Step 4: Run CSS and structure tests**

Run: `python3 -m unittest tests.test_site_structure -v`

Expected: all structure and CSS contract tests PASS.

- [ ] **Step 5: Review the task diff and stop at the commit gate**

Run: `git diff -- docs/assets/css/site.css tests/test_site_structure.py`

Expected: academic styling, exact non-crossing SVG paths, responsive rules, and reduced-motion support. Ask Sophie before committing.

---

### Task 4: Pure Replay State Model

**Files:**
- Create: `docs/assets/js/replay.js`
- Create: `tests/test_replay_state.mjs`
- Create: `package.json`

**Interfaces:**
- Produces `createReplayModel(runs, runId) -> { runs, runId, stateIndex, playing, speedMs }`.
- Produces `selectRun(model, runId)`, `setState(model, index)`, and `deriveScene(model)` as pure functions.
- `deriveScene` returns `phase`, `retention`, `route`, `version`, `gate`, `faultActive`, and edge-class maps.

- [ ] **Step 1: Write failing Node tests**

```javascript
// tests/test_replay_state.mjs
import test from "node:test";
import assert from "node:assert/strict";
import { createReplayModel, deriveScene, selectRun, setState } from "../docs/assets/js/replay.js";

const runs = [
  { id: "c3_rep01", fault_retention: 0.213, post_recovery_retention: 0.971, gate: "PASS" },
  { id: "c3_rep02", fault_retention: 0.215, post_recovery_retention: 0.853, gate: "FAIL" },
];

test("baseline uses Fabric A and matched retention", () => {
  const scene = deriveScene(createReplayModel(runs, "c3_rep01"));
  assert.equal(scene.route, "A");
  assert.equal(scene.version, 0);
  assert.equal(scene.retention, 1);
  assert.equal(scene.faultActive, false);
});

test("fault state marks only the degraded A edge", () => {
  const scene = deriveScene(setState(createReplayModel(runs, "c3_rep01"), 2));
  assert.equal(scene.retention, 0.213);
  assert.equal(scene.edgeClasses.a2, "edge route-a fault");
  assert.equal(scene.edgeClasses.b2, "edge");
});

test("committed state moves every active edge to Fabric B", () => {
  const scene = deriveScene(setState(createReplayModel(runs, "c3_rep01"), 5));
  assert.equal(scene.route, "B");
  assert.equal(scene.version, 1);
  assert.equal(scene.retention, 0.971);
  assert.equal(scene.edgeClasses.a2, "edge");
  assert.equal(scene.edgeClasses.b2, "edge route-b");
});

test("run selection resets the timeline and preserves the failed gate", () => {
  const selected = selectRun(setState(createReplayModel(runs, "c3_rep01"), 5), "c3_rep02");
  assert.equal(selected.stateIndex, 0);
  assert.equal(deriveScene(setState(selected, 5)).gate, "FAIL");
  assert.equal(deriveScene(setState(selected, 5)).retention, 0.853);
});
```

- [ ] **Step 2: Run Node tests and verify the module is missing**

Run: `node --test tests/test_replay_state.mjs`

Expected: FAIL with `ERR_MODULE_NOT_FOUND` for `docs/assets/js/replay.js`.

- [ ] **Step 3: Implement the pure replay model**

Create the root module declaration first:

```json
{
  "private": true,
  "type": "module",
  "scripts": {
    "test:site": "node --test tests/test_replay_state.mjs"
  }
}
```

Then create the replay module:

```javascript
// docs/assets/js/replay.js
export const PHASES = ["baseline", "fault", "detected", "confirmed", "committed", "recovered"];

export function createReplayModel(runs, runId = runs[0]?.id) {
  if (!Array.isArray(runs) || runs.length === 0) throw new Error("At least one C3 run is required");
  if (!runs.some((run) => run.id === runId)) throw new Error(`Unknown run: ${runId}`);
  return { runs, runId, stateIndex: 0, playing: false, speedMs: 1300 };
}

export function selectRun(model, runId) {
  if (!model.runs.some((run) => run.id === runId)) throw new Error(`Unknown run: ${runId}`);
  return { ...model, runId, stateIndex: 0, playing: false };
}

export function setState(model, index) {
  if (!Number.isInteger(index) || index < 0 || index >= PHASES.length) throw new RangeError(`Invalid replay state: ${index}`);
  return { ...model, stateIndex: index };
}

export function deriveScene(model) {
  const run = model.runs.find((candidate) => candidate.id === model.runId);
  const recovered = model.stateIndex >= 4;
  const faultActive = model.stateIndex >= 1 && !recovered;
  const edgeClasses = {};
  for (const id of ["a0", "a1", "a2", "a3"]) edgeClasses[id] = `edge${recovered ? "" : " route-a"}${id === "a2" && faultActive ? " fault" : ""}`;
  for (const id of ["b0", "b1", "b2", "b3"]) edgeClasses[id] = `edge${recovered ? " route-b" : ""}`;
  return {
    phase: PHASES[model.stateIndex],
    retention: model.stateIndex === 0 ? 1 : model.stateIndex < 5 ? run.fault_retention : run.post_recovery_retention,
    route: recovered ? "B" : "A",
    version: recovered ? 1 : 0,
    gate: run.gate,
    faultActive,
    edgeClasses,
    run,
  };
}
```

- [ ] **Step 4: Run replay tests**

Run: `node --test tests/test_replay_state.mjs`

Expected: four tests PASS.

- [ ] **Step 5: Review the task diff and stop at the commit gate**

Run: `git diff -- docs/assets/js/replay.js tests/test_replay_state.mjs package.json`

Expected: pure deterministic state transitions with no DOM dependency. Ask Sophie before committing.

---

### Task 5: Browser Application, Translation, Replay, and Evidence Explorer

**Files:**
- Modify: `docs/assets/js/app.js`
- Modify: `docs/index.html`
- Modify: `tests/test_site_structure.py`

**Interfaces:**
- Consumes `loadDemoData()`, `createReplayModel()`, `selectRun()`, `setState()`, and `deriveScene()`.
- Produces DOM functions `renderReplay`, `renderEvidence`, `renderNarrative`, `setLanguage`, `showDataError`, and `start`.
- Stores only the selected language under local-storage key `limer-language`.

- [ ] **Step 1: Add failing static contracts for controls and bilingual copy**

```python
def test_app_contains_required_interactions_and_translation_keys(self):
    app = (ROOT / "docs/assets/js/app.js").read_text(encoding="utf-8")
    for required in (
        "renderReplay",
        "renderEvidence",
        "setLanguage",
        "showDataError",
        'localStorage.setItem("limer-language"',
        'document.documentElement.lang = language',
        'addEventListener("click"',
        'addEventListener("input"',
        'addEventListener("change"',
    ):
        self.assertIn(required, app)
    self.assertIn('"hero.title"', app)
    self.assertIn('"roadmap.standby.title"', app)
    self.assertIn('"feedback.telemetry"', app)
```

- [ ] **Step 2: Run the app contract test and verify it fails**

Run: `python3 -m unittest tests.test_site_structure.SiteStructureTests.test_app_contains_required_interactions_and_translation_keys -v`

Expected: FAIL because `app.js` contains only the initial loader.

- [ ] **Step 3: Implement translations and data failure behavior**

Add the bilingual dictionary below to `app.js`. These are the fixed static keys; generated cards use the same `language` value to select their English or Chinese fields. Implement language selection and the visible error boundary:

```javascript
const translations = {
  en: {
    "nav.demo": "Demo",
    "nav.evidence": "Evidence",
    "nav.roadmap": "Roadmap",
    "hero.eyebrow": "Stage review · CPU/Mininet emulation",
    "hero.title": "A link can stay UP while collective performance collapses.",
    "hero.body": "LIMER detects a switch-facing signal, confirms end-host impact, and coordinates a move to a healthy fabric.",
    "hero.action": "Replay the archived incident",
    "demo.title": "Archived C3 incident replay",
    "architecture.title": "What the CPU prototype implements",
    "evidence.title": "Evidence explorer",
    "boundaries.title": "Interpretation boundary",
    "roadmap.title": "Prioritized next steps",
    "roadmap.standby.title": "Isolate standby-path variance",
    "roadmap.confirmation.title": "Reduce confirmation delay",
    "roadmap.scope.title": "Expand fault and platform scope",
    "feedback.title": "Feedback requested",
    "feedback.telemetry": "Which production telemetry target should be integrated first?",
    "feedback.redundancy": "Does the healthy second-fabric assumption match the intended deployment setting?",
    "feedback.order": "Should the next milestone prioritize the gray-loss matrix or GPU/NCCL integration?",
  },
  zh: {
    "nav.demo": "演示",
    "nav.evidence": "证据",
    "nav.roadmap": "下一步",
    "hero.eyebrow": "阶段性研究汇报 · CPU/Mininet 仿真",
    "hero.title": "链路保持 UP，集体通信性能仍可能骤降。",
    "hero.body": "LIMER 先捕获交换机侧信号，再确认端侧影响，并协调所有 worker 切换到健康 fabric。",
    "hero.action": "回放归档实验",
    "demo.title": "C3 归档事件回放",
    "architecture.title": "CPU 原型已经实现了什么",
    "evidence.title": "实验数据浏览器",
    "boundaries.title": "结论边界",
    "roadmap.title": "优先 next steps",
    "roadmap.standby.title": "隔离备用路径的性能波动",
    "roadmap.confirmation.title": "缩短端侧确认延迟",
    "roadmap.scope.title": "扩展故障类型与平台范围",
    "feedback.title": "希望获得的方向反馈",
    "feedback.telemetry": "下一阶段应优先接入哪种生产级遥测接口？",
    "feedback.redundancy": "健康第二张 fabric 的假设是否符合目标部署场景？",
    "feedback.order": "下一里程碑应优先做 gray-loss matrix，还是 GPU/NCCL 集成？",
  },
};

let language = (() => {
  try { return localStorage.getItem("limer-language") || (navigator.language.startsWith("zh") ? "zh" : "en"); }
  catch { return navigator.language.startsWith("zh") ? "zh" : "en"; }
})();

export function setLanguage(nextLanguage) {
  language = nextLanguage === "zh" ? "zh" : "en";
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = translations[language][node.dataset.i18n];
  });
  try { localStorage.setItem("limer-language", language); } catch {}
  renderNarrative();
}

export function showDataError(error) {
  const panel = document.querySelector("#data-error");
  panel.hidden = false;
  panel.textContent = language === "zh" ? "归档实验数据加载失败，交互控件已停用。" : "Archived experiment data failed to load; interactive controls are disabled.";
  document.querySelectorAll("#demo button, #demo select, #demo input, #evidence button").forEach((control) => { control.disabled = true; });
  console.error(error);
}
```

- [ ] **Step 4: Implement the interactive replay renderer**

`renderReplay()` must build the approved SVG using the eight exact paths from Task 3, render six clickable events, and update state through only the pure functions from `replay.js`. Bind:

```javascript
playButton.addEventListener("click", togglePlayback);
restartButton.addEventListener("click", () => updateModel(setState({ ...model, playing: false }, 0)));
scrubber.addEventListener("input", (event) => updateModel(setState({ ...model, playing: false }, Number(event.target.value))));
runSelect.addEventListener("change", (event) => updateModel(selectRun(model, event.target.value)));
speedSelect.addEventListener("change", (event) => { model = { ...model, speedMs: Number(event.target.value) }; scheduleNextState(); });
eventList.addEventListener("click", (event) => {
  const row = event.target.closest("[data-state-index]");
  if (row) updateModel(setState({ ...model, playing: false }, Number(row.dataset.stateIndex)));
});
```

`updateModel()` must set every path with `path.setAttribute("class", scene.edgeClasses[id])`, update the route/version label, set the retention bar width, announce the phase through an `aria-live="polite"` node, and show archived measured times from the selected run.

- [ ] **Step 5: Implement the evidence explorer and narrative cards**

`renderEvidence()` must render six condition tabs, a horizontal `0-1.2` retention scale, every raw retention point, the median, and `gate_pass_count/run_count`. C3/C4 display a fixed vertical `0.9` gate marker. Selecting a condition updates the chart and a bilingual explanation without reloading data.

`renderNarrative()` must render:

- three implemented-versus-required architecture cards;
- five explicit boundary cards from `payload.boundaries`;
- the three roadmap tracks from the approved spec;
- three general feedback questions with no organization-specific wording.

- [ ] **Step 6: Initialize the app and wire the language toggle**

```javascript
export async function start() {
  try {
    payload = await loadDemoData();
    model = createReplayModel(payload.c3_runs, "c3_rep01");
    renderReplay();
    renderEvidence("C3");
    setLanguage(language);
    document.querySelector("#language-toggle").addEventListener("click", () => setLanguage(language === "en" ? "zh" : "en"));
  } catch (error) {
    showDataError(error);
  }
}

start();
```

- [ ] **Step 7: Run app, replay, and evidence checks**

Run:

```bash
node --check docs/assets/js/app.js
node --check docs/assets/js/replay.js
node --test tests/test_replay_state.mjs
python3 -m unittest tests.test_site_structure -v
```

Expected: JavaScript syntax checks succeed; all Node and Python tests PASS.

- [ ] **Step 8: Review the task diff and stop at the commit gate**

Run: `git diff -- docs/index.html docs/assets/js/app.js tests/test_site_structure.py`

Expected: full bilingual replay, evidence explorer, architecture, boundaries, roadmap, and feedback. Ask Sophie before committing.

---

### Task 6: GitHub Pages Workflow and Reader Entry Point

**Files:**
- Create: `.github/workflows/pages.yml`
- Modify: `README.md:1-20`
- Modify: `tests/test_site_structure.py`

**Interfaces:**
- Consumes the complete static directory `docs/`.
- Produces a Pages deployment artifact and `github-pages` environment deployment.

- [ ] **Step 1: Add failing workflow contract tests**

```python
def test_pages_workflow_uses_current_official_static_actions(self):
    workflow = (ROOT / ".github/workflows/pages.yml").read_text(encoding="utf-8")
    for required in (
        "actions/checkout@v4",
        "actions/configure-pages@v5",
        "actions/upload-pages-artifact@v3",
        "actions/deploy-pages@v5",
        "path: docs",
        "pages: write",
        "id-token: write",
    ):
        self.assertIn(required, workflow)

def test_readme_links_to_the_interactive_site(self):
    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    self.assertIn("Interactive project demo", readme)
    self.assertIn("https://sophie508.github.io/LIMER_draft/", readme)
```

- [ ] **Step 2: Run workflow tests and verify they fail**

Run: `python3 -m unittest tests.test_site_structure -v`

Expected: FAIL because `.github/workflows/pages.yml` and the README link do not exist.

- [ ] **Step 3: Add the official static Pages workflow**

```yaml
# .github/workflows/pages.yml
name: Deploy static content to Pages

on:
  push:
    branches: [main]
  workflow_dispatch:

permissions:
  contents: read
  pages: write
  id-token: write

concurrency:
  group: pages
  cancel-in-progress: false

jobs:
  deploy:
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    runs-on: ubuntu-latest
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      - name: Setup Pages
        uses: actions/configure-pages@v5
      - name: Upload site artifact
        uses: actions/upload-pages-artifact@v3
        with:
          path: docs
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v5
```

- [ ] **Step 4: Add the README entry point**

Insert immediately below the README title:

```markdown
> **Interactive project demo:** [https://sophie508.github.io/LIMER_draft/](https://sophie508.github.io/LIMER_draft/)
>
> The site is a bilingual, evidence-driven stage review of the archived CPU/Mininet prototype. It is not a live hardware experiment.
```

- [ ] **Step 5: Run workflow and structure tests**

Run: `python3 -m unittest tests.test_site_structure -v`

Expected: all tests PASS.

- [ ] **Step 6: Review the task diff and stop at the commit gate**

Run: `git diff -- .github/workflows/pages.yml README.md tests/test_site_structure.py`

Expected: current official Pages action majors, `docs/` artifact scope, accurate README wording. Ask Sophie before committing.

---

### Task 7: Full Verification and Reviewable Diff

**Files:**
- Verify all files created or modified in Tasks 1-6.
- Do not modify `results/`.

**Interfaces:**
- Produces a local verification record and a complete unstaged diff for Sophie.

- [ ] **Step 1: Rebuild and check the derived data**

Run:

```bash
python3 scripts/build_demo_data.py --write
python3 scripts/build_demo_data.py --check
```

Expected: `demo-data.json matches archived evidence`.

- [ ] **Step 2: Run all automated verification**

Run:

```bash
python3 -m unittest discover -s tests -v
python3 -m py_compile limer_v0/*.py tests/*.py scripts/*.py
node --check docs/assets/js/app.js
node --check docs/assets/js/replay.js
node --test tests/test_replay_state.mjs
```

Expected: existing 51-test baseline remains passing with the known macOS loopback skip if local bind is denied; new Python and Node tests PASS; compile and syntax checks exit 0.

- [ ] **Step 3: Serve and inspect the site locally**

Run from the repository root: `python3 -m http.server 8000 --directory docs`

Inspect `http://localhost:8000/` at desktop and mobile widths. Verify:

- Chinese/English switching updates all visible and accessibility text.
- Play, pause, restart, speed, scrubber, event rows, and run selector work.
- SVG edges land on worker/fabric ports without crossing boxes; only the degraded A edge becomes red dashed.
- `rep01` ends at `0.971 PASS`; `rep02` at `0.853 FAIL`; `rep03` at `0.865 FAIL`.
- C0-C5 explorer shows 18 runs, 16/18 gate passes, and C3 1/3.
- Data-load failure shows a visible bilingual error and disables controls.
- Keyboard focus is visible and reduced-motion mode remains understandable.

- [ ] **Step 4: Check evidence immutability and wording**

Run:

```bash
git diff --exit-code -- results
rg -n "Huawei|华为|Live simulation|live simulation" docs README.md
git diff --check -- . ':!results/*.csv'
```

Expected: no `results/` diff; wording search returns no matches; whitespace check exits 0.

- [ ] **Step 5: Show the complete diff and status**

Run:

```bash
git status --short
git diff --stat
git diff -- . ':!results'
```

Expected: only the approved website, builder, tests, workflow, README, `.gitignore`, design, and plan files. `.superpowers/` must be ignored and absent from status.

- [ ] **Step 6: Stop before commit and push**

Present the complete diff summary and verification evidence to Sophie. Commit only after explicit approval. After an approved commit, ask separately before any `git push`. A successful push will trigger the Pages deployment workflow; verify its deployed URL only after push approval and workflow completion.
