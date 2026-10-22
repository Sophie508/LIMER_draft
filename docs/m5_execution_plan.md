# M5 execution plan (2026-10-10)

**Goal:** Execute the four approved workstreams with source-bounded paper claims,
an archived OptCC artifact, a verified cutover repair, and preregistered experiments.

**Architecture:** Keep CPU/Mininet execution evidence separate from SimAI model
evidence. Repair the existing framed-TCP implementation before extending its
signals. Reproduce published algorithm schedules before integrating them into a
shared packet-level simulator.

**Tech stack:** Python unittest, framed TCP, Mininet, C++17 DAG generators, SimAI.

**User priority update:** On 2026-10-10 Sophie selected the existing Overleaf
project as the main manuscript and requested baseline reproduction before new
method claims. The next performance experiment is therefore OptCC reproduction;
the signal and policy extensions remain secondary pending the common backend.

## Global constraints

- User approved the handoff recommendations on 2026-10-10; proceed inline.
- Show the diff for review before committing; ask separately before pushing.
- Do not access the prohibited H20 machine. Do not expose credentials or contacts.
- Preserve previous campaigns and failed runs. Register protocols before execution.
- Keep code, comments and paper prose in English; discussion with Sophie in Chinese.

## Pipeline and independent deliverables

1. [x] Read README and check root AGENTS/CLAUDE files (none present).
2. [x] Record clean baseline at 7629e67; unittest: 199 tests, one macOS skip.
3. [x] Archive all six public OptCC files as a ZIP plus extracted sources outside
   the Git repository. The snapshot omits MockNcclGroup.cc and run_all_experiments.sh.
4. [x] Read current Chameleon v4, OptCC v1 and SprayCheck v1 introduction,
   method, evaluation and conclusion; create a versioned comparison/claim ledger.
5. [x] Inspect VCCL recovery code; distinguish RDMA mechanisms from TCP framing.
6. [x] Reproduce the same-socket receive-reader race before modifying worker.py.
   Test: tests/test_worker_cutover.py. Repair: preserve a receive attempt across
   a send-side abort; never allow concurrent readers on the same incoming stream.
   Check unchanged receive routes, changed receive routes, partial frame reads,
   duplicate discard, version/checksum rejection and bounded timeout failure.
7. [x] Verify OptCC DAG examples with exact source hashes and separate outputs.
   A DAG run is algorithm verification, not a reproduced SimAI performance result.
8. [x] Register a Mininet regression and a SimAI reproduction/comparison protocol.
   Remote execution initially depended on reachable approved servers; otakotak
   is now reachable and executing the registered runs.
9. [x] Select a feasible new detector signal after reading SprayCheck; retain
   counter-only baseline and evaluate false alarms plus detection quantiles.
   Do not convert iterations to milliseconds without measured iteration time.
   Implement an opt-in observation-only TCP_INFO sampler, independent of the
   existing detector/policy. Read Linux tcpi_total_retrans from the 104-byte ABI
   prefix, preserve connection identity and missing/error samples, and log
   timestamped deltas. Unit-test native endian parsing, counter wrap, connection
   replacement, and failed reads before a Linux pilot. No trigger threshold or
   policy input is added until a frozen pilot amendment.
10. [x] Draft Background, Design, a bounded Introduction, and Related Work;
    include outline, evidence map and reviewer questions. No invented results.
11. [x] Check Jev official availability and prerequisites before an offline arm;
    no waitlist enrollment or API spending without concrete existing access.
12. [x] Produce an execution report, saved verification logs and reviewable diff.

## Decision updates from local verification

The preserved M4b failure does not establish that a resend was dropped twice.
Rank 3 completes step 2 after redo, while rank 2 remains at step 2 and buffers
step 4. A receiver thread started before a send error can remain alive while
the redo creates another reader of the same TCP stream. Test this concrete
mechanism before introducing retransmission. TCP already retransmits packet loss;
blindly retrying sendall after a partial write can corrupt stream framing.

Chameleon v4 selects data rerouting versus dynamic parallelism after node failure.
It blocks broad claims of being the first adaptive fault-tolerance policy.
LIMER's candidate distinction is link-slot routing with workers and training
configuration retained; this is a bounded comparison, not an exhaustive novelty proof.

## Acceptance and stop rules

- Repair accepted locally only if deterministic regression fails before repair,
  passes after repair, and all baseline checks remain passing.
- Full 25% loss reliability is unverified until fresh Mininet runs complete.
- OptCC head-to-head requires identical simulation backend, topology, workload,
  fault model and measured cutover cost; paper numbers remain separate references.
- SimAI scale results do not validate Python detector latency or NCCL correctness.
- No new signal receives a <100 ms claim until held-out healthy and fault traces
  satisfy the preregistered latency and false-positive gates.
- Service or machine access failures block dependent runs, not local work.

## Initial local verification snapshot (superseded by server update below)

- Items 4/5: inspected Chameleon/OptCC/SprayCheck and targeted VCCL mechanisms;
  Varuna archived, detailed review pending.
- Item 6: two old-code regressions fail; repaired code passes.
- Item 7: three generators compile, four DAG examples run; no SimAI throughput.
- Item 8: protocols registered, remote experiments unrun because both allowed
  hosts reset SSH during handshake.
- Item 9: signal selected and observation-only sampler/configs implemented;
  Linux runtime and detector improvement pending.
- Item 10: initial local review draft written and compiled. At Sophie's subsequent
  request, edited the existing Overleaf main.tex and refs.bib directly: baseline
  artifact-check table, reproduction gate, comparison methodology and bounded
  claims. Overleaf is now the main manuscript; the local draft is an earlier review aid.
- Item 11: six input states prepared; official key absent, no API calls.
- Local checks: 208 Python tests (2 skips), 6 JavaScript tests, syntax, replay
  consistency and diff-whitespace checks pass.
- Checkboxes mark these local deliverables, not the completion of their blocked
  remote experiments. No commit or push has occurred.
- Local Linux alternative: Docker/OrbStack responds and an Ubuntu container runs
  on aarch64. Official SimAI archived at current a57d765, then pinned to compatibility
  candidate f5efb5a (2026-04-24) with ns-3 submodule 7e3cb5b. The latter retains
  MockNcclGroup.cc; the current release moved it. This is not a verified OptCC
  paper backend version. SimAI build, DAG integration and performance run are pending.

## Server execution update (2026-10-10)

Sophie authorized otakotak for storage and Docker execution. Canonical private
work root: `/home/suliu/scratch/LIMER_WORK_2026-10-10`; the home-quota limitation
was resolved by a hash-verified relocation. A task-specific rootless daemon and
images keep existing server workloads separate. Full source and bulk traces
remain on the server; local copies contain thin reports and manuscript diffs.

- Native SimAI with the pinned compatibility candidate compiles and completes
  the original 8-GPU/NVSwitch micro-example. It is an infrastructure reference.
- A separate network-only DAG executor reconstructs disclosed OptCC schedules.
  Both arms share a repaired transport callback and serial chronological event
  executor. Earlier adapter, transport and MTP-order failures remain archived.
- Transport gates: 14/14 pass; graph/scheduler gates: 6/6 pass. Matched measurements:
  24/24 primary launches plus 6/6 references/sensitivities pass exact drain, byte
  accounting and parent/child timestamp checks. No numerical reduction claim.
- Four conditions show Ring/OptCC makespan ratios 1.116, 1.206, 1.259 and 1.405.
  These are independently reconstructed network measurements, not reproduced
  author figures. Three identical process repeats are deterministic checks.
- Overleaf now contains the setup, limitations and verified four-row table;
  compile reports zero errors and no overfull/underfull boxes.
- Complete Linux source suite: 208 tests pass, no skips. Healthy kernel-OVS
  Mininet workload completes all 6 collectives/24 worker rounds correctly.
- Registered 29-lifecycle fault regression is running. Completion, branch,
  fingerprint and correctness gates must be assessed independently. No fresh
  fault-reliability claim is made while it is incomplete.
- Varuna full-text recovery audit is complete; host retransmission pilot and
  shared-backend dual-plane route-choice matrix remain pending.

Private preregistrations and detailed evidence are in the server work root's
`baselines/simai_runtime/` and `logs/`; see the local `server_execution_report.md`
for the corresponding review summary. No commit or push has occurred.

## Terminal pilot update and decision gate (2026-10-10)

This section supersedes the previous running-server snapshot. The Linux suite
passes 217/217 tests. The original policy campaign stops after two failed active
attempts; 27 queued attempts remain explicitly unrun. The guarded switch pilot
completes; guarded stay selects its expected branch but times out. Repeat
expansion is blocked. Nine original v3 lifecycles complete with transport checks;
transient suppression succeeds only 2/3 times.

All 33 observer pilots end: 30 workloads complete and three at 25% loss time out.
All 615,998 counter reads are available. The raw counter meets neither a uniform
100-ms latency claim nor cause-specific detection. Formal validation is not
started because the frozen-rule gate is unmet. See m5_signal_pilot_results.md.

Eight ECN-amended four-rank static dual-plane calibrations pass, with a preferred
arm reversal under constrained B capacity. Six fixed-route 25% loss/B10Mb/s
diagnostics end: stay completes 0/3 workloads; switch completes 3/3, each with
eight post-fault rounds in 84.804–85.029 seconds. This oracle safe-boundary
comparison excludes detection and in-flight cutover. Recipes match, but realized
loss draws do not. See m5_constrained_route_results.md.

The 16-rank crossed schedule/route-choice dynamic matrix remains unrun. No new
cost-aware decision method has been implemented or validated. The existing spare
heuristic is not established as optimal. No exact author OptCC figures, GPU
training, RDMA failover, numerical reduction or ASIC footprint is claimed.

Overleaf contains actual prose, tables, failures and limits. The local standalone
draft remains an earlier review aid. Bulk data stays on otakotak scratch; local
copies are thin reports. Human contribution positioning is pending: prioritize
finite-episode route-choice cost and execution, or retain 100-ms gray detection
as the primary contribution. See m5_next_decision.md. No commit or push occurred.
