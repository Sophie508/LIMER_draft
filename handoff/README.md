# 合作者交接：先看实现，再看实验条件

这份交接对应 **2026-10-15 最后核验的论文快照**，整理于 2026-10-22。
论文快照在 [`paper/snapshot_2026-10-15/`](../paper/snapshot_2026-10-15/)，
不是对当前 Overleaf 内容的实时同步。整个项目的验收范围是 CPU 仿真与模拟，
不要求真实 GPU、交换机或网卡实验。

可以先想象一个包序列：D103 已到，而 D102 还没到。检测器先等待，缺口持续
40 ms 才作为异常证据。业务包少时，根据前一个已结束的 10 ms 发送窗口补探测包。
报警表示某条路径的交付出现异常，之后才评估换路是否划算。

## 已实现了什么

| 部分 | 代码入口 | 已有证据与边界 |
|---|---|---|
| 最新业务交付检测 M13 | [`business_delivery.py`](../limer_v0/business_delivery.py)、[`LimerBusinessObservation.cc`](../simulation/LimerBusinessObservation.cc)、[`probe_budget.h`](../simulation/probe_budget.h) | 自适应探测验证 400/400 次正确定位且严格 <100 ms，另有 60 个主对照与 60 个高业务量对照；限定为所注册的单跳模型 |
| 冻结的旧检测器 M7/M8/M12 | [`tcp_loss.py`](../limer_v0/tcp_loss.py)、[`batch_loss.py`](../limer_v0/batch_loss.py)、[`hybrid_delivery.py`](../limer_v0/hybrid_delivery.py) | 保留未达标结果、边界实验及同报告 shadow 比较，不把失败分母删掉 |
| ACK 进度检测与换路收益 M10/M11 | [`ack_progress.py`](../limer_v0/ack_progress.py)、[`pending_route_cost.py`](../limer_v0/pending_route_cost.py)、[`LimerClosedLoopReplay.cc`](../simulation/LimerClosedLoopReplay.cc) | 更快备用路径下切换有收益，较慢备用路径下选择 stay；使用的 ACK 检测器与最新 M13 不同 |
| 协调执行 M9 | [`LimerDynamicDagReplay.cc`](../simulation/LimerDynamicDagReplay.cc)、[`audit_dynamic_dag.py`](../simulation/audit_dynamic_dag.py) | PREPARE/READY/COMMIT、共同版本激活、仅迁移未启动流；8 个完成案例与 1 个预期拒绝案例 |
| CPU/TCP 原型 | [`worker.py`](../limer_v0/worker.py)、[`orchestrator.py`](../limer_v0/orchestrator.py)、[`configs/`](../configs/) | 帧标识、CRC、版本检查及局部换路；其墙钟时间与 ns-3 仿真时间分开报告 |
| Ring/OptCC 网络比较 | [`dag_tools.py`](../baselines/simai_runtime/dag_tools.py)、[`LimerDagReplay.cc`](../baselines/simai_runtime/LimerDagReplay.cc) | 固定输入的网络重放与分段敏感性共 30 条；不是完整 LIMER 对 OptCC 的比较 |

**还没有完成**：把最新 M13 检测接到 M11 集体通信控制器、Ring/OptCC 与
stay/fixed/LIMER 的交叉比较、数值 AllReduce 验证，以及已启动并卡住的流的迁移救援。

## 建议的阅读顺序

1. [`CONDITIONS.md`](CONDITIONS.md)：condition 从哪里来、每行具体改变什么。
2. [`PAPER_MAP.md`](PAPER_MAP.md)：论文每张表对应哪个实现、哪个归档。
3. [`conditions/m13_adaptive_validation.tsv`](conditions/m13_adaptive_validation.tsv)：主结果的分组参数；完整逐次 seed 与注入时间见对应 registration。
4. [`../simulation/README.md`](../simulation/README.md)：原始模型、观测字段、历史运行流程。
5. [`ARTIFACTS.md`](ARTIFACTS.md)：冻结代码、逐次结果、原始轨迹样本和大数据存放边界。

## 不装 Docker，先核对交接内容

需要 Python 3.12 或更新版本。只使用标准库，不需要 GPU 或第三方 Python 包。
在仓库根目录运行：

```bash
python3 handoff/verify.py --output /tmp/limer-offline-verification.json
python3 -m unittest discover -s tests -p 'test_*.py'
PYTHONPATH=baselines/simai_runtime python3 -m unittest discover -s baselines/simai_runtime -p 'test_*.py'
```

`verify.py` 会从逐次状态重算 M13 三个验证账本，用 14 个真实报告样本重放检测器，
重新核对 M9 的 9 个执行案例、M11 的 8 个闭环案例，以及 Ring/OptCC 的 30 条网络轨迹。
这一步验证归档与实现一致，不会启动新仿真，也不是新的独立实验样本。

## 在另一台 Linux/Docker 机器上启动

需要 Python 3.12+、Docker CLI、`patch`，以及能访问 GitHub 下载固定上游版本。
容器内使用 Ubuntu 20.04 构建 C++。宿主 Python 与容器 Python 的用途不同。
建议准备至少 5 GB 独立 scratch 空间。下面的 `--root` 必须放在源码仓库外，
避免把编译产物和新实验混进版本控制。

```bash
python3 handoff/backend.py prepare --root /tmp/limer-reproduction
python3 handoff/backend.py image --root /tmp/limer-reproduction
python3 handoff/backend.py build --root /tmp/limer-reproduction --stage m13 --jobs 2

python3 handoff/launch.py m13 --root /tmp/limer-reproduction -- \
  --campaign adaptive_smoke --tag collaborator_smoke --workers 1
```

rootless Docker 用户在 `image`、`build` 和 `launch` 上都加同一个
`--docker-host unix:///你的/docker.sock`。普通 Linux Docker 默认 socket 为
`unix:///var/run/docker.sock`。本交接不要求合作者拥有原服务器账号或 socket。

smoke 只检查入口能否运行。要重放论文的完整 M13 条件：

```bash
python3 handoff/launch.py m13 --root /tmp/limer-reproduction -- \
  --campaign adaptive_validation --tag collaborator_reproduction --workers 2
python3 handoff/launch.py m13 --root /tmp/limer-reproduction -- \
  --campaign adaptive_high_controls --tag collaborator_reproduction --workers 2
```

新 tag 不会产生新 seed。上述命令重放论文注册的条件与 seed，属于复现。
现有输出目录会被拒绝覆盖；改检测规则后的新验证应另行冻结代码和注册 seed。
新构建可能因编译器、库和镜像变化而有不同的二进制 hash，不能冒充原始运行环境。

## 其他组件的入口

`backend.py build --stage` 支持 `m8/m9/m10/m11/m12/m13/optcc/static`，
各自在独立后端目录构建。先构建相应阶段，再运行：

```bash
python3 handoff/launch.py m8 --root /tmp/limer-reproduction -- --campaign validation --tag collaborator
python3 handoff/launch.py m9 --root /tmp/limer-reproduction -- --tag collaborator
python3 handoff/launch.py m10 --root /tmp/limer-reproduction -- --tag collaborator
python3 handoff/launch.py m11 --root /tmp/limer-reproduction -- --tag collaborator
python3 handoff/launch.py m12 --root /tmp/limer-reproduction -- --campaign validation --tag collaborator --workers 2

python3 handoff/backend.py build --root /tmp/limer-reproduction --stage optcc
python3 handoff/replay_network.py --root /tmp/limer-reproduction --tag collaborator
```

`replay_network.py` 使用包内已保存的全部 30 个网络图与配置，重新运行论文的网络比较，
不依赖 OptCC 匿名仓当前是否在线。作者原始 DAG 生成器未被当成我们的代码重新署名或复制；
其来源、文件 hash 和四个生成器检查样例在 [`../baselines/optcc_checks/`](../baselines/optcc_checks/)。
要更改 OptCC 的算法或生成新参数，需要另取作者的原始生成器，不能把已保存图当成完整作者实现。

历史 CPU/Mininet 脚本在 `baselines/simai_runtime/`，对应冻结源码在
`artifacts/frozen/limer_source_m7_tcp_v3/`。这条路径需要 Linux Mininet、内核网络能力、
OVS/IFB 与 privileged 容器；它与上述无需 GPU 的单跳 UDP 仿真是不同平台。
原脚本、原 hash 和失败记录保留在包内，`launch.py` 仅在 scratch 副本里替换根目录、
Docker socket 和镜像名字，并把全部替换前后 hash 写入 `logs/handoff_source_adaptations.json`。
它不会更改 C++ 检测逻辑或 Python 检测器。
