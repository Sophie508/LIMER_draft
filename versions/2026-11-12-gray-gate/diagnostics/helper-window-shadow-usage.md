# Reproduce the helper-window shadow

`helper_window_shadow.py` is the saved analysis used for the 14-decision shadow.
It runs Python only and reads the accepted archive plus compact run evidence.
It never executes the simulator or changes policy, conditions, or accepted results.

On otakotak (or another machine with copies of the complete inputs), place this
script and the existing `helper-window-shadow.json` reference together. From that
directory:

```bash
GRAY_PILOT=/home/suliu/data/LIMER_GRAY_GATE_2026-11-12/results/pilot-v2
python3 helper_window_shadow.py \
  --archive "$GRAY_PILOT/archives/sustained_25_early-candidate_gate-s111213001.tar.gz" \
  --run "$GRAY_PILOT/runs/sustained_25_early-candidate_gate-s111213001" \
  --tooling "$GRAY_PILOT/tooling" \
  --expect-decisions 14 \
  --check-reference helper-window-shadow.json \
  --output /tmp/limer-helper-shadow-reproduction-new
```

The output directory must not exist and must be outside the accepted campaign,
raw archive directory, compact run and frozen tooling. The script refuses to
overwrite it. Choose a new output name for another run. It writes only
`helper-window-shadow.json` and `helper-window-shadow.md` into that new directory.
The original explanatory report and JSON remain untouched.

By default the accepted attempt is read from `campaign/attempts/<run>.json` and
registration from `campaign/registration.json`. Use `--attempt` and
`--registration` for another copied layout; `--logical-member` can specify a
logical CSV member name other than `logical_events.csv`. No archive is extracted
to disk. Bytecode cache writes are disabled when loading the frozen pure policy.

The analysis verifies:

- Archive SHA-256 against both the accepted attempt and archive manifest.
- Streamed `logical_events.csv` member SHA-256 against its accepted manifest.
- Compact policy/helper/phase evidence hashes against the manifest, and policy
  evidence against the accepted score.
- Frozen Python policy SHA-256 against the campaign registration.
- Original native/Python prediction equality before applying the shadow.
- Every original helper ACK numerator against raw logical ACK increments.
- Both numerator and denominator after clipping to the report's current phase.
- All non-helper-rate inputs and thresholds remain unchanged.
- With `--check-reference`, all 14 original/shadow inputs, reconstructed windows,
  predictions and the full summary match the earlier JSON exactly.

The saved script was rerun against the accepted archive. Verification passed with
**14 decisions, 28 helper reports, 0 decision flips, 3 reason changes, 8 shortened
windows and 0 discarded ACK-byte windows**. The independent logical member hash
was `bda6478961cccd8eaf03838d804fd824ca7b29f916bbe1211b94f8678939e70d`.
See [the compact reproduction verification](helper-window-shadow-reproduction.json).

This only reproduces a prediction shadow on an unchanged realized trajectory.
It does not assign any new communication duration to the proposed correction.
