#!/usr/bin/env bash
# SoloLedger pre-deploy health check.
# Run BEFORE deploying to catch common issues.
# Usage: bash bin/preflight.sh

set -uo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"

PYTHON="${PROJECT_ROOT}/.venv/bin/python3"
if [ ! -f "$PYTHON" ]; then PYTHON="python3"; fi

# The VPS runs deps inside the Docker image — there is no host venv.
# When .venv is absent, skip the Python import/pytest checks (they'd fail
# on system python) and rely on the docker build + health-check gate instead.
HAS_VENV=0
if [ -x "${PROJECT_ROOT}/.venv/bin/python3" ]; then HAS_VENV=1; fi

PASS=0
FAIL=0
ERRORS=""

check() {
  local name="$1" result="$2" detail="${3:-}"
  if [ "$result" = "pass" ]; then
    echo "  ✅ $name"
    PASS=$((PASS + 1))
  else
    echo "  ❌ $name — $detail"
    FAIL=$((FAIL + 1))
    ERRORS="$ERRORS  - $name: $detail\n"
  fi
}

echo "=== SoloLedger Preflight Check ==="
echo ""

# ── 1. Python checks ──────────────────────────────────────
echo "--- Python ---"

if [ "$HAS_VENV" = "0" ]; then
  echo "  ℹ  No .venv on this host (containerized deploy) — skipping Python checks"
  check "Python checks skipped (no venv)" pass
else
  for mod in app.api.deps app.api.auth app.api.onboarding app.api.banking app.api.subscriptions; do
    if "$PYTHON" -c "import $mod" 2>/dev/null; then
      check "$mod imports OK" pass
    else
      err=$("$PYTHON" -c "import $mod" 2>&1 | head -1)
      check "$mod imports" fail "$err"
    fi
  done

  echo ""
  echo "--- API Contract Tests ---"
  if "$PYTHON" -m pytest tests/ -q --tb=short 2>/dev/null; then
    check "pytest suite" pass
  else
    check "pytest suite" fail "Some tests failed — run 'python -m pytest tests/ -v' for details"
  fi
fi

# ── 2. JavaScript static checks ────────────────────────────
echo ""
echo "--- JavaScript ---"

# Check sw.js doesn't cache POST
if [ -f web/sw.js ]; then
  if grep -q "request.method === 'GET'" web/sw.js; then
    check "sw.js: only caches GET (not POST)" pass
  else
    check "sw.js: only caches GET" fail "Will crash on POST API calls"
  fi
fi

# Check GSI double-init guard
if [ -f web/js/pages/auth.js ]; then
  if grep -q "_gsiInitialized" web/js/pages/auth.js; then
    check "auth.js: GSI double-init guard" pass
  else
    check "auth.js: GSI double-init guard" fail "Missing — will cause console warning"
  fi
fi

# ── 3. Template data ──────────────────────────────────────
echo ""
echo "--- Templates ---"
if [ -f ledger/transactions.beancount ]; then
  TXN_COUNT=$(grep -c "^202" ledger/transactions.beancount || true)
  check "transactions.beancount ($TXN_COUNT sample txns)" pass
fi
if [ -f ledger/accounts.beancount ]; then
  ACCT_COUNT=$(grep -c "^202" ledger/accounts.beancount || true)
  check "accounts.beancount" pass
fi
if [ -f Dockerfile.api ]; then
  if grep -q "COPY ledger/ ledger/" Dockerfile.api; then
    check "Dockerfile includes ledger template" pass
  else
    check "Dockerfile includes ledger template" fail "Missing — template won'\''t be in image"
  fi
fi

# ── 4. Docker build (optional) ────────────────────────────
echo ""
echo "--- Docker ---"
if [ "$HAS_VENV" = "0" ]; then
  echo "  ℹ  Containerized host — docker build is gated by 'docker compose up -d --build' + health check"
elif command -v docker &>/dev/null; then
  if [ -f Dockerfile.api ]; then
    # Quick syntax check — build won't actually run
    docker build -f Dockerfile.api -t sololedger-check --quiet . 2>/dev/null && \
      check "docker build (syntax + deps)" pass && \
      docker rmi sololedger-check --quiet 2>/dev/null || \
      check "docker build" fail "Build failed — run 'docker build -f Dockerfile.api .' for details"
  fi
else
  echo "  ℹ  docker not available — skipping build check"
fi

# ── Summary ────────────────────────────────────────────────
echo ""
echo "=== Results: $PASS pass, $FAIL fail ==="
if [ "$FAIL" -gt 0 ]; then
  echo ""
  echo -e "$ERRORS"
  echo "Fix the failures above, then re-run: bash bin/preflight.sh"
  exit 1
fi
echo "  Ready to deploy."
exit 0
