# SoloLedger

**Open-source accounting, invoicing, and tax tools for your single-member consulting LLC.**

CLI on your laptop, API in the cloud, mobile app in your pocket. Built on [Beancount](https://beancount.github.io/) (double-entry accounting from plain text files).

```bash
# Quick start
pip install -r requirements.txt
python -m app.main status
```

[![Test](https://github.com/dilljens/sololedger/actions/workflows/test.yml/badge.svg)](https://github.com/dilljens/sololedger/actions/workflows/test.yml)

## What It Does

| Command | What |
|---|---|
| `llc status` | Dashboard: cash, P&L, tax deadlines |
| `llc invoice create` | Invoice + PDF + Stripe payment link |
| `llc invoice ar` | Accounts Receivable check |
| `llc expense import` | Bank CSV → auto-categorize → ledger |
| `llc receipt scan` | Receipt PDF/image → OCR → categorize |
| `llc tax estimate` | Federal + state tax estimate (WY, CA, TX, NY, FL) |
| `llc bank sync` | Plaid bank feed → auto-import |
| `llc time fetch` | Toggl/Clockify hours → invoice |
| `llc retainer process` | Auto-generate recurring invoices |
| `llc notify check` | Desktop + email deadline alerts |

## Architecture

```
┌──────────────┐     ┌──────────────┐     ┌──────────────┐
│   CLI (llc)  │     │  REST API    │     │  Mobile/Web  │
│  Terminal    │     │  FastAPI     │     │  Expo (soon) │
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

## Quick Start

### Prerequisites
- Python 3.11+
- Docker + Docker Compose (optional, for Fava web UI)

### Install
```bash
git clone https://github.com/dilljens/sololedger
cd sololedger
pip install -r requirements.txt
```

### Configure
Edit `config.toml` with your business info and state.

### Run
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

# Start the API server (for mobile/web app)
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

## Cloud

Hosted version coming soon at [sololedger.app](https://sololedger.app). Includes API hosting, mobile web app, and automated daily syncs.

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
