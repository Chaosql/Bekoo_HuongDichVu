#!/usr/bin/env bash
# This network is deliberately external: compose down must not remove MySQL's bind IP.
set -Eeuo pipefail
mode="${1:---create}"
[[ "$mode" == --create || "$mode" == --check ]] || exit 2
if ! docker network inspect bekoo-backend >/dev/null 2>&1; then
  if [[ "$mode" == --check ]]; then
    echo "Missing bekoo-backend network; run deploy/aws/server/setup-network.sh on the host first" >&2
    exit 1
  fi
  docker network create --driver bridge --subnet 172.30.83.0/24 \
    --gateway 172.30.83.1 bekoo-backend >/dev/null
fi
docker network inspect bekoo-backend | python3 -c '
import json, sys
network = json.load(sys.stdin)[0]
configs = network.get("IPAM", {}).get("Config", [])
if (network.get("Driver") != "bridge" or len(configs) != 1
        or configs[0].get("Subnet") != "172.30.83.0/24"
        or configs[0].get("Gateway") != "172.30.83.1"):
    raise SystemExit("bekoo-backend has unexpected IPAM; do not delete an in-use network")
'
