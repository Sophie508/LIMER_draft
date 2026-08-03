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
  ["docs/active_active_v1_verification.md", repoLink("docs/active_active_v1_verification.md")],
  ["limer_v0/topology.py", repoLink("limer_v0/topology.py")],
  ["limer_v0/qdisc.py", repoLink("limer_v0/qdisc.py")],
  ["limer_v0/faults.py", repoLink("limer_v0/faults.py")],
  ["limer_v0/sentinel.py", repoLink("limer_v0/sentinel.py")],
  ["limer_v0/orchestrator.py", repoLink("limer_v0/orchestrator.py")],
  ["limer_v0/refiner.py", repoLink("limer_v0/refiner.py")],
  ["limer_v0/metrics.py", repoLink("limer_v0/metrics.py")],
  ["limer_v0/route_plan.py", repoLink("limer_v0/route_plan.py")],
  ["limer_v0/coordinator.py", repoLink("limer_v0/coordinator.py")],
  ["limer_v0/state.py", repoLink("limer_v0/state.py")],
  ["limer_v0/worker.py", repoLink("limer_v0/worker.py")],
  ["limer_v0/protocol.py", repoLink("limer_v0/protocol.py")],
  ["limer_v0/report.py", repoLink("limer_v0/report.py")],
  ["configs/c1_rate20.json", repoLink("configs/c1_rate20.json")],
  ["configs/c3_full.json", repoLink("configs/c3_full.json")],
  ["configs/active_active_v1/aa3_local.json", repoLink("configs/active_active_v1/aa3_local.json")],
  ["results/aggregate_summary.json", repoLink("results/aggregate_summary.json")],
  ["results/c3_rep01/summary.json", repoLink("results/c3_rep01/summary.json")],
  ["results/c3_rep01/events.jsonl", repoLink("results/c3_rep01/events.jsonl")],
  ["results/c3_rep01/switch_timeseries.csv", repoLink("results/c3_rep01/switch_timeseries.csv")],
  ["results/c3_rep01/version_commits.csv", repoLink("results/c3_rep01/version_commits.csv")],
  ["results/c3_rep01/correctness.json", repoLink("results/c3_rep01/correctness.json")],
  ["results/c3_rep01/worker_rounds.csv", repoLink("results/c3_rep01/worker_rounds.csv")],
  ["tests/test_correctness.py", repoLink("tests/test_correctness.py")],
  ["tests/test_route_plan.py", repoLink("tests/test_route_plan.py")],
  ["tests/test_worker_data_path.py", repoLink("tests/test_worker_data_path.py")],
  ["tests/test_report.py", repoLink("tests/test_report.py")],
  ["tests/test_sentinel_burst.py", repoLink("tests/test_sentinel_burst.py")],
  ["tests/test_step_gate_monitor.py", repoLink("tests/test_step_gate_monitor.py")],
  ["scripts/replay_sentinel.py", repoLink("scripts/replay_sentinel.py")],
  ["configs/active_active_v2/aa6_stepdetect.json", repoLink("configs/active_active_v2/aa6_stepdetect.json")],
  ["configs/active_active_v2/aa3_local_longwindow.json", repoLink("configs/active_active_v2/aa3_local_longwindow.json")],
  ["configs/active_active_v2/aa5_transient_stepstack.json", repoLink("configs/active_active_v2/aa5_transient_stepstack.json")],
  ["configs/fault_profiles_v1/fp_r5_impact.json", repoLink("configs/fault_profiles_v1/fp_r5_impact.json")],
  ["configs/fault_profiles_v1/fp_l1_impact.json", repoLink("configs/fault_profiles_v1/fp_l1_impact.json")],
  ["configs/fault_profiles_v1/fp_d10_impact.json", repoLink("configs/fault_profiles_v1/fp_d10_impact.json")],
  ["configs/active_active_v1/aa0_healthy.json", repoLink("configs/active_active_v1/aa0_healthy.json")],
  ["docs/step_level_detection_v2_prereg.md", repoLink("docs/step_level_detection_v2_prereg.md")],
  ["docs/fault_profile_matrix.md", repoLink("docs/fault_profile_matrix.md")],
  ["docs/simai_plan.md", repoLink("docs/simai_plan.md")],
  ["results_active_active/aa0_healthy_rep01/correctness.json", repoLink("results_active_active/aa0_healthy_rep01/correctness.json")],
  ["results_active_active/aa3_local_rep01/correctness.json", repoLink("results_active_active/aa3_local_rep01/correctness.json")],
  ["results_active_active_v2_1/aggregate_summary.json", repoLink("results_active_active_v2_1/aggregate_summary.json")],
  ["results_active_active_v2_1/aa6_stepdetect_rep01/summary.json", repoLink("results_active_active_v2_1/aa6_stepdetect_rep01/summary.json")],
  ["results_active_active_v2_1/aa6_stepdetect_rep01/correctness.json", repoLink("results_active_active_v2_1/aa6_stepdetect_rep01/correctness.json")],
  ["results_active_active_v2_1/aa3_local_rep01/aggregate_rounds.csv", repoLink("results_active_active_v2_1/aa3_local_rep01/aggregate_rounds.csv")],
  ["results_active_active_v2_1/aa5_transient_rep01/summary.json", repoLink("results_active_active_v2_1/aa5_transient_rep01/summary.json")],
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
    "hero.body": "LIMER detects a switch-facing signal, confirms end-host impact, and coordinates a versioned localized route plan.",
    "hero.action": "Replay measured incidents",
    "demo.title": "Evidence-backed incident replay",
    "implementation.title": "What we built and where it lives",
    "evidence.title": "Evidence explorer",
    "mapping.title": "From requirements to evidence",
    "boundaries.title": "Interpretation boundary",
    "roadmap.title": "Prioritized next steps",
    "roadmap.standby.title": "Validate active-active localized routing",
    "roadmap.confirmation.title": "Reduce confirmation delay",
    "roadmap.scope.title": "Expand fault and platform scope",
    "feedback.title": "Feedback requested",
    "feedback.telemetry": "Which production telemetry target should be integrated first?",
    "feedback.redundancy": "Does the healthy second-fabric assumption match the intended deployment setting?",
    "feedback.order": "Should the next realism milestone prioritize SimAI or GPU/NCCL integration?",
    "meetings.previous": "Previous review · CPU v0 & active-active v1",
    "meetings.next": "This review · Feedback revisions & new results",
    "revisions.title": "Advisor feedback → what changed",
    "decisions.title": "Decisions needed before the next step",
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
    "hero.body": "LIMER 先捕获交换机侧信号，再确认端侧影响，并协调版本化的局部路由计划。",
    "hero.action": "回放实测事件",
    "demo.title": "有原始证据支撑的事件回放",
    "implementation.title": "我们具体实现了什么",
    "evidence.title": "实验数据浏览器",
    "mapping.title": "从项目要求到当前证据",
    "boundaries.title": "结论边界",
    "roadmap.title": "优先 next steps",
    "roadmap.standby.title": "验证 active-active 局部改道",
    "roadmap.confirmation.title": "缩短端侧确认延迟",
    "roadmap.scope.title": "扩展故障类型与平台范围",
    "feedback.title": "希望获得的方向反馈",
    "feedback.telemetry": "下一阶段应优先接入哪种生产级遥测接口？",
    "feedback.redundancy": "健康第二张 fabric 的假设是否符合目标部署场景？",
    "feedback.order": "下一项真实性里程碑应优先做 SimAI，还是 GPU/NCCL 集成？",
    "meetings.previous": "上次汇报 · CPU v0 与 active-active v1",
    "meetings.next": "本次汇报 · 针对反馈的修订与新结果",
    "revisions.title": "导师反馈 → 我们做了什么修订",
    "decisions.title": "进入下一步前需要确认的决定",
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
        ["HOST_CONFIRM", "The degraded round completes and the alternate-path health check passes."],
        ["RECOVERY_COMMIT", "All four ranks are READY; route B, version 1."],
        ["Recovered round", "Three archived post-recovery rounds determine the gate."],
      ],
      labels: ["Baseline", "Fault", "Detect", "Confirm", "Commit", "Recovered"],
      phaseHelp: [
        "Before fault injection, all four workers communicate normally on Fabric A.",
        "The w2 access link remains UP, but its rate drops from 100 to 20 Mbit/s.",
        "A distinct switch-facing counter observes persistent rate degradation.",
        "The host gate confirms collective slowdown and checks that alternate Fabric B is healthy.",
        "All four workers agree to apply route version 1 at the same future round.",
        "Legacy CPU v0 moves the whole ring to Fabric B and measures recovery retention.",
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
      intro: "Each prototype layer is linked to its tools, source modules, tests, and—where measurements exist—archived artifacts.",
      stackLabel: "Prototype technology stack",
      stack: ["Python 3", "Mininet", "Open vSwitch", "Linux tc/netem", "Framed TCP ring", "JSON · JSONL · CSV evidence"],
      labels: {
        built: "What we built",
        tools: "Tools",
        source: "Source code",
        evidence: "Evidence and checks",
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
          built: "A deterministic gate combines switch suspicion, completed-round slowdown, and alternate-path health to confirm, suppress, or defer recovery.",
          tools: ["Python 3", "Round timing", "Matched baseline", "Alternate-path probe"],
          files: ["limer_v0/refiner.py", "limer_v0/metrics.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/events.jsonl", "results/c3_rep01/summary.json"],
          boundary: "Explainable fixed rule; the proposed neuro-fuzzy classifier and Gaussian Process uncertainty are not implemented.",
        },
        {
          layer: "Layer 3",
          title: "Coordinated recovery",
          built: "Both fabrics carry healthy traffic. Four workers prepare and commit one fingerprinted plan that changes only worker 2's affected send slots at a safe round boundary.",
          tools: ["Python 3", "TCP control channel", "Immutable route plan", "Dual active OVS fabrics"],
          files: ["limer_v0/route_plan.py", "limer_v0/coordinator.py", "limer_v0/state.py", "limer_v0/worker.py", "limer_v0/protocol.py", "limer_v0/orchestrator.py"],
          evidence: ["tests/test_route_plan.py", "tests/test_worker_data_path.py", "tests/test_correctness.py", "docs/active_active_v1_verification.md"],
          boundary: "Executable route-plan scaffold; v1 Mininet measurements and real PyTorch/NCCL communicator adaptation remain pending.",
        },
        {
          layer: "Experiment pipeline",
          title: "Repeatable execution and reporting",
          built: "Legacy C0-C5 evidence stays immutable while seven v1 scenarios predeclare active-active, detect-only, localized, global, oracle, and transient semantics.",
          tools: ["Versioned JSON configs", "Immutable event log", "Python unittest", "Static report generation"],
          files: ["configs/c3_full.json", "configs/active_active_v1/aa3_local.json", "limer_v0/orchestrator.py", "limer_v0/report.py", "tests/test_report.py"],
          evidence: ["results/aggregate_summary.json", "tests/test_report.py", "docs/active_active_v1_verification.md"],
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
          implemented: "A versioned all-rank protocol installs one localized plan while unaffected workers retain their active-active schedules.",
          missing: "Real GPU/NCCL communicator adaptation and production recovery failure handling.",
          evidence: ["limer_v0/route_plan.py", "limer_v0/coordinator.py", "tests/test_worker_data_path.py", "docs/active_active_v1_verification.md"],
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
      ["Directed fault scope", "v1 degrades only worker 2's egress toward Fabric A; bidirectional access-link faults remain untested."],
      ["Latency bottleneck", "The v1 host gate still waits for a completed round; the page does not claim millisecond end-to-end recovery."],
    ],
    roadmap: [
      ["Validate active-active localized routing", "Measure both fabrics under healthy load and compare localized recovery against an explicitly configured global baseline."],
      ["Reduce confirmation delay", "Emit step-level progress while a round is in flight, while retaining a transient condition to measure false-trigger suppression."],
      ["Expand fault profiles", "Predeclare rate-cap, low-loss, duration, and bidirectional cases so the detector is tested beyond directed bandwidth degradation."],
      ["Replace the telemetry proxy", "Connect the same interface to realistic streaming telemetry and measure polling, memory, and switch-side overhead."],
      ["Implement uncertainty-aware classification", "Train and calibrate the proposed classifier and uncertainty estimator on separately generated traces."],
      ["Increase realism in stages", "Use SimAI for realistic collective studies up to 128 simulated GPUs, then implement GPU/NCCL communicator recovery."],
    ],
    feedback: [
      "Which production telemetry target should be integrated first?",
      "Does the healthy second-fabric assumption match the intended deployment setting?",
      "Should the next realism milestone prioritize SimAI or GPU/NCCL integration?",
    ],
    meeting2: {
      intro: "Each card restates one point from the advisor feedback on the previous review, shows the revision we made in response, and links the artifacts — code, configs, and archived run evidence — that implement it. Every number below is recomputed from raw run files, not from summaries.",
      metrics: [
        ["36 ms", "fault → switch suspicion (was 2.78 s)"],
        ["1.07 s", "fault → host confirmation (was 2.87 s)"],
        ["≈ 1.000", "steady-state retention after localized recovery"],
        ["9 / 9", "preregistered gates passed in the new campaign"],
      ],
      labels: {
        ask: "Feedback point",
        revision: "Revision and measured result",
        artifacts: "Artifacts (open the implementation)",
        open: "Open in repository",
      },
      statusLabels: {
        delivered: "Delivered",
        partial: "Partially delivered",
        planned: "Planned, awaiting decisions",
      },
      items: [
        {
          tag: "Q1 · Detection latency",
          ask: "Millisecond-level fault detection and recovery is the top KPI.",
          revision: "The detector was rebuilt. The old rule calibrated its baseline on idle-mode samples and could only see silence, so a capped-but-flowing fault took 2.78 s to detect. The new burst-aware rule calibrates on burst windows only and raises suspicion in 34.8–37.1 ms across three formal repeats; an in-round step-level host gate confirms in about 1.07 s instead of waiting for the full degraded round. The route commit itself still happens at the round boundary (~2.87 s): removing that wait is the declared next work item, and the page makes no millisecond end-to-end recovery claim.",
          artifacts: ["limer_v0/sentinel.py", "limer_v0/orchestrator.py", "limer_v0/worker.py", "scripts/replay_sentinel.py", "configs/active_active_v2/aa6_stepdetect.json", "results_active_active_v2_1/aa6_stepdetect_rep01/summary.json", "docs/step_level_detection_v2_prereg.md", "tests/test_sentinel_burst.py"],
          status: "partial",
        },
        {
          tag: "Q1 · Performance loss",
          ask: "Failure-case performance should stay as close as possible to the fault-free scenario.",
          revision: "A 20-round post-recovery window (three repeats) shows localized recovery settles back to retention ≈ 1.000 of the fault-free baseline. The 0.936 reported previously was a convergence transient limited to the first ~5 recovered rounds, not a steady-state cost.",
          artifacts: ["configs/active_active_v2/aa3_local_longwindow.json", "results_active_active_v2_1/aa3_local_rep01/aggregate_rounds.csv", "results_active_active_v2_1/aggregate_summary.json"],
          status: "delivered",
        },
        {
          tag: "Q2 · Second fabric is not a backup",
          ask: "The second Dual-ToR fabric must forward traffic like a normal switch in healthy operation, not sit idle as a backup.",
          revision: "The baseline is now balanced active-active: in every round, every worker sends on both Fabric A and Fabric B, and the per-rank byte counts on both fabrics are verified in the archived correctness evidence of each healthy run.",
          artifacts: ["limer_v0/route_plan.py", "configs/active_active_v1/aa0_healthy.json", "results_active_active/aa0_healthy_rep01/correctness.json"],
          status: "delivered",
        },
        {
          tag: "Q2 · Localized rerouting",
          ask: "When the link between one worker and Fabric A degrades, only that worker's affected traffic should move; the other workers keep using Fabric A. The earlier demo incorrectly showed the whole ring shifting to Fabric B.",
          revision: "Recovery now installs a localized route plan: exactly the affected worker's three Fabric-A send slots move to B, and the other three workers' send schedules are byte-identical before and after (checked from raw per-round send routes, and enforced as a run gate). The replay demo on this page shows the localized plan.",
          artifacts: ["limer_v0/route_plan.py", "results_active_active/aa3_local_rep01/correctness.json", "results_active_active_v2_1/aa6_stepdetect_rep01/correctness.json", "tests/test_worker_data_path.py"],
          status: "delivered",
        },
        {
          tag: "Q3 · “Gray-loss matrix” was unclear",
          ask: "The term needs a concrete, discussable definition.",
          revision: "Replaced by an explicit fault-profile matrix: named profiles over rate cap, packet loss, delay, queue depth, direction, duration, scope, and onset. Three new profiles are runnable configs today (5 Mbit cap, 1% loss, +10 ms delay); which dimensions to prioritize is an open decision below.",
          artifacts: ["docs/fault_profile_matrix.md", "configs/fault_profiles_v1/fp_r5_impact.json", "configs/fault_profiles_v1/fp_l1_impact.json", "configs/fault_profiles_v1/fp_d10_impact.json", "limer_v0/faults.py"],
          status: "partial",
        },
        {
          tag: "Scale · SimAI at ≤ 128 GPUs",
          ask: "Stay at a low GPU count (at most 128) and use the realistic SimAI model first; larger systems only if time remains.",
          revision: "An execution plan is drafted from the official SimAI repository and paper: a 4→128 GPU ladder, calibration against the Mininet evidence through dimensionless ratios, and an ns-3-level fault-injection patch (the official repo ships none). SimAI results will never be mixed with Mininet packet evidence in one table. Execution starts once the decisions below are settled.",
          artifacts: ["docs/simai_plan.md", "docs/fault_profile_matrix.md"],
          status: "planned",
        },
      ],
      decisions: [
        ["Numeric target for the latency KPI", "“Millisecond-level” needs an interval and a threshold. Measured today: fault → switch suspicion 36 ms; fault → host confirmation 1.07 s; fault → first recovered round complete 3.96 s. Which interval is the KPI, and what number must it beat?"],
        ["What “gray” primarily means", "Rate cap, random loss, added delay, or partial-flow damage (e.g. one ECMP bucket)? And is egress-only degradation enough, or must ingress/bidirectional and ToR-uplink faults be covered?"],
        ["Scope of the SimAI stage", "Model fault impact and rerouting benefit only (recommended, plan ready), or also reproduce the detection loop inside the simulator (roughly triples the work)?"],
        ["Acceptance bar for recovery", "The preregistered retention gate is ≥ 0.9 and the measured steady state is ≈ 1.000. Should the bar be raised, and over how many post-recovery rounds should it be evaluated?"],
      ],
    },
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
        ["HOST_CONFIRM", "退化轮次结束，且替代路径健康检查通过。"],
        ["RECOVERY_COMMIT", "四个 rank 全部 READY，切换到 route B、version 1。"],
        ["恢复轮次完成", "三个归档的恢复后轮次共同决定 gate。"],
      ],
      labels: ["基线", "故障", "检测", "确认", "提交", "恢复"],
      phaseHelp: [
        "故障注入前，四个 worker 在 Fabric A 上正常通信。",
        "w2 接入链路仍显示 UP，但带宽从 100 降到 20 Mbit/s。",
        "独立的交换机侧计数器观察到持续速率下降。",
        "主机侧确认 collective 变慢，并检查替代 Fabric B 是否健康。",
        "四个 worker 同意在同一个未来轮次启用 route version 1。",
        "旧版 CPU v0 将整个 ring 移到 Fabric B，并据此计算恢复后 retention。",
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
      intro: "每一层原型都对应到实际工具、源码、测试；已有测量的部分再链接归档 artifact，方便逐项检查。",
      stackLabel: "原型技术栈",
      stack: ["Python 3", "Mininet", "Open vSwitch", "Linux tc/netem", "带帧校验的 TCP ring", "JSON · JSONL · CSV 证据"],
      labels: {
        built: "具体实现",
        tools: "使用工具",
        source: "核心代码",
        evidence: "证据与检查",
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
          built: "将交换机可疑信号、完整轮次 slowdown 和替代路径健康状态组合起来，输出 confirm、suppress 或 defer。",
          tools: ["Python 3", "轮次计时", "匹配基线", "替代路径探测"],
          files: ["limer_v0/refiner.py", "limer_v0/metrics.py", "limer_v0/orchestrator.py"],
          evidence: ["results/c3_rep01/events.jsonl", "results/c3_rep01/summary.json"],
          boundary: "目前是可解释的确定性规则；Proposal 中的 neuro-fuzzy classifier 和 GP uncertainty 尚未实现。",
        },
        {
          layer: "Layer 3",
          title: "协调恢复",
          built: "健康状态下两张 fabric 同时承载流量；四个 worker 在安全轮次边界提交同一份带 fingerprint 的计划，只修改 w2 受影响的发送槽位。",
          tools: ["Python 3", "TCP 控制通道", "不可变路由计划", "双 active OVS fabric"],
          files: ["limer_v0/route_plan.py", "limer_v0/coordinator.py", "limer_v0/state.py", "limer_v0/worker.py", "limer_v0/protocol.py", "limer_v0/orchestrator.py"],
          evidence: ["tests/test_route_plan.py", "tests/test_worker_data_path.py", "tests/test_correctness.py", "docs/active_active_v1_verification.md"],
          boundary: "这是可执行的 route-plan 脚手架；v1 Mininet 测量与真实 PyTorch/NCCL communicator 适配仍待完成。",
        },
        {
          layer: "实验管线",
          title: "可重复执行与报告",
          built: "旧版 C0-C5 证据保持不变；七个 v1 场景预先声明 active-active、仅检测、局部、全局、oracle 与短暂故障语义。",
          tools: ["版本化 JSON 配置", "不可变事件日志", "Python unittest", "静态报告生成"],
          files: ["configs/c3_full.json", "configs/active_active_v1/aa3_local.json", "limer_v0/orchestrator.py", "limer_v0/report.py", "tests/test_report.py"],
          evidence: ["results/aggregate_summary.json", "tests/test_report.py", "docs/active_active_v1_verification.md"],
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
          implemented: "版本化全 rank 协议安装同一份局部计划，未受影响 worker 保留原有 active-active 调度。",
          missing: "真实 GPU/NCCL communicator 适配，以及生产级恢复失败处理。",
          evidence: ["limer_v0/route_plan.py", "limer_v0/coordinator.py", "tests/test_worker_data_path.py", "docs/active_active_v1_verification.md"],
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
      ["定向故障边界", "v1 只退化 w2 发往 Fabric A 的 egress；尚未验证双向 access-link 故障。"],
      ["延迟瓶颈", "v1 的端侧 gate 仍等待完整轮次；页面不声称已经实现端到端毫秒级恢复。"],
    ],
    roadmap: [
      ["验证 active-active 局部改道", "测量健康状态下两张 fabric 的承载，并用显式全局策略作为局部恢复的对照。"],
      ["缩短确认延迟", "在轮次执行中输出 step-level 进度，同时保留短暂异常条件衡量误触发抑制能力。"],
      ["扩展故障画像", "预声明限速、低丢包、持续时间与双向故障，让检测不只覆盖定向带宽退化。"],
      ["替换遥测 proxy", "接入更真实的 streaming telemetry，并测量轮询、内存和交换机侧开销。"],
      ["实现不确定性感知分类", "在独立生成的 traces 上训练并校准 Proposal 中的分类器和不确定性估计器。"],
      ["分阶段提高真实性", "先用 SimAI 研究最多 128 张模拟 GPU 的 collective，再实现 GPU/NCCL communicator 恢复。"],
    ],
    feedback: [
      "下一阶段应优先接入哪种生产级遥测接口？",
      "健康第二张 fabric 的假设是否符合目标部署场景？",
      "下一项真实性里程碑应优先做 SimAI，还是 GPU/NCCL 集成？",
    ],
    meeting2: {
      intro: "每张卡片先复述上次汇报后收到的一条导师反馈，再给出我们针对性完成的修订与实测结果，并链接实现它的 artifact——代码、配置与归档实验数据。以下所有数字都从原始 run 文件独立重算，而非引用汇总。",
      metrics: [
        ["36 ms", "故障 → 交换机侧可疑信号（此前 2.78 s）"],
        ["1.07 s", "故障 → 端侧确认（此前 2.87 s）"],
        ["≈ 1.000", "局部恢复后的稳态 retention"],
        ["9 / 9", "新一轮 campaign 预注册 gate 全部通过"],
      ],
      labels: {
        ask: "反馈要点",
        revision: "修订内容与实测结果",
        artifacts: "Artifact（点击打开实现）",
        open: "在仓库中打开",
      },
      statusLabels: {
        delivered: "已交付",
        partial: "部分交付",
        planned: "已规划，等待确认",
      },
      items: [
        {
          tag: "Q1 · 检测延迟",
          ask: "毫秒级故障检测与恢复是最重要的 KPI。",
          revision: "检测器已重建。旧规则的基线被空闲态样本拉低，只能检测“静默”，导致限速但仍在流动的故障要 2.78 s 才被发现。新的 burst 感知规则只用突发窗口做校准，三次正式重复中 34.8–37.1 ms 即产生可疑信号；轮内 step 级端侧 gate 约 1.07 s 完成确认，不再等完整退化轮。路由 commit 仍发生在轮边界（约 2.87 s）：消除这一等待是已声明的下一工作项，页面不声称已实现毫秒级端到端恢复。",
          artifacts: ["limer_v0/sentinel.py", "limer_v0/orchestrator.py", "limer_v0/worker.py", "scripts/replay_sentinel.py", "configs/active_active_v2/aa6_stepdetect.json", "results_active_active_v2_1/aa6_stepdetect_rep01/summary.json", "docs/step_level_detection_v2_prereg.md", "tests/test_sentinel_burst.py"],
          status: "partial",
        },
        {
          tag: "Q1 · 性能损失",
          ask: "故障情况下的性能应尽量接近无故障训练场景。",
          revision: "20 个恢复轮的长窗口（三次重复）显示：局部恢复最终回到无故障基线的 retention ≈ 1.000。此前汇报的 0.936 只是恢复后前约 5 轮的收敛瞬态，不是稳态代价。",
          artifacts: ["configs/active_active_v2/aa3_local_longwindow.json", "results_active_active_v2_1/aa3_local_rep01/aggregate_rounds.csv", "results_active_active_v2_1/aggregate_summary.json"],
          status: "delivered",
        },
        {
          tag: "Q2 · 第二张 fabric 不是备份",
          ask: "Dual-ToR 中的第二台交换机在健康状态下应像普通交换机一样正常转发流量，而不是只作备份。",
          revision: "基线已改为 balanced active-active：每一轮里每个 worker 都同时在 Fabric A 和 B 上发送，每个健康 run 的归档 correctness 证据都验证了两张 fabric 上的逐 rank 字节数均非零。",
          artifacts: ["limer_v0/route_plan.py", "configs/active_active_v1/aa0_healthy.json", "results_active_active/aa0_healthy_rep01/correctness.json"],
          status: "delivered",
        },
        {
          tag: "Q2 · 局部改道",
          ask: "某个 worker 到 Fabric A 的链路故障时，只应改道该 worker 受影响的通信；其余 worker 继续使用 Fabric A。此前 demo 里整个 ring 都切到 Fabric B 是不对的。",
          revision: "恢复现在安装局部路由计划：只有受影响 worker 的三个 Fabric-A 发送槽位改走 B，其余三个 worker 的发送调度在故障前后逐字节一致（从原始逐轮 send routes 核验，并作为 run gate 强制）。本页的回放 demo 展示的就是局部计划。",
          artifacts: ["limer_v0/route_plan.py", "results_active_active/aa3_local_rep01/correctness.json", "results_active_active_v2_1/aa6_stepdetect_rep01/correctness.json", "tests/test_worker_data_path.py"],
          status: "delivered",
        },
        {
          tag: "Q3 · “gray-loss matrix”含义不清",
          ask: "这个术语需要一个具体、可讨论的定义。",
          revision: "已替换为显式的 fault-profile matrix：以限速、丢包、时延、队列深度、方向、持续时间、影响范围、渐变方式为维度命名每个 profile。其中三个新 profile（5 Mbit 限速、1% 丢包、+10 ms 时延）今天就是可运行的配置；优先覆盖哪些维度列在下方待确认决定中。",
          artifacts: ["docs/fault_profile_matrix.md", "configs/fault_profiles_v1/fp_r5_impact.json", "configs/fault_profiles_v1/fp_l1_impact.json", "configs/fault_profiles_v1/fp_d10_impact.json", "limer_v0/faults.py"],
          status: "partial",
        },
        {
          tag: "规模 · SimAI ≤ 128 GPU",
          ask: "先聚焦不超过 128 GPU 的小规模，用真实的 SimAI 模型获得更准确的性能；有余力再研究更大系统。",
          revision: "已依据 SimAI 官方仓库与论文起草执行计划：4→128 GPU 阶梯、通过无量纲比值与 Mininet 证据校准、以及 ns-3 层的故障注入补丁（官方仓库不自带故障注入）。SimAI 结果永远不会与 Mininet packet 证据混在同一张表里。待下方决定确认后即可开工。",
          artifacts: ["docs/simai_plan.md", "docs/fault_profile_matrix.md"],
          status: "planned",
        },
      ],
      decisions: [
        ["延迟 KPI 的数值口径", "“毫秒级”需要明确区间和阈值。当前实测：故障→交换机可疑 36 ms；故障→端侧确认 1.07 s；故障→第一个恢复轮完成 3.96 s。KPI 取哪个区间、要低于多少？"],
        ["“gray”的首要含义", "限速、随机丢包、附加时延，还是部分流损伤（如单个 ECMP 桶）？只做 egress 方向是否足够，是否需要覆盖 ingress/双向以及 ToR 上联故障？"],
        ["SimAI 阶段的范围", "只模拟故障影响与改道收益（推荐，计划已就绪），还是同时在模拟器内复刻检测闭环（工作量约乘三）？"],
        ["恢复的验收标准", "预注册 retention gate 为 ≥ 0.9，实测稳态 ≈ 1.000。标准是否应提高？应在多少个恢复轮上评估？"],
      ],
    },
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


function replayContent(scene) {
  const base = content[language].replay;
  if (scene.mode !== "active_active_local") return base;
  const active = language === "zh"
    ? {
        boundary: "Active-active v1 实测回放 · 视觉时间已压缩",
        scene: {
          baseline: "两张 Fabric 在健康状态下同时承载流量",
          fault: "w2 发往 Fabric A 的 egress 降速，但仍保持 UP",
          detected: "交换机侧计数器发出可疑信号",
          confirmed: "端侧确认 collective 受到持续影响",
          committed: "所有 rank 提交同一个局部路由计划",
          recovered: "只改 w2 受影响槽位后的 round 完成",
        },
        events: [
          ["Active-active 基线", "每个 step 中 Fabric A 和 B 都承载 worker 边。"],
          ["FAULT_APPLIED", "仅 w2→Fabric A egress 从 100 降到 20 Mbit/s，接口仍 UP。"],
          ["SWITCH_SUSPECT", "独立的交换机侧 RX counter 连续观察到低速。"],
          ["HOST_CONFIRM", "完整退化 round 确认 collective 影响，alternate Fabric B 健康。"],
          ["RECOVERY_COMMIT", "全部 rank 同意 version 1，但 plan 只改 w2 的三个槽位。"],
          ["恢复完成", "w0、w1、w3 的发送计划不变，恢复 retention 来自真实 artifact。"],
        ],
        phaseHelp: [
          "rank-offset 计划让 A/B 在每个 step 同时有流量。",
          "这是定向 egress 灰色退化，不是双向断线。",
          "Layer 1 只在交换机侧做高召回粗筛。",
          "当前 Layer 2 仍等待完整 round，因此它主导延迟。",
          "全 rank 协调保证 sender 与 receiver 使用同一个 plan fingerprint。",
          "只有 w2 原来走 A 的三个发送槽位改走 B。",
        ],
        activeRoute: "活动路由计划",
      }
    : {
        boundary: "Measured active-active v1 replay · visual time compressed",
        scene: {
          baseline: "Both fabrics carry healthy traffic concurrently",
          fault: "w2 egress to Fabric A slows down but stays UP",
          detected: "The switch-facing counter emits a suspicion",
          confirmed: "The host confirms persistent collective impact",
          committed: "All ranks commit one localized route plan",
          recovered: "Rounds complete after changing only w2's affected slots",
        },
        events: [
          ["Active-active baseline", "Fabric A and B both carry worker edges in every step."],
          ["FAULT_APPLIED", "Only w2→Fabric A egress changes from 100 to 20 Mbit/s; operstate stays UP."],
          ["SWITCH_SUSPECT", "The isolated switch-facing RX counter observes persistent low rate."],
          ["HOST_CONFIRM", "A completed degraded round confirms impact and alternate Fabric B is healthy."],
          ["RECOVERY_COMMIT", "Every rank agrees on version 1, but the plan changes only three w2 slots."],
          ["Recovered", "w0, w1, and w3 sender schedules stay unchanged; retention comes from real artifacts."],
        ],
        phaseHelp: [
          "The rank-offset plan puts traffic on A and B in every step.",
          "This is a directed egress gray degradation, not a bidirectional link cut.",
          "Layer 1 performs a high-recall switch-facing screen.",
          "Layer 2 still waits for a full round, so it dominates latency.",
          "All-rank coordination gives sender and receiver one plan fingerprint.",
          "Only w2's three baseline-A send slots move to B.",
        ],
        activeRoute: "Active route plan",
      };
  return { ...base, ...active };
}


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
  const c = replayContent(scene);
  const recovered = scene.version === 1;
  const activeLocal = scene.mode === "active_active_local";
  const impacted = scene.faultActive;
  const readyClass = recovered ? " ready" : "";
  const routeDisplay = activeLocal
    ? recovered
      ? language === "zh"
        ? "A+B · 仅 w2 的 A 槽位改道到 B"
        : "A+B · only w2 A slots rerouted to B"
      : language === "zh"
        ? "A+B active-active"
        : "A+B active-active"
    : scene.routeLabel;
  return `
    <div class="network-wrap">
      <svg class="network-svg" viewBox="0 0 550 260" role="img" aria-labelledby="network-title network-desc">
        <title id="network-title">${language === "zh" ? "四个 worker 与两张 fabric 的连接" : "Four workers connected to two fabrics"}</title>
        <desc id="network-desc">${language === "zh" ? "当前路由计划与 w2 定向 egress 退化随回放状态变化。" : "The route plan and directed w2 egress degradation change during replay."}</desc>
        <defs>
          <marker id="egress-arrow" viewBox="0 0 10 10" refX="7" refY="5" markerWidth="5" markerHeight="5" orient="auto-start-reverse">
            <path d="M 0 0 L 10 5 L 0 10 z"></path>
          </marker>
        </defs>
        <path data-edge="a0" class="${scene.edgeClasses.a0}" d="M59 42 H178 Q207 42 227 48"></path>
        <path data-edge="a1" class="${scene.edgeClasses.a1}" d="M59 218 H78 V103 Q78 92 90 92 H194 Q214 92 227 74"></path>
        <path data-edge="a2" class="${scene.edgeClasses.a2}${activeLocal ? " directed-egress" : ""}"${activeLocal ? ' marker-end="url(#egress-arrow)"' : ""} d="M491 42 H372 Q343 42 323 48"></path>
        <path data-edge="a3" class="${scene.edgeClasses.a3}" d="M491 218 H472 V103 Q472 92 460 92 H356 Q336 92 323 74"></path>
        <path data-edge="b0" class="${scene.edgeClasses.b0}" d="M59 42 H68 V157 Q68 168 80 168 H194 Q214 168 227 184"></path>
        <path data-edge="b1" class="${scene.edgeClasses.b1}" d="M59 218 H178 Q207 218 227 212"></path>
        <path data-edge="b2" class="${scene.edgeClasses.b2}${activeLocal ? " directed-egress" : ""}"${activeLocal ? ' marker-end="url(#egress-arrow)"' : ""} d="M491 42 H482 V157 Q482 168 470 168 H356 Q336 168 323 184"></path>
        <path data-edge="b3" class="${scene.edgeClasses.b3}" d="M491 218 H372 Q343 218 323 212"></path>

        <rect class="fabric-node${activeLocal || !recovered ? " active-a" : ""}" x="227" y="28" width="96" height="58" rx="12"></rect>
        <text class="network-label" x="275" y="52">Fabric A</text>
        <text class="network-sub-label" x="275" y="69">sA · ${activeLocal ? "active" : "version 0"}</text>
        <rect class="fabric-node${activeLocal || recovered ? " active-b" : ""}" x="227" y="174" width="96" height="58" rx="12"></rect>
        <text class="network-label" x="275" y="198">Fabric B</text>
        <text class="network-sub-label" x="275" y="215">sB · ${activeLocal ? "active" : recovered ? "version 1" : "standby"}</text>

        <circle class="worker-node${readyClass}" cx="35" cy="42" r="22"></circle>
        <circle class="worker-node${readyClass}" cx="35" cy="218" r="22"></circle>
        <circle class="worker-node${impacted ? " impacted" : readyClass}" cx="515" cy="42" r="22"></circle>
        <circle class="worker-node${readyClass}" cx="515" cy="218" r="22"></circle>
        <text class="network-label" x="35" y="47">w0</text>
        <text class="network-label" x="35" y="223">w1</text>
        <text class="network-label" x="515" y="47">w2</text>
        <text class="network-label" x="515" y="223">w3</text>
      </svg>
      <p class="fault-callout${scene.faultActive ? " visible" : ""}">100 → 20 Mbit/s · ${activeLocal ? "w2 egress" : "link"} stays UP</p>
      <p class="micro-label">${c.activeRoute}: ${routeDisplay} · version ${scene.version}</p>
    </div>`;
}


function renderEventRows(scene) {
  const c = replayContent(scene);
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
  const c = replayContent(scene);
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
              ${model.runs.map((run) => `<option value="${run.id}"${run.id === model.runId ? " selected" : ""}>${run.family_label || "Legacy CPU v0"} · ${run.id} · ${run.gate}</option>`).join("")}
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


let meeting = (() => {
  try {
    return localStorage.getItem("limer-meeting") || "2";
  } catch {
    return "2";
  }
})();


export function setMeeting(nextMeeting) {
  meeting = nextMeeting === "1" ? "1" : "2";
  document.body.dataset.meeting = meeting;
  document.querySelectorAll(".meeting-tab").forEach((tab) => {
    const active = tab.dataset.meeting === meeting;
    tab.classList.toggle("active", active);
    tab.setAttribute("aria-selected", String(active));
  });
  try {
    localStorage.setItem("limer-meeting", meeting);
  } catch {
    // Meeting selection remains available for the current page session.
  }
}


export function renderMeeting2() {
  const c = content[language].meeting2;
  const revisionsRoot = document.querySelector("#revisions-root");
  revisionsRoot.innerHTML = `
    <div class="revisions-intro"><p>${c.intro}</p></div>
    <div class="revision-metrics">
      ${c.metrics.map(([value, label]) => `<div class="revision-metric"><strong>${value}</strong><span>${label}</span></div>`).join("")}
    </div>
    <div class="revision-grid">
      ${c.items.map((item) => `
        <article class="revision-card">
          <header>
            <span class="revision-tag">${item.tag}</span>
            <span class="mapping-status ${item.status === "planned" ? "not-started" : item.status === "partial" ? "partial" : "delivered"}">${c.statusLabels[item.status]}</span>
          </header>
          <div class="revision-ask"><strong>${c.labels.ask}</strong><p>${item.ask}</p></div>
          <div class="revision-body"><strong>${c.labels.revision}</strong><p>${item.revision}</p></div>
          <div class="revision-artifacts"><strong>${c.labels.artifacts}</strong>${renderRepositoryLinks(item.artifacts, c.labels.open)}</div>
        </article>`).join("")}
    </div>`;

  const decisionsRoot = document.querySelector("#decisions-root");
  decisionsRoot.className = "roadmap-grid";
  decisionsRoot.innerHTML = c.decisions.map(([title, body], index) => `
    <article class="roadmap-card decision-card"><span class="roadmap-index">${index + 1}</span><h3>${title}</h3><p>${body}</p></article>`).join("");
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
  renderMeeting2();
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
    const replayRuns = payload.replay_runs || payload.c3_runs;
    const defaultRunId = payload.active_active_runs?.[0]?.id || "c3_rep01";
    model = createReplayModel(replayRuns, defaultRunId);
    renderNarrative();
    renderMeeting2();
    renderReplay();
    renderEvidence("C3");
    setLanguage(language);
    setMeeting(meeting);
    document.querySelector("#language-toggle").addEventListener("click", () => {
      setLanguage(language === "en" ? "zh" : "en");
    });
    document.querySelectorAll(".meeting-tab").forEach((tab) => {
      tab.addEventListener("click", () => setMeeting(tab.dataset.meeting));
    });
    document.addEventListener("click", (event) => {
      const anchor = event.target.closest('a[href^="#"]');
      if (!anchor) return;
      const target = document.querySelector(anchor.getAttribute("href"));
      if (target?.classList.contains("meeting-1-only") && meeting === "2") {
        setMeeting("1");
      }
    });
  } catch (error) {
    showDataError(error);
  }
}


start();
