#include "limer-route-choice.h"

#include <atomic>
#include <mutex>

namespace ns3 {
namespace {

std::atomic<LimerRouteChoiceSink> g_limerRouteChoiceSink(nullptr);
std::atomic<void*> g_limerRouteChoiceContext(nullptr);
std::atomic<uint64_t> g_limerRouteChoiceMaxEvents(0);
std::atomic<uint64_t> g_limerRouteChoiceSeen(0);
std::atomic<uint64_t> g_limerRouteChoiceRecorded(0);
std::atomic<uint64_t> g_limerRouteChoiceDeduplicated(0);
std::atomic<uint64_t> g_limerRouteChoiceOverflow(0);
std::mutex g_limerRouteChoiceRegistrationMutex;

}  // namespace

bool RegisterLimerRouteChoiceSink(
    LimerRouteChoiceSink sink, void* context, uint64_t max_events) {
  if (sink == nullptr || max_events == 0 || max_events > 10000000ULL) {
    return false;
  }
  std::lock_guard<std::mutex> guard(g_limerRouteChoiceRegistrationMutex);
  if (g_limerRouteChoiceSink.load(std::memory_order_acquire) != nullptr) {
    return false;
  }
  g_limerRouteChoiceMaxEvents.store(max_events, std::memory_order_relaxed);
  g_limerRouteChoiceSeen.store(0, std::memory_order_relaxed);
  g_limerRouteChoiceRecorded.store(0, std::memory_order_relaxed);
  g_limerRouteChoiceDeduplicated.store(0, std::memory_order_relaxed);
  g_limerRouteChoiceOverflow.store(0, std::memory_order_relaxed);
  g_limerRouteChoiceContext.store(context, std::memory_order_relaxed);
  g_limerRouteChoiceSink.store(sink, std::memory_order_release);
  return true;
}

bool ClearLimerRouteChoiceSink(LimerRouteChoiceSink sink, void* context) {
  std::lock_guard<std::mutex> guard(g_limerRouteChoiceRegistrationMutex);
  if (sink == nullptr ||
      g_limerRouteChoiceSink.load(std::memory_order_acquire) != sink ||
      g_limerRouteChoiceContext.load(std::memory_order_acquire) != context) {
    return false;
  }
  // Simulator workers are quiescent before the frontend clears the sink.
  // Publish the null sink first so no subsequent emitter can consume the
  // context that is about to be cleared.
  g_limerRouteChoiceSink.store(nullptr, std::memory_order_release);
  g_limerRouteChoiceContext.store(nullptr, std::memory_order_release);
  return true;
}

bool HasLimerRouteChoiceSink() {
  return g_limerRouteChoiceSink.load(std::memory_order_acquire) != nullptr;
}

void EmitLimerRouteChoice(const LimerRouteChoiceEvent& event) {
  LimerRouteChoiceSink sink =
      g_limerRouteChoiceSink.load(std::memory_order_acquire);
  if (sink == nullptr) return;
  void* context = g_limerRouteChoiceContext.load(std::memory_order_acquire);
  sink(event, context);
}

LimerRouteChoiceCounters GetLimerRouteChoiceCounters() {
  return LimerRouteChoiceCounters{
      g_limerRouteChoiceMaxEvents.load(std::memory_order_relaxed),
      g_limerRouteChoiceSeen.load(std::memory_order_relaxed),
      g_limerRouteChoiceRecorded.load(std::memory_order_relaxed),
      g_limerRouteChoiceDeduplicated.load(std::memory_order_relaxed),
      g_limerRouteChoiceOverflow.load(std::memory_order_relaxed)};
}

bool EmitLimerRouteChoiceOnce(
    std::set<LimerRouteChoiceKey>* observed,
    const LimerRouteChoiceEvent& event) {
  if (observed == nullptr || !HasLimerRouteChoiceSink()) return false;
  g_limerRouteChoiceSeen.fetch_add(1, std::memory_order_relaxed);
  const LimerRouteChoiceKey key = LimerRouteChoiceKey::From(event);
  if (observed->find(key) != observed->end()) {
    g_limerRouteChoiceDeduplicated.fetch_add(1, std::memory_order_relaxed);
    return false;
  }

  uint64_t recorded =
      g_limerRouteChoiceRecorded.load(std::memory_order_relaxed);
  const uint64_t cap =
      g_limerRouteChoiceMaxEvents.load(std::memory_order_relaxed);
  while (recorded < cap &&
         !g_limerRouteChoiceRecorded.compare_exchange_weak(
             recorded, recorded + 1, std::memory_order_relaxed,
             std::memory_order_relaxed)) {
  }
  if (recorded >= cap) {
    g_limerRouteChoiceOverflow.fetch_add(1, std::memory_order_relaxed);
    LimerRouteChoiceEvent overflow = event;
    overflow.evidence_overflow = true;
    EmitLimerRouteChoice(overflow);
    return false;
  }

  observed->insert(key);
  EmitLimerRouteChoice(event);
  return true;
}

}  // namespace ns3
