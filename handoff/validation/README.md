# Verification performed for this handoff

These are packaging checks from 2026-10-22, kept separate from paper evidence.

- Local Python suite: 308 tests, OK, 3 platform-dependent skips.
- DAG adapter suite: 4 tests, OK.
- JavaScript replay-state suite: 6 tests, OK.
- Offline reconstruction: three complete M13 validation ledgers, 14 sampled
  M13 report/packet/probe-wave reconstructions, all 9 M9 cases, all 8 M11
  closed-loop cases, and all 30 Ring/OptCC network traces pass.
- Clean upstream preparation: fixed SimAI and ns-3 archives were downloaded
  into a new scratch directory and the published transport/adapter corrections
  were applied. Archive hashes are in `../upstream.lock.json`.
- Clean native M13 compilation passed using the existing owned Linux Docker
  image. The new compiler output has its own binary hash. The image was not
  rebuilt during this verification.
- The portable launcher ran all four registered `adaptive_smoke` cases in that
  new backend. This is an entry-point smoke check, not a fresh held-out 400-trial
  efficacy campaign. The two fault decisions were 59.162201 and 48.701337 ms.
  The two healthy controls had no alarm. Details are in the accompanying
  registration and summary JSON files.

Fresh native builds/reruns of M7/M8/M9/M10/M11/M12 and the complete Ring/OptCC
matrix were not performed during packaging. Their archived evidence is
included. The complete detector/collective integration remains unrun.

`source_adaptations.json` records the source hashes and infrastructure string
substitutions used for the native smoke check.
