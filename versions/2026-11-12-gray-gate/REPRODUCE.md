# Reproduce or inspect the gray-gate revision

## Inspect retained evidence without rerunning the simulator

Use a complete checkout, including the historical `2026-10-28-rdma` dependency
snapshot. `project/third_party` is a relative symlink into that snapshot; copying
only this directory without dereferencing the link is insufficient. Large raw
archives remain on otakotak. The evidence manifests identify their paths,
SHA-256 hashes, member verification and compact files.

From this version directory, after the evidence export is present:

```bash
python3 verify_compact.py evidence-v1
python3 verify_compact.py evidence
python3 write_report.py evidence /tmp/limer-gray-report
```

Document paths mentioned inside the generated report refer to this version
directory; the temporary output contains only the three regenerated report
files, not a copied project or research-document tree.

The second command verifies source/build/tooling identities, registered case
identity, preserved archive receipts, compact hashes and regenerated summaries.
It does not download or independently re-audit raw packet logs. Raw archive hashes
were rechecked on otakotak during export; replaying the full audits needs those
archives. The first command retains the failed initial candidate as invalid.

The separate terminal repair has its own source and evidence. After its export:

```bash
python3 verify_compact.py evidence-terminal-fix
python3 verify_terminal_repair.py
```

The latter verifies the exact source-change scope, unchanged job timestamps,
policy/alarm streams and precompletion control records across the ten selected
runs, plus final-phase lease closure. It preserves the original failed attempt.

## Run a fresh campaign on Linux

The native backend runs on CPU. Its build dependencies are GCC/G++, CMake,
Python 3, pkg-config, Boost headers, GSL, SQLite and libxml2 development headers,
as listed in `project/Dockerfile`. No GPU, CUDA or hardware RDMA access is needed.
The reported native runs used the toolchain image recorded in the build evidence;
a different toolchain must produce its own build identity.

Choose new output directories on a volume with enough **user quota**, not merely
filesystem free space. Never point registration at retained evidence directories.
The following paths are examples to replace with a new project-specific location:

```bash
cd project
python3 limer.py check
python3 limer.py build --out /path/to/new-gray-run/build --jobs 2
python3 tools/gray_gate_campaign.py register --preset pilot \
  --build /path/to/new-gray-run/build --out /path/to/new-gray-run/pilot
python3 tools/gray_gate_campaign.py register --preset confirmation \
  --build /path/to/new-gray-run/build --out /path/to/new-gray-run/confirmation
python3 /path/to/new-gray-run/pilot/tooling/tools/gray_gate_campaign.py execute \
  --out /path/to/new-gray-run/pilot --workers 1
```

Register both presets before inspecting outcomes. Pilot has 20 cases;
confirmation has 30. These are fixed, paired LIMER ablations. Review native
correctness and space before running the separately registered confirmation:

```bash
python3 /path/to/new-gray-run/confirmation/tooling/tools/gray_gate_campaign.py execute \
  --out /path/to/new-gray-run/confirmation --workers 1
```

The registration freezes Python tooling and native source/build identities.
Run the frozen tooling path when resuming or summarizing. `--resume` skips every
recorded attempt, including invalid ones; it must not replace failed outcomes.
An invalid attempt calls for diagnosis and a separately named revision if a fix
is needed. Valid but unfinished cases remain legitimate negative outcomes.

The registered maximum is two workers, allowed only after measuring a first
attempt and establishing headroom for two raw attempts plus 10 GiB, as well as
projected archives. One measured raw attempt was about 520 MiB and its archive
about 91 MiB; these are planning measurements, not guarantees for other cases.
The pilot and confirmation seeds are fixed. New deterministic repeats do not
provide independent stochastic evidence.

## Run the separate terminal repair regression

Build `project-terminal-fix` into a new directory with the same build command.
Register its full confirmation preset against that new binary, then select only
the predeclared three conditions:

```bash
python3 /path/to/new-repair/confirmation/tooling/tools/gray_gate_campaign.py execute \
  --out /path/to/new-repair/confirmation --workers 1 \
  --only-condition healthy --only-condition sustained_50_early --only-condition blackhole
```

This attempts ten cases and leaves the other 20 registrations explicitly unrun.
It is a targeted correctness check, not full qualification of the repaired
version. Do not point this command at the retained original campaigns.

## Which files answer which question?

| Question | Entry point |
| --- | --- |
| What changed relative to the throughput release? | `review/implementation.diff` |
| What is the policy allowed to observe? | `project/python/limerlab/benefit_policy.py`, `policy_replay.py` |
| Where are paid helper reports, leases and cancellation implemented? | `project/src/simulator/recovery/proxy.h`, `python/limerlab/audit.py` |
| Which conditions and seeds are fixed? | `research/pilot-plan.json`, `research/confirmation-plan.json` |
| How are denominators and paired times scored? | `project/tools/gray_gate_campaign.py` |
| Why did the first candidate fail validation? | `research/FAILED_ATTEMPTS.md` |
| What can be claimed relative to prior work? | `research/NOVELTY_AUDIT.md` |

The historical `project/README.md` preserves earlier release commands and
results. Its old `verify`, `verify-reference` and historical acceptance tables
are not certification of this modified source. Use this revision's evidence
verification and exact registered matrix for current claims.
