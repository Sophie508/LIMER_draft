# 归档、复现与未包含的大文件

`artifacts/` 保存历史输入与结果，不能作为新实验输出目录。
原始 JSON 保留原服务器目录和命令，这是历史溯源信息，不是运行新机器时必须存在的路径。

| 目录 | 内容 |
|---|---|
| `artifacts/m13/` | M13 各次注册、逐次状态与 truth、汇总、独立 audit 和冻结科学源码，保留初始失败与中断 |
| `artifacts/m12/` | M12 各版 development、validation、boundary 与选择性丢包反例，保留失败口径 |
| `artifacts/server/` | M7/M8/M9/M10/M11、静态校准、Ring/OptCC 的注册与输入、逐次状态、汇总和压缩轨迹 |
| `artifacts/frozen/` | 原服务器冻结版本；用于识别哪版代码产生了哪组结果，不是重复运行所有旧分支的入口 |
| `artifacts/samples/m13/` | 主验证每个故障/对照 condition 的一条完整报告轨迹，并带 packet、采样和收集器事件；14 个案例 |
| `baselines/optcc_checks/` | 作者源文件与下载包 hash、四个作者生成器输出；不包含作者二进制 |

大规模 packet/report 数据继续留在 otakotak 的
`/home/suliu/scratch/LIMER_WORK_2026-10-10`。
仅 M13 自适应主验证的完整原始运行目录约 3 GB，不把它们全部塞进 Git。
本包带全部注册、逐次状态和结果分母；只带部分完整 M13 输入轨迹，不能据此声称
在离线交接机上重新审计了全部 400 次的每个 packet 事件。
已有原始独立 audit 账本保留在包内，新的全量核验可访问服务器或重新运行注册 campaign。

`handoff/verify.py` 的检查范围比原服务器的全量审计窄，输出中会明确注明。
`.gz` 轨迹是无损压缩，Python 标准库 `gzip` 或常见解压工具均可读取。

SimAI 与其 ns-3 后端是外部依赖，通过固定 commit 下载，不复制 Docker layer、
机器缓存或二进制。原始许可在 `handoff/licenses/`，我们的 replay adapter 和
transport correction 在 `baselines/simai_runtime/replay_adapter.diff` 与
`transport_repair.diff`。`backend.py` 只在新的 scratch 副本应用这些修改。

这份归档没有新增科学结果。交接入口的测试记录单独写在 `handoff/validation/`，
不加入论文的样本数或实验成功率。
