# Research Release Implementation Plan

**Goal:** Deliver a versioned, runnable collaborator update with full compact experiment evidence in the existing repository.
**Architecture:** Preserve the old handoff, add an isolated `versions/2026-10-28-rdma/` package, and link it from the root README. Keep native source byte-identical to the reviewed working copy. Archive compact campaigns separately, with checksums and an extraction entry point.
**Tech stack:** Existing C++/Python simulator, standard-library packaging and Git worktree.

## Constraints

- No commit until Sophie reviews the concrete diff; ask before push.
- Sophie-only authorship; no coauthor trailer.
- No native algorithm, frozen input or experimental-result changes.
- Preserve 580 main + 60 independent-loss runs and the failed 580-attempt v1 separately.
- Raw packet archives remain on otakotak; describe compact-only verification explicitly.
- Do not include the unrelated untracked paper draft, credentials, build outputs or caches.

## Tasks

- [x] Copy runnable source and fixed dependencies; retain collaborator-relative patch and hashes.
- [x] Archive each compact campaign below GitHub's per-file limit, retain readable tables and verification receipts, and add checked extraction.
- [x] Include the current paper snapshot and a concise change/conditions/results guide; update the repository entry point.
- [x] Verify source identity, archive members, extracted evidence, 142 tests and final Git diff; present that exact diff for approval before commit/push.
