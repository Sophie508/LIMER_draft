# Publish LIMER CPU Prototype Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Publish a clean, reproducible, and claim-bounded snapshot of the validated LIMER CPU-only prototype in `Sophie508/LIMER_draft`.

**Architecture:** Preserve the tested flat Python layout and copy only a strict source/evidence whitelist from the private research archive. Add a reader-first README and three focused technical documents, then verify code, evidence integrity, exclusions, and credentials before presenting a staged diff for approval.

**Tech Stack:** Python 3, Mininet, Open vSwitch, Linux `tc/netem`, JSON/JSONL, CSV, SVG, Git, GitHub CLI.

## Global Constraints

- Conversation is Chinese; code, comments, documentation filenames, and commit message are English.
- Do not include `results_pre_audit_same_qdisc_2026-07-14/` or private proposal/literature files.
- Do not claim NCCL, RDMA, numerical AllReduce, GPU, Huawei hardware, switch-resident detection, or end-to-end millisecond recovery.
- Preserve all 18 valid runs and the fixed C3 recovery-retention gate of `0.9`.
- Show the complete staged diff and verification evidence before commit.
- Do not commit or push without Sophie's explicit approval after diff review.
- The commit author is Sophie only; no AI attribution or `Co-Authored-By` trailer.

---

### Task 1: Assemble the approved artifact

**Files:**
- Copy: `limer_v0/*.py`
- Copy: `configs/*.json`
- Copy: `tests/*.py`
- Copy: `results/**`
- Copy: `environment_probe.txt`

**Interfaces:**
- Consumes: `/Users/sophie/Documents/LIMER/prototype/cpu_v0` as the read-only validated source.
- Produces: a runnable repository root with unchanged module and config paths.

- [x] **Step 1: Copy the implementation whitelist**

Run:

```bash
cp -R /Users/sophie/Documents/LIMER/prototype/cpu_v0/limer_v0 .
cp -R /Users/sophie/Documents/LIMER/prototype/cpu_v0/configs .
cp -R /Users/sophie/Documents/LIMER/prototype/cpu_v0/tests .
cp -R /Users/sophie/Documents/LIMER/prototype/cpu_v0/results .
cp /Users/sophie/Documents/LIMER/prototype/cpu_v0/environment_probe.txt .
```

Expected: only the current implementation, tests, configs, valid results, and
environment probe appear at repository root.

- [x] **Step 2: Prove the invalid result tree is absent**

Run:

```bash
test ! -e results_pre_audit_same_qdisc_2026-07-14
```

Expected: exit code `0`.

### Task 2: Add reader-facing documentation

**Files:**
- Create: `.gitignore`
- Create: `README.md`
- Create: `docs/architecture.md`
- Create: `docs/experiment_design.md`
- Create: `docs/current_limitations.md`

**Interfaces:**
- Consumes: names, commands, metrics, and boundaries in the copied code and raw result artifacts.
- Produces: an accurate entry point and separated explanations of architecture, experiment semantics, and limitations.

- [x] **Step 1: Write the root README**

Include the project purpose, exact status, C0-C5 result table, architecture
picture in text, prerequisites, copy-paste reproduction commands, artifact map,
and next experiment. State `NO-GO (16/18)` prominently.

- [x] **Step 2: Write focused technical documents**

`architecture.md` maps modules to the three-layer LIMER concept and distinguishes
implemented proxies from research targets. `experiment_design.md` defines C0-C5,
the matched-baseline denominator, fault placement, gates, and raw artifacts.
`current_limitations.md` records every unsupported inference and the immediate
C3 standby-path and host-gate studies.

- [x] **Step 3: Add repository hygiene rules**

Ignore Python caches, test caches, local virtual environments, macOS metadata,
temporary archives, ad-hoc run directories, and the superseded result-tree name.
Do not ignore the committed 18-run `results/` evidence.

### Task 3: Verify software and evidence

**Files:**
- Test: `tests/*.py`
- Inspect: `results/aggregate_summary.json`
- Inspect: `results/summary.csv`
- Inspect: `results/c*_rep*/manifest.json`
- Inspect: `results/c*_rep*/correctness.json`

**Interfaces:**
- Consumes: the assembled repository.
- Produces: fresh local verification output and evidence-integrity counts.

- [x] **Step 1: Run the local test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected on macOS: 51 tests discovered, pure logic tests pass, and the loopback
socket integration test may skip when sandbox networking is unavailable.

- [x] **Step 2: Compile every Python module**

Run:

```bash
python3 -m py_compile limer_v0/*.py tests/*.py
```

Expected: exit code `0`.

- [x] **Step 3: Recompute evidence invariants from raw files**

Run a read-only checker that asserts: 18 run directories; three per C0-C5;
zero checksum/version errors; 18/18 injector-detector isolation; 16/18 passing
condition assertions; C3 passing 1/3; overall acceptance false; both SVG files
parse as XML.

- [x] **Step 4: Compare copied files to the validated source**

Run recursive checksums over `limer_v0`, `configs`, `tests`, `results`, and
`environment_probe.txt` on both trees after excluding cache files.

Expected: identical sorted checksum manifests.

### Task 4: Audit publication safety and readability

**Files:**
- Inspect: all untracked repository files except `.git/**`.

**Interfaces:**
- Consumes: the final candidate tree.
- Produces: secret-scan evidence, broken-link evidence, and an exact publication inventory.

- [x] **Step 1: Scan for credentials and private material**

Search for private-key headers, password assignments, password-based automation
helpers, known server address fragments, tokens, and common cloud/GitHub secret
patterns.

Expected: no credential or private-key match. Benign documentation words such as
`password` must be manually classified if present.

- [x] **Step 2: Validate Markdown links and referenced files**

Extract relative links from the Markdown documents and verify every referenced
path exists. Verify all documented commands use paths present in the repository.

- [x] **Step 3: Inspect repository size and inventory**

Run:

```bash
du -sh .
git status --short
```

Expected: a small prototype repository with no superseded experiment tree,
proposal, PDF, office document, cache, or temporary archive.

### Task 5: Present the Git gate

**Files:**
- Stage: the explicit approved repository inventory.

**Interfaces:**
- Consumes: verified candidate files.
- Produces: a reviewable staged diff; later, only after approval, one initial commit on `main` and its GitHub push.

- [x] **Step 1: Stage only approved paths**

Run:

```bash
git add .gitignore README.md limer_v0 configs tests results docs environment_probe.txt
```

Expected: `git status --short` lists no untracked approved file and no unexpected
staged path.

- [x] **Step 2: Show the complete staged diff and validation summary**

Run:

```bash
git diff --cached --stat
git diff --cached --check -- . ':!results/*.csv' ':!results/**/*.csv'
git diff --cached -- README.md .gitignore docs configs limer_v0 tests
```

Expected: no whitespace error in code, configuration, or documentation and no
file outside the approved scope. The archived CSV evidence keeps its original
Python `csv` CRLF bytes so its checksum remains identical to the validated
source; the raw CSV path is therefore excluded from the whitespace-only check.

- [ ] **Step 3: Stop for Sophie's post-diff approval**

Do not commit or push. Ask explicitly whether the reviewed staged diff may be
committed and pushed to `origin/main`.

- [ ] **Step 4: Commit and push only after approval**

Run after approval:

```bash
git commit -m "Initialize LIMER CPU prototype"
git push -u origin main
```

Expected: one commit authored by `Sophie <Sophie508727@gmail.com>`, no co-author
trailers, and `origin/main` points to that commit.
