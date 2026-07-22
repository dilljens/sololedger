#!/usr/bin/env bash
# Ferrum Engineering — VPS health check
# Runs every 5 min via cron to alert on resource pressure
set -euo pipefail

EMAIL="dillon@ferrumengineeringllc.com"
LOG="/var/log/ferrum-health.log"
THRESHOLD_MEM_PCT=90
THRESHOLD_DISK_PCT=85
THRESHOLD_SWAP_PCT=80

MEM_PCT=$(free | awk '/Mem:/ {printf "%.0f", $3/$2 * 100}')
DISK_PCT=$(df / | awk 'NR==2 {print $5}' | tr -d '%')
SWAP_PCT=$(free | awk '/Swap:/ {if ($2 > 0) printf "%.0f", $3/$2 * 100; else print "0"}')

ALERTS=""
[ "$MEM_PCT" -ge "$THRESHOLD_MEM_PCT" ] && ALERTS="${ALERTS}MEMORY: ${MEM_PCT}% used\n"
[ "$DISK_PCT" -ge "$THRESHOLD_DISK_PCT" ] && ALERTS="${ALERTS}DISK: ${DISK_PCT}% used\n"
[ "$SWAP_PCT" -ge "$THRESHOLD_SWAP_PCT" ] && ALERTS="${ALERTS}SWAP: ${SWAP_PCT}% used\n"

if [ -n "$ALERTS" ]; then
  echo "[$(date -Iseconds)] ⚠  ALERT:\n$ALERTS" >> "$LOG"
  echo -e "Ferrum Engineering VPS Alert\n\n$ALERTS\n\nHost: $(hostname)\nIP: $(curl -s ifconfig.me 2>/dev/null || echo 'unknown')" \
    | mail -s "⚠ Ferrum VPS Alert — Resource Warning" "$EMAIL" 2>/dev/null || true
else
  echo "[$(date -Iseconds)] OK — mem:${MEM_PCT}% disk:${DISK_PCT}% swap:${SWAP_PCT}%" >> "$LOG"
fi
