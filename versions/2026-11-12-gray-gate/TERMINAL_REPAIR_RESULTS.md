# Terminal cleanup repair: targeted regression

The separately built `project-terminal-fix` repairs terminal lease cleanup.
All 10 preselected native cases passed the unchanged execution and observation
audits. The registration retains 30 definitions; the other 20 are intentionally
unrun. This is a post-failure correctness check, not a new full performance
confirmation or additional independent detection trials.

| Condition | Arm | Communication ms | Detection class |
| --- | --- | ---: | --- |
| healthy | adaptive | 63.965513 | healthy_clear |
| healthy | direct | 63.965513 | healthy_clear |
| healthy | legacy_gate | 63.965513 | healthy_clear |
| healthy | candidate_gate | 63.965513 | healthy_clear |
| blackhole | direct | 84.230882 | timely |
| blackhole | candidate_gate | 84.300279 | timely |
| sustained_50_early | adaptive | 84.493738 | miss |
| sustained_50_early | direct | 78.712694 | miss |
| sustained_50_early | legacy_gate | 84.247467 | miss |
| sustained_50_early | candidate_gate | 84.251871 | miss |

**Execution validity does not imply detection success.**
4 selected runs still have missed-path detection outcomes:
- `sustained_50_early-adaptive-s111213033`: observed paths [13]; missed paths [721] through the 250-ms monitor horizon.
- `sustained_50_early-direct-s111213033`: observed paths [13]; missed paths [721] through the 250-ms monitor horizon.
- `sustained_50_early-legacy_gate-s111213033`: observed paths [13]; missed paths [721] through the 250-ms monitor horizon.
- `sustained_50_early-candidate_gate-s111213033`: observed paths [13]; missed paths [721] through the 250-ms monitor horizon.

The original and repaired alarm streams match exactly. This detector
limitation predates the cleanup repair and remains unresolved; these
runs do not meet the all-affected-paths-below-100-ms target.

For every selected case, the business completion timestamp, policy-decision
stream, detection-alarm stream and control records sent before completion
are identical to the retained original trace. Every requested final-phase
candidate lease now has its paid release recorded. Cleanup does not make
the business job finish sooner; post-completion message costs remain charged.

The original sustained-50% candidate remains invalid in the main result table.
Its timestamp is used only to check repair locality, not as an accepted old
performance measurement. All other original outcomes remain unchanged.

The repaired source has only two changed native files and three test changes
relative to `project`. The full local suite passes 216 tests. This repair
does not address the conservative rate/helper forecast or establish the
70%–80% throughput target across gray-fault workloads.

Protocol: `research/TERMINAL_REPAIR_PROTOCOL.md`. Full compact/source
verification: `verification/compact-terminal-fix.json`. Exact comparisons:
`verification/terminal-repair-locality.json`. Diff: `review/terminal-fix.diff`.
