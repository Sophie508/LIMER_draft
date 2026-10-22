# Local SimAI compatibility probe — 2026-10-10

Goal: prepare a CPU packet-simulation baseline environment without depending on
the unreachable approved remote hosts. This is setup verification, not an
experiment or a performance reproduction.

- Official source: https://github.com/aliyun/SimAI
- Retrieved current commit: a57d765c5478f319c5f5ab6fdc53f9cc7f461743 (2026-09-20).
- History records MockNccl relocation at 356c990 (2026-07-10).
- Compatibility candidate: f5efb5a93ea9be7db25a8843f9f7ff54044f6062 (2026-04-24),
  selected as the last main-history commit before the OptCC arXiv v1 date.
- Pinned ns-3 submodule: 7e3cb5b88c99abcb582c5abc3919484a4805111b.
- Candidate contains MockNcclGroup.cc and the ring flow-model entry points, but
  not the missing OptCC integration. It is not verified as the paper's exact backend.
- Docker/OrbStack engine responds; a fresh ephemeral Ubuntu 22.04 container
  completes uname -m with aarch64. Existing unrelated containers remain untouched.
- No SimAI binary built, no simulated result generated, no OptCC patch installed.

Next gate: inspect candidate build dependencies and architecture support, build
the unmodified simulator, and run its native microbenchmark under a registered
setup protocol. Then integrate reference DAGs with dependencies preserved and
match original settings. Keep any independent reconstruction labeled separately.
