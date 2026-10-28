/* -*- Mode:C++; c-file-style:"gnu"; indent-tabs-mode:nil; -*- */
#ifndef MTP_INTERFACE_H
#define MTP_INTERFACE_H

#include "logical-process.h"
#include "ns3/atomic-counter.h"
#include "ns3/global-value.h"
#include "ns3/nstime.h"
#include "ns3/simulator.h"

#include <map>
#include <pthread.h>
#include <type_traits>
#include <utility>

namespace ns3 {

class MtpInterface
{
public:
  class CriticalSection
  {
  public:
    inline CriticalSection ()
    {
      while (g_inCriticalSection.exchange (true, std::memory_order_acquire))
        ;
    }

    inline ~CriticalSection ()
    {
      g_inCriticalSection.store (false, std::memory_order_release);
    }
  };

  class explicitCriticalSection
  {
  public:
    inline explicitCriticalSection ()
    {
      while (g_e_inCriticalSection.exchange (true, std::memory_order_acquire))
        ;
    }

    inline void ExitSection() 
    {
      g_e_inCriticalSection.store (false, std::memory_order_release);
    }

    inline ~explicitCriticalSection ()
    {
      // g_e_inCriticalSection.store (false, std::memory_order_release);
    }
  };

  static void Enable (); // auto topology partition
  static void Enable (const uint32_t threadCount); // auto partition, specify thread count
  static void Enable (const uint32_t threadCount, const uint32_t systemCount); // manual partition
  static void EnableNew (const uint32_t newSystemCount); // add LPs for dynamic added node
  static void Disable ();
  static void Run ();
  static void RunBefore ();
  static void ProcessOneRound ();
  static void CalculateSmallestTime ();
  static void RunAfter ();
  static bool isEnabled ();
  static bool isPartitioned ();
  static void CalculateLookAhead ();

  // get current thread's executing logical process
  inline static LogicalProcess *
  GetSystem ()
  {
    return static_cast<LogicalProcess *> (pthread_getspecific (g_key));
  }

  inline static LogicalProcess *
  GetSystem (const uint32_t systemId)
  {
    return &g_systems[systemId];
  }

  // set current thread's executing logical process
  inline static void
  SetSystem (const uint32_t systemId)
  {
    pthread_setspecific (g_key, &g_systems[systemId]);
  }

  inline static uint32_t
  GetSize ()
  {
    return g_systemCount + 1;
  }

  inline static uint32_t
  GetRound ()
  {
    return g_round;
  }

  inline static Time
  GetSmallestTime ()
  {
    return g_smallestTime;
  }

  inline static void
  SetSmallestTime (const Time smallestTime)
  {
    g_smallestTime = smallestTime;
  }

  inline static Time
  GetNextPublicTime ()
  {
    return g_nextPublicTime;
  }

  inline static Time
  GetNextFaultBarrierTime ()
  {
    return TimeStep (g_nextFaultBarrierTimeStep.load (std::memory_order_acquire));
  }

  inline static bool
  HasPendingFaultBarrierEvents ()
  {
    return !g_faultBarrierEvents.empty ();
  }

  inline static bool
  isFinished ()
  {
    return g_globalFinished;
  }

  template <typename FUNC,
            typename std::enable_if<!std::is_convertible<FUNC, Ptr<EventImpl>>::value, int>::type,
            typename std::enable_if<
                !std::is_function<typename std::remove_pointer<FUNC>::type>::value, int>::type,
            typename... Ts>
  inline static void
  ScheduleGlobal (FUNC f, Ts &&...args)
  {
    CriticalSection cs;
    g_systems[0].ScheduleAt (Simulator::NO_CONTEXT, Min (g_smallestTime, g_nextPublicTime),
                             MakeEvent (f, std::forward<Ts> (args)...));
  }

  template <typename... Us, typename... Ts>
  inline static void
  ScheduleGlobal (void (*f) (Us...), Ts &&...args)
  {
    CriticalSection cs;
    g_systems[0].ScheduleAt (Simulator::NO_CONTEXT, Min (g_smallestTime, g_nextPublicTime),
                             MakeEvent (f, std::forward<Ts> (args)...));
  }

  // LIMER fault injection is the sole intended caller of this API.  The
  // callback executes on the public LP at its requested time, but in a
  // dedicated pre-private phase so a carrier transition at T precedes node
  // events at T.  Events scheduled normally from the callback remain ordinary
  // public events and retain the established private-before-public ordering.
  // Hybrid runs require the same pre-registered fault timeline on every rank;
  // this process-local queue is not a general cross-rank scheduling API.
  template <typename FUNC,
            typename std::enable_if<!std::is_convertible<FUNC, Ptr<EventImpl>>::value, int>::type =
                0,
            typename std::enable_if<
                !std::is_function<typename std::remove_pointer<FUNC>::type>::value, int>::type = 0,
            typename... Ts>
  inline static void
  ScheduleFaultBarrier (Time const &delay, FUNC f, Ts &&...args)
  {
    ScheduleFaultBarrierEvent (delay, MakeEvent (f, std::forward<Ts> (args)...));
  }

  template <typename... Us, typename... Ts>
  inline static void
  ScheduleFaultBarrier (Time const &delay, void (*f) (Us...), Ts &&...args)
  {
    ScheduleFaultBarrierEvent (delay, MakeEvent (f, std::forward<Ts> (args)...));
  }

  // Simulator implementations call this on Stop()/Destroy().  Auto-
  // partitioning deliberately does not clear the queue, so events registered
  // before Partition() survive the replacement of the public LogicalProcess.
  static void ClearFaultBarrierEvents ();

private:
  static void *ThreadFunc (void *arg);
  static void ProcessPrivateStage (bool respectFaultBarrier);
  static void ProcessFaultBarrierEvents ();
  static void ScheduleFaultBarrierEvent (Time const &delay, EventImpl *event);
  static void RefreshNextFaultBarrierTime ();

  // determine logical process priority
  static bool SortByExecutionTime (const uint32_t &i, const uint32_t &j);
  static bool SortByEventCount (const uint32_t &i, const uint32_t &j);
  static bool SortByPendingEventCount (const uint32_t &i, const uint32_t &j);
  static bool SortBySimulationTime (const uint32_t &i, const uint32_t &j);
  static bool (*g_sortFunc) (const uint32_t &, const uint32_t &);
  static GlobalValue g_sortMethod;
  static GlobalValue g_sortPeriod;
  static uint32_t g_period;

  static pthread_t *g_threads;
  static LogicalProcess *g_systems;
  static uint32_t g_threadCount;
  static uint32_t g_systemCount;

  static uint32_t *g_sortedSystemIndices;
  static std::atomic<uint32_t> g_systemIndex;
  static std::atomic<uint32_t> g_finishedSystemCount;

  static uint32_t g_round;
  static Time g_smallestTime;
  static Time g_nextPublicTime;
  // Stop() may be invoked by a private worker while the other workers are
  // reading this boundary.  Keep the published timestamp atomic; the event
  // map itself remains owned by the public/main thread except for Stop's
  // terminal clear.
  static std::atomic<uint64_t> g_nextFaultBarrierTimeStep;
  static bool g_recvMsgStage;
  static bool g_respectFaultBarrier;
  static bool g_globalFinished;
  static bool g_enabled;

  typedef std::pair<uint64_t, uint64_t> FaultBarrierKey;
  static std::map<FaultBarrierKey, EventImpl *> g_faultBarrierEvents;
  static uint64_t g_faultBarrierSequence;

  static pthread_key_t g_key;
  static std::atomic<bool> g_inCriticalSection;

  static std::atomic<bool> g_e_inCriticalSection;
};

} // namespace ns3

#endif /* MTP_INTERFACE_H */
