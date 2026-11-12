# Recovery throughput development — 2026-11-12

This candidate follows the throughput diagnosis of the phase integration.
The preceding source and all 41 attempts remain unchanged in their existing
directories. This directory is a separate experiment, not a replacement of
the old 907.90-ms blackhole result. Final audited outcomes and their limits are
reported in [RESULTS.md](RESULTS.md).

## Implemented controls

- `--relay-completion final_ack --helper-mode idle`: prior integration behavior.
- `--relay-completion pipelined --helper-mode idle`: physical NIC and helper
  buffer credits release after the last data leg; logical ownership remains
  outstanding until the same charged final source notification arrives. A
  bounded 32-chunk confirmation window replaces the coupled eight-slot window.
- `--relay-completion pipelined --helper-mode shared`: explicit design extension.
  After detection, two charged requests enable lending by a helper in each
  endpoint server. A helper reserves one of its four B-NIC admission credits
  for the relay while its own traffic can use the other three. Existing own
  transfers drain normally. Relays and original traffic share the same link
  bandwidth and the same four physical NIC/buffer caps. The helper need not
  finish its whole current-phase workload first.

Every route still requires a full 64-KiB three-leg probe, delivered health
report, and phase-local PREPARE/READY/COMMIT transaction. Original B eligibility
returns at each phase boundary. No phase is complete until all declared logical
chunks have their final confirmations. Fault rules, detector thresholds,
control-channel speed/delay, chunk sizes and access-link rates are unchanged.

Shared lending is **an architectural extension of the collaborator's idle-only
helper assumption**, not merely a bug fix. Its impact on the helper's own
completion is included in total phase/job time. New audit fields explicitly
distinguish idle-only verification from shared-resource verification.

## Source and reproduction

`project/` contains the v2 candidate source and all owned tools.
`project-v1/` preserves the first candidate and its negative results.
The [review note and patch](review/REVIEW.md) explain the change relative to the
preceding phase-integration source. The relative
`project/third_party` symlink uses the unchanged vendored dependency already in
`versions/2026-10-28-rdma/project/third_party`. Clone the whole repository or
resolve that symlink when making an independent export. Old delivery manifests
certify their immutable original source; they do not certify this candidate.

```bash
cd versions/2026-11-12-throughput/project
python3 limer.py check --verbose
python3 limer.py build --out /work/new-build --jobs 8
python3 tools/throughput_campaign.py register --preset pilot --build /work/new-build --out /work/pilot
python3 tools/throughput_campaign.py execute --out /work/pilot --workers 2
python3 tools/throughput_campaign.py register --preset full --build /work/new-build --out /work/full
python3 tools/throughput_campaign.py execute --out /work/full --workers 2
```

To reproduce one target case directly from `project/`:

```bash
python3 limer.py run --build /work/new-build --out /work/one-blackhole \
  --method G11 --scenario blackhole --rounds 1 --chunks 512 \
  --phases-per-round 30 --horizon-ms 2000 --fault-ms 40 --seed 111210016 \
  --detector service --policy always --replacement-lifetime phase \
  --relay-completion pipelined --helper-mode shared
```

The scalar CLI defaults still select the earlier resource/helper modes.
Use the registered full preset or the explicit flags above for this candidate.

The frozen v1 pilot has 12 attempts. The v2 pilot has three and the registered
v2 full workload has seven. Two later registered four-phase gate diagnostics
bring the revision to 24 attempts. The full v2 plan
includes the original matched seed and one fresh matched seed, plus an idle-only
pipeline control. `full-plan.json` is the unused v1 design; the executed full
campaign uses `full-v2-plan.json`. Cases and source/build hashes freeze before
each group executes. Failed/unfinished attempts stay in the table.

The v2 helper-selection change assigns disjoint GPUs to concurrent helper
roles so two recoveries do not compete for one helper buffer pool. It does not
change physical capacities. Both v2 campaigns were registered before their
pilot outcomes. The archive compression change is lossless and does not change
the simulated execution.

## Reporting rule

The target is healthy-normalized **whole-job useful throughput**:
`T_healthy / T_fault`, for equal payload and matched workload/seed. Report the
candidate-matched healthy denominator and the old 480.178448-ms healthy
reference. Do not improve the ratio by slowing its denominator. Detection
latency below 100 ms is a separate outcome. Neither the simulations nor these
small development cohorts establish numerical AllReduce or hardware throughput.

Native builds and raw evidence live under the authorized research-data path
`otakotak:/home/suliu/data/LIMER_THROUGHPUT_2026-11-12/`.
Original source snapshots and raw archives remain preserved. This revision is
published on `codex/phase-scoped-recovery-2026-11-12` following Sophie's explicit
push authorization on 2026-11-12.

## Verification and raw evidence

```bash
python3 versions/2026-11-12-throughput/verify_compact.py
```

Compact evidence retains all attempts, configuration, faults, results, control
and phase logs, audit/replay receipts, source/build provenance and archive
hashes. `summarize.py` re-derives every table from those records. Raw packet
archives remain on otakotak; `export_evidence.py` rechecks their hashes before
export. See `verification/final-check.json` for the completed verification scope.

The throughput target is evaluated with direct recovery (`policy=always`). Two
supplementary short cases check the old gate on the frozen candidate; their
outcomes are reported separately in RESULTS.md. This does not resolve
the benefit gate's earlier weak-loss tail-estimation regression. The existing
gate remains available as a research option, not a validated default for this
throughput result. The four-phase no-healthy-helper boundary remains unfinished
and is included in the results.

Reproduce the supplementary gate diagnostic after building the candidate:

```bash
cd versions/2026-11-12-throughput
python3 register_policy_pilot.py --build /work/new-build --out /work/policy-pilot
python3 project/tools/integration_campaign.py execute --out /work/policy-pilot --workers 1
```
