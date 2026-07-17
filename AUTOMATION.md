# Automation Setup

Run these from cron to make your LLC operations fully automatic.

## Quick Start: Add to your crontab

```bash
crontab -e
```

Paste the schedule below (adjust paths to your setup):

```cron
# ── LLC Tools Automation ──────────────────────────────────────────
SHELL=/bin/bash
PATH=/usr/local/bin:/usr/bin:/bin
LLC_DIR=/home/dillon/_code/sololedger
LLC="$LLC_DIR/.venv/bin/python -m app.main"
# NOTIFY_SMTP_PASSWORD   # optional: set Gmail app password for email alerts

# Daily: Check deadlines, unpaid invoices, ledger health (9 AM)
0 9 * * * cd $LLC_DIR && $LLC notify check

# Weekly: Time tracking summary for last 7 days (Friday 5 PM)
0 17 * * 5 cd $LLC_DIR && $LLC time fetch --days 7

# Monthly: Process retainer invoices (1st of month, 10 AM)
0 10 1 * * cd $LLC_DIR && $LLC retainer process --no-preview

# Weekly: Sync bank feed from Plaid (Monday 8 AM)
0 8 * * 1 cd $LLC_DIR && $LLC bank sync --days 14

# Monthly: Tax estimate check (15th of month, 10 AM)
0 10 15 * * cd $LLC_DIR && $LLC notify deadlines
```

## What Each Command Does

| Cron Schedule | Command | What It Does |
|---|---|---|
| Daily 9 AM | `llc notify check` | Desktop alert if tax deadlines approaching, invoices overdue, ledger errors |
| Weekly Friday 5 PM | `llc time fetch` | Shows tracked hours from Toggl/Clockify |
| Monthly 1st 10 AM | `llc retainer process --no-preview` | Auto-generates invoices for retainer clients |
| Weekly Monday 8 AM | `llc bank sync --days 14` | Auto-imports bank transactions from Plaid |
| Monthly 15th 10 AM | `llc notify deadlines` | Sends tax deadline reminder |

## Running the API Server (for phone/web app)

```bash
# Start the API server on port 8100
uvicorn app.api:app --host 0.0.0.0 --port 8100

# Or via the alias
python -m app.api

# With Docker
docker compose up api
```

The API serves:
- JSON endpoints for every CLI command at `http://localhost:8100/api/v1/`
- Interactive Swagger docs at `http://localhost:8100/docs`
- OpenAPI schema at `http://localhost:8100/openapi.json`

**Auth:** Set `API_KEYS=key1,key2` env var to require API keys (comma-separated).
If unset, the API runs in open mode (useful behind a VPN).

## API Endpoints at a Glance

| Method | Path | What |
|---|---|---|
| GET | `/api/v1/health` | Health check |
| GET | `/api/v1/status` | Dashboard — cash, P&L, deadlines |
| POST | `/api/v1/invoices` | Create invoice (with optional Stripe payment link) |
| GET | `/api/v1/invoices` | List invoices |
| GET | `/api/v1/invoices/ar` | Accounts Receivable summary |
| POST | `/api/v1/expenses/import` | Import bank CSV |
| POST | `/api/v1/receipts/scan` | Scan a receipt (PDF/image upload) |
| GET | `/api/v1/tax/estimate` | Tax estimate |
| GET | `/api/v1/tax/deadlines` | Upcoming tax deadlines |
| GET | `/api/v1/tax/schedule-c` | Schedule C data |
| POST | `/api/v1/bank/sync` | Sync Plaid transactions |
| GET | `/api/v1/bank/accounts` | Connected bank accounts |
| POST | `/api/v1/time/entries` | Fetch time entries |
| POST | `/api/v1/time/invoice` | Create invoice from time |
| GET | `/api/v1/retainers` | List retainers |
| POST | `/api/v1/retainers` | Add retainer |
| POST | `/api/v1/retainers/process` | Process due retainers |
| POST | `/api/v1/notify/check` | Check notifications |

## Environment Variables to Set

These can go in your crontab, Docker env, or `.env` file:

```bash
# Stripe (for payment links on invoices)
# Set STRIPE_SECRET_KEY from https://dashboard.stripe.com/apikeys

# Plaid (for automated bank feeds)
# Set PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN, PLAID_ENV

# Toggl Track (for time tracking)
# Set TOGGL_API_TOKEN from your Toggl profile

# Clockify (alternative to Toggl)
# Set CLOCKIFY_API_KEY from your Clockify profile

# Email notifications (optional)
# Set NOTIFY_SMTP_PASSWORD (Gmail app password)
```

## Manual Automation Triggers

You can also run these on-demand:

```bash
# Full status check + notifications right now
python -m app.main notify check

# Process retainers (preview first)
python -m app.main retainer process

# Process retainers for real
python -m app.main retainer process --no-preview

# Sync bank feed
python -m app.main bank sync

# Sync bank feed (preview)
python -m app.main bank sync --preview

# Check accounts receivable
python -m app.main invoice ar
```

## Setting Up Email Notifications (Gmail)

1. Generate an App Password at https://myaccount.google.com/apppasswords
2. Set it as `NOTIFY_SMTP_PASSWORD` env var
3. Update `config.toml`:
   ```
   [notifications]
   email_enabled = true
   smtp_user = "your@gmail.com"
   alert_email = "your@gmail.com"
   ```
