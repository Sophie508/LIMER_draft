# OptCC reference-algorithm verification protocol

Registered 2026-10-10 before compilation/execution. No algorithm is changed.
Expected: three C++17 generators compile, their README examples exit zero,
produce nonempty DAG JSON and report internal validation. These are algorithm
schedule checks, not packet-level SimAI reproduction or LIMER head-to-head.

Commands: single_straggler 5 4 9000 1000 2; multi_straggler 5 4 2 9000 1000 2,1.5;
multi_gpu_per_server 4 4 2.0 4. Extra single-straggler bubble-fill check: L=1.5.
Preserve compiler output, program output, exit code, source/ZIP SHA256, DAG JSON.
The six-file artifact lacks the SimAI integration and end-to-end experiment script.
