#pragma once
namespace limer { namespace engine {
static std::vector<std::array<unsigned,3>> Edges(const Route& r){
 if(!r.relay)return {{r.src,r.dst,r.rail+2}};
 return {{r.src,r.hs,1},{r.hs,r.hd,r.rail+2},{r.hd,r.dst,1}};
}

static bool Capacity(const Route& r){
 for(auto e:Edges(r))if(tx[e[0]][e[2]]>=4||rx[e[1]][e[2]]>=4)return false;
 return !r.relay||(buffers[r.hs]<4&&buffers[r.hd]<4);
}

static void Reserve(Route& r,bool add){
 int delta=add?1:-1;
 for(auto e:Edges(r)){
   if(!add&&(!tx[e[0]][e[2]]||!rx[e[1]][e[2]]))throw std::logic_error("credit underflow");
   tx[e[0]][e[2]]+=delta;rx[e[1]][e[2]]+=delta;
 }
 if(r.relay){buffers[r.hs]+=delta;buffers[r.hd]+=delta;}
 r.reserved=add;
 peers<<PeerNow()<<','<<(add?"RESERVE":"RELEASE")<<','<<r.id<<','<<r.chunk<<','<<r.p<<','<<r.src<<','<<r.dst<<','<<r.hs<<','<<r.hd<<','<<r.rail<<','<<r.relay<<','<<r.probe<<','<<r.length<<'\n';
}

}}
