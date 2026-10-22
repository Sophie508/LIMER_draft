#!/bin/bash
set -euo pipefail
root=/work/baselines/SimAI-official
astra="$root/astra-sim-alibabacloud"
backend="$astra/extern/network_backend/ns3-interface"
if [ -e "$backend/simulation/build/scratch/ns3.36.1-AstraSimNetwork-debug" ]; then
    echo "Refusing to overwrite an existing baseline binary" >&2
    exit 2
fi
mkdir -p "$backend" "$root/bin"
cp -a "$root/ns-3-alibabacloud/." "$backend/"
cp "$astra/astra-sim/network_frontend/ns3/AstraSimNetwork.cc" "$backend/simulation/scratch/"
cp "$astra/astra-sim/network_frontend/ns3/"*.h "$backend/simulation/scratch/"
cp -a "$astra/astra-sim" "$backend/simulation/src/applications/"
cd "$backend/simulation"
gcc --version
cmake --version
python3 --version
./ns3 configure -d debug --enable-mtp
./ns3 build -j 8
binary="$backend/simulation/build/scratch/ns3.36.1-AstraSimNetwork-debug"
test -x "$binary"
sha256sum "$binary"
ln -s "$binary" "$root/bin/SimAI_simulator"
