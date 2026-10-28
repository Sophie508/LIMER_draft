#include "limer-congestion-signal.h"

#include <atomic>
#include <mutex>

namespace ns3 {
namespace {
std::atomic<LimerCongestionSignalSink> g_sink(nullptr);
std::atomic<void*> g_context(nullptr);
std::mutex g_registration_mutex;
}  // namespace

bool RegisterLimerCongestionSignalSink(
    LimerCongestionSignalSink sink, void* context) {
  if (sink == nullptr) return false;
  std::lock_guard<std::mutex> guard(g_registration_mutex);
  if (g_sink.load(std::memory_order_acquire) != nullptr) return false;
  g_context.store(context, std::memory_order_relaxed);
  g_sink.store(sink, std::memory_order_release);
  return true;
}

bool ClearLimerCongestionSignalSink(
    LimerCongestionSignalSink sink, void* context) {
  std::lock_guard<std::mutex> guard(g_registration_mutex);
  if (sink == nullptr || g_sink.load(std::memory_order_acquire) != sink ||
      g_context.load(std::memory_order_acquire) != context) return false;
  g_sink.store(nullptr, std::memory_order_release);
  g_context.store(nullptr, std::memory_order_release);
  return true;
}

bool HasLimerCongestionSignalSink() {
  return g_sink.load(std::memory_order_acquire) != nullptr;
}

void EmitLimerCongestionSignal(const LimerCongestionSignalEvent& event) {
  LimerCongestionSignalSink sink = g_sink.load(std::memory_order_acquire);
  if (sink == nullptr) return;
  sink(event, g_context.load(std::memory_order_acquire));
}
}  // namespace ns3
