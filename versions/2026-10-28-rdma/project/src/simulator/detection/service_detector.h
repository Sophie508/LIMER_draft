#pragma once
#include <algorithm>
#include <cstdint>
#include <deque>
#include <functional>
#include <map>
#include <set>
#include <stdexcept>
#include <string>
#include <vector>

namespace limer { namespace detection {

// Times are simulated endpoint-clock observations, in nanoseconds: sender
// transport events and receiver-local window summaries. No fault metadata is
// accepted. Calibration is an explicit assumption, not a known healthy oracle.
// v2 also counts sender-observed retransmission on distinct canaries: this is
// transport repair cost/delivery risk, not proof of unrecoverable packet loss.
// v3 includes an active business transfer's last real ACK progress timestamp.
// v4 adds receiver-observed whole-path full-packet dispersion summaries. The
// caller computes each summary from past accepted packets and charges reports.
struct ServiceDetectorConfig {
  int64_t calibration_ns = 20000000;
  uint64_t multiplier_num = 2;
  uint64_t multiplier_den = 1;
  int64_t margin_ns = 100000;
  int64_t floor_ns = 100000;
  int64_t fallback_ns = 2000000;
  int64_t window_ns = 40000000;
  unsigned bad_samples = 3;
  int64_t min_span_ns = 4000000;
  int64_t business_stall_ns = 40000000;
  int64_t spacing_window_ns = 10000000;
  unsigned spacing_min_samples = 64;
  uint64_t spacing_multiplier_num = 2;
  uint64_t spacing_multiplier_den = 1;
  int64_t spacing_margin_ns = 100;
  unsigned spacing_bad_windows = 2;
  uint64_t spacing_packet_bytes = 976;
  unsigned spacing_quantile_num = 1;
  unsigned spacing_quantile_den = 10;
};

struct ServiceAlarm {
  std::string rule_version = "canary-service-v4";
  unsigned path = 0;
  int64_t decision_t_ns = 0;
  std::string signal = "canary_service";
  int64_t baseline_ns = 0;
  int64_t deadline_ns = 0;
  std::vector<uint64_t> evidence_tokens;
  std::vector<int64_t> evidence_submitted_ns;
};

class ServiceDetector {
  struct Sample {
    int64_t submitted;
    uint64_t bytes;
    bool bad;
  };
  struct Bad {
    int64_t observed;
    int64_t submitted;
    uint64_t token;
  };
  struct Path {
    int64_t first = -1;
    int64_t baseline = 0;
    bool frozen = false;
    bool alarmed = false;
    uint64_t bytes = 0;
    std::map<uint64_t, Sample> pending;
    std::set<uint64_t> tokens;
    std::deque<Bad> bad;
    int64_t spacing_baseline = 0;
    int64_t spacing_last = -1;
    std::deque<int64_t> spacing_bad;
  };
  ServiceDetectorConfig cfg;
  int64_t now = -1;
  std::map<unsigned, Path> paths;

  int64_t deadline(const Path& p) const {
    if (!p.baseline) return std::max(cfg.floor_ns, cfg.fallback_ns);
    const int64_t scaled = (p.baseline * cfg.multiplier_num + cfg.multiplier_den - 1) / cfg.multiplier_den;
    return std::max(cfg.floor_ns, scaled + cfg.margin_ns);
  }
  void recordBad(Path& p, uint64_t token, Sample& s) {
    if (s.bad) return;
    s.bad = true;
    p.bad.push_back(Bad{now, s.submitted, token});
  }
  void evaluate(unsigned key, Path& p) {
    while (!p.bad.empty() && p.bad.front().observed < now - cfg.window_ns) p.bad.pop_front();
    if (p.alarmed || p.bad.size() < cfg.bad_samples) return;
    int64_t first = p.bad.front().submitted, last = first;
    for (const auto& b : p.bad) { first = std::min(first, b.submitted); last = std::max(last, b.submitted); }
    if (last - first < cfg.min_span_ns) return;
    p.alarmed = true;
    ServiceAlarm a; a.path = key; a.decision_t_ns = now;
    a.baseline_ns = p.baseline; a.deadline_ns = deadline(p);
    for (const auto& b : p.bad) { a.evidence_tokens.push_back(b.token); a.evidence_submitted_ns.push_back(b.submitted); }
    if (onAlarm) onAlarm(a);
  }

public:
  std::function<void(const ServiceAlarm&)> onAlarm;
  explicit ServiceDetector(const ServiceDetectorConfig& config = ServiceDetectorConfig()) : cfg(config) {
    if (cfg.calibration_ns < 0 || !cfg.multiplier_num || !cfg.multiplier_den || cfg.margin_ns < 0 ||
        cfg.floor_ns <= 0 || cfg.fallback_ns <= 0 || cfg.window_ns <= 0 || !cfg.bad_samples ||
        cfg.min_span_ns < 0 || cfg.min_span_ns > cfg.window_ns || cfg.business_stall_ns <= 0 ||
        cfg.spacing_window_ns <= 0 || !cfg.spacing_min_samples || !cfg.spacing_multiplier_num ||
        !cfg.spacing_multiplier_den || cfg.spacing_margin_ns < 0 || !cfg.spacing_bad_windows ||
        !cfg.spacing_packet_bytes || !cfg.spacing_quantile_den || cfg.spacing_quantile_num >= cfg.spacing_quantile_den)
      throw std::invalid_argument("Invalid service detector configuration");
  }
  const ServiceDetectorConfig& config() const { return cfg; }
  void advance(int64_t time) {
    if (time < 0 || time < now) throw std::invalid_argument("Nonmonotone service observation time");
    now = time;
    for (auto& kv : paths) {
      auto& p = kv.second;
      if (!p.frozen && now >= p.first + cfg.calibration_ns) p.frozen = true;
      if (!p.frozen) continue;
      const auto limit = deadline(p);
      // Expired outstanding samples count even if the network never completes.
      for (auto& pending : p.pending)
        if (now - pending.second.submitted > limit) recordBad(p, pending.first, pending.second);
      evaluate(kv.first, p);
    }
  }
  void submit(unsigned path, uint64_t token, int64_t time, uint64_t bytes) {
    if (!bytes) throw std::invalid_argument("Canary payload must be positive");
    auto found = paths.find(path);
    if (found != paths.end() && (found->second.tokens.count(token) || found->second.bytes != bytes))
      throw std::invalid_argument("Duplicate canary token or changed payload size");
    advance(time);
    auto& p = paths[path];
    if (p.first < 0) { p.first = time; p.bytes = bytes; p.frozen = !cfg.calibration_ns; }
    p.tokens.insert(token); p.pending.emplace(token, Sample{time, bytes, false});
  }
  void complete(unsigned path, uint64_t token, int64_t time) {
    auto p = paths.find(path);
    if (p == paths.end() || !p->second.pending.count(token)) throw std::invalid_argument("Unknown/completed canary token");
    advance(time);
    auto& state = p->second;
    auto it = state.pending.find(token);
    const int64_t elapsed = now - it->second.submitted;
    if (!state.frozen) state.baseline = std::max(state.baseline, elapsed);
    // advance already marks late completions; equality is considered on time.
    state.pending.erase(it);
  }
  void retransmit(unsigned path, uint64_t token, int64_t time) {
    auto p = paths.find(path);
    if (p == paths.end() || !p->second.pending.count(token)) throw std::invalid_argument("Unknown/completed canary token");
    advance(time);
    auto& state = p->second;
    // Retransmissions during calibration do not count as bad observations.
    // A canary with many repaired packets still contributes only one sample.
    if (state.frozen) {
      recordBad(state, token, state.pending.at(token));
      evaluate(path, state);
    }
  }
  void stall(unsigned path, uint64_t token, int64_t time, int64_t last_progress_ns, uint64_t remaining_bytes) {
    auto p = paths.find(path);
    if (p == paths.end()) throw std::invalid_argument("Unknown business observation path");
    if (last_progress_ns < 0 || last_progress_ns > time) throw std::invalid_argument("Invalid ACK progress timestamp");
    advance(time);
    auto& state = p->second;
    if (!state.frozen || state.alarmed || !remaining_bytes || now - last_progress_ns < cfg.business_stall_ns) return;
    state.alarmed = true;
    ServiceAlarm a; a.path = path; a.decision_t_ns = now; a.signal = "business_ack_stall";
    a.baseline_ns = state.baseline; a.deadline_ns = cfg.business_stall_ns;
    a.evidence_tokens.push_back(token); a.evidence_submitted_ns.push_back(last_progress_ns);
    if (onAlarm) onAlarm(a);
  }
  void spacing(unsigned path, int64_t window_end_ns, int64_t p10_spacing_ns, uint64_t sample_count) {
    auto p = paths.find(path);
    if (p == paths.end()) throw std::invalid_argument("Unknown receiver spacing path");
    auto& state = p->second;
    const int64_t expected = state.spacing_last < 0 ? state.first + cfg.calibration_ns : state.spacing_last + cfg.spacing_window_ns;
    if (window_end_ns != expected || p10_spacing_ns < 0 ||
        (sample_count >= cfg.spacing_min_samples && !p10_spacing_ns))
      throw std::invalid_argument("Invalid/missing receiver spacing window");
    advance(window_end_ns);
    const bool calibration = state.spacing_last < 0;
    state.spacing_last = window_end_ns;
    if (calibration) {
      if (sample_count >= cfg.spacing_min_samples) state.spacing_baseline = p10_spacing_ns;
      return;
    }
    if (state.alarmed || !state.spacing_baseline) return;
    const int64_t threshold = (state.spacing_baseline * cfg.spacing_multiplier_num + cfg.spacing_multiplier_den - 1) / cfg.spacing_multiplier_den + cfg.spacing_margin_ns;
    if (sample_count < cfg.spacing_min_samples || p10_spacing_ns <= threshold) {
      state.spacing_bad.clear(); return;
    }
    state.spacing_bad.push_back(window_end_ns);
    if (state.spacing_bad.size() < cfg.spacing_bad_windows) return;
    state.alarmed = true;
    ServiceAlarm a; a.path = path; a.decision_t_ns = now; a.signal = "delivery_spacing_shift";
    a.baseline_ns = state.spacing_baseline; a.deadline_ns = threshold;
    for (auto end : state.spacing_bad) {
      a.evidence_tokens.push_back(uint64_t(end)); a.evidence_submitted_ns.push_back(end - cfg.spacing_window_ns);
    }
    if (onAlarm) onAlarm(a);
  }
  int64_t baselineNs(unsigned path) const { auto p = paths.find(path); return p == paths.end() ? 0 : p->second.baseline; }
  int64_t deadlineNs(unsigned path) const { auto p = paths.find(path); return p == paths.end() ? std::max(cfg.floor_ns, cfg.fallback_ns) : deadline(p->second); }
  bool calibrated(unsigned path) const { auto p = paths.find(path); return p != paths.end() && p->second.frozen; }
  bool alarmed(unsigned path) const { auto p = paths.find(path); return p != paths.end() && p->second.alarmed; }
  int64_t spacingBaselineNs(unsigned path) const { auto p = paths.find(path); return p == paths.end() ? 0 : p->second.spacing_baseline; }
  size_t pendingCount(unsigned path) const { auto p = paths.find(path); return p == paths.end() ? 0 : p->second.pending.size(); }
};

}}
