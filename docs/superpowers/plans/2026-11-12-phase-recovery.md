# Phase-scoped Recovery Implementation Plan

**Goal:** Repair round-boundary eligibility and measure genuine new B-prime work without changing the detection deadline or hiding costs.
**Architecture:** Preserve the historical persistent mode and add a phase-scoped binding lifecycle. Extend immutable case parameters, independent auditors and per-phase metrics together. Run explicit frozen development comparisons on otakotak.
**Tech Stack:** Python standard library, C++ ns-3/RDMA, Linux Docker.

## Global Constraints
- No commit or push before Sophie reviews the diff.
- Historical results remain unchanged; all new output directories are new.
- Detection strictly below 100 ms; job horizon is a distinct parameter.
- Chunk-level allocation, packet-level backend; no tensor-reduction claim.

## Tasks
- [x] Regression: compile a small native lifecycle test against the actual reset function; first prove current code leaves B disabled and skips fresh phase gate checks.
- [x] Add explicit `replacement_lifetime` and `phases_per_round` to config/CLI/runner/native status. Add `A_ONLY` as a business-only single-lane control with unchanged topology/detector load.
- [x] Implement phase reset in scheduling, guard callbacks with fresh versions, keep original alarm lifetime, and require full phase coordination and gate authorization. Log zero-wire RESET_TO_AB state transitions.
- [x] Update `audit.py` retirement and coordination checks to phase scope. Test accepted reset, rejected direct B after same-phase commit, missing next-phase coordination and missing benefit authorization.
- [x] Extend metrics with per-phase reset/activation timelines, A/B/B-prime fresh allocation and completion, and drained pending work at activation. Keep rescued chunks separate.
- [x] Freeze a development matrix before execution: old short persistent/phase cases, longer opportunity cases, healthy/A_ONLY, G00/G10/G01/G11, always/benefit, plus matched faults and helpers. Store every failed attempt.
- [x] Run unit checks locally; build in a new remote directory. Run small native checks before longer/full-ring cases, with quota-aware concurrency and streamed verified archives.
- [x] Export compact results, write meeting-to-code explanation, collect a reviewable patch and run `git diff --check`. Stop before commit/push.
