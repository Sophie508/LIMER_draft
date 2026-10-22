# 论文到实现与实验的映射

表号依据 `paper/snapshot_2026-10-15/main.tex`。后续论文重排应优先使用表的 LaTeX label。

| 表 | LaTeX label | 实现与入口 | 条件和结果归档 |
|---|---|---|---|
| 1 自适应检测 | `tab:adaptive-business-validation` | `limer_v0/business_delivery.py`, `simulation/LimerBusinessObservation.cc`, `simulation/run_business_observation.py::make_trials` | `artifacts/m13/runs/m13_adaptive_validation_v1/registration.json`, 同目录逐次 `status.json` 与 `summary.json` |
| 2 实际探测成本 | `tab:probe-cost` | `simulation/probe_budget.h`, `run_business_observation.py::audit_probe_waves` | 同一 adaptive 验证的逐次 `truth.json`；1 Gb/s 补充对照在 `m13_adaptive_high_controls_v1` |
| 3 静态双平面 | `tab:dual-calibration` | `baselines/simai_runtime/LimerDualPlaneReplay.cc`, `dual_calibration_library.py`, `run_dual_calibration_ecn_v1.py`, `run_dual_calibration_extra.py` | `artifacts/server/logs/ecn_v1_dual_plane_calibration_summary.json`, `dual_plane_extra_summary.json`；对应 `artifacts/server/runs/ecn_v1_*` |
| 4 在线换路 | `tab:online-route` | `simulation/LimerClosedLoopReplay.cc`, `ack_progress_policy_observer.h`, `limer_v0/pending_route_cost.py`, `simulation/run_closed_loop.py` | `artifacts/server/runs/m11_closed_loop_v1/registration.json`, 8 个输入及状态、trace/progress 压缩轨迹 |
| 5 Ring/OptCC | `tab:optcc-replay` | `baselines/simai_runtime/dag_tools.py`, `LimerDagReplay.cc`, `handoff/replay_network.py` | `artifacts/server/logs/measurements_summary.json`, 30 个完整网络输入及压缩轨迹 |
| 6 TCP host | `tab:tcp-host-validation` | `limer_v0/tcp_loss.py`, `baselines/simai_runtime/m7_tcp_wrapper_ingress_v3.py`, `run_m7_validation_v3.py` | `artifacts/server/logs/m7_validation_v3_summary.json` 与 stress/sensor-off 账本；冻结源码 `artifacts/frozen/limer_source_m7_tcp_v3/` |
| 7 双端 batch | `tab:batch-validation` | `limer_v0/batch_loss.py`, `simulation/LimerBatchObservation.cc`, `run_batch_observation.py` | `artifacts/server/runs/m8_validation_v1/`, `m8_stress_v1/` |
| 8 hybrid | `tab:hybrid-validation` | `limer_v0/hybrid_delivery.py`, `early_delivery.py`, `simulation/LimerHybridObservation.cc`, `batch_deficit_observer.h` | `artifacts/m12/m12_validation_v2/`, `m12_boundary_v2/`, `m12_boundary_size_v1/`，连同早期版本账本 |
| 9 固定代表性探测 | `tab:business-validation` | M13 同一模型，`coverage_validation` campaign，1500 bytes / 35000 pps | `artifacts/m13/runs/m13_coverage_validation_v1/`；旧预算失败在 development/representative 账本中 |
| 10 OptCC 生成器检查 | `tab:optcc-artifact` | 作者外部 DAG 生成器，输出由 `dag_tools.py` 校验和转换 | `baselines/optcc_checks/manifest.json` 记录四次运行与 source hashes，四个生成图均已保存 |

文中无表编号的执行正确性证据：

- M9 原生协议的 9 个案例：`artifacts/server/runs/m9_execution_v1/`，由
  `simulation/audit_dynamic_dag.py` 离线重建。8 个工作负载完成，1 个非连续版本按预期拒绝。
- M10 的速率恢复修复与 120 ms 报告延迟失败：`artifacts/server/runs/m10_progress_*`
  及 `artifacts/server/logs/m10_*`。旧 v1 代码在 `artifacts/frozen/m10_source_frozen_v1/`。
- CPU/TCP 帧完整性、READY 协调、M5 换路与失败边界：仓库原有 results 树、
  `docs/m5_*`、`baselines/simai_runtime/`，以及 `artifacts/server/logs/`。

SprayCheck、Chameleon、VCCL、Varuna 在论文中的角色是相关工作或机制参照。
没有把论文里的数字冒充本项目复现实验，也没有它们与完整 LIMER 的已完成头对头结果。
