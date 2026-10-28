# 2026-10-28 代码交接：检测与换路收益

这份源码从合作者的 `LIMER-1027.zip` 解压版独立复制后继续开发。
原解压目录的 4,117 个文件已重新对照提取清单核验，未修改。
原交付 ZIP SHA-256 为
`73f6ee061855a9ea5f6a043453b51b0007dc65406b6026796225ee21be5b5549`。
本轮没有提交或推送 Git；review patch 相对该原版生成。

## 先看什么

- [实现说明](research_implementation.md)：检测怎么做，换路比较哪些代价。
- [预先定义的实验协议](research_protocol.md)：条件、分母、配对、统计口径和边界。
- [Condition 对照说明](research_conditions.md)：每个名字在模拟器里实际改变什么，哪些是人为边界。
- `research_evidence/validation-v2/registration.json`：修正版 580 次的精确输入、冻结工具和构建哈希。
- `research_evidence/validation-v2/research_trials.csv`：每一次检测及任务完成结果。
- `research_evidence/validation-v2/research_pairs.csv`：同 seed、节点、注入时刻和负载的三策略比较。
- `research_evidence/validation-loss-independent-v4/`：补充 60 次不复用丢包流的预注册确认。
- [结果报告](results/validation-final/README.md)：完成核验后导出的表和图。
- `research_evidence/validation-v1/`：保留第一轮正式失败的全部注册输入和得分，不能替换成新成绩。
- [首次失败说明](research_failed_validation.md)：18 次降速漏检与 50 次基础设施错误分开解释。

检测不是重用旧 UDP 模型的 400/400 结果。本版用实际模拟的 RDMA canary、
重传与业务 ACK 停滞形成报警，报警还要经过真实计费的控制 FIFO。
收益门控在合作者已有三段代理和四方协调上增加估计，不改变物理双平面。

## 本轮已经完成什么

新正式实验共 640 次，全部通过执行审计、检测/策略独立重放和服务器原始
归档核验。四类主检测队列各 60/60 次在 100 ms 内正确定位全部受影响方向；
p95 分别为黑洞 8.64 ms、25% 容量 29.82 ms、独立弱丢包 43.12 ms、
80 ms 链路延迟 8.66 ms。最慢一次为 47.63 ms。结论仅覆盖注册仿真条件。

慢代理降速边界中，收益门控把平均完成时间从直接换路的 440.80 ms 降到
389.54 ms；持续黑洞和弱丢包下则分别多花 5.75 ms 和 11.60 ms。因此目前
证明的是能避免一类有害换路，而不是所有故障都更快。主条件中代理实际
抢救了在途数据，没有新 B′ chunk 完成，不能表述成恢复健康双平面吞吐。

原生验证时 140 项代码检查通过；本次报告兼容性修正后，当前源码 142 项检查通过。完整数据、失败记录、存储位置与核验范围见
[证据索引](../research_evidence/README.md)。本轮仍未提交或推送 Git。

## 代码入口

| 部分 | 原生实现 | 独立重放 / 检查 |
| --- | --- | --- |
| 检测规则 | `src/simulator/detection/service_detector.h` | `python/limerlab/detector/service_detector.py` |
| 实际观测、报警运输 | `detection/monitor.h`, `transport/rdma.h` | `python/limerlab/service_replay.py` |
| 接收间隔窗口 | `detection/spacing.h` | 从原始 source/RX 逐包记录独立重建 P10、样本数和窗口 |
| 留下 / 替换代价 | `recovery/benefit_policy.h`, `recovery/decision.h` | `python/limerlab/benefit_policy.py`, `policy_replay.py` |
| 探测、健康报告、提交 | `recovery/proxy.h`, `transport/rdma.h` | `python/limerlab/audit.py` |
| 故障注入 | `experiment/faults.h`, `python/limerlab/inputs.py` | 注入真值仅供事后评分 |
| 冻结实验和完整性 | `tools/research_campaign.py` | `tools/verify_research.py` |
| 表图导出 | `tools/research_report.py` | 只读取完成的结果，不改变冻结输入 |

表中省略的原生路径前缀均为 `src/simulator/`。报警、策略和健康报告均有
独立日志及反例测试；代码、注释和测试名称使用英文。

## 实验流水线

先核验原交付并隔离副本，再用新源码从零编译原生后端。开发阶段暴露过
弱丢包不报警、短暂故障业务停滞、健康报告信息过早可见等问题；开发记录
保留在服务器，不能算正式成绩。修正后冻结二进制、源码、规则参数和新 seed，
运行 580 次正式矩阵。v3 在降速条件只达到 42/60，第一轮失败记录原样保留。
修正为 v4 后，先做独立重放和开发回归，再冻结新的不重叠 seed 范围做第二轮
580 次验收；不在同一冻结验证中边看结果边改参数。

检查 RNG 映射时又发现旧注入器 `seed+node` 会让相邻 scene seed 复用丢包流。
主矩阵不修改，另外注册 60 次 stride=32 的弱丢包确认，保持 native 规则和
负载不变。最终弱丢包检测采用该队列，原 60 次及其策略配对仍公开保留，
不合并样本以提高成功率。总计 640 次，原正式失败另列。

每次运行先检查执行正确性，再从实际传输日志独立重放检测与策略。压缩包
逐成员校验后才裁剪大日志。最后核对全部归档 SHA、保留证据和冻结评分器
重新计算的得分，按条件和配对导出报告。

## 从零复现

在 Linux（或本项目 Docker 镜像）中，从项目根目录执行。构建和实验输出
目录必须是新目录，不要覆盖现有正式记录。

```bash
python3 limer.py check --verbose
python3 limer.py build --out /work/research-build --jobs 16
python3 tools/research_campaign.py register --phase validation \
  --build /work/research-build --out /work/research-validation \
  --horizon-ms 400 --rounds 2 --chunks 64 \
  --include-delay --include-slow-quarter --seed-base 103200000 --seed-stride 32
python3 tools/research_campaign.py execute /work/research-validation --workers 8
python3 tools/verify_research.py /work/research-validation --progress
python3 tools/research_report.py /work/research-validation \
  --out /work/research-report --plots
```

上面的命令用当前默认的分隔随机流生成器创建新矩阵。历史 v2 的 stride=1
必须从它自己的 frozen tooling 重现，不可用当前生成器冒充同一注册。
补充队列的精确命令见 protocol；合并报告使用
`--independent-loss-campaign /work/results/validation-loss-independent-v4`。

运行和审计只用标准库；绘图另需 Matplotlib。复现相同注册 seed 是复核，
不能冒充新的 held-out 验证。改变算法后的下一次验收须另建独立 seed 范围。
`tools/dev_native_smoke.py` 是最早开发诊断的历史入口，含固定旧构建路径；
正式复现使用上面的 campaign 工具。

## 证据在哪里

原始归档保留在 otakotak：
`/home/suliu/LIMER_RESEARCH_2026-10-28/results/validation-v2/archives/`。
原生构建为同一服务器的 `build-v7/`；容器中对应 `/work/build-v7`。
本地 `research_evidence/validation-v2/` 是紧凑导出，省略大日志和原生二进制。
本地检查明确使用：

```bash
python3 tools/verify_research.py research_evidence/validation-v2 --skip-archives
```

这不能替代服务器全量归档核验。服务器核验结果随导出提供；需要从原始包
重新执行 packet audit 时，先取回对应归档并解压，而不能只靠紧凑表格。

`limer.py verify` 和 `tools/package_delivery.py` 属于原 2026-10-27 交付清单流程，
会正确地拒绝被修改的源码，不能用它们为本轮源码作原版认证。历史清单和
`reference/`、`validation/` 都保留原样，本轮使用新的研究核验流程。

这仍是 CPU simulation。检测达标只覆盖注册条件；完成审计证明逻辑交付、
epoch 和 ACK 约束，不等同于真实 GPU 验证或张量数值正确性。
