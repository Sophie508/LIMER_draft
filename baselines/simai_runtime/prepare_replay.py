"""Prepare a reviewable replay adapter in the copied build backend only."""
import difflib
import hashlib
import json
from pathlib import Path
import shutil

root=Path('/work')
astra=root/'baselines/SimAI-official/astra-sim-alibabacloud'
backend=astra/'extern/network_backend/ns3-interface/simulation'
binary=backend/'build/scratch/ns3.36.1-AstraSimNetwork-debug'
archive=root/'baselines/simai_runtime/native_binary'
archive.mkdir(exist_ok=False)
shutil.copy2(binary,archive/binary.name)
(archive/'sha256.json').write_text(json.dumps({binary.name:hashlib.sha256(binary.read_bytes()).hexdigest()},indent=2)+'\n')
header=backend/'src/applications/astra-sim/system/RecvPacketEventHadndlerData.hh'
original=header.read_text()
anchor='  RecvPacketEventHadndlerData(\n'
assert original.count(anchor)==1
addition='''  // Direct-network callback data; no BaseStream or Sys clock is required.
  RecvPacketEventHadndlerData(EventType event, AstraSim::ncclFlowTag tag)
      : BasicEventHandlerData(nullptr, event), owner(nullptr), vnet(0),
        stream_num(0), message_end(true), ready_time(0), flow_id(-1),
        channel_id(tag.channel_id), child_flow_id(-1), flowTag(tag) {}
'''
updated=original.replace(anchor,addition+anchor)
header.write_text(updated)
diff=''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),
             fromfile='a/astra-sim/system/RecvPacketEventHadndlerData.hh',
             tofile='b/astra-sim/system/RecvPacketEventHadndlerData.hh'))
source=astra/'astra-sim/network_frontend/ns3/entry.h'
original=source.read_text()
assert original.count('AstraSim::Sys::boostedTick()')==4
updated=original.replace('AstraSim::Sys::boostedTick()', 'Simulator::Now().GetNanoSeconds()')
(backend/'scratch/replay_entry.h').write_text(updated)
diff+=''.join(difflib.unified_diff(original.splitlines(True),updated.splitlines(True),
              fromfile='a/entry.h',tofile='b/replay_entry.h'))
(root/'baselines/simai_runtime/replay_adapter.diff').write_text(diff)
shutil.copy2(root/'baselines/simai_runtime/LimerDagReplay.cc',backend/'scratch/LimerDagReplay.cc')
print('Native baseline binary archived; replay adapter prepared in copied backend')
