# LIMER 2026-10-28：RDMA 检测与换路收益版本

这是在合作者 **LIMER-1027.zip** 上继续实现、冻结实验并复核后的交接版本。
不需要再取得该 ZIP 就能检查代码或从源码构建新的模拟器。全部仿真在 CPU 上运行。

## 相对合作者版本改了什么

合作者已有双平面自适应分流、M13 检测、三段 GPU 代理、四方协调和未确认数据续传。
本轮保留这些结构，增加：

1. **RDMA 检测器 v4**：每条原路径每 2 ms 发 64 KiB canary，结合真实重传、业务 ACK 停滞和接收包间隔变化。检测目标是异常交付，包含严重变慢；不要求证明永久丢包。报警时间包含控制消息实际到达。
2. **换路收益门控**：根据剩余工作、最近 ACK 服务、完整三段候选探测及控制/协调/最终确认成本，比较留下和换路。健康备用路径也可能不划算。
3. **证据与审计**：冻结输入、参数、二进制和评分工具；独立重建检测与决策；检查物理 NIC、资源额度、epoch、ACK 前缀和最终完成。
4. **正式实验与失败保留**：580 次新主矩阵、60 次独立丢包确认，以及单独保留的首次失败验证；同时交接当前论文快照。

精确的 **45 个变更文件**见 [相对合作者的 diff](changes/CODE_DIFF.patch)、
[文件哈希](changes/source_changes.json) 和 [复核说明](changes/DIFF_REVIEW.md)。
`project/third_party/` 是原交付的固定依赖，保留来源和许可；没有把它们声称为本轮新增方法。

## 先看结果，再看条件和代码

| 注册故障条件 | 全部受影响方向正确且 <100 ms | p95 ms | 最大值 ms |
| --- | ---: | ---: | ---: |
| 持续黑洞 | 60/60 | 8.64 | 8.81 |
| B 容量降至 25% | 60/60 | 29.82 | 30.02 |
| 0.5% 弱丢包，独立新随机流 | 60/60 | 43.12 | 47.63 |
| 链路传播延迟增至 80 ms | 60/60 | 8.66 | 8.72 |

共 640 次新运行通过执行审计和独立重放；**不表示每个通信任务都完成**。
健康对照 0/60 误报，但重复同一确定性轨迹，不能当成 60 类业务覆盖。

收益门控在“B 降速且本地代理仅 1 Gb/s”的配对中，把直接换路的平均完成时间
440.80 ms 降到 389.54 ms，仍比不启用代理的 389.15 ms 稍慢。
持续黑洞和弱丢包下，门控分别比直接换路多花 5.75 ms 和 11.60 ms。
这是内部机制消融，不是与 OptCC、VCCL 等系统的完整头对头实验。

- [完整结果、三策略完成数和截尾成本](project/docs/results/validation-final/README.md)
- [Condition 的来源和实际注入定义](project/docs/research_conditions.md)
- [实现入口和复现交接](project/docs/research_handoff.md)
- [预先定义的协议、分母和随机流说明](project/docs/research_protocol.md)
- [首次失败的原因和原判定](project/docs/research_failed_validation.md)
- [无需解压即可浏览的逐次表、配对表和注册输入](evidence/tables/)
- [与当前 Overleaf 对应的论文 PDF](paper/limer.pdf)；[论文源码](paper/main.tex)

## 先做快速检查

从这个版本目录执行，需要 Python 3.8+；代码检查和证据核验只用标准库。
C++ 镜像一致性测试还需要系统 C++ 编译器；Linux/Docker 构建需要项目说明中的依赖。

```bash
python3 verify_release.py
cd project
python3 limer.py check --verbose
```

当前代码检查为 **142 项通过**。本轮原生验收时为 140 项；后续仅修正报告工具
在不同 Python 版本间的浮点求和末位兼容性，增加两项回归检查。
冻结原生算法、参数、输入和结果没有因此改变，重算后的最终 report.json 完全一致。

## 取出本版本内附的完整紧凑证据

从版本目录执行。目标 `project/research_evidence/` 必须不存在，避免覆盖任何现有数据。

```bash
python3 verify_release.py --unpack-evidence
cd project
python3 tools/verify_research.py research_evidence/validation-v2 --skip-archives
python3 tools/verify_research.py research_evidence/validation-loss-independent-v4 --skip-archives
python3 tools/research_report.py research_evidence/validation-v2 \
  --independent-loss-campaign research_evidence/validation-loss-independent-v4 \
  --out /tmp/limer-review-report
```

解压后约 0.7 GB，包含三个队列的注册、每次输入、冻结工具、运行状态、紧凑日志、审计和得分。
每个压缩包均低于 GitHub 单文件限制，并已逐成员核验。
`--skip-archives` 明确表示只核验紧凑证据；它没有重新检查远端原始逐包归档或二进制。
服务器完成过的全量核验和本地核验范围均在 `evidence/verification/` 中保留。

首次失败队列也能核验，但预期返回失败状态：

```bash
python3 tools/verify_research.py research_evidence/validation-v1 --skip-archives
```

该队列 580 次注册中 530 次有效、50 次遇到磁盘配额错误；降速主队列 60 次执行均有效，
其中 42 次及时、18 次漏掉一个方向。它没有被新成绩覆盖，也没有混入新 640 次。
主矩阵弱丢包的 60 次仅对应 38 个派生随机流对，因此最终检测行改用单独预注册的
stride=32 确认队列，不合并两批样本；策略配对保留主矩阵的经验比较。

## 从源码运行新的实验

`project/` 包含本轮源码及固定 ns-3/RDMA 依赖，构建不需要服务器上的旧目标文件。
在配置好依赖的 Linux 中：

```bash
cd project
python3 limer.py build --out /tmp/limer-research-build --jobs 8
python3 tools/research_campaign.py register --phase validation \
  --build /tmp/limer-research-build --out /tmp/limer-new-validation \
  --horizon-ms 400 --rounds 2 --chunks 64 --include-delay --include-slow-quarter \
  --seed-base 103200000 --seed-stride 32
python3 tools/research_campaign.py execute /tmp/limer-new-validation --workers 8
python3 tools/verify_research.py /tmp/limer-new-validation --progress
```

这是用当前生成器创建新矩阵；历史 v2 的 stride=1 必须通过其冻结工具重现。
重跑同一 seed 是复核，不应冒充新的独立验证。所有输出目录应是新目录。

## 当前限制和原始数据位置

- 结论限定在注册的 16-GPU 拓扑、负载和故障分布。前 20 ms 假定健康，端点时间戳为理想精度；原始观测和接收窗口摘要直接供共享 detector 使用，没有单独模拟跨机摘要交换或 CPU 处理时间。报警、候选报告及恢复控制消息另行计费。
- 在主矩阵的四类收益门控队列中，180 次激活代理、1107 个 chunk 开始抢救，但没有新分配的 B′ chunk 完成；不能据此宣称恢复健康双平面吞吐。
- 代理发现依赖模拟阶段状态；启动即退化、任意拥塞背景、代理二次故障、旧 B 恢复和多次故障尚未验收。不执行张量数值、CUDA、HBM 或计算重叠。
- 所有有效实验原始逐包归档仍在 otakotak 的 `/home/suliu/LIMER_RESEARCH_2026-10-28/results/`，部分通过校验后存入个人 scratch，由原路径链接访问。当前版本只附紧凑证据。

原合作者交付 ZIP 的 SHA-256：
`73f6ee061855a9ea5f6a043453b51b0007dc65406b6026796225ee21be5b5549`。
该交付内的旧 53 次参考归档和重构验证大日志没有重复纳入本版本；它们既不是本轮新结果，
也不是构建依赖。`project/reference/index.json` 和原清单保留来源。
旧 `limer.py verify` / `verify-reference` 属于原交付验证流程，不能用于认证本轮修改；
请使用上述研究核验入口。

当前论文：[Overleaf](https://www.overleaf.com/project/6ad9dce761ca17ea4b0e7371)。
论文快照中 Table 1 在第 4 页、Table 2 在第 5 页；§5.4 保留首次失败，§6 说明限制。
