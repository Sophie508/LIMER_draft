# 来源与第三方文件

本工程保留原代码版权声明，不将外部网络库声称为本项目原创。

| 部分 | 来源 | 当前用途 |
| --- | --- | --- |
| RDMA/ns-3 | ns-3 7e3cb5b88c99abcb582c5abc3919484a4805111b 及服务器救援版本的补丁 | 固定的网络模拟后端，源码位于 `third_party/ns3` |
| 网络初始化 | SimAI f5efb5a93ea9be7db25a8843f9f7ff54044f6062 的修改后 `common.h` | 提取拓扑、路由和网卡初始化；不依赖 AstraSim 应用入口 |
| 反馈与传输修改 | ZjianJ/simai-limer，7c372d6f7e4e49ac2ccd0d2c923636c6324128b3 及本地整合实现 | 完成反馈、路径绑定、唯一 ACK 和三段代理传输 |
| M13 | Sophie508/LIMER_draft，1447bc48689802662f0571feaf0d3e03cace1475 | C++ 检测与独立 Python 重放，阈值和判定规则保持原样 |
| 53 次参考验证 | 2026-10-27 完成的双平面闭环验证 | 不可变的结果来源和回归参照，不作为新工程重新运行的结果 |

ns-3 的许可原文见 `third_party/ns3/LICENSE` 和 `third_party/LICENSE.ns3`。源自 SimAI 的文件保留 Apache 2.0 声明；原上游许可见 `third_party/LICENSE.SimAI`。合作者项目没有在这里新授予许可，本工程保留其来源、原声明和固定提交记录，见 `provenance/original_sources.json`。

`third_party/ns3/src/point-to-point/model/rdma-hw.cc` 是经过验证的观测线协议、物理 NIC 绑定、机内 ACK 返回路径修改版。它与其他 RDMA 修改共同编译，无须从旧构建目录读取目标文件或库。

M13 Python 文件仅把模块导入改为本项目包内相对导入。C++ 增加告警回调与有向路径编码适配；原规则源码同时保存在 `third_party/m13`。重构的函数映射在 `provenance/migration.json`。
