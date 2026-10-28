# 2026-10-28：检测与收益判断扩展

本目录在合作者 2026-10-27 交付上继续开发。`reference/` 和 `validation/`
不改写，也不作为新源码的性能证明。新版本只做 CPU 网络仿真。

## 一个具体过程

GPU 0 的 B 接入链路发生交付异常。源端既观察自己的真实业务 ACK，也每隔
2 ms 在同一条物理路径发送一个 64 KiB canary。报警后，先让同机代理与远端
代理完成一条三段传输，再把测得的路线信息通过计费的 96 B `HEALTH_REPORT`
送回源端。源端估计留下和替换各需多久，足够划算才开始协调。

## 检测输入和规则

`src/simulator/detection/service_detector.h` 与
`python/limerlab/detector/service_detector.py` 实现同一冻结规则，版本
`canary-service-v4`。输入没有故障时间、位置、丢包率或未来恢复时间。

- 首次 canary 后 20 ms 是校准期，冻结每路径完成时间的最大值。假定这段时间
  代表健康服务；从启动就持续变慢而没有健康参考，不属于本次验收保证。
- Canary 服务阈值为 `max(100 us, 2 * baseline + 100 us)`。未完成样本也可超时。
  实际 sender 重传同样把对应 canary 记作异常样本；同一 canary 多次重传只算一次。
- 在 40 ms 窗口内至少三个异常 canary，发送跨度至少 4 ms，形成一类报警证据。
- 对已分配、未完成、尚未迁移的原业务，40 ms 没有实际 ACK 前缀进展也可报警。
  空闲或尚未发出的业务不会触发此信号。
- 每路径只取首次满足规则的报警，不由 scorer 事后挑选最好信号。
  报警经 96 B 控制消息传送；<100 ms 用控制器实际收到的时间计算。

v3 的第一轮正式验证在降速上失败：健康排队抬高 RTT 阈值，60 次中有
18 次漏掉一个方向，42/60，未达到 95%。`validation-v1` 保留失败记录。
单独 canary 的 packet train 也受 QP 轮询干扰，不能直接当成链路容量。

v4 新增 receiver-local 的整条路径接收间隔信号：业务与探测的 accepted 包
一起统计，仅相邻两包都为完整 976 B payload 且间隔为正时采样，短尾包不
跳过。前 20 ms 校准 P10；之后每个非重叠 10 ms 窗至少 64 个样本，P10
连续两窗超过 `2 * baseline + 100 ns` 才报警。不足样本会中断确认；校准
不足时不能拿故障期补训。每窗 summary 由逐包日志独立重建核验。这排除了
首包前排队及同路径 QP 轮询的一部分混杂，不代表能在任意共享网络区分所有拥塞。

这判断的是交付服务异常和传输修复开销，不证明数据永久丢失。测量的包型、
阈值和校准条件必须一起公开；这是 [RFC 7679 的测量口径要求](https://www.rfc-editor.org/rfc/rfc7679.html)
所强调的背景，并非本实现已经获得普适性证明。

## 何时替换

`recovery/benefit_policy.h` 和 `limerlab/benefit_policy.py` 比较受限的
sender/phase 预计完成时间，不是全局 DAG 优化器。使用当前剩余 A/B 归属字节、
可重新分配的 pending 字节、近 10 ms 实际 ACK 服务、三段路线实测时间、
控制排队、四方协调和每 chunk 最终确认成本。

未知或过期路线要先测；健康候选不意味着更快。足够新鲜的数据支持下，预计
收益须超过 `max(1 ms, 10% * stay_time)`。零服务是当前观察窗口无进展，不是
知道故障会持续多久。即使不足一个 chunk，也支付完整首次转发和确认延迟。

Service 模式的 always 和 benefit 都使用 64 KiB 候选路线测量及计费健康报告，
使收益门控对照的测量条件一致。历史 legacy/always 仍保留 1024 B liveness probe。
二者的性能比较必须注明这一区别，不能把不同探测形状悄悄混成同一消融。

报告携带的实测时间在到达前不能被源端使用。时间戳的新鲜度从最后一段实测
完成计算，包含报告运输时间。旧 phase/version 报告只能释放自身资源，不能
清除新 pending 或覆盖新 binding。协调仍是 PREPARE/READY/COMMIT，未确认后缀
带新 epoch 续传；第三段和最终 ACK 完成后才记逻辑 DONE。

## 如何验证

```bash
python3 limer.py check --verbose
python3 limer.py build --out /work/research-build --jobs 16
python3 tools/research_campaign.py register --phase validation \
  --build /work/research-build --out /work/research-validation \
  --horizon-ms 400 --rounds 2 --chunks 64 --include-delay --include-slow-quarter \
  --seed-base 103200000 --seed-stride 32
python3 tools/research_campaign.py execute /work/research-validation --workers 32
python3 tools/verify_research.py /work/research-validation --progress
```

预期矩阵 580 次，四个主故障条件各 60 个 held-out seed；另外保留健康对照、
相同输入的策略配对和边界。慢代理且 B 仍可服务的长任务条件单独采用至少
800 ms 上限；同一配对内所有方法条件相同。见 protocol 的完整定义。

上面创建的是当前生成器的新矩阵；历史 `validation-v2` 使用其自己的冻结
stride=1 工具，不能由新默认重生成。旧注入器 `seed+node` 的随机流复用
问题另以 60 次 stride=32 弱丢包队列确认，不改变 detector 或 native build。
最终检测行的来源、旧队列经验结果和不池化原则见 protocol 与结果报告。

原始数据保留在服务器，归档后核对内容哈希才裁剪工作目录的六份大日志。
新归档使用 gzip level 6。须检查账号 quota，不能把 `df` 的整块磁盘空余
当成个人可写额度；部分已核验归档通过哈希校验后迁往个人 scratch，原路径
保留 symlink。全量核验容器必须同时挂载这些真实归档路径。
`service_replay` 对照真实 QP、线上重复发送、业务 ACK 和控制 FIFO 重放检测；
`policy_replay` 独立重建剩余字节、服务率、候选路线报告和收益判断。
完整性核验再检查冻结工具、构建、归档 SHA、保留文件与得分。
本地仅有紧凑导出时必须明确 `--skip-archives`，不声称核过服务器原始归档。

## 结果边界

先完成冻结验证再报告是否达标。开发案例、单元测试和 native 冒烟均不能代替
正式每条件的分母。跨文件同一 ns 没有统一事件序号，审计有明确的排序边界。

当前不验证张量数值、GPU/HBM/计算重叠，也没有实现独立分布式代理发现。
接收事件时间戳是理想的仿真纳秒时间戳，未模拟软件采样噪声。
端点事件与接收窗口 summary 直接送入共享 detector 对象；没有单独序列化
每条原始观测或跨机 summary 的传输。报警、候选健康报告和恢复控制消息
按 FIFO 计费；这不等于已经验收分布式遥测实现。
候选资格使用阶段完成状态，再通过计费探测和协调确认。一次故障 episode
后如何恢复旧 B、代理随后再次故障、启动即退化和任意网络背景均没有覆盖。
线上计数统计的是数据侧 wire（含观测头及重传），不是包含所有 transport ACK
的完整链路字节总量；控制流量另计。Canary 固定负载约为每路径链路容量的
2.62% payload，实际头部和重传开销须从实验记录另报。
