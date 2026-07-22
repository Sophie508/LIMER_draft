# LIMER Advisor Reading Path Expansion Design

## Purpose

Expand the bilingual GitHub Pages stage review so an advisor can understand
how to operate the archived replay, what the CPU prototype actually implements,
and how the completed work maps to both the initial milestone requirements and
the formal LIMER research objectives.

The revision keeps the current clean academic visual language and evidence
discipline. It adds explanatory depth without presenting the CPU prototype as
the complete LIMER system.

## Audience and Reading Outcome

The primary reader is a research advisor or technical reviewer who has not
read the repository. After one scroll, the reader should be able to answer:

1. What still-up gray degradation is being demonstrated?
2. How can the archived C3 run be explored interactively?
3. Which tools and source files implement each part of the CPU prototype?
4. Which initial milestone requirements have been delivered?
5. How far does the prototype progress toward formal objectives O1-O4?
6. Which gaps directly motivate the next experiments?

## Privacy and Attribution Boundary

The public page must not expose internal collaboration material. In
particular, it must not mention or reproduce:

- Notion or screenshots of an internal workspace;
- advisor, partner, or contact names;
- internal deadlines, contact-management notes, or meeting-note wording;
- organization-specific feedback or branding.

The two public mapping labels are:

- `Initial Milestone Requirements / 阶段任务要求`;
- `Formal Research Objectives / 正式研究目标`.

Only task-level requirements are extracted from the internal brief. The public
page explains what was required, what was delivered, and which repository
evidence supports the status.

## Revised Reading Path

The single-page order is:

1. Research problem and stage scope.
2. Guided archived incident replay.
3. Concrete CPU implementation trace.
4. C0-C5 evidence explorer.
5. Dual-layer requirements mapping.
6. Interpretation boundaries.
7. Derived next steps and requested feedback.

The sticky navigation links to Demo, Implementation, Evidence, Mapping, and
Next steps. The page remains a scrolling narrative rather than a tabbed lab
interface.

## Guided Incident Replay

The replay retains the three real C3 repeats and the existing playback model.
It adds an always-visible three-step guide:

1. Select an archived repeat.
2. Drag the timeline or click an event.
3. Observe the route, retention metric, and explanation change together.

The scrubber receives a visible `Draggable / 可拖动` affordance, a pointer icon,
and a short first-visit motion cue. The cue stops after the reader interacts and
is disabled when reduced motion is requested.

Each phase combines its technical event name with a plain-language sentence:

- baseline: Fabric A is healthy before injection;
- fault: rank 2 stays UP but is limited from 100 to 20 Mbit/s;
- detected: the switch-facing counter proxy observes persistent degradation;
- confirmed: the host gate confirms collective impact and standby health;
- committed: all four workers agree on one future route version;
- recovered: traffic completes on Fabric B and recovery retention is measured.

The section explicitly states that playback is visually compressed and the
displayed measurements come from archived evidence. Range input, event rows,
playback buttons, and left/right keyboard navigation all update one shared
replay state.

## CPU Implementation Trace

The existing three abstract architecture cards become a traceable
implementation section. A technology strip names the actual platform:

- Python 3;
- Mininet;
- Open vSwitch;
- Linux `tc/netem` and interface counters;
- framed TCP ring workload;
- JSON, JSONL, and CSV evidence artifacts.

Each implementation layer presents five fields: implemented behavior, tools,
source modules, evidence artifacts, and current boundary.

### Layer 1: switch-facing first signal

- Behavior: target 20 ms counter polling and a three-sample persistent-rate
  trigger.
- Source: `topology.py`, `qdisc.py`, `faults.py`, `sentinel.py`, and
  `orchestrator.py`.
- Evidence: `switch_timeseries.csv`, `events.jsonl`, and C2/C3 detection
  timings.
- Boundary: management-plane switch-facing proxy, not ASIC, P4, or a resident
  switch agent.

### Layer 2: end-host confirmation

- Behavior: evaluate switch suspicion, completed-round slowdown, and standby
  health to return confirm, suppress, or defer.
- Source: `refiner.py`, `metrics.py`, and `orchestrator.py`.
- Evidence: C3 confirmation, C5 suppression, and host-confirmation timings.
- Boundary: deterministic rule, not the proposed neuro-fuzzy and Gaussian
  Process model.

### Layer 3: coordinated recovery

- Behavior: four-rank prepare, READY, and commit at a shared round boundary.
- Source: `coordinator.py`, `state.py`, `worker.py`, `protocol.py`, and
  `orchestrator.py`.
- Evidence: `version_commits.csv`, `correctness.json`, and worker route/version
  records.
- Boundary: executable route-version protocol scaffold, not NCCL communicator
  reconstruction.

A fourth card explains experiment orchestration and reporting through
`configs/`, `orchestrator.py`, `report.py`, `results/`, and `tests/`. Source and
evidence names link directly to the public GitHub repository.

## Dual-Layer Mapping

Both mapping layers use a common four-part row:

`Requirement -> Current delivery -> Evidence -> Status`.

Statuses use accessible text and color, with three values:

- `Delivered`: the bounded phase requirement is satisfied;
- `Partial`: an executable proxy or scaffold exists, but the formal objective
  is not complete;
- `Not started`: the formal mechanism has not been implemented.

### Initial Milestone Requirements

The public task-level rows are:

1. Understand and bound the problem: delivered through the documented gray
   failure question, architecture, experiment semantics, and limitations.
2. Lock the first-stage scope: delivered as one AllReduce-like scenario on a
   simulation platform using controlled synthetic fault injection.
3. Review related work and choose an emulation platform: delivered through a
   separate background review and the selection of Mininet plus Open vSwitch;
   the review corpus is not reproduced in this public code artifact.
4. Build a small network and communication demo: delivered through four
   Mininet namespaces, OVS fabrics, and a framed TCP ring.
5. Inject a still-up network fault: delivered through rank 2 bandwidth
   degradation from 100 to 20 Mbit/s with both endpoints UP.
6. Observe and record impact signals: delivered through switch counters,
   timing, throughput, route/version, and correctness artifacts.
7. Produce initial experimental results: delivered as the predeclared C0-C5
   matrix with 18 runs and failed repeats retained.

Literature-review notes and internal planning documents are not reproduced in
the public artifact. The page does not imply that absence from the website
means the background work did not occur.

### Formal Research Objectives O1-O4

- O1 Lightweight in-network monitoring: `Partial`. The prototype implements a
  switch-facing counter interface and high-recall trigger, but not a
  switch-resident implementation or resource budget.
- O2 Uncertainty-informed fault detection: `Partial`. The control boundary and
  deterministic confirm/suppress behavior exist, but the neuro-fuzzy model,
  GP uncertainty, trained fault classes, and calibrated accuracy do not.
- O3 Rapid topology recovery: `Partial`. A versioned all-rank route handover to
  a pre-existing healthy fabric is executable, but GPU/NCCL communicator
  recovery is not implemented.
- O4 Online self-evolution: `Not started`. There is no weak supervision,
  pseudo-labeling, or online model update in CPU v0.

The mapping must never summarize O1-O4 as complete. It should make partial
progress legible while preserving the formal research gap.

## Evidence and Next-Step Linkage

The existing evidence explorer remains before the mapping so the reader sees
the measurements that support each status. Mapping evidence links may target
code, architecture documents, aggregate results, or a representative raw run.

The roadmap is explicitly derived from remaining gaps:

1. Stabilize and explain C3 recovery variance while keeping the fixed 0.9 gate.
2. Replace whole-round confirmation with step-level evidence.
3. Add orthogonal gray-loss conditions.
4. Replace the switch-facing proxy with realistic telemetry and measure its
   resource cost.
5. Implement and evaluate the proposed classifier and uncertainty layer.
6. Move from the TCP route scaffold to numerical collective and GPU/NCCL
   recovery only after the CPU controls are understood.

## Responsive and Accessible Behavior

- Desktop mapping rows use aligned columns; narrow screens stack the same four
  labeled fields.
- File links show readable paths and visible focus states.
- Status is never encoded by color alone.
- The scrubber guidance remains readable without motion.
- Language switching covers all new headings, labels, explanations, status
  text, link labels, and accessibility descriptions.
- Critical implementation and mapping content is visible by default. Only long
  file lists may use disclosure controls.

## Data and Code Boundaries

No archived result is edited. Existing `demo-data.json` remains the numeric
source for the replay and evidence explorer. Implementation and mapping content
is static bilingual metadata in the site code because it describes repository
structure rather than derived measurements.

If a referenced source path is missing, automated tests fail. The page does not
invent a replacement link or silently downgrade the status.

## Verification

The implementation is complete only after:

1. Existing Python and JavaScript tests pass.
2. New structure tests verify the interaction guidance, implementation trace,
   dual mapping headings, O1-O4 statuses, and privacy boundary.
3. Every linked repository source path exists locally.
4. Static bilingual keys are complete in both languages.
5. The website contains no organization names, Notion references, internal
   deadlines, advisor names, or contact details.
6. The replay still supports run switching, playback, dragging, event clicking,
   and keyboard navigation.
7. The site is served locally and the HTML, CSS, JavaScript, and evidence JSON
   return HTTP 200.
8. The full working-tree diff is shown for review before any commit.
