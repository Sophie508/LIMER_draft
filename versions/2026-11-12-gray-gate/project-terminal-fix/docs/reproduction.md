# 构建、运行与复现

所有命令从本项目根目录执行。无需原仓库、旧 Docker 卷或旧构建。

## 环境

Python 3.8+，Python 运行和审计仅使用标准库。C++ 需 Linux、GCC 9+、CMake、Boost、GSL、SQLite、libxml2。推荐 README 中的 Dockerfile。Windows 可核验参考数据和运行 Python 测试；原生网络仿真请使用 Linux/Docker。

可选的开发安装为 `python -m pip install -e .`，之后使用 `limer` 命令。构建、配置和第三方源码属于本项目源码目录；本版本按源码交付，不以脱离源码目录的 wheel 作为部署方式。

## 独立构建

```bash
python3 limer.py build --out /tmp/limer-build --jobs 2
```

构建器把自有后端源码复制到新目录，仅创建 `LimerSimulator` 一个应用目标，以 O2 编译并保留断言和日志。不会读取任何原工程的 `flags.make`、目标文件、链接命令或预编译库。构建后生成 `build.json`、二进制和库 SHA256、源码哈希与编译日志。编译期间源码变化会拒绝生成成功记录。

## 单场景

```bash
python3 limer.py run --build /tmp/limer-build --out /tmp/blackhole-g11 \
  --method G11 --scenario blackhole --rounds 2 --chunks 64 \
  --fault-ms 20 --horizon-ms 2500 --node 0 --seed 100001
```

四种方法为 G00/G10/G01/G11。场景包括 `healthy`、`quarter`、`weak_loss`、`blackhole`、`no_idle_helpers`、`slow_local`、`short_blackhole`。单次运行默认保留原始日志；需要验证压缩档时指定 `--archive-to /tmp/case.tar.gz`。再加 `--prune-raw` 才会在逐成员 SHA 核验后删除四份大日志。

每次自动执行独立审计、逐包重建的 Python M13 重放和性能计算。任一技术核验失败都返回非零并保留日志。任务达到观察上限是科学结果，与程序错误分开，运行成功不意味着任务已恢复完成。

## 配对实验

`experiments/qualification.json` 固定 7 项工程检查；`experiments/main.json` 固定 40 项主对照及 6 项边界，参数与参考验证一致。修改参数须另建实验文件和输出目录。

```bash
python3 limer.py campaign --build /tmp/limer-build --out /tmp/qualification
python3 limer.py campaign --build /tmp/limer-build --out /tmp/main \
  --preset experiments/main.json --workers 2
python3 limer.py report /tmp/main
```

运行前冻结 Python 包、检测规则、配置、场景文件和测试代码。每个并发 worker 使用独立进程，避免 Python GIL 串行化重放。所有已登记用例均出现在报告中；未运行、未核验和观察上限不会悄悄消失。暂时中断后可加同样参数与 `--resume`，只复用校验通过的完整归档；未完成的 attempt 保留并拒绝覆盖。

## 指标

主要指标为所有 rank、所有阶段所有逻辑数据经 ACK 确认的通信完成时间，扣除 1 ms 起点。另记录检测延迟、替换时间、新 B′chunk、救援 chunk、逐阶段耗时、10 ms 唯一 ACK 吞吐和三段传输/最终通知开销。替换后完整阶段与同编号健康阶段比较，不能将“任务恢复完成”等同于“恢复全部性能”。

## 数据和来源

`reference/` 保存不可变的 53 次原验证导出证据。机器旧路径只是记录；核验不执行这些路径上的命令。原始逐包大日志压缩档仍需从其归档存储另取，本交付的参考 bundle 不包含卷内原始大日志。新实验会在指定输出目录生成自身完整日志和压缩档。

参考结果和本次重构回归必须分开引用。参考结论：黑洞 G11 约 498–511 ms，弱丢包约 527–1496 ms，替换后阶段约为健康的 2.19 倍；纯降速没有 M13 告警。更长时间尺度的性能退化诊断分支尚未实现。
