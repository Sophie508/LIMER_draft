# LIMER GitHub Pages Interactive Demo Design

## Purpose

Create a bilingual, interactive GitHub Pages site for a stage research review. The site should help a reviewer understand the gray-failure problem, replay the implemented CPU/Mininet prototype from archived evidence, inspect the current results without hiding failed repeats, and give useful feedback on the next research steps.

The site is a research-progress report, not a product launch. It must distinguish implemented behavior from final-system claims.

## Audience and Success Criteria

The primary audience is a technical reviewer or research advisor. A successful visit should leave the reviewer able to answer four questions:

1. What failure does LIMER address?
2. What closed-loop behavior has the current prototype implemented?
3. What do the 18 archived runs support, and where does C3 still fail?
4. Which next experiment or platform step should be prioritized?

## Scope

### In scope

- A static GitHub Pages site with no server-side dependency.
- Chinese and English content with a visible one-click language toggle.
- A real-data incident replay for all three C3 repeats.
- A C0-C5 evidence explorer based on the archived aggregate results.
- An architecture section that separates implemented proxies from intended research components.
- An explicit interpretation-boundary section.
- A prioritized next-steps section and general feedback questions.
- Responsive desktop and mobile layouts.
- Keyboard navigation, reduced-motion support, and clear chart labels.

### Out of scope

- A live Mininet experiment in the browser.
- A free-form simulator that invents results for arbitrary parameters.
- A claim of switch-resident, GPU, NCCL, RDMA, or numerical AllReduce validation.
- Editing or normalizing archived evidence files.
- Organization-specific branding or reviewer names.

## Narrative Structure

The page uses a single scrolling narrative:

1. **Project premise:** a link can remain `UP` while a synchronized workload loses most of its throughput.
2. **Interactive incident replay:** the reviewer advances through a real C3 run.
3. **What was built:** switch-facing signal, end-host confirmation, and coordinated route-version transition.
4. **Evidence explorer:** C0-C5 and all 18 runs, with C3 failures retained.
5. **Interpretation boundary:** what this CPU prototype does and does not prove.
6. **Prioritized next steps:** three concrete experiment tracks.
7. **Feedback requested:** general research-direction questions, with no organization-specific wording.

## Visual Direction

Use a clean academic style:

- white and light-gray surfaces;
- restrained blue as the primary interaction color;
- green for healthy or passing states;
- red only for faults and failed gates;
- blue for the recovered Fabric B state;
- chart-like typography and generous whitespace;
- no terminal, cyber-security, or product-marketing treatment.

The network replay uses SVG paths. Each edge is anchored to a worker and fabric port, and the two fabric route sets use explicit non-crossing paths. The degraded `w2 -> Fabric A` edge becomes a red animated dashed path. Fabric A is highlighted before recovery, and Fabric B is highlighted only after the versioned commit.

## Site Architecture

Use a zero-dependency static implementation under `docs/`:

```text
docs/
  index.html
  assets/
    css/site.css
    js/app.js
    data/demo-data.json
scripts/
  build_demo_data.py
tests/
  test_demo_data.py
```

GitHub Pages will publish the `docs/` site. The existing research documentation remains available at its current paths; the website does not replace it.

`scripts/build_demo_data.py` derives a compact browser payload from the existing immutable evidence:

- `results/aggregate_summary.json`;
- `results/c3_rep01/summary.json` through `c3_rep03/summary.json`;
- the corresponding C3 `events.jsonl` and `correctness.json` files.

The generated JSON is committed for static hosting, but every displayed numeric result remains traceable to a source path recorded in the payload. The builder never writes into `results/`.

## Components

### Navigation and language

The sticky navigation links to Overview, Demo, Evidence, Boundaries, and Roadmap. The language toggle switches all headings, labels, explanations, controls, accessibility text, and feedback questions. The initial language follows the browser locale and the explicit selection is remembered when local storage is available.

### Hero

The hero shows the concrete failure: rank 2's still-up link changes from 100 to 20 Mbit/s. It labels the artifact as a CPU/Mininet stage prototype and links directly to the replay.

### Incident replay

The replay defaults to `c3_rep01` and supports:

- run selection for `c3_rep01`, `c3_rep02`, and `c3_rep03`;
- play, pause, restart, and 1x/2x/4x visual playback speeds;
- a range scrubber and clickable event rows;
- six states: baseline, fault applied, switch suspect, host confirm, recovery commit, and recovered round complete;
- synchronized SVG topology, active route, matched-baseline retention, event log, and gate result.

Playback is visually compressed. Labels show the archived measured times rather than implying the animation duration is physical time. The module is always titled `Archived run replay`, never `Live simulation`.

### Evidence explorer

The explorer presents C0-C5 with the declared run count, median selected retention, raw retention points, and gate pass count. Selecting C3 exposes all three repeat values: `0.971`, `0.853`, and `0.865`. A fixed `0.9` reference line remains visible for C3/C4 recovery comparisons.

The page states the formal denominator before the result: 18 topology lifecycles, three per condition, with no failed repeat discarded.

### Architecture and boundaries

Each of the three layers has paired columns:

- implemented in CPU v0;
- required for the research system.

The boundary section explicitly covers AllReduce-like versus numerical AllReduce, management-plane counter proxy versus switch residency, CPU versus GPU/NCCL, the healthy Fabric B assumption, and the whole-round host-confirmation bottleneck.

### Roadmap and feedback

The roadmap preserves the current priorities:

1. Compare idle, keepalive, and pre-warmed standby B treatments while keeping the C3 `>= 0.9` gate fixed.
2. Replace whole-round waiting with step-level host evidence while retaining a transient suppression condition.
3. Add an orthogonal gray-loss matrix, then replace telemetry and workload proxies one boundary at a time before GPU/NCCL recovery work.

The feedback section asks general questions about telemetry target, redundancy assumptions, and the ordering of loss-matrix versus GPU/NCCL work. It contains no organization names.

## Data Flow

```text
immutable results JSON/JSONL
          |
          v
build_demo_data.py --check/--write
          |
          v
docs/assets/data/demo-data.json
          |
          v
app.js state model
          |
          +-- bilingual narrative
          +-- C3 SVG replay
          +-- C0-C5 evidence explorer
```

`--check` verifies that the committed browser payload matches the archived evidence. `--write` regenerates only the derived website payload.

## Error Handling

- If `demo-data.json` cannot load, disable replay and evidence controls and show a bilingual, visible data-load error.
- If an expected run or field is missing, display `Unavailable` rather than substituting a number.
- If local storage is unavailable, language switching still works for the current page session.
- Unknown replay events remain accessible in the source-evidence link but do not create invented visual states.
- Motion is disabled when `prefers-reduced-motion` is set; state changes remain visible without animation.
- All derived metrics are checked during data generation. A mismatch fails the build instead of silently rendering stale values.

## Verification

Before calling the site complete:

1. Run the existing Python unit suite and compile checks.
2. Add tests for exact C0-C5 counts, C3 timings, three recovery values, gate labels, and source-path traceability.
3. Run the data builder in `--check` mode.
4. Parse the final HTML and JSON and run JavaScript syntax checks.
5. Validate internal links and verify no organization-specific wording remains.
6. Serve `docs/` locally and test language switching, replay controls, run switching, event clicking, keyboard focus, reduced motion, and mobile layout.
7. Confirm the page shows 18 runs, 16/18 gates, C3 1/3, and zero checksum/version errors without presenting overall acceptance as a pass.

## GitHub Pages Delivery

The implementation will include the files required to publish the static site from the repository. Publishing remains a separate Git action: show the complete diff first, then commit only after explicit approval, and push only after a second explicit approval. Commits use Sophie's identity alone with no AI attribution or co-author trailer.
