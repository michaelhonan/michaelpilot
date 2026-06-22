#!/usr/bin/env bash
# dev-offline branch only: defense-in-depth outbound block for comma/sunnylink endpoints.
#
# The primary "no phoning home" guarantee is that the networking daemons are not launched
# (see system/manager/process_config.py). This script is belt-and-suspenders: it drops any
# outbound traffic to the comma/sunnylink hosts via a dedicated, idempotent iptables chain,
# and mirrors the block into /etc/hosts when that file is writable.
#
# It is intentionally fail-safe: any error is logged and ignored so it can never block boot.
# Reversible: `./block_comma.sh off` removes everything it added.

set -u

CHAIN="OFFLINE_DEV_BLOCK"
HOSTS_MARK="# offline-dev-block"
DOMAINS=(
  "comma.ai"
  "www.comma.ai"
  "api.commadotai.com"
  "athena.comma.ai"
  "connect.comma.ai"
  "api.sunnypilot.ai"
  "stg.api.sunnypilot.ai"
  "athena.sunnylink.ai"
)

log() { echo "[offline-dev block_comma] $*"; }

remove_rules() {
  # iptables chain
  if command -v iptables >/dev/null 2>&1; then
    iptables -D OUTPUT -j "$CHAIN" 2>/dev/null
    iptables -F "$CHAIN" 2>/dev/null
    iptables -X "$CHAIN" 2>/dev/null
  fi
  # /etc/hosts entries
  if [ -w /etc/hosts ]; then
    sed -i "/$HOSTS_MARK/d" /etc/hosts 2>/dev/null
  fi
}

add_rules() {
  # --- iptables layer (block by resolved IP) ---
  if command -v iptables >/dev/null 2>&1; then
    iptables -N "$CHAIN" 2>/dev/null
    iptables -F "$CHAIN" 2>/dev/null
    for d in "${DOMAINS[@]}"; do
      # resolve A records; getent works without extra tooling on AGNOS
      for ip in $(getent ahostsv4 "$d" 2>/dev/null | awk '{print $1}' | sort -u); do
        iptables -A "$CHAIN" -d "$ip" -j REJECT 2>/dev/null \
          && log "blocking $d -> $ip"
      done
    done
    # hook the chain into OUTPUT once
    iptables -C OUTPUT -j "$CHAIN" 2>/dev/null || iptables -I OUTPUT 1 -j "$CHAIN" 2>/dev/null
  else
    log "iptables not available, relying on /etc/hosts + daemon gating"
  fi

  # --- /etc/hosts layer (defense-in-depth, only if writable) ---
  if [ -w /etc/hosts ]; then
    for d in "${DOMAINS[@]}"; do
      grep -q " $d $HOSTS_MARK" /etc/hosts 2>/dev/null || \
        echo "0.0.0.0 $d $HOSTS_MARK" >> /etc/hosts
    done
  else
    log "/etc/hosts not writable, skipping hosts layer"
  fi
}

case "${1:-on}" in
  off) remove_rules; log "removed" ;;
  *)   remove_rules; add_rules; log "applied" ;;
esac

exit 0
