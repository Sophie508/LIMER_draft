# LIMER Advisor Reading Path Expansion Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Expand the bilingual LIMER stage-review site with guided replay affordances, a source-linked CPU implementation trace, and privacy-safe dual requirements mapping.

**Architecture:** Keep the zero-dependency single-page site and its existing replay state model. Extend `app.js` with bilingual structured metadata and focused render functions, extend the existing CSS design system, and add structural tests that validate copy, source paths, privacy constraints, and interactions.

**Tech Stack:** Static HTML, CSS, browser-native ES modules, Python `unittest`, Node.js test runner, GitHub Pages.

## Global Constraints

- Preserve the single scrolling narrative and clean academic visual language.
- Do not expose Notion, internal workspace screenshots, names, contacts, deadlines, organization-specific feedback, or branding in the public site.
- Use `Initial Milestone Requirements / 阶段任务要求` and `Formal Research Objectives / 正式研究目标` as the public mapping labels.
- Keep archived results immutable and retain all failed repeats.
- Present O1-O3 as partial and O4 as not started; never imply full LIMER completion.
- Keep every new reader-facing label bilingual.
- Do not add runtime dependencies.
- Do not commit until Sophie has reviewed and approved the complete diff; do not push without a separate explicit approval.

---

### Task 1: Add tests for the expanded advisor reading path

**Files:**
- Modify: `tests/test_site_structure.py`

**Interfaces:**
- Consumes: final static HTML, CSS, and JavaScript source text.
- Produces: regression checks for required sections, affordances, mapping statuses, source links, and privacy boundaries.

- [ ] **Step 1: Add failing structural tests**

Add test methods that assert:

```python
def test_navigation_exposes_implementation_and_mapping(self):
    self.assertIn('href="#implementation"', self.index)
    self.assertIn('href="#mapping"', self.index)

def test_replay_has_visible_interaction_guidance(self):
    for token in ("replay-guide", "drag-hint", "ArrowLeft", "ArrowRight"):
        self.assertIn(token, self.app)

def test_implementation_trace_links_source_and_evidence(self):
    for token in (
        "implementation-stack",
        "limer_v0/sentinel.py",
        "limer_v0/refiner.py",
        "limer_v0/coordinator.py",
        "results/c3_rep01/events.jsonl",
    ):
        self.assertIn(token, self.app)

def test_dual_mapping_preserves_formal_status_boundary(self):
    for token in (
        "Initial Milestone Requirements",
        "Formal Research Objectives",
        'objective: "O1"',
        'objective: "O4"',
        'status: "not-started"',
    ):
        self.assertIn(token, self.app)
```

Extend the public-copy privacy scan to reject `Notion`, internal deadline text,
names from the supplied internal note, and organization-specific terms in
`docs/index.html` and `docs/assets/js/app.js`. Do not scan design/plan documents,
which record the privacy requirement itself.

- [ ] **Step 2: Add repository-link target validation**

Extract every `repoLink("...")` literal from `app.js`, resolve it against the
repository root, and assert that the path exists. This covers source modules,
documentation, and evidence artifacts without making network requests.

- [ ] **Step 3: Run the focused test and confirm failure**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
```

Expected: new tests fail because the expanded sections and tokens do not yet
exist.

---

### Task 2: Add guided replay affordances

**Files:**
- Modify: `docs/assets/js/app.js`
- Modify: `docs/assets/css/site.css`
- Test: `tests/test_site_structure.py`
- Test: `tests/test_replay_state.mjs`

**Interfaces:**
- Consumes: existing `ReplayModel`, `PHASES`, and bilingual replay content.
- Produces: visible guide markup, draggable hint state, and keyboard phase navigation.

- [ ] **Step 1: Add bilingual replay-guide content**

Add exact content fields for:

```javascript
guideTitle: "How to explore this archived run",
guideSteps: [
  "Choose one real repeat",
  "Drag the timeline or select an event",
  "Watch the route, retention, and explanation update together",
],
dragHint: "Interactive · drag this timeline or select an event",
compressed: "Playback is visually compressed; displayed timings come from archived evidence.",
```

Add the equivalent Chinese copy using direct, non-jargon explanations.

- [ ] **Step 2: Render the guide and affordance**

In `renderReplay()`, place a `.replay-guide` block before the toolbar, add a
`.drag-hint` label associated with the range input, and add a plain-language
phase explanation beside the current phase metadata.

Use a `replayHasInteracted` boolean. Add `.is-pristine` to the scrubber wrapper
until the reader plays, drags, changes the run, or selects an event. The class
drives one subtle CSS motion cue and is removed permanently for the session
after first interaction.

- [ ] **Step 3: Add keyboard navigation**

Listen for `keydown` on the replay root. When the target is not a select or
button, `ArrowLeft` decrements the state index and `ArrowRight` increments it,
bounded to `0..PHASES.length - 1`. Re-render and restore focus to the scrubber.

- [ ] **Step 4: Add accessible CSS**

Style the guide as a restrained pale-blue instructional strip. Use numbered
guide items on desktop and stacked items on narrow screens. Add a small
horizontal cue to `.replay-scrubber.is-pristine input`; disable it inside the
existing `prefers-reduced-motion: reduce` block.

- [ ] **Step 5: Run replay-focused tests**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
node --test tests/test_replay_state.mjs
node --check docs/assets/js/app.js
```

Expected: all focused checks pass.

---

### Task 3: Replace abstract architecture cards with an implementation trace

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/assets/js/app.js`
- Modify: `docs/assets/css/site.css`
- Test: `tests/test_site_structure.py`

**Interfaces:**
- Consumes: bilingual implementation metadata and public repository paths.
- Produces: `renderImplementation()` and source-linked implementation cards.

- [ ] **Step 1: Rename and anchor the section**

Change section ID `architecture` to `implementation`, keep its number `02`, and
render into `#implementation-root`. Update the navigation link and bilingual
title to `What we built and where it lives / 我们具体实现了什么`.

- [ ] **Step 2: Add a repository-link helper**

Define:

```javascript
const REPOSITORY_BASE = "https://github.com/Sophie508/LIMER_draft/blob/main/";
const repoLink = (path) => `${REPOSITORY_BASE}${path}`;
```

All code and evidence links use this helper, open in a new tab, and include
`rel="noreferrer"` plus bilingual accessible text.

- [ ] **Step 3: Add the exact implementation metadata**

Create four bilingual records: switch-facing signal, end-host confirmation,
coordinated recovery, and experiment/report pipeline. Each record contains:

```javascript
{
  layer: "Layer 1",
  title: "Switch-facing first signal",
  behavior: "...",
  tools: ["Python 3", "Mininet", "Open vSwitch", "Linux counters"],
  files: ["limer_v0/topology.py", "limer_v0/qdisc.py", "limer_v0/faults.py", "limer_v0/sentinel.py", "limer_v0/orchestrator.py"],
  evidence: ["results/c3_rep01/switch_timeseries.csv", "results/c3_rep01/events.jsonl"],
  boundary: "Management-plane proxy, not resident switch logic.",
}
```

Use the source and evidence paths listed in the approved design for Layers 2-3
and the pipeline card.

- [ ] **Step 4: Render the technology strip and trace cards**

Render `.implementation-stack` followed by four `.implementation-card`
articles. Each card visibly labels `Built`, `Tools`, `Source`, `Evidence`, and
`Current boundary`; do not hide these fields in tabs or accordions.

- [ ] **Step 5: Style responsive source-linked cards**

Use a two-column card grid above 900 px and one column below. Render paths in a
monospace treatment with wrapping, visible hover/focus states, and no terminal
visual motif.

- [ ] **Step 6: Run focused tests**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
node --check docs/assets/js/app.js
```

Expected: implementation and repository-path tests pass.

---

### Task 4: Add privacy-safe dual requirements mapping

**Files:**
- Modify: `docs/index.html`
- Modify: `docs/assets/js/app.js`
- Modify: `docs/assets/css/site.css`
- Test: `tests/test_site_structure.py`

**Interfaces:**
- Consumes: static bilingual milestone and O1-O4 mapping records.
- Produces: `renderMapping()` and seven milestone plus four formal-objective rows.

- [ ] **Step 1: Add the mapping section after evidence**

Insert section `#mapping` as section `04`. Renumber Boundaries, Roadmap, and
Feedback to `05`, `06`, and `07`. Add the navigation link.

- [ ] **Step 2: Add milestone mapping records**

Create seven bilingual task records with status `delivered`:

1. Understand and bound the problem.
2. Lock the first-stage scope around one AllReduce-like simulation scenario.
3. Review related work and choose Mininet plus Open vSwitch for the bounded CPU prototype.
4. Build a small emulated network and communication workload.
5. Inject a still-up 100-to-20 Mbit/s fault.
6. Observe and record switch, timing, throughput, route, and correctness signals.
7. Produce a repeated C0-C5 evidence matrix with failed repeats retained.

Each record includes `requirement`, `delivery`, `evidence`, and `status`. Link
evidence to existing docs, source files, configs, and results.

- [ ] **Step 3: Add formal O1-O4 records**

Use exact status boundaries:

```javascript
[
  { objective: "O1", status: "partial", implemented: "Switch-facing counter proxy and persistent trigger", missing: "Switch-resident implementation and measured resource budget" },
  { objective: "O2", status: "partial", implemented: "Confirm/suppress control boundary", missing: "Neuro-fuzzy classifier, GP uncertainty, trained classes, and calibration" },
  { objective: "O3", status: "partial", implemented: "Versioned all-rank A-to-B route handover", missing: "Real GPU/NCCL communicator recovery" },
  { objective: "O4", status: "not-started", implemented: "No mechanism in CPU v0", missing: "Weak supervision, pseudo-labeling, and online adaptation" },
]
```

Add equivalent Chinese text without changing the status semantics.

- [ ] **Step 4: Render the two mapping layers**

Render separate headings for Initial Milestone Requirements and Formal Research
Objectives. Each row has visible labels for Requirement, Current delivery,
Evidence, and Status. Formal rows additionally distinguish `Implemented now`
from `Still required`.

Status pills include text (`Delivered`, `Partial`, `Not started`) and do not
depend on color alone.

- [ ] **Step 5: Derive roadmap copy from remaining gaps**

Expand the roadmap from three cards to six concise priorities in this order:
C3 variance, step-level confirmation, gray loss, realistic switch telemetry,
classifier/uncertainty implementation, then numerical collective and GPU/NCCL
recovery.

- [ ] **Step 6: Style desktop rows and mobile cards**

Use a four-column comparison grid on desktop. Below 760 px, stack each row and
show field labels so no relationship depends on horizontal alignment.

- [ ] **Step 7: Run mapping and privacy tests**

Run:

```bash
python3 -m unittest tests.test_site_structure -v
node --check docs/assets/js/app.js
```

Expected: mapping tokens, status boundaries, source paths, and public-copy
privacy checks pass.

---

### Task 5: Verify the complete site and prepare the review diff

**Files:**
- Modify only if verification reveals a scoped defect.

**Interfaces:**
- Consumes: complete working tree.
- Produces: fresh automated evidence, local HTTP checks, and a complete diff for Sophie.

- [ ] **Step 1: Run data and Python verification**

Run:

```bash
python3 scripts/build_demo_data.py --check
python3 -m unittest discover -s tests -v
python3 -m py_compile limer_v0/*.py tests/*.py scripts/*.py
```

Expected: generated data matches evidence; all tests pass except the existing
documented macOS loopback skip; compilation exits zero.

- [ ] **Step 2: Run JavaScript verification**

Run:

```bash
node --check docs/assets/js/app.js
node --check docs/assets/js/replay.js
node --test tests/test_replay_state.mjs
```

Expected: syntax checks exit zero and all replay-state tests pass.

- [ ] **Step 3: Check evidence immutability and diff quality**

Run:

```bash
git diff --exit-code -- results
git diff --check
```

Expected: no archived result changes and no whitespace errors.

- [ ] **Step 4: Serve and request all public assets**

Run `python3 -m http.server 8000 --directory docs` and verify HTTP 200 for:

- `/`;
- `/assets/css/site.css`;
- `/assets/js/app.js`;
- `/assets/js/replay.js`;
- `/assets/data/demo-data.json`.

- [ ] **Step 5: Review the final working-tree diff**

Inspect `git diff --stat`, `git diff --name-status`, and the complete patch.
Confirm only the spec, plan, page source, styling, and site tests changed.

- [ ] **Step 6: Stop before commit**

Present the complete diff and verification evidence to Sophie. Wait for explicit
approval before staging or committing. Ask separately before any push.
