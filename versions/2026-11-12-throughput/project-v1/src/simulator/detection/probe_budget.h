// Causal packet-opportunity compensation from the last closed TX window.
#include <cstdint>
#include <stdexcept>
inline uint32_t ProbeBudget(uint64_t previousData,int64_t spanNs,uint32_t targetPps) {
  if(spanNs<=0 || spanNs>10'000'000) throw std::runtime_error("Invalid probe wave span");
  uint64_t target=uint64_t(targetPps)*uint64_t(spanNs)/1'000'000'000;
  uint64_t data=previousData*uint64_t(spanNs)/10'000'000;
  return uint32_t(target>data?target-data:0);
}
