import {
  PHASES,
  createReplayModel,
  deriveScene,
  selectRun,
  setState,
} from "./replay.js";


const DATA_URL = "assets/data/demo-data.json";
const REPOSITORY_URL = "https://github.com/Sophie508/LIMER_draft";
const REPOSITORY_BASE = `${REPOSITORY_URL}/blob/main/`;
const repoLink = (path) => `${REPOSITORY_BASE}${path}`;
const repositoryLinks = new Map([
  ["README.md", repoLink("README.md")],
  ["environment_probe.txt", repoLink("environment_probe.txt")],
  ["docs/architecture.md", repoLink("docs/architecture.md")],
  ["docs/experiment_design.md", repoLink("docs/experiment_design.md")],
  ["docs/current_limitations.md", repoLink("docs/current_limitations.md")],
  ["limer_v0/topology.py", repoLink("limer_v0/topology.py")],
  ["limer_v0/qdisc.py", repoLink("limer_v0/qdisc.py")],
  ["limer_v0/faults.py", repoLink("limer_v0/faults.py")],
  ["limer_v0/sentinel.py", repoLink("limer_v0/sentinel.py")],
  ["limer_v0/orchestrator.py", repoLink("limer_v0/orchestrator.py")],
  ["limer_v0/refiner.py", repoLink("limer_v0/refiner.py")],
  ["limer_v0/metrics.py", repoLink("limer_v0/metrics.py")],
  ["limer_v0/coordinator.py", repoLink("limer_v0/coordinator.py")],
  ["limer_v0/state.py", repoLink("limer_v0/state.py")],
  ["limer_v0/worker.py", repoLink("limer_v0/worker.py")],
  ["limer_v0/protocol.py", repoLink("limer_v0/protocol.py")],
  ["limer_v0/report.py", repoLink("limer_v0/report.py")],
  ["configs/c1_rate20.json", repoLink("configs/c1_rate20.json")],
  ["configs/c3_full.json", repoLink("configs/c3_full.json")],
  ["results/aggregate_summary.json", repoLink("results/aggregate_summary.json")],
  ["results/c3_rep01/summary.json", repoLink("results/c3_rep01/summary.json")],
  ["results/c3_rep01/events.jsonl", repoLink("results/c3_rep01/events.jsonl")],
  ["results/c3_rep01/switch_timeseries.csv", repoLink("results/c3_rep01/switch_timeseries.csv")],
  ["results/c3_rep01/version_commits.csv", repoLink("results/c3_rep01/version_commits.csv")],
  ["results/c3_rep01/correctness.json", repoLink("results/c3_rep01/correctness.json")],
  ["results/c3_rep01/worker_rounds.csv", repoLink("results/c3_rep01/worker_rounds.csv")],
  ["tests/test_report.py", repoLink("tests/test_report.py")],
]);
const MAX_RETENTION = 1.2;

const translations = {
  en: {
    "nav.demo": "Demo",
    "nav.implementation": "Implementation",
    "nav.evidence": "Evidence",
    "nav.mapping": "Mapping",
    "nav.roadmap": "Next steps",
    "hero.eyebrow": "Stage review · CPU/Mininet emulation",
    "hero.title": "A link can stay UP while collective performance collapses.",
    "hero.body": "LIMER detects a switch-facing signal, confirms end-host impact, and coordinates a move to a healthy fabric.",
    "hero.action": "Replay the archived incident",
    "demo.title": "Archived C3 incident replay",
    "implementation.title": "What we built and where it lives",
    "evidence.title": "Evidence explorer",
    "mapping.title": "From requirements to evidence",
    "boundaries.title": "Interpretation boundary",
    "roadmap.title": "Prioritized next steps",
    "roadmap.standby.title": "Isolate standby-path variance",
    "roadmap.confirmation.title": "Reduce confirmation delay",
    "roadmap.scope.title": "Expand fault and platform scope",
    "feedback.title": "Feedback requested",
    "feedback.telemetry": "Which production telemetry target should be integrated first?",
    "feedback.redundancy": "Does the healthy second-fabric assumption match the intended deployment setting?",
    "feedback.order": "Should the next milestone prioritize the gray-loss matrix or GPU/NCCL integration?",
    "footer.note": "Evidence-driven CPU prototype stage review",
  },
  zh: {
    "nav.demo": "演示",
    "nav.implementation": "具体实现",
    "nav.evidence": "证据",
    "nav.mapping": "任务对应",
    "nav.roadmap": "下一步",
    "hero.eyebrow": "阶段性研究汇报 · CPU/Mininet 仿真",
    "hero.title": "链路保持 UP，集体通信性能仍可能骤降。",
    "hero.body": "LIMER 先捕获交换机侧信号，再确认端侧影响，并协调所有 worker 切换到健康 fabric。",
    "hero.action": "回放归档实验",
    "demo.title": "C3 归档事件回放",
    "implementation.title": "我们具体实现了什么",
    "evidence.title": "实验数据浏览器",
    "mapping.title": "从项目要求到当前证据",
    "boundaries.title": "结论边界",
    "roadmap.title": "优先 next steps",
    "roadmap.standby.title": "隔离备用路径的性能波动",
    "roadmap.confirmation.title": "缩短端侧确认延迟",
    "roadmap.scope.title": "扩展故障类型与平台范围",
    "feedback.title": "希望获得的方向反馈",
    "feedback.telemetry": "下一阶段应优先接入哪种生产级遥测接口？",
    "feedback.redundancy": "健康第二张 fabric 的假设是否符合目标部署场景？",
    "feedback.order": "下一里程碑应优先做 gray-loss matrix，还是 GPU/NCCL 集成？",
    "footer.note": "基于真实证据的 CPU 原型阶段汇报",
  },
};

const content = {
  en: {
    hero: {
      baseline: "100 Mbit/s",
      fault: "20 Mbit/s",
      stages: ["Switch signal", "Host confirmation", "Coordinated recovery"],
    },
    replay: {
      boundary: "Archived run replay · visual time compressed",
      guideTitle: "How to explore this archived run",
      guideSteps: [
        "Choose one real repeat",
        "Drag the timeline or select an event",
        "Watch the route, retention, and explanation update together",
      ],
      dragHint: "Interactive · drag this timeline or select an event",
      compressed: "Playback is visually compressed; displayed timings come from archived evidence.",
      play: "Play",
      pause: "Pause",
      restart: "Restart",
      run: "Run",
      speed: "Visual speed",
      scene: {
        baseline: "Healthy baseline on Fabric A",
        fault: "Rank 2 access link is rate-limited but stays UP",
        detected: "Switch-facing counter emits a suspicion",
        confirmed: "End-host impact is confirmed",
        committed: "All ranks commit route version 1",
        recovered: "Recovered rounds complete on Fabric B",
      },
      events: [
        ["Healthy baseline", "Four workers use Fabric A, route version 0."],
        ["FAULT_APPLIED", "w2-eth0 stays UP; rate becomes 20 Mbit/s."],
        ["SWITCH_SUSPECT", "Observed at the distinct switch-facing sA-eth3 counter."],
        ["HOST_CONFIRM", "The degraded round completes and standby B health passes."],
        ["RECOVERY_COMMIT", "All four ranks are READY; route B, version 1."],
        ["Recovered round", "Three archived post-recovery rounds determine the gate."],
      ],
      labels: ["Baseline", "Fault", "Detect", "Confirm", "Commit", "Recovered"],
      phaseHelp: [
        "Before fault injection, all four workers communicate normally on Fabric A.",
        "The w2 access link remains UP, but its rate drops from 100 to 20 Mbit/s.",
        "A distinct switch-facing counter observes persistent rate degradation.",
        "The host gate confirms collective slowdown and checks that standby B is healthy.",
        "All four workers agree to apply route version 1 at the same future round.",
        "Traffic completes on Fabric B and the archived run measures recovery retention.",
      ],
      activeRoute: "Active route",
      retention: "Matched-baseline retention",
      gate: "Fixed C3 gate ≥ 0.900",
      faultRetention: "Fault retention",
      recoveryRetention: "Post-recovery",
      checksumErrors: "CRC errors",
      versionErrors: "Version errors",
      source: "Open source evidence",
    },
    implementation: {
      intro: "Each prototype layer is linked to the tools, source modules, and archived artifacts that make the claim inspectable.",
      stackLabel: "Prototype technology stack",
      stack: ["Python 3", "Mininet", "Open vSwitch", "Linux tc/netem", "Framed TCP ring", "JSON · JSONL · CSV evidence"],
      labels: {
        built: "What we built",
        tools: "Tools",
        source: "Source code",
        evidence: "Evidence produced",
        boundary: "Current boundary",
        open: "Open in repository",
      },
      cards: [
        {
          layer: "Layer 1",
          title: "Switch-facing first signal",
          built: "A target 20 ms sampler reads the distinct switch-facing RX counter. Three consecutive low-rate samples trigger a high-recall suspicion.",
          tools: ["Python 3", "Mininet", "Open vSwitch", "Linux counters"],
          files: ["limer_v0/topology.py", "limer_v0/qdisc.py", "limer_v0/faults.py", "limer_v0/sentinel.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/switch_timeseries.csv", "results/c3_rep01/events.jsonl"],
          boundary: "Management-plane switch-facing proxy; no ASIC, P4 pipeline, or resident switch agent is claimed.",
        },
        {
          layer: "Layer 2",
          title: "End-host confirmation",
          built: "A deterministic gate combines switch suspicion, completed-round slowdown, and standby-fabric health to confirm, suppress, or defer recovery.",
          tools: ["Python 3", "Round timing", "Matched baseline", "Standby probe"],
          files: ["limer_v0/refiner.py", "limer_v0/metrics.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/events.jsonl", "results/c3_rep01/summary.json"],
          boundary: "Explainable fixed rule; the proposed neuro-fuzzy classifier and Gaussian Process uncertainty are not implemented.",
        },
        {
          layer: "Layer 3",
          title: "Coordinated recovery",
          built: "Four workers execute prepare, READY, and commit so one future round activates Fabric B with route version 1 for every rank.",
          tools: ["Python 3", "TCP control channel", "Versioned state machine", "Dual OVS fabrics"],
          files: ["limer_v0/coordinator.py", "limer_v0/state.py", "limer_v0/worker.py", "limer_v0/protocol.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/version_commits.csv", "results/c3_rep01/correctness.json", "results/c3_rep01/worker_rounds.csv"],
          boundary: "Executable route-version scaffold; no real PyTorch process group or NCCL communicator is rebuilt.",
        },
        {
          layer: "Experiment pipeline",
          title: "Repeatable execution and reporting",
          built: "Predeclared conditions drive one topology lifecycle per run. The reporter recomputes gates and retains all failed repeats.",
          tools: ["C0-C5 JSON configs", "Immutable event log", "Python unittest", "Static report generation"],
          files: ["configs/c3_full.json", "limer_v0/orchestrator.py", "limer_v0/report.py", "tests/test_report.py"],
          evidence: ["results/aggregate_summary.json", "docs/experiment_design.md"],
          boundary: "Three repeats per condition support an engineering stage review, not publication-level tail claims.",
        },
      ],
    },
    evidence: {
      denominator: "18 clean topology lifecycles: C0-C5, three repeats each. No failed repeat is discarded.",
      median: "Median selected retention",
      gates: "Run gates passed",
      overall: "Overall acceptance remains false",
      raw: "Raw repeats",
      source: "Open aggregate evidence",
      conditions: {
        C0: ["Fault-free control", "Matched fault-free rounds remain near baseline."],
        C1: ["Persistent rate fault", "The still-up 20 Mbit/s access link reduces completed throughput to about 21%."],
        C2: ["Detect only", "Detection fires, but performance remains degraded without recovery."],
        C3: ["Full proxy closed loop", "The closed loop commits to Fabric B; only one of three repeats clears the fixed 0.9 gate."],
        C4: ["Oracle recovery", "Oracle-triggered recovery estimates the current emulation upper bound."],
        C5: ["100 ms transient", "The host gate suppresses recovery for the short transient."],
      },
    },
    mapping: {
      intro: "This mapping separates the bounded first-stage deliverables from the longer-term research system. A delivered milestone does not mean the corresponding formal objective is complete.",
      milestoneTitle: "Initial Milestone Requirements",
      milestoneNote: "Public task-level requirements only; internal planning material and collaboration notes are not reproduced here.",
      formalTitle: "Formal Research Objectives",
      formalNote: "O1-O4 are evaluated against the intended research mechanisms, not only against the CPU demo.",
      labels: {
        requirement: "Requirement",
        delivery: "Current delivery",
        evidence: "Evidence",
        status: "Status",
        implemented: "Implemented now",
        missing: "Still required",
        open: "Open evidence",
      },
      statusLabels: {
        delivered: "Delivered",
        partial: "Partial",
        "not-started": "Not started",
      },
      milestones: [
        {
          id: "M1",
          requirement: "Understand and bound the problem",
          delivery: "Defined the still-up access-link degradation question, the three-layer control loop, experiment semantics, and explicit claim boundaries.",
          evidence: ["docs/architecture.md", "docs/experiment_design.md", "docs/current_limitations.md"],
          status: "delivered",
        },
        {
          id: "M2",
          requirement: "Lock the first-stage scope",
          delivery: "Focused on one AllReduce-like scenario, CPU/Mininet emulation, and controlled synthetic fault injection.",
          evidence: ["configs/c3_full.json", "docs/experiment_design.md"],
          status: "delivered",
        },
        {
          id: "M3",
          requirement: "Review related work and choose an emulation platform",
          delivery: "A separate background review informed the design; Mininet with Open vSwitch was selected for the bounded CPU prototype.",
          evidence: ["README.md", "environment_probe.txt", "docs/architecture.md"],
          status: "delivered",
        },
        {
          id: "M4",
          requirement: "Build a small network and communication demo",
          delivery: "Created four worker namespaces, one or two OVS fabrics, and a framed four-rank TCP ring workload.",
          evidence: ["limer_v0/topology.py", "limer_v0/worker.py", "limer_v0/protocol.py"],
          status: "delivered",
        },
        {
          id: "M5",
          requirement: "Inject a still-up network fault",
          delivery: "Rate-limited rank 2 from 100 to 20 Mbit/s while both link endpoints remained UP.",
          evidence: ["configs/c1_rate20.json", "limer_v0/faults.py", "results/c3_rep01/events.jsonl"],
          status: "delivered",
        },
        {
          id: "M6",
          requirement: "Observe and record impact signals",
          delivery: "Recorded switch counters, timings, throughput, route versions, CRC checks, and all-rank completion evidence.",
          evidence: ["results/c3_rep01/switch_timeseries.csv", "results/c3_rep01/worker_rounds.csv", "results/c3_rep01/correctness.json"],
          status: "delivered",
        },
        {
          id: "M7",
          requirement: "Produce initial repeated results",
          delivery: "Ran the predeclared C0-C5 matrix across 18 independent topology lifecycles and retained both failed C3 repeats.",
          evidence: ["results/aggregate_summary.json", "limer_v0/report.py"],
          status: "delivered",
        },
      ],
      objectives: [
        {
          objective: "O1",
          title: "Lightweight in-network monitoring",
          implemented: "Switch-facing counter interface, target 20 ms polling, and a persistent high-recall trigger.",
          missing: "Switch-resident implementation, production telemetry integration, and measured switch resource budget.",
          evidence: ["limer_v0/sentinel.py", "results/c3_rep01/switch_timeseries.csv", "docs/architecture.md"],
          status: "partial",
        },
        {
          objective: "O2",
          title: "Uncertainty-informed fault detection",
          implemented: "The switch-triggered host decision boundary and deterministic confirm/suppress behavior are executable.",
          missing: "Neuro-fuzzy classification, GP uncertainty, trained fault classes, calibration, and accuracy evaluation.",
          evidence: ["limer_v0/refiner.py", "results/c3_rep01/events.jsonl", "docs/current_limitations.md"],
          status: "partial",
        },
        {
          objective: "O3",
          title: "Rapid topology recovery",
          implemented: "A versioned all-rank handover moves the TCP workload from Fabric A to a pre-existing healthy Fabric B.",
          missing: "Real GPU/NCCL communicator adaptation and production recovery failure handling.",
          evidence: ["limer_v0/coordinator.py", "results/c3_rep01/version_commits.csv", "results/c3_rep01/correctness.json"],
          status: "partial",
        },
        {
          objective: "O4",
          title: "Online self-evolution",
          implemented: "No learning or adaptation mechanism is included in CPU v0.",
          missing: "Weak supervision, pseudo-labeling, online model updates, and unseen-fault evaluation.",
          evidence: ["docs/current_limitations.md"],
          status: "not-started",
        },
      ],
    },
    boundaries: [
      ["AllReduce-like", "Framed TCP ring traffic exercises synchronization pressure but does not reduce tensors."],
      ["CPU / Mininet", "No GPU, training framework, NCCL, RDMA, checkpoint, or optimizer participates."],
      ["Management-plane proxy", "The detector reads switch-facing Linux counters but is not resident in switch hardware."],
      ["Redundant path assumed", "Recovery requires a healthy pre-existing Fabric B and persistent B-side TCP rings."],
      ["Latency bottleneck", "Switch suspicion is about 50 ms, but whole-round host confirmation is about 5.27 s."],
    ],
    roadmap: [
      ["Stabilize C3 recovery", "Keep the fixed 0.9 gate and compare idle, keepalive, and pre-warmed Fabric B to isolate standby-path variance."],
      ["Reduce confirmation delay", "Emit step-level progress while a round is in flight, while retaining a transient condition to measure false-trigger suppression."],
      ["Add gray-loss conditions", "Hold rate constant and predeclare low non-zero loss levels so the detector is tested beyond bandwidth degradation."],
      ["Replace the telemetry proxy", "Connect the same interface to realistic streaming telemetry and measure polling, memory, and switch-side overhead."],
      ["Implement uncertainty-aware classification", "Train and calibrate the proposed classifier and uncertainty estimator on separately generated traces."],
      ["Move to real collectives", "Validate numerical CPU collectives first, then implement and test GPU/NCCL communicator recovery."],
    ],
    feedback: [
      "Which production telemetry target should be integrated first?",
      "Does the healthy second-fabric assumption match the intended deployment setting?",
      "Should the next milestone prioritize the gray-loss matrix or GPU/NCCL integration?",
    ],
  },
  zh: {
    hero: {
      baseline: "100 Mbit/s",
      fault: "20 Mbit/s",
      stages: ["交换机侧信号", "端侧确认", "协同恢复"],
    },
    replay: {
      boundary: "归档实验回放 · 视觉时间已压缩",
      guideTitle: "如何查看这次真实归档实验",
      guideSteps: [
        "选择一次真实重复实验",
        "拖动时间轴，或点击任一事件",
        "同时观察路径、retention 和解释如何变化",
      ],
      dragHint: "可交互 · 拖动此时间轴，或点击任一事件",
      compressed: "播放过程经过视觉压缩；页面中的毫秒和秒数来自归档实验数据。",
      play: "播放",
      pause: "暂停",
      restart: "重播",
      run: "实验",
      speed: "视觉速度",
      scene: {
        baseline: "Fabric A 上的健康基线",
        fault: "Rank 2 接入链路被限速，但仍保持 UP",
        detected: "交换机侧计数器发出可疑信号",
        confirmed: "端侧确认集体通信受到影响",
        committed: "所有 rank 提交 route version 1",
        recovered: "Fabric B 上的恢复轮次完成",
      },
      events: [
        ["健康基线", "四个 worker 使用 Fabric A，route version 0。"],
        ["FAULT_APPLIED", "w2-eth0 保持 UP，带宽降为 20 Mbit/s。"],
        ["SWITCH_SUSPECT", "在独立的交换机侧 sA-eth3 计数器观察到。"],
        ["HOST_CONFIRM", "退化轮次结束，且备用 Fabric B 健康检查通过。"],
        ["RECOVERY_COMMIT", "四个 rank 全部 READY，切换到 route B、version 1。"],
        ["恢复轮次完成", "三个归档的恢复后轮次共同决定 gate。"],
      ],
      labels: ["基线", "故障", "检测", "确认", "提交", "恢复"],
      phaseHelp: [
        "故障注入前，四个 worker 在 Fabric A 上正常通信。",
        "w2 接入链路仍显示 UP，但带宽从 100 降到 20 Mbit/s。",
        "独立的交换机侧计数器观察到持续速率下降。",
        "主机侧确认 collective 变慢，并检查备用 Fabric B 是否健康。",
        "四个 worker 同意在同一个未来轮次启用 route version 1。",
        "流量在 Fabric B 上完成，归档实验据此计算恢复后 retention。",
      ],
      activeRoute: "当前路径",
      retention: "相对匹配基线的 retention",
      gate: "固定 C3 gate ≥ 0.900",
      faultRetention: "故障期 retention",
      recoveryRetention: "恢复后 retention",
      checksumErrors: "CRC 错误",
      versionErrors: "版本错误",
      source: "查看源证据",
    },
    implementation: {
      intro: "每一层原型都对应到实际工具、源码模块和归档证据，导师可以直接检查我们具体做了什么。",
      stackLabel: "原型技术栈",
      stack: ["Python 3", "Mininet", "Open vSwitch", "Linux tc/netem", "带帧校验的 TCP ring", "JSON · JSONL · CSV 证据"],
      labels: {
        built: "具体实现",
        tools: "使用工具",
        source: "核心代码",
        evidence: "产生证据",
        boundary: "当前边界",
        open: "在仓库中打开",
      },
      cards: [
        {
          layer: "Layer 1",
          title: "交换机侧第一信号",
          built: "以 20 ms 为目标读取独立交换机侧 RX 计数器；连续三个低速样本触发高召回可疑信号。",
          tools: ["Python 3", "Mininet", "Open vSwitch", "Linux 接口计数器"],
          files: ["limer_v0/topology.py", "limer_v0/qdisc.py", "limer_v0/faults.py", "limer_v0/sentinel.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/switch_timeseries.csv", "results/c3_rep01/events.jsonl"],
          boundary: "这是管理面 switch-facing proxy；目前不声称已实现 ASIC、P4 pipeline 或驻交换机 agent。",
        },
        {
          layer: "Layer 2",
          title: "主机侧确认",
          built: "将交换机可疑信号、完整轮次 slowdown 和备用 fabric 健康状态组合起来，输出 confirm、suppress 或 defer。",
          tools: ["Python 3", "轮次计时", "匹配基线", "备用路径探测"],
          files: ["limer_v0/refiner.py", "limer_v0/metrics.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/events.jsonl", "results/c3_rep01/summary.json"],
          boundary: "目前是可解释的确定性规则；Proposal 中的 neuro-fuzzy classifier 和 GP uncertainty 尚未实现。",
        },
        {
          layer: "Layer 3",
          title: "协调恢复",
          built: "四个 worker 执行 prepare、READY 和 commit，在同一个未来轮次启用 Fabric B 与 route version 1。",
          tools: ["Python 3", "TCP 控制通道", "版本化状态机", "双 OVS fabric"],
          files: ["limer_v0/coordinator.py", "limer_v0/state.py", "limer_v0/worker.py", "limer_v0/protocol.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/version_commits.csv", "results/c3_rep01/correctness.json", "results/c3_rep01/worker_rounds.csv"],
          boundary: "这是可执行的 route-version 协议脚手架；尚未重建真实 PyTorch process group 或 NCCL communicator。",
        },
        {
          layer: "实验管线",
          title: "可重复执行与报告",
          built: "预声明条件驱动每次独立拓扑实验；报告器重新计算 gate，并保留所有失败重复。",
          tools: ["C0-C5 JSON 配置", "不可变事件日志", "Python unittest", "静态报告生成"],
          files: ["configs/c3_full.json", "limer_v0/orchestrator.py", "limer_v0/report.py", "tests/test_report.py"],
          evidence: ["results/aggregate_summary.json", "docs/experiment_design.md"],
          boundary: "每个条件三次重复适合阶段性工程验证，不足以支持 publication-level tail claim。",
        },
      ],
    },
    evidence: {
      denominator: "18 次独立拓扑生命周期：C0-C5 各重复三次，没有丢弃任何失败重复。",
      median: "中位 selected retention",
      gates: "通过的 run gate",
      overall: "总体 acceptance 仍为 false",
      raw: "三次原始重复",
      source: "查看聚合证据",
      conditions: {
        C0: ["无故障对照", "匹配的无故障轮次保持在基线附近。"],
        C1: ["持续限速故障", "保持 UP 的 20 Mbit/s 接入链路把完成吞吐降到约 21%。"],
        C2: ["仅检测", "检测能够触发，但没有恢复时性能仍处于退化状态。"],
        C3: ["完整 proxy 闭环", "闭环提交到 Fabric B，但三次中只有一次超过固定 0.9 gate。"],
        C4: ["Oracle 恢复", "Oracle 触发的恢复估计当前仿真环境的上界。"],
        C5: ["100 ms 短暂退化", "端侧 gate 对短暂异常抑制恢复。"],
      },
    },
    mapping: {
      intro: "这里把阶段性任务和长期研究目标分开评估。阶段任务已经交付，并不代表对应的正式研究目标已经全部完成。",
      milestoneTitle: "阶段任务要求",
      milestoneNote: "这里只展示适合公开的任务级要求，不复现内部规划材料或协作记录。",
      formalTitle: "正式研究目标",
      formalNote: "O1-O4 按最终研究机制评估，而不是只看 CPU demo 是否能运行。",
      labels: {
        requirement: "项目要求",
        delivery: "当前完成内容",
        evidence: "代码与证据",
        status: "当前状态",
        implemented: "目前已实现",
        missing: "仍然需要",
        open: "打开证据",
      },
      statusLabels: {
        delivered: "已交付",
        partial: "部分完成",
        "not-started": "尚未开始",
      },
      milestones: [
        {
          id: "M1",
          requirement: "理解问题并明确边界",
          delivery: "定义链路仍为 UP 时的接入链路退化问题、三层控制闭环、实验语义和结论边界。",
          evidence: ["docs/architecture.md", "docs/experiment_design.md", "docs/current_limitations.md"],
          status: "delivered",
        },
        {
          id: "M2",
          requirement: "锁定第一阶段范围",
          delivery: "聚焦一个 AllReduce-like 场景，使用 CPU/Mininet 仿真和可控合成故障注入。",
          evidence: ["configs/c3_full.json", "docs/experiment_design.md"],
          status: "delivered",
        },
        {
          id: "M3",
          requirement: "调研相关工作并选择仿真平台",
          delivery: "独立的背景调研为设计提供依据；第一阶段选择 Mininet 与 Open vSwitch 构建有边界的 CPU 原型。",
          evidence: ["README.md", "environment_probe.txt", "docs/architecture.md"],
          status: "delivered",
        },
        {
          id: "M4",
          requirement: "搭建小型网络与通信 demo",
          delivery: "创建四个 worker namespace、一或两张 OVS fabric，以及带帧校验的四 rank TCP ring workload。",
          evidence: ["limer_v0/topology.py", "limer_v0/worker.py", "limer_v0/protocol.py"],
          status: "delivered",
        },
        {
          id: "M5",
          requirement: "注入链路仍在线的网络故障",
          delivery: "将 rank 2 从 100 限速到 20 Mbit/s，同时确认链路两端仍保持 UP。",
          evidence: ["configs/c1_rate20.json", "limer_v0/faults.py", "results/c3_rep01/events.jsonl"],
          status: "delivered",
        },
        {
          id: "M6",
          requirement: "观察并记录影响信号",
          delivery: "记录交换机计数器、时间、吞吐、route version、CRC 校验和全 rank 完成情况。",
          evidence: ["results/c3_rep01/switch_timeseries.csv", "results/c3_rep01/worker_rounds.csv", "results/c3_rep01/correctness.json"],
          status: "delivered",
        },
        {
          id: "M7",
          requirement: "产出初始重复实验结果",
          delivery: "完成预声明的 C0-C5 矩阵，共 18 次独立拓扑实验，并保留两次失败的 C3 重复。",
          evidence: ["results/aggregate_summary.json", "limer_v0/report.py"],
          status: "delivered",
        },
      ],
      objectives: [
        {
          objective: "O1",
          title: "轻量级网络内监测",
          implemented: "交换机侧计数器接口、20 ms 目标轮询，以及持续异常触发规则。",
          missing: "驻交换机实现、生产级遥测集成，以及经过测量的交换机资源预算。",
          evidence: ["limer_v0/sentinel.py", "results/c3_rep01/switch_timeseries.csv", "docs/architecture.md"],
          status: "partial",
        },
        {
          objective: "O2",
          title: "不确定性感知故障检测",
          implemented: "switch-triggered 主机决策边界，以及确定性的 confirm/suppress 行为已经可以执行。",
          missing: "Neuro-fuzzy 分类、GP uncertainty、故障类别训练、校准和准确率评估。",
          evidence: ["limer_v0/refiner.py", "results/c3_rep01/events.jsonl", "docs/current_limitations.md"],
          status: "partial",
        },
        {
          objective: "O3",
          title: "快速拓扑恢复",
          implemented: "版本化的全 rank handover 将 TCP workload 从 Fabric A 移到预先存在的健康 Fabric B。",
          missing: "真实 GPU/NCCL communicator 适配，以及生产级恢复失败处理。",
          evidence: ["limer_v0/coordinator.py", "results/c3_rep01/version_commits.csv", "results/c3_rep01/correctness.json"],
          status: "partial",
        },
        {
          objective: "O4",
          title: "在线自演化",
          implemented: "CPU v0 中没有学习或自适应机制。",
          missing: "弱监督、pseudo-label、在线模型更新和未见故障评估。",
          evidence: ["docs/current_limitations.md"],
          status: "not-started",
        },
      ],
    },
    boundaries: [
      ["AllReduce-like", "TCP 环形字节流复现同步压力，但不执行 tensor reduction。"],
      ["CPU / Mininet", "没有 GPU、训练框架、NCCL、RDMA、checkpoint 或 optimizer 参与。"],
      ["管理面 proxy", "检测器读取交换机侧 Linux 计数器，但并不驻留在交换机硬件。"],
      ["假设存在冗余路径", "恢复依赖预先存在的健康 Fabric B 和已建立的 B 侧 TCP ring。"],
      ["延迟瓶颈", "交换机侧可疑信号约 50 ms，但等待完整轮次使端侧确认约为 5.27 s。"],
    ],
    roadmap: [
      ["稳定 C3 恢复表现", "保持固定 0.9 gate，对比 idle、keepalive 和 pre-warmed Fabric B，隔离备用路径波动。"],
      ["缩短确认延迟", "在轮次执行中输出 step-level 进度，同时保留短暂异常条件衡量误触发抑制能力。"],
      ["加入 gray-loss 条件", "保持速率不变，预声明低非零丢包率，让检测不再只覆盖带宽退化。"],
      ["替换遥测 proxy", "接入更真实的 streaming telemetry，并测量轮询、内存和交换机侧开销。"],
      ["实现不确定性感知分类", "在独立生成的 traces 上训练并校准 Proposal 中的分类器和不确定性估计器。"],
      ["进入真实 collective", "先验证数值正确的 CPU collective，再实现和测试 GPU/NCCL communicator 恢复。"],
    ],
    feedback: [
      "下一阶段应优先接入哪种生产级遥测接口？",
      "健康第二张 fabric 的假设是否符合目标部署场景？",
      "下一里程碑应优先做 gray-loss matrix，还是 GPU/NCCL 集成？",
    ],
  },
};

let payload;
let model;
let selectedCondition = "C3";
let replayTimer;
let replayHasInteracted = false;
let language = (() => {
  try {
    return localStorage.getItem("limer-language") ||
      (navigator.language.startsWith("zh") ? "zh" : "en");
  } catch {
    return navigator.language.startsWith("zh") ? "zh" : "en";
  }
})();


export async function loadDemoData(fetchImpl = fetch) {
  const response = await fetchImpl(DATA_URL);
  if (!response.ok) {
    throw new Error(`Demo data request failed: ${response.status}`);
  }
  return response.json();
}


function formatMilliseconds(value) {
  return value >= 1000 ? `${(value / 1000).toFixed(3)} s` : `${value.toFixed(1)} ms`;
}


function eventTimes(run) {
  return [
    "baseline",
    "t = 0",
    `+${formatMilliseconds(run.switch_detection_ms)}`,
    `+${formatMilliseconds(run.host_confirmation_ms)}`,
    `+${run.coordination_ms.toFixed(3)} ms`,
    `+${formatMilliseconds(run.fault_to_recovered_round_ms)}`,
  ];
}


function replaySvg(scene) {
  const c = content[language].replay;
  const recovered = scene.route === "B";
  const impacted = scene.faultActive;
  const readyClass = recovered ? " ready" : "";
  return `
    <div class="network-wrap">
      <svg class="network-svg" viewBox="0 0 550 260" role="img" aria-labelledby="network-title network-desc">
        <title id="network-title">${language === "zh" ? "四个 worker 与两张 fabric 的连接" : "Four workers connected to two fabrics"}</title>
        <desc id="network-desc">${language === "zh" ? "当前路径与 rank 2 退化接入边随回放状态变化。" : "The active route and degraded rank 2 access edge change during replay."}</desc>
        <path data-edge="a0" class="${scene.edgeClasses.a0}" d="M59 42 H178 Q207 42 227 48"></path>
        <path data-edge="a1" class="${scene.edgeClasses.a1}" d="M59 218 H78 V103 Q78 92 90 92 H194 Q214 92 227 74"></path>
        <path data-edge="a2" class="${scene.edgeClasses.a2}" d="M491 42 H372 Q343 42 323 48"></path>
        <path data-edge="a3" class="${scene.edgeClasses.a3}" d="M491 218 H472 V103 Q472 92 460 92 H356 Q336 92 323 74"></path>
        <path data-edge="b0" class="${scene.edgeClasses.b0}" d="M59 42 H68 V157 Q68 168 80 168 H194 Q214 168 227 184"></path>
        <path data-edge="b1" class="${scene.edgeClasses.b1}" d="M59 218 H178 Q207 218 227 212"></path>
        <path data-edge="b2" class="${scene.edgeClasses.b2}" d="M491 42 H482 V157 Q482 168 470 168 H356 Q336 168 323 184"></path>
        <path data-edge="b3" class="${scene.edgeClasses.b3}" d="M491 218 H372 Q343 218 323 212"></path>

        <rect class="fabric-node${recovered ? "" : " active-a"}" x="227" y="28" width="96" height="58" rx="12"></rect>
        <text class="network-label" x="275" y="52">Fabric A</text>
        <text class="network-sub-label" x="275" y="69">sA · version 0</text>
        <rect class="fabric-node${recovered ? " active-b" : ""}" x="227" y="174" width="96" height="58" rx="12"></rect>
        <text class="network-label" x="275" y="198">Fabric B</text>
        <text class="network-sub-label" x="275" y="215">sB · ${recovered ? "version 1" : "standby"}</text>

        <circle class="worker-node${readyClass}" cx="35" cy="42" r="22"></circle>
        <circle class="worker-node${readyClass}" cx="35" cy="218" r="22"></circle>
        <circle class="worker-node${impacted ? " impacted" : readyClass}" cx="515" cy="42" r="22"></circle>
        <circle class="worker-node${readyClass}" cx="515" cy="218" r="22"></circle>
        <text class="network-label" x="35" y="47">w0</text>
        <text class="network-label" x="35" y="223">w1</text>
        <text class="network-label" x="515" y="47">w2</text>
        <text class="network-label" x="515" y="223">w3</text>
      </svg>
      <p class="fault-callout${scene.faultActive ? " visible" : ""}">100 → 20 Mbit/s · link stays UP</p>
      <p class="micro-label">${c.activeRoute}: ${scene.route} · version ${scene.version}</p>
    </div>`;
}


function renderEventRows(scene) {
  const c = content[language].replay;
  const times = eventTimes(scene.run);
  return c.events.map(([title, description], index) => `
    <button class="event-row${index <= model.stateIndex ? " done" : ""}${index === model.stateIndex ? " current" : ""}${index === 1 ? " fault" : ""}" type="button" data-state-index="${index}" aria-current="${index === model.stateIndex ? "step" : "false"}">
      <span class="event-time">${times[index]}</span>
      <span class="event-dot" aria-hidden="true"></span>
      <span class="event-copy"><strong>${title}</strong><small>${description}</small></span>
    </button>`).join("");
}


function scheduleNextState() {
  clearTimeout(replayTimer);
  if (!model.playing) return;
  replayTimer = window.setTimeout(() => {
    if (model.stateIndex >= PHASES.length - 1) {
      model = { ...model, playing: false };
      renderReplay();
      return;
    }
    model = setState(model, model.stateIndex + 1);
    renderReplay();
    scheduleNextState();
  }, model.speedMs);
}


function togglePlayback() {
  replayHasInteracted = true;
  clearTimeout(replayTimer);
  if (model.playing) {
    model = { ...model, playing: false };
    renderReplay();
    return;
  }
  if (model.stateIndex >= PHASES.length - 1) {
    model = setState(model, 0);
  }
  model = { ...model, playing: true };
  renderReplay();
  scheduleNextState();
}


export function renderReplay() {
  const root = document.querySelector("#replay-root");
  const scene = deriveScene(model);
  const c = content[language].replay;
  const retentionPercent = Math.min(scene.retention * 100, 100);
  const retentionColor = model.stateIndex === 0
    ? "var(--healthy)"
    : model.stateIndex < 5
      ? "var(--fault)"
      : "var(--recovered)";
  const statusClass = scene.phase === "recovered"
    ? "recovered"
    : scene.phase === "baseline"
      ? ""
      : "fault";

  root.innerHTML = `
    <article class="replay-card" tabindex="0">
      <div class="replay-guide">
        <div class="replay-guide-intro">
          <p class="micro-label">${c.guideTitle}</p>
          <p>${c.compressed}</p>
        </div>
        <ol>${c.guideSteps.map((step) => `<li>${step}</li>`).join("")}</ol>
      </div>
      <div class="replay-toolbar">
        <div><p class="micro-label">${c.boundary}</p></div>
        <div class="control-group">
          <label><span class="micro-label">${c.run}</span>
            <select class="select-control" id="run-select">
              ${model.runs.map((run) => `<option value="${run.id}"${run.id === model.runId ? " selected" : ""}>${run.id} · ${run.gate}</option>`).join("")}
            </select>
          </label>
          <label><span class="micro-label">${c.speed}</span>
            <select class="select-control" id="speed-select">
              <option value="1300"${model.speedMs === 1300 ? " selected" : ""}>1×</option>
              <option value="850"${model.speedMs === 850 ? " selected" : ""}>2×</option>
              <option value="520"${model.speedMs === 520 ? " selected" : ""}>4×</option>
            </select>
          </label>
          <button class="button-secondary" id="restart-button" type="button">↺ ${c.restart}</button>
          <button class="button-primary" id="play-button" type="button">${model.playing ? "Ⅱ " + c.pause : "▶ " + c.play}</button>
        </div>
      </div>
      <div class="replay-layout">
        <div class="network-stage">
          <div class="scene-heading" aria-live="polite">
            <span class="scene-copy"><strong>${c.scene[scene.phase]}</strong><small>${c.phaseHelp[model.stateIndex]}</small></span>
            <strong class="status-pill ${statusClass}">${c.labels[model.stateIndex]}</strong>
          </div>
          ${replaySvg(scene)}
          <div class="retention-heading"><span>${c.retention}</span><strong>${scene.retention.toFixed(3)}</strong></div>
          <div class="retention-track"><div class="retention-fill" style="width:${retentionPercent}%;background:${retentionColor}"></div></div>
          <p class="micro-label">${c.gate}</p>
        </div>
        <aside class="event-panel">
          <h3>${language === "zh" ? "事件日志" : "Event log"} · ${scene.run.id}</h3>
          <div class="event-list">${renderEventRows(scene)}</div>
          <div class="metric-grid">
            <div class="metric"><strong>${scene.run.fault_retention.toFixed(3)}</strong>${c.faultRetention}</div>
            <div class="metric"><strong>${scene.run.post_recovery_retention.toFixed(3)}</strong>${c.recoveryRetention}</div>
            <div class="metric"><strong>${scene.run.checksum_errors}</strong>${c.checksumErrors}</div>
            <div class="metric"><strong class="gate-pill ${scene.run.gate.toLowerCase()}">${scene.run.gate}</strong>${c.versionErrors}: ${scene.run.version_errors}</div>
          </div>
          <a class="source-link" href="${REPOSITORY_URL}/blob/main/${scene.run.source_summary}" target="_blank" rel="noreferrer">${c.source} ↗</a>
        </aside>
      </div>
      <div class="replay-scrubber${replayHasInteracted ? "" : " is-pristine"}">
        <div class="drag-hint"><span aria-hidden="true">↔</span><label for="replay-scrubber">${c.dragHint}</label></div>
        <input id="replay-scrubber" type="range" min="0" max="${PHASES.length - 1}" step="1" value="${model.stateIndex}" aria-label="${language === "zh" ? "回放时间轴" : "Replay timeline"}">
        <div class="scrubber-labels">${c.labels.map((label) => `<span>${label}</span>`).join("")}</div>
      </div>
    </article>`;

  root.querySelector("#play-button").addEventListener("click", togglePlayback);
  root.querySelector("#restart-button").addEventListener("click", () => {
    replayHasInteracted = true;
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, 0);
    renderReplay();
  });
  root.querySelector("#replay-scrubber").addEventListener("input", (event) => {
    replayHasInteracted = true;
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, Number(event.target.value));
    renderReplay();
  });
  root.querySelector("#run-select").addEventListener("change", (event) => {
    replayHasInteracted = true;
    clearTimeout(replayTimer);
    model = selectRun(model, event.target.value);
    renderReplay();
  });
  root.querySelector("#speed-select").addEventListener("change", (event) => {
    model = { ...model, speedMs: Number(event.target.value) };
    if (model.playing) scheduleNextState();
  });
  root.querySelector(".event-list").addEventListener("click", (event) => {
    const row = event.target.closest("[data-state-index]");
    if (!row) return;
    replayHasInteracted = true;
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, Number(row.dataset.stateIndex));
    renderReplay();
  });
  root.addEventListener("keydown", (event) => {
    if (!["ArrowLeft", "ArrowRight"].includes(event.key)) return;
    if (event.target.closest("button, select")) return;
    event.preventDefault();
    replayHasInteracted = true;
    clearTimeout(replayTimer);
    const delta = event.key === "ArrowLeft" ? -1 : 1;
    const nextIndex = Math.max(0, Math.min(PHASES.length - 1, model.stateIndex + delta));
    model = setState({ ...model, playing: false }, nextIndex);
    renderReplay();
    document.querySelector("#replay-scrubber")?.focus();
  });
}


function retentionPosition(value) {
  return Math.min((value / MAX_RETENTION) * 100, 100);
}


export function renderEvidence(conditionId = selectedCondition) {
  selectedCondition = conditionId;
  const root = document.querySelector("#evidence-root");
  const c = content[language].evidence;
  const ids = Object.keys(payload.conditions);
  const selected = payload.conditions[selectedCondition];
  const [selectedTitle, selectedDescription] = c.conditions[selectedCondition];
  const needsGate = selectedCondition === "C3" || selectedCondition === "C4";

  root.innerHTML = `
    <article class="evidence-card">
      <div class="evidence-toolbar">
        <p>${c.denominator}</p>
        <div class="condition-tabs" role="tablist" aria-label="${language === "zh" ? "实验条件" : "Experiment conditions"}">
          ${ids.map((id) => `<button class="condition-tab" type="button" role="tab" data-condition="${id}" aria-selected="${id === selectedCondition}">${id}</button>`).join("")}
        </div>
      </div>
      <div class="evidence-layout">
        <div class="evidence-chart">
          ${ids.map((id) => {
            const condition = payload.conditions[id];
            return `<div class="condition-row">
              <strong>${id}</strong>
              <div class="condition-track" aria-label="${id} retention values">
                ${(id === "C3" || id === "C4") ? `<span class="gate-marker" style="left:${retentionPosition(0.9)}%" title="gate 0.9"></span>` : ""}
                ${condition.retention_values.map((value) => `<span class="retention-point" style="left:${retentionPosition(value)}%" title="${value.toFixed(3)}"></span>`).join("")}
                <span class="retention-median" style="left:${retentionPosition(condition.median_retention)}%" title="median ${condition.median_retention.toFixed(3)}"></span>
              </div>
              <span>${condition.median_retention.toFixed(3)}</span>
            </div>`;
          }).join("")}
          <p class="micro-label">0　　　　　　　　　　　0.6　　　　　　　　　　　1.2</p>
        </div>
        <aside class="evidence-summary">
          <p class="micro-label">${selectedCondition}</p>
          <h3>${selectedTitle}</h3>
          <p>${selectedDescription}</p>
          <div class="evidence-result"><span>${c.median}</span><strong>${selected.median_retention.toFixed(3)}</strong></div>
          <div class="evidence-result"><span>${c.gates}</span><strong>${selected.gate_pass_count}/${selected.run_count}</strong></div>
          <p><strong>${c.raw}:</strong> ${selected.retention_values.map((value) => value.toFixed(3)).join(" · ")}</p>
          ${needsGate ? `<p class="micro-label">gate = 0.900</p>` : ""}
          <p class="gate-pill fail">${c.overall}</p>
          <a class="source-link" href="${REPOSITORY_URL}/blob/main/${payload.meta.source}" target="_blank" rel="noreferrer">${c.source} ↗</a>
        </aside>
      </div>
    </article>`;

  root.querySelector(".condition-tabs").addEventListener("click", (event) => {
    const tab = event.target.closest("[data-condition]");
    if (tab) renderEvidence(tab.dataset.condition);
  });
}


function renderRepositoryLinks(paths, linkLabel) {
  return `<ul class="repo-links">${paths.map((path) => `
    <li><a href="${repositoryLinks.get(path)}" target="_blank" rel="noreferrer" aria-label="${linkLabel}: ${path}"><code>${path}</code><span aria-hidden="true">↗</span></a></li>`).join("")}</ul>`;
}


function statusPill(mapping, status) {
  return `<span class="mapping-status ${status}">${mapping.statusLabels[status]}</span>`;
}


export function renderImplementation() {
  const root = document.querySelector("#implementation-root");
  const c = content[language].implementation;
  root.innerHTML = `
    <div class="implementation-intro">
      <p>${c.intro}</p>
      <div class="implementation-stack" aria-label="${c.stackLabel}">
        <strong>${c.stackLabel}</strong>
        <div>${c.stack.map((tool) => `<span>${tool}</span>`).join("")}</div>
      </div>
    </div>
    <div class="implementation-grid">
      ${c.cards.map((card) => `
        <article class="implementation-card">
          <header><span>${card.layer}</span><h3>${card.title}</h3></header>
          <div class="implementation-built"><strong>${c.labels.built}</strong><p>${card.built}</p></div>
          <div class="implementation-tools"><strong>${c.labels.tools}</strong><div>${card.tools.map((tool) => `<span>${tool}</span>`).join("")}</div></div>
          <div class="implementation-sources"><strong>${c.labels.source}</strong>${renderRepositoryLinks(card.files, c.labels.open)}</div>
          <div class="implementation-evidence"><strong>${c.labels.evidence}</strong>${renderRepositoryLinks(card.evidence, c.labels.open)}</div>
          <div class="implementation-boundary"><strong>${c.labels.boundary}</strong><p>${card.boundary}</p></div>
        </article>`).join("")}
    </div>`;
}


export function renderMapping() {
  const root = document.querySelector("#mapping-root");
  const c = content[language].mapping;
  root.innerHTML = `
    <div class="mapping-intro"><p>${c.intro}</p></div>
    <div class="mapping-layer milestone-layer">
      <header class="mapping-layer-heading">
        <div><p class="micro-label">01</p><h3>${c.milestoneTitle}</h3></div>
        <p>${c.milestoneNote}</p>
      </header>
      <div class="mapping-table">
        <div class="mapping-table-head" aria-hidden="true">
          <span>${c.labels.requirement}</span><span>${c.labels.delivery}</span><span>${c.labels.evidence}</span><span>${c.labels.status}</span>
        </div>
        ${c.milestones.map((item) => `
          <article class="mapping-row">
            <div data-label="${c.labels.requirement}"><span class="mapping-id">${item.id}</span><strong>${item.requirement}</strong></div>
            <div data-label="${c.labels.delivery}"><p>${item.delivery}</p></div>
            <div data-label="${c.labels.evidence}">${renderRepositoryLinks(item.evidence, c.labels.open)}</div>
            <div data-label="${c.labels.status}">${statusPill(c, item.status)}</div>
          </article>`).join("")}
      </div>
    </div>
    <div class="mapping-layer formal-layer">
      <header class="mapping-layer-heading">
        <div><p class="micro-label">02</p><h3>${c.formalTitle}</h3></div>
        <p>${c.formalNote}</p>
      </header>
      <div class="objective-grid">
        ${c.objectives.map((item) => `
          <article class="objective-card">
            <header><div><span class="mapping-id">${item.objective}</span><h3>${item.title}</h3></div>${statusPill(c, item.status)}</header>
            <div class="objective-progress">
              <div><strong>${c.labels.implemented}</strong><p>${item.implemented}</p></div>
              <div><strong>${c.labels.missing}</strong><p>${item.missing}</p></div>
            </div>
            <div class="objective-evidence"><strong>${c.labels.evidence}</strong>${renderRepositoryLinks(item.evidence, c.labels.open)}</div>
          </article>`).join("")}
      </div>
    </div>`;
}


export function renderNarrative() {
  const c = content[language];
  document.querySelector("#hero-visual").innerHTML = `
    <div class="hero-diagram">
      <div class="hero-rate"><div><p class="micro-label">${language === "zh" ? "健康基线" : "baseline"}</p><strong>${c.hero.baseline}</strong></div><span>→</span><div><p class="micro-label">${language === "zh" ? "链路仍为 UP" : "still UP"}</p><strong>${c.hero.fault}</strong></div></div>
      <div class="hero-signal">${c.hero.stages.map((stage, index) => `<div>${index + 1}<br>${stage}</div>`).join("")}</div>
      <div class="hero-metrics">
        <div><strong>${payload.meta.formal_run_count}</strong><span>${language === "zh" ? "正式运行" : "formal runs"}</span></div>
        <div><strong>${payload.meta.gate_pass_count}/${payload.meta.formal_run_count}</strong><span>${language === "zh" ? "通过 run gate" : "run gates passed"}</span></div>
        <div><strong>${payload.conditions.C3.gate_pass_count}/${payload.conditions.C3.run_count}</strong><span>${language === "zh" ? "C3 通过" : "C3 passed"}</span></div>
      </div>
    </div>`;

  renderImplementation();
  renderMapping();

  const boundaryRoot = document.querySelector("#boundary-grid");
  boundaryRoot.className = "boundary-grid";
  boundaryRoot.innerHTML = c.boundaries.map(([title, body]) => `
    <article class="boundary-card"><h3>${title}</h3><p>${body}</p></article>`).join("");

  const roadmapRoot = document.querySelector("#roadmap-grid");
  roadmapRoot.className = "roadmap-grid";
  roadmapRoot.innerHTML = c.roadmap.map(([title, body], index) => `
    <article class="roadmap-card"><span class="roadmap-index">${index + 1}</span><h3>${title}</h3><p>${body}</p></article>`).join("");

  const feedbackRoot = document.querySelector("#feedback-grid");
  feedbackRoot.className = "feedback-grid";
  feedbackRoot.innerHTML = c.feedback.map((question, index) => `
    <article class="feedback-card"><p class="micro-label">Q${index + 1}</p><h3>${question}</h3></article>`).join("");
}


export function setLanguage(nextLanguage) {
  language = nextLanguage === "zh" ? "zh" : "en";
  document.documentElement.lang = language;
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = translations[language][node.dataset.i18n];
  });
  const toggle = document.querySelector("#language-toggle");
  toggle.textContent = language === "zh" ? "EN" : "中";
  toggle.setAttribute(
    "aria-label",
    language === "zh" ? "Switch to English" : "切换为中文",
  );
  try {
    localStorage.setItem("limer-language", language);
  } catch {
    // Language switching remains available for the current page session.
  }
  renderNarrative();
  renderReplay();
  renderEvidence(selectedCondition);
}


export function showDataError(error) {
  const panel = document.querySelector("#data-error");
  panel.hidden = false;
  panel.textContent = language === "zh"
    ? "归档实验数据加载失败，交互控件已停用。"
    : "Archived experiment data failed to load; interactive controls are disabled.";
  document
    .querySelectorAll("#demo button, #demo select, #demo input, #evidence button")
    .forEach((control) => {
      control.disabled = true;
    });
  console.error(error);
}


export async function start() {
  try {
    payload = await loadDemoData();
    model = createReplayModel(payload.c3_runs, "c3_rep01");
    renderNarrative();
    renderReplay();
    renderEvidence("C3");
    setLanguage(language);
    document.querySelector("#language-toggle").addEventListener("click", () => {
      setLanguage(language === "en" ? "zh" : "en");
    });
  } catch (error) {
    showDataError(error);
  }
}


start();
