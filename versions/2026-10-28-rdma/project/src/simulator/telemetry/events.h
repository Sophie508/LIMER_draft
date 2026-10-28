#pragma once
namespace limer { namespace engine {
static void PeerEvent(const char* name,const PeerChunk& c,uint64_t route){
 events<<PeerNow()<<','<<name<<','<<c.id<<','<<c.p<<','<<c.src<<','<<c.dst<<','<<c.offset<<','<<ChunkBytes<<','<<c.acked<<','<<c.epoch<<','<<c.lane<<','<<route<<'\n';
}

static uint64_t Message(const char* name,unsigned src,uint64_t route){
 auto at=control.send(PeerNow(),96);controls<<PeerNow()<<','<<at<<','<<name<<','<<src<<','<<phase<<','<<route<<",96\n";return at;
}

}}
