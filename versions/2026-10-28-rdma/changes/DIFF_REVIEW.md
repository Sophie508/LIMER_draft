# LIMER diff review — 2026-10-28

Reviewed the collaborator-relative 45-file delta, with focused tracing of native detector events, physical RDMA routes, benefit estimates, paid control/health messages, epoch/ACK completion, frozen scoring, archive pruning and report selection. This is a review of the declared simulation contract, not a proof for arbitrary traffic or hardware.

## Findings and disposition

1. **Fixed: cross-Python report portability.** Python 3.14 summation differs from the server's frozen scorer by roughly 1e-13 ms in several aggregate means. Exact dictionary equality falsely rejected an unchanged campaign. The postprocessor now permits at most 1e-9 ms (one picosecond) absolute difference only for `groups[].mean_capped_ms`. Counts, p95, trial CSV and pair CSV remain exact. No retained evidence or frozen scorer was rewritten. Two regression tests accept harmless roundoff and reject changed counts, changed p95 and materially changed means. Both real campaigns now regenerate the identical final report JSON.
2. **Documented model assumption: endpoint evidence availability.** Receiver timestamps/summaries and sender events feed a shared detector object. Raw inter-host observation exchange and callback processing are not separately charged. Alarms and recovery control/health reports pay the declared FIFO. The paper states this in Method and Limitations.
3. **Documented performance boundary:** the gate saves 51.26 ms against direct replacement in the slow-helper/quarter boundary but costs 5.75 ms and 11.60 ms under blackhole and weak loss. It remains 0.39 ms slower than no proxy in the favorable boundary. No universal improvement claim.
4. **Documented execution boundary:** the main 240 benefit trials show 180 activations and 1107 chunks beginning rescue, but zero new B-prime chunk completions or sustained new B-prime use. Logical audit is not tensor AllReduce correctness.
5. **Retained failure/sampling history:** v1 has 580 attempts, 530 valid and 50 infrastructure errors; quarter has 42/60 timely, 18 misses. Main v2 weak loss has only 38 unique derived stream pairs. The separate preregistered stride-32 cohort provides the final 60-trial loss row without pooling. Policy pairs remain empirical main-matrix comparisons.

No unresolved blocking issue was found for reporting these bounded simulation results after the portability fix. General grey-fault coverage, distributed telemetry/discovery and external full-system comparisons remain unvalidated.

## Fresh checks

- Full current local suite: 142 tests, OK.
- Main compact verification: 580/580, passed. Supplemental compact verification: 60/60, passed.
- Trial CSV and pair CSV exactly match frozen rescoring; final report JSON exactly equals the earlier final JSON.
- Prior server receipts retain full raw archive and native-build verification. This review did not re-download/re-hash all remote raw data.
- Original frozen tooling, native build and campaign inputs were not changed. No experiments were newly run for this review.
- Patch is regenerated and actually applied to an original-file copy, then every resulting changed file is hash-compared.

## Paper organization

Introduction → problem and comparator roles → RDMA detector with observation assumptions → measured helper benefit and epoch completion → registered detection and paired policy results → limitations. Historical UDP, pending-only route results and their failures remain in a clearly marked appendix. Reconstructed OptCC remains a separate scheduling comparator.

## Claim-evidence map and adversarial self-review

| Dimension | Claim or question | Evidence / disposition |
| --- | --- | --- |
| Contribution | What is newly implemented? | Connected packet-level detector, measured helper gate and rescue; no unsupported novelty priority claim. |
| Clarity | Can a reader identify conditions and metric? | Method cadence/thresholds, 16-GPU setup, exact workload/horizon, all-direction score and tables. |
| Experimental strength | Does the gate always win? | No; all 120 matched triples, completion counts, capped costs and both overheads retained. |
| Evaluation completeness | Is full LIMER compared with external systems? | No; internal mechanism controls and separate OptCC scheduling result explicitly distinguished. Needs new experiments for external superiority. |
| Method soundness | Does the model validate distributed telemetry and sustained B-prime service? | No; shared ideal observations and zero new B-prime completions explicitly disclosed. Needs new simulation validation. |

Paper-specific backups and diff are in this directory. The live Overleaf destination is https://www.overleaf.com/project/6ad9dce761ca17ea4b0e7371 . Git commit and push remain unperformed.
