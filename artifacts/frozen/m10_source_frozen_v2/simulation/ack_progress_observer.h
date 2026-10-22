// Sender-side ACK-progress observer. Injector settings never enter these APIs.
struct ProgressReport {
  int path;
  uint64_t acked;
  int64_t sample;
  bool full_busy;
};
struct ProgressState {
  bool previous = false, alarmed = false;
  uint64_t acked = 0;
  int64_t sample = 0;
  std::vector<double> calibration;
  double reference = 0;
  int slow_windows = 0;
};
static std::map<int,ProgressState> progress_states;
static std::ofstream progress_log;
static int64_t progress_period = 2'000'000, progress_propagation = 1'000'000;
static uint64_t progress_capacity = 10'000'000;
static int64_t progress_free = 0;
static int progress_pending = 0;
static bool progress_sampling_done = false;

static void progress_delivered(ProgressReport report) {
  int64_t arrival = Simulator::Now().GetNanoSeconds();
  progress_log << "{\"kind\":\"report\",\"path\":" << report.path
      << ",\"acked_bytes\":" << report.acked << ",\"sample_ns\":" << report.sample
      << ",\"arrival_ns\":" << arrival << ",\"full_busy\":"
      << (report.full_busy ? "true" : "false") << "}\n";
  auto& state = progress_states[report.path];
  if (state.previous) {
    if (report.sample <= state.sample || report.acked < state.acked)
      throw std::runtime_error("Nonmonotonic ACK progress");
    double rate = double(report.acked-state.acked)/double(report.sample-state.sample);
    if (!report.full_busy) state.slow_windows = 0;
    else if (state.reference == 0) {
      if (rate > 0) {
        state.calibration.push_back(rate);
        if (state.calibration.size() == 4) {
          auto sorted = state.calibration; std::sort(sorted.begin(),sorted.end());
          state.reference = (sorted[1]+sorted[2])/2;
        }
      }
    } else {
      state.slow_windows = rate < state.reference/2 ? state.slow_windows+1 : 0;
      if (state.slow_windows >= 3 && !state.alarmed) {
        state.alarmed = true;
        progress_log << "{\"kind\":\"alarm\",\"path\":" << report.path
            << ",\"decision_ns\":" << arrival << "}\n";
      }
    }
  }
  state.previous = true; state.acked = report.acked; state.sample = report.sample;
  progress_log.flush(); --progress_pending;
  observer_complete = progress_sampling_done && progress_pending == 0;
  maybe_stop();
}

static void progress_sample() {
  int64_t now = Simulator::Now().GetNanoSeconds();
  for (int path = 0; path < 2*logical_ranks; ++path) {
    uint64_t acknowledged = 0;
    // A deleted completed QP contributes its entire ACK-complete flow volume.
    for (const auto& pair : flows)
      if (pair.second.received && pair.second.port_src == path)
        acknowledged += pair.second.bytes;
    auto driver = n.Get(path)->GetObject<RdmaDriver>();
    if (!driver || !driver->m_rdma) throw std::runtime_error("Missing RDMA observer");
    bool full_busy = false;
    for (const auto& pair : driver->m_rdma->m_qpMap) {
      auto qp = pair.second;
      if (qp->snd_una > qp->m_init_size) throw std::runtime_error("ACK exceeds flow size");
      acknowledged += qp->snd_una;
      if (qp->startTime.GetNanoSeconds() <= now-progress_period) full_busy = true;
    }
    ProgressReport report{path,acknowledged,now,full_busy};
    int64_t start = std::max(now,progress_free);
    int64_t end = start+int64_t(std::ceil(512.0*1e9/progress_capacity));
    progress_free = end;
    progress_log << "{\"kind\":\"offer\",\"path\":" << path
        << ",\"sample_ns\":" << now << ",\"start_ns\":" << start
        << ",\"end_ns\":" << end << ",\"bytes\":64}\n";
    ++progress_pending;
    Simulator::Schedule(NanoSeconds(end+progress_propagation-now),progress_delivered,report);
  }
  progress_sampling_done = recv_count == int(flows.size());
  if (!progress_sampling_done) Simulator::Schedule(NanoSeconds(progress_period),progress_sample);
  progress_log.flush();
}

static void load_progress(const char* config, const char* output) {
  std::ifstream input(config);
  if (!(input >> progress_period >> progress_capacity >> progress_propagation)
      || progress_period <= 0 || progress_capacity == 0 || progress_propagation < 0)
    throw std::runtime_error("Invalid progress channel configuration");
  std::string trailing; if (input >> trailing) throw std::runtime_error("Trailing observer configuration");
  progress_log.open(output);
  if (!progress_log) throw std::runtime_error("Cannot open progress log");
  Simulator::ScheduleNow(progress_sample);
}

// Separate fault action; the observation and decision callbacks receive no
// event time, target identity, configured capacity or private injection state.
static void inject_egress_rate(int path, uint64_t rate) {
  Ptr<QbbNetDevice> selected;
  auto node = n.Get(path);
  for (uint32_t i = 0; i < node->GetNDevices(); ++i) {
    auto device = DynamicCast<QbbNetDevice>(node->GetDevice(i));
    if (device) {
      if (selected) throw std::runtime_error("Ambiguous fault egress");
      selected = device;
    }
  }
  if (!selected) throw std::runtime_error("Missing fault egress");
  selected->SetDataRate(DataRate(rate));
  // This injector models a configured NIC service change, including restoration
  // of transport pacing. Device-only restoration leaves QPs created during the
  // reduced-rate interval permanently capped at that interval's initial rate.
  auto hw = node->GetObject<RdmaDriver>()->m_rdma;
  if (hw->m_cc_mode != 1) throw std::runtime_error("Rate event requires DCQCN");
  for (const auto& pair : hw->m_qpMap) {
    auto qp = pair.second;
    qp->m_max_rate = DataRate(rate);
    qp->mlx.m_targetRate = DataRate(rate);
    hw->ChangeRate(qp,DataRate(rate));
  }
  std::cout << "RATE_EVENT ns=" << Simulator::Now().GetNanoSeconds()
            << " path=" << path << " bps=" << rate
            << " active_qps=" << hw->m_qpMap.size() << '\n';
}
static void load_rate_events(const char* path) {
  std::ifstream input(path); int count;
  if (!(input >> count) || count < 0) throw std::runtime_error("Invalid rate event count");
  for (int i = 0; i < count; ++i) {
    int endpoint; int64_t at; uint64_t rate;
    if (!(input >> at >> endpoint >> rate) || at < 0 || at >= 10'000'000'000LL
        || endpoint < 0 || endpoint >= 2*logical_ranks || rate == 0)
      throw std::runtime_error("Invalid directed rate event");
    Simulator::Schedule(NanoSeconds(at),inject_egress_rate,endpoint,rate);
  }
  std::string trailing; if (input >> trailing) throw std::runtime_error("Trailing rate events");
}
