#pragma once
namespace limer { namespace engine {

// Receiver-local delivery samples. Aggregate all QPs on the same physical
// endpoint path so round-robin interleaving is not mistaken for link service.
// No injector state, configured service fraction, or future endpoint is read.
struct ReceiverSpacing {
 int64_t previous=-1;
 bool previousFull=false;
 std::vector<int64_t> gaps;
};
static std::map<unsigned,ReceiverSpacing> receiverSpacing;
static uint64_t spacingEnd=1000000+serviceDetector.config().calibration_ns;

static void ReceiverSpacingAdvance(){
 if(!serviceMode)return;
 const auto& cfg=serviceDetector.config();
 while(PeerNow()>=spacingEnd){
  if(PeerNow()!=spacingEnd)throw std::logic_error("receiver spacing window was not flushed on time");
  for(unsigned s=0;s<16;++s)for(unsigned rail=0;rail<2;++rail){
   unsigned path=Key(s,Dest(s),rail);auto& state=receiverSpacing[path];
   int64_t value=0;auto count=state.gaps.size();
   if(count){
    auto rank=(count*cfg.spacing_quantile_num+cfg.spacing_quantile_den-1)/cfg.spacing_quantile_den-1;
    std::nth_element(state.gaps.begin(),state.gaps.begin()+rank,state.gaps.end());
    value=state.gaps[rank];
   }
   serviceEvents<<PeerNow()<<",SPACING,"<<path<<','<<spacingEnd<<",0,0,"<<value<<','<<count<<'\n';
   serviceDetector.spacing(path,spacingEnd,value,count);
   state.gaps.clear();
  }
  spacingEnd+=cfg.spacing_window_ns;
 }
}

static void ReceiverSpacingObserve(unsigned path,unsigned bytes){
 if(!serviceMode)return;
 unsigned src=path/48,rail=path%3;
 if(src>=16||rail>1||path!=Key(src,Dest(src),rail))return;
 ReceiverSpacingAdvance();
 auto& state=receiverSpacing[path];
 bool full=bytes==serviceDetector.config().spacing_packet_bytes;
 if(full&&state.previousFull&&state.previous>=0&&PeerNow()>uint64_t(state.previous))
  state.gaps.push_back(PeerNow()-state.previous);
 state.previous=PeerNow();state.previousFull=full;
}

static void ReceiverSpacingTick(){
 ReceiverSpacingAdvance();
 if(spacingEnd<horizon)Simulator::Schedule(NanoSeconds(spacingEnd-PeerNow()),&ReceiverSpacingTick);
}

}}
