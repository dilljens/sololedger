#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────────────────────────────────
# SoloLedger — One-command deploy script
# ──────────────────────────────────────────────────────────────────────────
# Usage:
#   curl -fsSL https://sololedger.ferrumeng.com/deploy.sh | bash
#   curl -fsSL https://sololedger.ferrumeng.com/deploy.sh | bash -s -- --port 8100
# ──────────────────────────────────────────────────────────────────────────

REPO="https://github.com/dilljens/sololedger.git"
INSTALL_DIR="${HOME}/sololedger"
API_PORT="${1:-8100}"
UBUNTU=$(grep -c ubuntu /etc/os-release 2>/dev/null || echo "0")

echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║       SoloLedger Installer           ║"
echo "  ╚══════════════════════════════════════╝"
echo ""

# ── 1. Check prerequisites ─────────────────────────────────────────
echo "  Checking prerequisites..."

if ! command -v python3 &>/dev/null; then
    echo "  Installing Python 3..."
    if [ "$UBUNTU" -gt 0 ]; then
        sudo apt-get update -qq && sudo apt-get install -y -qq python3 python3-pip python3-venv git curl
    else
        echo "  ⚠ Please install Python 3.11+ manually, then re-run this script."
        exit 1
    fi
fi

if ! command -v git &>/dev/null; then
    echo "  Installing git..."
    sudo apt-get install -y -qq git
fi

PYTHON_VERSION=$(python3 --version 2>&1 | grep -oP '\d+\.\d+' | head -1)
echo "  ✓ Python ${PYTHON_VERSION} found"
echo "  ✓ git found"

# ── 2. Clone repo ─────────────────────────────────────────────────
if [ -d "$INSTALL_DIR" ]; then
    echo "  SoloLedger already installed at ${INSTALL_DIR}"
    echo "  Pulling latest..."
    cd "$INSTALL_DIR" && git pull
else
    echo "  Cloning SoloLedger..."
    git clone "$REPO" "$INSTALL_DIR"
fi

cd "$INSTALL_DIR"

# ── 3. Create virtual env + install deps ───────────────────────────
echo "  Installing Python dependencies..."
python3 -m venv .venv 2>/dev/null || true
source .venv/bin/activate 2>/dev/null || source "${INSTALL_DIR}/.venv/bin/activate"
pip install -q -r requirements.txt 2>/dev/null || pip install -r requirements.txt

# ── 4. Run init if config doesn't exist ────────────────────────────
if [ ! -f config.toml ] || grep -q "Your LLC Name Here" config.toml 2>/dev/null; then
    echo ""
    echo "  ── Setup ───────────────────────────────"
    echo "  Let's configure your business:"
    python3 -m app.main init
fi

# ── 5. Run doctor ─────────────────────────────────────────────────
echo ""
echo "  ── Diagnostics ────────────────────────────"
python3 -m app.main doctor

# ── 6. Create systemd service ─────────────────────────────────────
if command -v systemctl &>/dev/null; then
    SERVICE_FILE="/etc/systemd/system/sololedger.service"
    if [ ! -f "$SERVICE_FILE" ]; then
        echo "  Creating systemd service..."
        sudo tee "$SERVICE_FILE" > /dev/null <<SVC
[Unit]
Description=SoloLedger API Server
After=network.target

[Service]
Type=simple
User=$USER
WorkingDirectory=${INSTALL_DIR}
ExecStart=${INSTALL_DIR}/.venv/bin/uvicorn app.api:app --host 0.0.0.0 --port ${API_PORT}
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
SVC
        sudo systemctl daemon-reload
        sudo systemctl enable sololedger
        sudo systemctl start sololedger
        echo "  ✓ systemd service created and started"
    else
        echo "  ✓ systemd service already exists"
        sudo systemctl restart sololedger
    fi
fi

# ── 7. Print summary ──────────────────────────────────────────────
HOSTNAME=$(hostname -I 2>/dev/null | awk '{print $1}' || echo "localhost")
echo ""
echo "  ╔══════════════════════════════════════╗"
echo "  ║        Installation Complete          ║"
echo "  ╚══════════════════════════════════════╝"
echo ""
echo "  Web app:  http://${HOSTNAME}:${API_PORT}/app/"
echo "  API:      http://${HOSTNAME}:${API_PORT}/api/v1/"
echo "  Docs:     http://${HOSTNAME}:${API_PORT}/docs"
echo ""
echo "  Run 'llc doctor' to check all integrations."
echo "  Run 'llc demo' to load sample data."
echo "  Run 'llc backup' to set up git backups."
echo ""
echo "  Next: Set STRIPE_SECRET_KEY for payment links"
echo "        Set PLAID_* for bank feeds"
echo "        Set TOGGL_API_TOKEN for time tracking"
echo ""
