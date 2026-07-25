# SoloLedger Deployment Guide

## Quick Deploy Options

| Platform | How | Time |
|----------|-----|------|
| **VPS (Ubuntu)** | `curl -fsSL https://sololedger.ferrumeng.com/deploy.sh \| bash` | 5 min |
| **Docker compose** | `docker compose up -d` | 2 min |
| **Fly.io** | `fly launch --copy-config --no-deploy && fly deploy` | 5 min |
| **Railway** | Fork repo → Connect → Deploy | 2 min |
| **Local dev** | `pip install -r requirements.txt && uvicorn app.api:app` | 1 min |

---

## 1. VPS / Bare Metal (Ubuntu)

```bash
curl -fsSL https://sololedger.ferrumeng.com/deploy.sh | bash
```

This installs Python, clones the repo, creates a systemd service, and starts the API on port 8100.

**Manual install:**
```bash
git clone https://github.com/dilljens/sololedger.git
cd sololedger
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.api:app --host 0.0.0.0 --port 8100
```

Open `http://your-server:8100/app/` in your browser.

---

## 2. Docker Compose

```bash
git clone https://github.com/dilljens/sololedger.git
cd sololedger
docker compose up -d
```

This starts:
- `sololedger-api` — FastAPI + SPA on port 8100
- `fava` — Beancount web UI on port 5000

Open `http://localhost:8100/app/`.

**Production stack** (with Caddy reverse proxy + auto TLS):
```bash
cd deploy
cp .env.example .env
# Edit .env with your secrets
docker compose -f docker-compose.yml up -d
```

---

## 3. Fly.io

```bash
# Install flyctl first: https://fly.io/docs/hands-on/install-flyctl/
fly launch --copy-config --no-deploy
# Set any environment variables needed
fly secrets set STRIPE_SECRET_KEY=sk_live_...
fly secrets set GOOGLE_CLIENT_ID=xxx.apps.googleusercontent.com
# Deploy
fly deploy
```

The included `fly.toml` handles the rest. Opens on `https://your-app.fly.dev/app/`.

---

## 4. Railway

[![Deploy on Railway](https://railway.app/button.svg)](https://railway.app/template/sololedger)

1. Fork the repo at https://github.com/dilljens/sololedger
2. Create a new Railway project → Deploy from GitHub repo
3. Railway auto-detects the Dockerfile
4. Add env vars as needed:
   - `GOOGLE_CLIENT_ID`
   - `STRIPE_SECRET_KEY`
   - `API_KEYS`

---

## 5. Environment Variables

| Variable | Required | Description |
|----------|----------|-------------|
| `API_PORT` | No | Port (default: 8100) |
| `API_CONFIG` | No | Path to config.toml (auto-detected) |
| `API_KEYS` | No | Comma-separated API keys for auth |
| `GOOGLE_CLIENT_ID` | No | Google OAuth client ID |
| `STRIPE_SECRET_KEY` | No | Stripe secret key for payment links |
| `PLAID_CLIENT_ID` | No | Plaid client ID for bank feeds |
| `PLAID_SECRET` | No | Plaid secret |
| `PLAID_ACCESS_TOKEN` | No | Plaid access token |
| `TOGGL_API_TOKEN` | No | Toggl API token for time tracking |

---

## 6. Configuration

Edit `config.toml` to set your business details:

```toml
[business]
name = "Your LLC"
owner = "Your Name"
state = "WY"  # Two-letter state code

[entity]
entity_type = "smllc"  # or "scorp" for S-Corp

[ledger]
path = "ledger/main.beancount"
```

---

## 7. First Run

On first load, the web app shows a setup wizard. Fill in your business details and click "Complete Setup."

To load demo data:
```bash
llc demo
```

Or just start adding transactions through the web UI.

---

## 8. Updating

```bash
# Docker
git pull && docker compose up -d --build

# VPS
./deploy/deploy.sh  # or systemctl restart sololedger

# Fly.io
fly deploy

# Railway
git push  # auto-deploys
```
