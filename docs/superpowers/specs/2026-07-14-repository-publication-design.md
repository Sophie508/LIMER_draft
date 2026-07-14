# LIMER CPU Prototype Repository Publication Design

**Date:** 2026-07-14
**Repository:** `Sophie508/LIMER_draft`
**Status:** Approved for implementation

## Purpose

Publish a self-contained, reviewable snapshot of the current CPU-only LIMER
prototype. A new reader should be able to understand the experiment, inspect
the implementation and raw evidence, and reproduce it on a suitable Linux
host without seeing the wider private research archive.

## Selected structure

```text
LIMER_draft/
├── README.md
├── .gitignore
├── limer_v0/
├── configs/
├── tests/
├── results/
├── docs/
│   ├── architecture.md
│   ├── experiment_design.md
│   ├── current_limitations.md
│   └── superpowers/
└── environment_probe.txt
```

The repository keeps the already-tested flat import and command paths. It does
not refactor the prototype into an installable package in this publication
step, because that would change the artifact being reported and require a new
experiment cycle.

`LICENSE` is intentionally omitted until the project owners choose one; this
publication step does not silently assign rights.

## Included evidence

- Python implementation under `limer_v0/`.
- C0-C5 JSON configurations.
- Unit and integration tests.
- The valid 18-run matrix: three clean topology lifecycles per condition.
- Aggregate JSON/CSV summaries and SVG plots generated from those runs.
- Environment probe and concise architecture, experiment, and limitation
  documents.

## Explicit exclusions

- `results_pre_audit_same_qdisc_2026-07-14/`, because the detector and injector
  observed the same qdisc in that superseded experiment.
- Proposal files, sponsor documents, literature-review attachments, and other
  private research-archive material.
- Server credentials, SSH material, caches, bytecode, macOS metadata, and
  temporary archives.

## Claim boundaries

The README must describe a CPU/Mininet emulation, not a complete LIMER system.
The workload is framed TCP Ring AllReduce-like traffic, not numerical
AllReduce, NCCL, RDMA, a GPU training run, or Huawei hardware. The switch-side
detector is an off-switch management-plane proxy that reads a switch-facing
counter. C3/C4 recovery assumes a healthy second fabric.

All measured failures remain visible. The headline result is 16/18 condition
gates, with C3 passing 1/3 repeats at the fixed 0.9 recovery-retention gate.
The repository must not convert this into an overall pass.

## Publication workflow

Because the remote repository is empty, create its first commit on `main`.
Before committing, stage only the approved files, run the full verification
suite and a credential scan, and show the complete staged diff to Sophie.
Commit and push only after her explicit post-diff approval. The commit must be
authored only by Sophie and contain no AI attribution or co-author trailer.
