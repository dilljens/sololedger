#!/usr/bin/env bash
# Ferrum Engineering — weekly VPS cleanup
# Runs via cron every Sunday at 3 AM
set -euo pipefail

LOG="/var/log/ferrum-cleanup.log"

log() {
  echo "[$(date -Iseconds)] $*" | tee -a "$LOG"
}

log "═══ Weekly cleanup started ═══"

# ── 1. GitHub Actions runner build artifacts ────────────────────────
# These are checked-out repos + CI outputs. Runners re-clone on demand.
WORK_DIRS=(
  "/opt/actions-runner/_work"
  "/opt/actions-runner-imposter/_work"
)
for dir in "${WORK_DIRS[@]}"; do
  if [ -d "$dir" ] && [ "$(ls -A "$dir" 2>/dev/null)" ]; then
    size_before=$(du -sh "$dir" 2>/dev/null | cut -f1)
    rm -rf "$dir"/* 2>/dev/null
    log "Cleaned GH runner work dir: $dir (was $size_before)"
  fi
done

# ── 2. Docker — prune unused images, cache, stopped containers ─────
# Safe: only removes things no running container references
log "Running docker system prune..."
docker system prune -af --volumes=false 2>&1 | tee -a "$LOG"

# ── 3. Systemd journal — keep last 7 days ──────────────────────────
log "Vacuuming journal logs (keep 7d)..."
journalctl --vacuum-time=7d 2>&1 | tee -a "$LOG"

# ── 4. APT cache ────────────────────────────────────────────────────
log "Cleaning APT cache..."
apt-get clean -y 2>&1 | tee -a "$LOG"

# ── 5. Old rotated log files ────────────────────────────────────────
# Remove .gz logs older than 30 days (rotated logs already compressed)
log "Removing rotated logs older than 30 days..."
find /var/log -name '*.gz' -type f -mtime +30 -delete 2>/dev/null || true

# ── Summary ────────────────────────────────────────────────────────
MEM=$(free -h | awk '/Mem:/ {print $3"/"$2}')
DISK=$(df -h / | awk 'NR==2 {print $3"/"$2" ("$5")"}')
log "Done — mem: $MEM, disk: $DISK"
log "═══ Cleanup complete ═══"
echo "" >> "$LOG"
