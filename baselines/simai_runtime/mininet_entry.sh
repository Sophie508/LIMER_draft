#!/bin/bash
set -euo pipefail
/usr/share/openvswitch/scripts/ovs-ctl --system-id=random --no-ovs-vswitchd start
ovs-vswitchd --pidfile --detach --log-file
cd /work
export PYTHONPATH="/work:${PYTHONPATH:-}"
exec "$@"
