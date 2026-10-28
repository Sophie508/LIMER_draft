# LIMER

> **2026-10-28 research extension:** This working copy adds a versioned
> canary/retransmission/business-stall/receiver-spacing detector and an observable switching-benefit
> gate. The 2026-10-27 `reference/` and `validation/` remain historical evidence,
> not results for the changed source. See [implementation](docs/research_implementation.md)
> and [registered experiment protocol](docs/research_protocol.md).
> Start with the [research handoff](docs/research_handoff.md) for conditions, code
> entry points, retained failures and evidence locations.

双平面通信的自适应分流、异常检测和 GPU 代理恢复仿真项目。

本项目是独立交付工程。运行和构建只使用本目录内的源码、配置与第三方网络库；不需要原来的两个仓库、原工作区目录或旧构建结果。仿真在 CPU 上运行，不需要真实 GPU。下述 G00–G11 定义保留；新增 `--detector service` 与 `--policy benefit`，原设置为 `legacy/always`。

## 系统做什么

B 线路退化后，自适应分流先减少其负担；所选检测器根据实际交付观测确认异常；经过探测和协调，用健康 GPU 中转路线 B′替换旧 B。未确认数据正确续传，后续新数据可在 A/B′间分配。物理网络保持两个平面。`legacy` 使用原 M13，`service` 使用新增 v4 规则；实际是否有后续 B′新业务须看 performance 指标，不能由一次激活推断。

| 方法 | 分流 | 检测驱动的线路替换 |
| --- | --- | --- |
| G00 | 预先固定 A/B 各半 | 关闭 |
| G10 | 完成反馈自适应分流 | 关闭 |
| G01 | 固定分配，B′接手原 B 份额 | 开启 |
| G11 | 自适应，替换后继续在 A/B′间分流 | 开启 |

同一检测设置下所有组支付同样的检测和报告成本；关闭替换的组仍记录检测结果。所选检测器的告警是恢复前提，不包含隐藏的阶段落后触发或额外 RTO 扩展。新增收益对照中，两种 G11 还支付同样的候选测量成本。

## 工程结构

```text
src/simulator/        检测、调度、代理、传输、控制、完成记账模块
python/limerlab/      配置、构建入口、实验执行、审计、重放和报告
configs/             自有拓扑与传输配置模板
experiments/         7 项资格检查、40+6 配对实验预设
tests/               正确性及配置边界检查
third_party/         固定的 RDMA/ns-3 源码和 M13 来源文件
reference/           原 53 次验证的不可变证据归档
validation/          本次独立构建和重构回归的证据
docs/                架构、复现、指标和边界
provenance/          来源提交、源码映射及改动说明
```

## 快速检查

Python 3.8+，仅标准库，无须安装 Python 依赖：

```bash
python limer.py --help
python limer.py check --verbose
python limer.py verify
python limer.py verify-reference
```

`verify` 校验的是原 2026-10-27 交付清单，会拒绝本轮新增/改动的源码；本轮核验请按 [研究交接](docs/research_handoff.md) 使用 `tools/verify_research.py`。

最后一条会校验并临时解压 `reference/` 中的原始导出证据，核对全部 53 次运行和冻结工具哈希。需要查看里面的逐项文件时使用 `python limer.py verify-reference --extract /tmp/limer-reference`，目标目录必须不存在。

## 构建和运行

Linux 使用 GCC 9+、CMake、Boost、GSL、SQLite 和 libxml2；完整环境见 `Dockerfile`。推荐直接使用 Docker：

```bash
docker build -t limer-delivery .
docker volume create limer-delivery-work
docker run --rm -v limer-delivery-work:/work limer-delivery build --out /work/build --jobs 2
docker run --rm -v limer-delivery-work:/work limer-delivery run \
  --build /work/build --out /work/healthy --method G11 --scenario healthy \
  --rounds 1 --chunks 16 --horizon-ms 100 --fault-ms 5
```

已准备好 Linux 工具链时，直接在项目目录执行：

```bash
python3 limer.py build --out /tmp/limer-build --jobs 2
python3 limer.py campaign --build /tmp/limer-build --out /tmp/limer-qualification
python3 limer.py campaign --build /tmp/limer-build --out /tmp/limer-main \
  --preset experiments/main.json --workers 2
python3 limer.py report /tmp/limer-main
```

单次运行与实验输出目录必须不存在。执行器冻结自己的 Python 工具和配置，保存原始数据、独立审计和逐包检测重放，并在核验压缩档后整理大日志。未完成任务如实保留。详见 [复现说明](docs/reproduction.md)。

## 结果与边界

原 53 次验证中，弱丢包和黑洞主用例在 G01/G11 下全部恢复完成，但 G11 替换后的阶段仍约为健康阶段的 2.19 倍。纯降速没有触发 M13；无空闲代理时不能恢复。完整证据在 `reference/`，本次重构回归见 `validation/`。

模型不执行 CUDA、张量运算、HBM 争用或计算重叠。以上 53 次数字描述 2026-10-27 基线版本；新增检测和收益判断必须由新的冻结矩阵验收。原 40+6 验证不等同于原计划的 700 次正式矩阵。`python limer.py verify` 核对的是原交付清单，编辑后的源码不能冒充该原构建；新实验使用 `tools/verify_research.py`。

来源、版权和依赖修改见 [第三方说明](THIRD_PARTY.md) 与 `provenance/`。历史证据中的旧机器路径只是不可变记录，运行时不使用它们。
