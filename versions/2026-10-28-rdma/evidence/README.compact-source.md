# Research evidence index — 2026-10-28

This directory contains compact evidence, not the full raw-packet archives or native binaries.

| Campaign | Registered / execution-and-replay verified | Role |
| --- | ---: | --- |
| validation-v2 | 580 / 580 | Frozen main matrix; all internal policy pairs |
| validation-loss-independent-v4 | 60 / 60 | Prospective, non-reused loss streams; final weak-loss detection row |
| validation-v1 | 580 / 530 | Retained earlier failure: 18 quarter-capacity misses and 50 infrastructure errors |

The new 640 valid runs do not mean that every communication job completed. Unfinished controls remain in the policy table. Do not pool the two weak-loss cohorts. The old main weak-loss schedule reused derived RNG streams; its policy results are retained as empirical matched comparisons.

Start with [the final report](../docs/results/validation-final/README.md),
[conditions](../docs/research_conditions.md), and
[implementation handoff](../docs/research_handoff.md).

## Frozen inputs and timing

Each campaign retains registration, cases, attempts, frozen scoring/tooling, compact run logs, trial tables, and aggregates. Main plan SHA-256:
`67b754bd64d590b1d66d8357f5157a9bf3b75779f25d51b872e7ac2fd6e6b5e6`.
Independent-loss plan SHA-256:
`30c4cad6ee5fda1a90031ee01f821331e47cebca266848bdb2dd75f115072dba`.

The supplementary registration preceded the first main weak-loss result; the filesystem/process trace is retained in `verification/confirmation-timing.json`. It is a timing trace, not a signed timestamp authority. Native rules, parameters, workload, and core audit hashes are unchanged between the two final campaigns.

## Verification scopes

- `verification/server-validation-v2.json` and `server-validation-loss-independent-v4.json`: all 580 + 60 runs, full archive digests and native binary checked.
- `verification/local-validation-v2.json` and `local-validation-loss-independent-v4.json`: compact-only verification; raw archives and binaries explicitly skipped.
- `verification/server-validation-v1.json` and `local-validation-v1.json`: expected failure reports; 530 valid and 50 infrastructure errors, not a passing campaign.
- `verification/unit-tests-final.log` and `.exit`: 140 tests at native validation.
- `verification/unit-tests-review-20261028.log` and `.exit`: current source, 142 tests passed after the report portability fix.
- Final `report.json` records `frozen_aggregate_replay_checked=true`: retained trial, pair, and summary aggregates were regenerated using each campaign's frozen scorer and compared without overwriting the originals.

## Raw data and storage

All valid scientific archives remain on otakotak under
`/home/suliu/LIMER_RESEARCH_2026-10-28/results/`, with some hash-verified symlinks into
`/home/suliu/scratch/LIMER_RESEARCH_2026-10-28/`.
The native build is `/home/suliu/LIMER_RESEARCH_2026-10-28/build-v7/`.
Storage relocation receipts are in `verification/storage/`.

A small subset of infrastructure-damaged forensic backups was relocated to
`/Users/sophie/Documents/LIMER_COLLAB_REVIEW_2026-10-28/infrastructure_failure_archives/`
after local and server SHA-256 checks. These backups are excluded from this compact package; their original locations and new paths are recorded in the relocation receipt. They are not valid scientific runs.

For local compact verification, run from the project root:

```bash
python3 tools/verify_research.py research_evidence/validation-v2 --skip-archives
python3 tools/verify_research.py research_evidence/validation-loss-independent-v4 --skip-archives
```

To repeat raw packet audits, retrieve the corresponding archive from otakotak first. Compact verification is not a replacement for full archive verification.
