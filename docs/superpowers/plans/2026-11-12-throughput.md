# Recovery throughput implementation plan

> Execute inline with executing-plans; no commit or push until user review.

Goal: improve matched whole-job throughput toward 70–80% of healthy while
preserving all prior evidence and cost/correctness requirements.

- [x] Read current project instructions, prior results, source and diagnostics.
- [x] Create isolated candidate source with an unchanged vendored dependency.
- [x] Add explicit completion and helper modes to validated CLI/config/native metadata.
- [x] Separate physical release from logical final notification, with a bounded
  32-chunk confirmation window and production-function resource regression tests.
- [x] Implement charged shared-helper lending with one borrowed credit and
  unchanged physical caps; preserve idle-only mode as the paired control.
- [x] Extend independent execution audit to reconstruct early releases, lending
  arrivals, own-traffic credit caps, final notifications and phase reset boundaries.
- [x] Build in a new otakotak research-data directory; freeze source and cases.
- [x] Run paired development tests, then registered full-size and fresh-seed
  checks if correctness passes. Retain every invalid/unfinished attempt.
- [x] Investigate the tail-sensitive gate only after transport evidence; if the
  current gate remains adverse, report it as unresolved rather than claim success.
- [x] Export compact evidence, reproduce summary, verify archive integrity,
  and deliver the diff and factual target status without committing/pushing.

Before each run: describe the exact mode change and expected observable result.
Native backward-compatible argv retains the original mode. All candidate
switches are explicit in Scenario, run_status and registration. Test commands:
`python3 limer.py check --verbose`; candidate native paired campaign uses the
same audited `run_case` pipeline as the previous integration campaign.

Review outcome: the existing benefit estimator remains unresolved. This
throughput revision validates direct recovery only; see the retained weak-loss
gate regression and the explicit scope in the candidate review note.

Supplementary diagnostic: after the original-seed direct-recovery full cases
passed, register two four-phase cases that change only policy to benefit on
frozen v2. Expect possible rejection of useful early recovery because the
estimator still includes the final notification in a four-credit rate model.
Run one short diagnostic at a time; measured research quota use was 776 GiB
against 810 GiB soft quota. Keep outcomes separate from throughput acceptance.

Accepted evidence: 24 registered attempts; 24 execution/observation-valid,
23 completed and one retained no-healthy-helper boundary failure. All seven
full-size jobs completed. Four shared-helper fault cases retain 73.88–78.07%
of unchanged healthy throughput. The gate diagnostic remains adverse under
weak loss and is not part of the accepted throughput mode. 152 unit tests,
637 compact-file hashes, 24 server archive hashes, native source provenance
and regenerated tables pass. Diff prepared; no commit or push performed.
