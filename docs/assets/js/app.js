import {
  PHASES,
  createReplayModel,
  deriveScene,
  selectRun,
  setState,
} from "./replay.js";


const DATA_URL = "assets/data/demo-data.json";
const REPOSITORY_URL = "https://github.com/Sophie508/LIMER_draft";
const MAX_RETENTION = 1.2;

const translations = {
  en: {
    "nav.demo": "Demo",
    "nav.evidence": "Evidence",
    "nav.roadmap": "Roadmap",
    "hero.eyebrow": "Stage review · CPU/Mininet emulation",
    "hero.title": "A link can stay UP while collective performance collapses.",
    "hero.body": "LIMER detects a switch-facing signal, confirms end-host impact, and coordinates a move to a healthy fabric.",
    "hero.action": "Replay the archived incident",
    "demo.title": "Archived C3 incident replay",
    "architecture.title": "What the CPU prototype implements",
    "evidence.title": "Evidence explorer",
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
    "nav.evidence": "证据",
    "nav.roadmap": "下一步",
    "hero.eyebrow": "阶段性研究汇报 · CPU/Mininet 仿真",
    "hero.title": "链路保持 UP，集体通信性能仍可能骤降。",
    "hero.body": "LIMER 先捕获交换机侧信号，再确认端侧影响，并协调所有 worker 切换到健康 fabric。",
    "hero.action": "回放归档实验",
    "demo.title": "C3 归档事件回放",
    "architecture.title": "CPU 原型已经实现了什么",
    "evidence.title": "实验数据浏览器",
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
      activeRoute: "Active route",
      retention: "Matched-baseline retention",
      gate: "Fixed C3 gate ≥ 0.900",
      faultRetention: "Fault retention",
      recoveryRetention: "Post-recovery",
      checksumErrors: "CRC errors",
      versionErrors: "Version errors",
      source: "Open source evidence",
    },
    architecture: [
      {
        title: "1 · Switch-side first signal",
        implemented: "Implemented: 20 ms target polling of the distinct switch-facing sA-eth3 RX counter and a three-sample high-recall rule.",
        required: "Still required: switch-resident or production telemetry, a resource budget, and broader symptoms.",
      },
      {
        title: "2 · End-host refinement",
        implemented: "Implemented: a deterministic impact and standby-health gate that confirms or suppresses recovery.",
        required: "Still required: calibrated uncertainty, NIC/collective signals, and evaluation on unseen faults.",
      },
      {
        title: "3 · Coordinated recovery",
        implemented: "Implemented: four-rank prepare / READY / commit and a route-version move from Fabric A to B.",
        required: "Still required: real process-group or communicator adaptation with production abort and timeout behavior.",
      },
    ],
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
    boundaries: [
      ["AllReduce-like", "Framed TCP ring traffic exercises synchronization pressure but does not reduce tensors."],
      ["CPU / Mininet", "No GPU, training framework, NCCL, RDMA, checkpoint, or optimizer participates."],
      ["Management-plane proxy", "The detector reads switch-facing Linux counters but is not resident in switch hardware."],
      ["Redundant path assumed", "Recovery requires a healthy pre-existing Fabric B and persistent B-side TCP rings."],
      ["Latency bottleneck", "Switch suspicion is about 50 ms, but whole-round host confirmation is about 5.27 s."],
    ],
    roadmap: [
      ["Isolate standby-path variance", "Keep the C3 gate fixed. Compare idle, low-rate keepalive, and pre-warmed Fabric B treatments to test the cold-path hypothesis."],
      ["Reduce confirmation delay", "Emit step-level progress evidence while a round is in flight, while retaining C5 to measure false-trigger suppression."],
      ["Expand fault and platform scope", "Add an orthogonal gray-loss matrix, then replace telemetry and workload proxies one boundary at a time before GPU/NCCL recovery."],
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
      activeRoute: "当前路径",
      retention: "相对匹配基线的 retention",
      gate: "固定 C3 gate ≥ 0.900",
      faultRetention: "故障期 retention",
      recoveryRetention: "恢复后 retention",
      checksumErrors: "CRC 错误",
      versionErrors: "版本错误",
      source: "查看源证据",
    },
    architecture: [
      {
        title: "1 · 交换机侧第一信号",
        implemented: "已实现：以 20 ms 为目标轮询独立的交换机侧 sA-eth3 RX 计数器，并使用连续三样本高召回规则。",
        required: "仍需：驻交换机或生产级遥测路径、资源预算，以及更广的异常症状。",
      },
      {
        title: "2 · 端侧精化判断",
        implemented: "已实现：确定性的影响与备用路径健康 gate，用于确认或抑制恢复。",
        required: "仍需：经过校准的不确定性、NIC/collective 信号和未见故障评估。",
      },
      {
        title: "3 · 协同恢复",
        implemented: "已实现：四 rank prepare / READY / commit，以及从 Fabric A 到 B 的 route-version 切换。",
        required: "仍需：真实 process group 或 communicator 适配，以及生产级 abort 和 timeout 行为。",
      },
    ],
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
    boundaries: [
      ["AllReduce-like", "TCP 环形字节流复现同步压力，但不执行 tensor reduction。"],
      ["CPU / Mininet", "没有 GPU、训练框架、NCCL、RDMA、checkpoint 或 optimizer 参与。"],
      ["管理面 proxy", "检测器读取交换机侧 Linux 计数器，但并不驻留在交换机硬件。"],
      ["假设存在冗余路径", "恢复依赖预先存在的健康 Fabric B 和已建立的 B 侧 TCP ring。"],
      ["延迟瓶颈", "交换机侧可疑信号约 50 ms，但等待完整轮次使端侧确认约为 5.27 s。"],
    ],
    roadmap: [
      ["隔离备用路径波动", "保持 C3 gate 不变，对比 idle、低速 keepalive 和 pre-warmed Fabric B，检验 cold-path 假设。"],
      ["缩短确认延迟", "在轮次执行中输出 step-level 进度证据，同时保留 C5 衡量误触发抑制能力。"],
      ["扩展故障与平台范围", "先加入正交 gray-loss matrix，再逐层替换遥测和 workload proxy，最后进入 GPU/NCCL 恢复。"],
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
    <article class="replay-card">
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
          <div class="scene-heading" aria-live="polite"><span>${c.scene[scene.phase]}</span><strong class="status-pill ${statusClass}">${c.labels[model.stateIndex]}</strong></div>
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
      <div class="replay-scrubber">
        <input id="replay-scrubber" type="range" min="0" max="${PHASES.length - 1}" step="1" value="${model.stateIndex}" aria-label="${language === "zh" ? "回放时间轴" : "Replay timeline"}">
        <div class="scrubber-labels">${c.labels.map((label) => `<span>${label}</span>`).join("")}</div>
      </div>
    </article>`;

  root.querySelector("#play-button").addEventListener("click", togglePlayback);
  root.querySelector("#restart-button").addEventListener("click", () => {
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, 0);
    renderReplay();
  });
  root.querySelector("#replay-scrubber").addEventListener("input", (event) => {
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, Number(event.target.value));
    renderReplay();
  });
  root.querySelector("#run-select").addEventListener("change", (event) => {
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
    clearTimeout(replayTimer);
    model = setState({ ...model, playing: false }, Number(row.dataset.stateIndex));
    renderReplay();
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

  document.querySelector("#architecture-grid").innerHTML = c.architecture.map((item) => `
    <article class="layer-card"><h3>${item.title}</h3><p>${item.implemented}</p><p class="required">${item.required}</p></article>`).join("");

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
