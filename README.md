# SoloLedger

**Open-source accounting, invoicing, and tax tools for your single-member consulting LLC.**

A web app, REST API, and CLI — built on [Beancount](https://beancount.github.io/)
(double-entry accounting from plain-text files you own).

**Try it live:** [sololedger.ferrumeng.com](https://sololedger.ferrumeng.com)
— free to start, no credit card, 14-day trial on paid plans.

[![Test](https://github.com/dilljens/sololedger/actions/workflows/test.yml/badge.svg)](https://github.com/dilljens/sololedger/actions/workflows/test.yml)

## What It Does

| Feature | What |
|---|---|
| **Web dashboard** | Cash, P&L, AR, tax deadlines — live from your ledger |
| **Invoicing** | Invoice + PDF + Stripe payment link, AR tracking |
| **Receipt capture** | Receipt PDF/image → OCR → auto-categorize |
| **Bank & expense import** | Bank CSV → auto-categorize → ledger; Plaid bank feeds |
| **Tax estimates** | Federal + state estimate (WY, CA, TX, NY, FL), 1040-ES voucher |
| **Reconciliation** | Bank statement matching (Business plan) |
| **Time tracking** | Toggl/Clockify hours → invoice |
| **Retainers** | Auto-generate recurring invoices |

## Quick Start (cloud)

1. Open [sololedger.ferrumeng.com](https://sololedger.ferrumeng.com)
2. Sign in with Google or email
3. Start entering transactions — a workspace is provisioned for you

## Self-Host / Deploy

SoloLedger runs as a CLI, a single-process API, or a full multi-tenant SaaS.
The web app is a Vue SPA served by the FastAPI backend.

```bash
git clone https://github.com/dilljens/sololedger
cd sololedger
pip install -r requirements.txt

# CLI
python -m app.main status

# API + web app (http://localhost:8100/app/)
uvicorn app.api:app --port 8100
```

Or Docker Compose (production stack with Caddy + TLS in `deploy/`):
```bash
cd deploy && cp .env.example .env && docker compose up -d
```

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   CLI (llc)  │     │  REST API    │     │  Vue web app │
│  Terminal    │     │  FastAPI     │     │  (browser)   │
└──────┬───────┘     └──────┬───────┘     └──────┬───────┘
       │                    │                    │
       └────────────────────┼────────────────────┘
                            ▼
              ┌─────────────────────────┐
              │  Ledger (Beancount)     │
              │  Plain text, git-       │
              │  versioned accounting   │
              └─────────────────────────┘
                            │
         ┌──────────────────┼──────────────────┐
         ▼                  ▼                  ▼
    ┌────────┐       ┌──────────┐       ┌──────────┐
    │ Stripe │       │  Plaid   │       │  Toggl   │
    │Payments│       │Bank Feeds│       │Time Track│
    └────────┘       └──────────┘       └──────────┘
```

## CLI Reference

The `python -m app.main` CLI covers the same features as the web app from the terminal:

```bash
# Dashboard
python -m app.main status

# Create an invoice with Stripe payment link
python -m app.main invoice create \
    --client "Acme Corp" \
    --description "Q3 Consulting" \
    --amount 5000 \
    --payment-link

# Tax estimate (California)
python -m app.main tax estimate --state CA

# Start the API server (serves the web app at /app/)
uvicorn app.api:app --port 8100
```

## State Tax Support

| State | Income Tax | Franchise Tax | Annual Fee |
|---|---|---|---|
| Wyoming (WY) | $0 | $0 | $60 |
| California (CA) | 1-13.3% | $800 + graduated | $20 |
| Texas (TX) | $0 | 0.75% margin >$2.47M | $0 |
| New York (NY) | 4-10.9% (NYC +3.9%) | $0 | $25 |
| Florida (FL) | $0 | $0 | $138.75 |

## Automation

Set up daily/weekly/monthly cron jobs:

```bash
# Daily 9AM — check deadlines, unpaid invoices
0 9 * * * cd /path/to/sololedger && python -m app.main notify check

# Monthly 1st — process retainers
0 10 1 * * cd /path/to/sololedger && python -m app.main retainer process --no-preview

# Weekly Monday — sync bank feed
0 8 * * 1 cd /path/to/sololedger && python -m app.main bank sync --days 14
```

## Hosted SaaS

The hosted version — [sololedger.ferrumeng.com](https://sololedger.ferrumeng.com) —
includes the Vue web app, Google + email auth, Stripe billing, and persistent
per-account workspaces.

### Deploy as a multi-tenant SaaS

SoloLedger is a multi-tenant SaaS: each account gets an isolated workspace
(Beancount ledger + metadata DB), gated by plan and billing status.

1. **Set required env vars** (see `deploy/.env.example`): `STRIPE_SECRET_KEY`,
   `STRIPE_WEBHOOK_SECRET`, `RESEND_API_KEY`, `GOOGLE_CLIENT_ID`, `ADMIN_API_KEY`,
   `APP_URL`.
2. **Register the Stripe webhook** at `https://<app>/api/v1/stripe-webhook`
   with events: `checkout.session.completed`, `customer.subscription.updated`,
   `customer.subscription.deleted`, `invoice.paid`, `invoice.payment_failed`.
3. **Deploy with persistent data**: `SOLOLEDGER_DATA_DIR` must point at a
   persistent volume — `deploy/docker-compose.yml` mounts `sololedger_data`
   at `/data` so accounts and ledgers survive container rebuilds.

**Tiers** (per market research): Free $0 (10 invoices, 5 receipt scans/mo),
Professional $19/mo (bank sync, receipt OCR, all importers, tax estimates),
Business $45/mo (reconciliation, exports). Paid plans start with a 14-day
trial via Stripe Checkout, which collects the card up front.

**Access gates**: email verification is required before a workspace is
provisioned; a card is required before paid features unlock. Auth is
fail-closed — unauthenticated access needs explicit `SOLOLEDGER_OPEN_MODE=true`
(never set in production).

See `docs/SECURITY.md` for the full security model and `deploy/` for the
production compose stack.

## Built With

- [Beancount](https://beancount.github.io/) — double-entry accounting engine
- [Fava](https://beancount.github.io/fava/) — web dashboard
- [FastAPI](https://fastapi.tiangolo.com/) — REST API
- [Stripe](https://stripe.com/) — payment processing
- [Plaid](https://plaid.com/) — bank feeds
- [Tesseract](https://github.com/tesseract-ocr/tesseract) — receipt OCR
- [Toggl](https://toggl.com/) / [Clockify](https://clockify.me/) — time tracking

## Screenshots

<!-- Add a dashboard screenshot here before posting to HN -->
<!-- ![SoloLedger Dashboard](docs/dashboard.png) -->

## License

MIT — the code is free to use, modify, and distribute.

**SoloLedger™** is a trademark. You may use the code under MIT, but you may not distribute services using the SoloLedger name without permission.
