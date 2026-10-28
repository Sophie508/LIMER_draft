# Detection and Switching Benefit Implementation Plan

> Execute inline with independent module workers, following executing-plans. User authorization covers implementation and experiments, but no commit or push.

**Goal:** Implement and measure timely detection and cost-aware replacement on the collaborator's real packet simulator.
**Architecture:** Versioned pure C++/Python detector and decision modules, integrated into existing RDMA events, with independently replayed observations and a frozen paired native campaign.
**Tech Stack:** C++ ns-3/RDMA, Python standard library, Linux Docker on otakotak.

## Global Constraints
- No injector truth or future-state inputs to online algorithms.
- Each eligible fault condition: >=95% correctly localized <100ms, late/miss/error retained.
- Preserve physical planes, resource credits, ACK prefix and epoch completion invariants.
- Native experiment efficacy must be reported separately from unit test success.
- No commit/push; prepare reviewable diff only.

### Task 1: Isolate and provision
- [x] Preserve original source and create working copy.
- [x] Provision isolated server source/build/results directories and compile a fresh backend.
- [x] Record initial source hashes; preserve legacy reference data unchanged.

### Task 2: Detection module
Files: src/simulator/detection/service_detector.h; python/limerlab/detector/service_detector.py; tests/test_service_detector.py.
- [x] Implement submit(path,token,now,bytes), complete(path,token,now), advance(now), deterministic baseline and evidence window.
- [x] Test startup calibration, isolated benign delays, persistent weak evidence, outstanding deadlines, late ACKs and timestamp validity.
- [x] Integrate canary transfer generation, raw events, alarms, actual wire accounting and independent replay.

### Task 3: Benefit module
Files: src/simulator/recovery/benefit_policy.h; python/limerlab/benefit_policy.py; tests/test_benefit_policy.py.
- [x] Implement stay/switch completion estimates, unknown/stale evidence, real coordination/final ACK cost and benefit margin.
- [x] Test slow alternate, short remaining work, absent service, absent candidate sample and break-even.
- [x] Integrate measured ACK windows and paid full-route probe timing; record and independently replay decisions.

### Task 4: Native development
- [x] Freeze per-attempt inputs and run paired healthy/weak-loss/quarter/blackhole cases.
- [x] Diagnose mismatches from actual event logs; retain all development attempts.
- [x] Check physical/logical audit plus independent detector and policy replay.

### Task 5: Frozen validation and handoff
- [x] Register validation seeds and code/parameter/binary hashes before execution; correct the discovered derived loss-stream reuse with a separate prospective cohort.
- [x] Execute per-condition detection and paired policy tests, including negative boundaries.
- [x] Report timely/late/miss/error, false alarms, overhead and completion times without dropping failures.
- [x] Produce source diff, reproducible commands and bounded results for user review.

## Retained deviations and new validation

- `validation-v1` is retained as a failed canary-service-v3 validation: the
  quarter-capacity group had 42/60 timely trials and 18 missed directions.
  The remaining boundary runs also encountered the account's /home hard quota;
  damaged outputs are preserved separately and cannot become successes.
- v4 adds receiver-local whole-path full-payload spacing, after single-canary
  train analysis exposed healthy QP-interleaving confounding. Raw packet replay
  verifies every calibration/10 ms P10 window and its payload provenance.
- New held-out seeds use explicit base 102990000, disjoint from all v1 seeds.
  Four v1 misses are used only as declared development regressions.
- Hash-verified raw archives can be relocated to personal scratch with symlinks.
  New archives use level-6 gzip and prune six redundant raw-workspace copies
  only after member verification. Infrastructure preservation is not scientific
  verification of the damaged experiments.
- The inherited `seed + node` loss mapping reuses stream pairs under the old
  consecutive-seed schedule. Keep all 580 v2 cases unchanged, and preregister a
  separate 60-case benefit-only weak-loss confirmation with base 103100000 and
  stride 32. No native algorithm, detector parameter, policy or workload changes.
  Final detection uses that cohort for weak loss, without pooling old/new counts;
  all policy pairs remain the main matrix's empirical comparisons.
