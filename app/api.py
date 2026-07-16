"""SoloLedger REST API — wraps all CLI modules as JSON endpoints.

Run with:
    uvicorn app.api:app --reload --port 8100

Or with Docker:
    docker compose up api

Authentication:
    Pass API key via header: Authorization: Bearer YOUR_API_KEY
    Set API_KEYS env var as a comma-separated list of valid keys.
    If not set, API runs in "open" mode (no auth — useful behind a VPN).

Endpoints:
    GET  /api/v1/status            — Dashboard: cash, P&L, deadlines
    GET  /api/v1/health            — Health check

    POST /api/v1/invoices          — Create invoice
    GET  /api/v1/invoices          — List invoices
    GET  /api/v1/invoices/ar       — Accounts Receivable summary

    POST /api/v1/expenses/import   — Import bank CSV
    POST /api/v1/receipts/scan     — Scan a receipt file

    GET  /api/v1/tax/estimate      — Tax estimate
    GET  /api/v1/tax/deadlines     — Upcoming deadlines
    GET  /api/v1/tax/schedule-c    — Schedule C data

    POST /api/v1/bank/sync         — Sync Plaid transactions
    GET  /api/v1/bank/accounts     — List connected bank accounts

    GET  /api/v1/time/entries      — Fetch time entries from Toggl/Clockify
    POST /api/v1/time/invoice      — Create invoice from time entries

    GET  /api/v1/retainers         — List retainers
    POST /api/v1/retainers         — Add a retainer
    POST /api/v1/retainers/process — Process due retainers

    POST /api/v1/notify/check      — Check and send notifications
"""

import datetime
import io
import json
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, Depends
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel, Field

from .config import Config
from .ledger import Ledger
from .invoice import Invoicer, RetainerConfig

# ── App setup ──────────────────────────────────────────────────────────────

app = FastAPI(
    title="SoloLedger API",
    description="Self-hosted accounting, invoicing, and tax API for your Wyoming consulting LLC.",
    version="0.2.0",
)

# CORS — allow any origin for self-hosted use; lock down in production
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Serve web UI from web/ directory
_web_dir = Path(__file__).parent.parent / "web"
if _web_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/app", StaticFiles(directory=str(_web_dir), html=True), name="web")

# Auth
security = HTTPBearer(auto_error=False)


def get_config() -> Config:
    """Load and return the Config."""
    # Respect API_CONFIG env var, else default discovery
    config_path = os.environ.get("API_CONFIG")
    try:
        return Config(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config load failed: {e}")


def check_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Optional API key auth. If API_KEYS is set, validate. Otherwise open."""
    api_keys_env = os.environ.get("API_KEYS", "")
    if not api_keys_env:
        return  # Open mode — no auth needed

    valid_keys = [k.strip() for k in api_keys_env.split(",") if k.strip()]
    if not valid_keys:
        return

    if credentials is None:
        raise HTTPException(status_code=401, detail="API key required (Authorization: Bearer <key>)")

    if credentials.credentials not in valid_keys:
        raise HTTPException(status_code=403, detail="Invalid API key")


# ── Pydantic models ────────────────────────────────────────────────────────


class InvoiceCreateRequest(BaseModel):
    client: str
    description: str
    amount: float
    date: Optional[str] = None
    due_days: int = 30
    generate_pdf: bool = True
    payment_link: bool = False
    client_email: Optional[str] = None
    recurring: Optional[str] = None  # "month" or "year"


class TaxEstimateResponse(BaseModel):
    ytd_net_profit: float
    projected_annual_net: float
    self_employment_tax: dict
    federal_income_tax: dict
    total_estimated_tax: float
    effective_tax_rate: float
    already_paid: float
    suggested_next_payment: float
    note: str


class RetainerRequest(BaseModel):
    client: str
    description: str
    amount: float
    interval: str = "monthly"  # monthly, quarterly, yearly
    day_of_month: int = 1
    stripe_recurring: bool = False


class TimeFetchRequest(BaseModel):
    source: str = "toggl"  # toggl or clockify
    days: int = 7
    hourly_rate: Optional[float] = None
    billable_only: bool = True


class TimeInvoiceRequest(TimeFetchRequest):
    client: Optional[str] = None
    no_preview: bool = False


class BankSyncRequest(BaseModel):
    days: int = 90
    preview: bool = False


# ── helpers ─────────────────────────────────────────────────────────────────


def _ok(data: dict, status_code: int = 200):
    """Standard success envelope."""
    return {"success": True, "data": data}


def _err(msg: str, status_code: int = 400):
    """Standard error envelope."""
    from fastapi.responses import JSONResponse
    return JSONResponse({"success": False, "error": msg}, status_code=status_code)


def _decimal_to_float(val) -> float:
    """Convert Decimal to float for JSON serialization."""
    if isinstance(val, Decimal):
        return float(val)
    return val


# ── Health ──────────────────────────────────────────────────────────────────


@app.get("/api/v1/health", dependencies=[Depends(check_auth)])
async def health():
    """Simple health check — returns OK if the API is running."""
    return _ok({"status": "ok", "timestamp": datetime.datetime.now().isoformat()})


# ── Status / Dashboard ─────────────────────────────────────────────────────


@app.get("/api/v1/status", dependencies=[Depends(check_auth)])
async def get_status():
    """Get financial dashboard: cash, P&L, upcoming deadlines."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    cash = _decimal_to_float(ledger.cash_balance())
    revenue = _decimal_to_float(ledger.gross_revenue())
    expenses = _decimal_to_float(ledger.total_expenses())
    net = _decimal_to_float(ledger.net_income())

    # Tax estimate
    from .taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger)
    if net > 0:
        est = taxer.quarterly_estimate(ledger.net_income())
        tax_info = {
            "annual_total_tax": _decimal_to_float(est["annual_total_tax"]),
            "already_paid": _decimal_to_float(est["already_paid"]),
            "suggested_payment": _decimal_to_float(est["suggested_payment"]),
            "note": est["note"],
        }
    else:
        tax_info = {"annual_total_tax": 0, "already_paid": 0, "suggested_payment": 0, "note": "No tax due"}

    # Deadlines
    deadlines = taxer.deadline_info()

    # Ledger health
    errors = ledger.check()

    return _ok({
        "cash": cash,
        "gross_revenue": revenue,
        "total_expenses": expenses,
        "net_profit": net,
        "tax": tax_info,
        "deadlines": deadlines["deadlines"],
        "ledger_errors": len(errors),
    })


# ── Invoices ────────────────────────────────────────────────────────────────


@app.post("/api/v1/invoices", dependencies=[Depends(check_auth)])
async def create_invoice(req: InvoiceCreateRequest):
    """Create a new invoice (with optional Stripe payment link)."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    inv_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()

    result = invoicer.create(
        client=req.client,
        description=req.description,
        amount=Decimal(str(req.amount)).quantize(Decimal("0.01")),
        invoice_date=inv_date,
        due_days=req.due_days,
        generate_pdf=req.generate_pdf,
        payment_link=req.payment_link,
        client_email=req.client_email,
        recurring=req.recurring,
    )

    return _ok({
        "number": result["number"],
        "date": result["date"],
        "due": result.get("due"),
        "client": result["client"],
        "description": result["description"],
        "amount": float(result["amount"]),
        "payment_url": result.get("payment_url"),
        "pdf_path": result.get("pdf_path"),
        "status": result["status"],
    })


@app.get("/api/v1/invoices", dependencies=[Depends(check_auth)])
async def list_invoices(year: Optional[int] = Query(None), ar_only: bool = Query(False)):
    """List invoices, optionally filtered by year or unpaid only."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    invoices = invoicer.list(year=year, ar_only=ar_only)
    return _ok({
        "invoices": [
            {
                "date": str(i["date"]),
                "client": i["client"],
                "description": i["description"],
                "amount": float(i["amount"]),
                "paid": i.get("paid", False),
            }
            for i in invoices
        ],
        "total": len(invoices),
    })


@app.get("/api/v1/invoices/ar", dependencies=[Depends(check_auth)])
async def accounts_receivable():
    """Get Accounts Receivable summary."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    info = invoicer.check_ar()
    return _ok({
        "total_ar": float(info["total_ar"]),
        "invoice_count": info["invoice_count"],
        "overdue_count": info["overdue_count"],
        "estimated_overdue_amount": float(info["estimated_overdue_amount"]),
    })


# ── Expenses ────────────────────────────────────────────────────────────────


@app.post("/api/v1/expenses/import", dependencies=[Depends(check_auth)])
async def import_expenses(
    file: UploadFile = File(...),
    preview: bool = Form(False),
):
    """Import expenses from a bank CSV file."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    from .expenses import ExpenseImporter

    # Save upload to temp file
    suffix = Path(file.filename or "import.csv").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = ExpenseImporter(cfg, ledger)
        results = importer.import_csv(tmp_path, preview=preview)

        income_count = sum(1 for r in results if r["type"] == "income")
        expense_count = sum(1 for r in results if r["type"] == "expense")
        total = sum(r["amount"] for r in results)

        return _ok({
            "imported": len(results),
            "income_count": income_count,
            "expense_count": expense_count,
            "net_total": float(total),
            "preview": preview,
            "transactions": [
                {
                    "date": r["date"],
                    "description": r["description"],
                    "amount": float(r["amount"]),
                    "type": r["type"],
                    "account": r["account"],
                }
                for r in results
            ],
        })
    finally:
        os.unlink(tmp_path)


# ── Receipts ────────────────────────────────────────────────────────────────


@app.post("/api/v1/receipts/scan", dependencies=[Depends(check_auth)])
async def scan_receipt(
    file: UploadFile = File(...),
    preview: bool = Form(True),
):
    """Scan a receipt (PDF or image) and extract expense data."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from .receipts import ReceiptScanner

    suffix = Path(file.filename or "receipt.pdf").suffix
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        scanner = ReceiptScanner(cfg)
        result = scanner.process_file(tmp_path, preview=preview)

        return _ok({
            "success": result.get("success", False),
            "merchant": result.get("merchant"),
            "date": result.get("date"),
            "total": float(result["total"]) if result.get("total") else None,
            "line_items": result.get("line_items", []),
            "appended": result.get("appended", False),
        })
    finally:
        os.unlink(tmp_path)


# ── Tax ─────────────────────────────────────────────────────────────────────


@app.get("/api/v1/tax/estimate", dependencies=[Depends(check_auth)])
async def tax_estimate(projected_income: Optional[float] = Query(None)):
    """Calculate estimated quarterly tax payment."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        taxer = type('TaxEstimator', (object,), {})()
        from .taxes import TaxEstimator as TE
        taxer = TE(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    ytd_net = ledger.net_income()

    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        projection = ytd_net * Decimal("2")

    if ytd_net <= 0:
        return _ok({"note": "No net profit yet. No tax estimated."})

    annual = taxer.total_projected_tax(projection)
    quarterly = taxer.quarterly_estimate(ytd_net, projection)

    return _ok({
        "ytd_net_profit": float(ytd_net),
        "projected_annual_net": float(projection),
        "self_employment_tax": {
            "total": float(annual["self_employment_tax"]["total_se_tax"]),
            "deductible_half": float(annual["self_employment_tax"]["deductible_half"]),
        },
        "federal_income_tax": {
            "total": float(annual["federal_income_tax"]["income_tax"]),
            "taxable_income": float(annual["federal_income_tax"]["taxable_income"]),
            "effective_rate": annual["federal_income_tax"]["effective_rate"],
        },
        "total_estimated_tax": float(annual["total_tax"]),
        "effective_tax_rate": annual["effective_tax_rate"],
        "already_paid": float(quarterly["already_paid"]),
        "suggested_next_payment": float(quarterly["suggested_payment"]),
        "remaining_quarters": quarterly["remaining_quarters"],
        "note": quarterly["note"],
    })


@app.get("/api/v1/tax/deadlines", dependencies=[Depends(check_auth)])
async def tax_deadlines():
    """Show upcoming tax deadlines."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from .taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    info = taxer.deadline_info()
    return _ok(info)


@app.get("/api/v1/tax/schedule-c", dependencies=[Depends(check_auth)])
async def tax_schedule_c():
    """Generate Schedule C summary data."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from .taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
    except Exception as e:
        return _err(f"Tax engine error: {e}", 500)

    summary = taxer.schedule_c_summary()
    return _ok({
        "gross_receipts": float(summary["gross_receipts"]),
        "total_expenses": float(summary["total_expenses"]),
        "net_profit": float(summary["net_profit"]),
        "expense_detail": [
            {"account": e["account"], "amount": float(e["amount"])}
            for e in summary["expense_detail"]
        ],
        "taxes_paid": {
            "federal_estimated": float(summary["taxes_paid"]["federal_estimated"]),
            "fica_employer": float(summary["taxes_paid"]["fica_employer"]),
        },
    })


# ── Bank / Plaid ────────────────────────────────────────────────────────────


@app.post("/api/v1/bank/sync", dependencies=[Depends(check_auth)])
async def bank_sync(req: BankSyncRequest):
    """Fetch transactions from Plaid and import into ledger."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    feed = PlaidFeed(cfg)
    if not feed.enabled:
        return _err("Plaid not configured (set PLAID_* env vars)", 400)

    accounts = feed.fetch_accounts()
    txns = feed.fetch_transactions(days_back=req.days)

    if req.preview:
        return _ok({
            "preview": True,
            "accounts": [
                {"name": a["name"], "balance": a["current"], "type": a["type"]}
                for a in accounts
            ],
            "transactions_found": len(txns),
            "transactions": [
                {
                    "date": t.date,
                    "description": t.description,
                    "amount": float(t.amount),
                    "pending": t.pending,
                }
                for t in txns[:50]
            ],
        })

    results = feed.import_transactions(txns)
    income_count = sum(1 for r in results if r["type"] == "income")
    expense_count = sum(1 for r in results if r["type"] == "expense")
    total = sum(r["amount"] for r in results)

    return _ok({
        "imported": len(results),
        "income_count": income_count,
        "expense_count": expense_count,
        "net_total": float(total),
        "accounts": [
            {"name": a["name"], "balance": a["current"], "type": a["type"]}
            for a in accounts
        ],
    })


@app.get("/api/v1/bank/accounts", dependencies=[Depends(check_auth)])
async def bank_accounts():
    """List connected bank accounts and balances."""
    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    feed = PlaidFeed()
    accounts = feed.fetch_accounts()

    return _ok({
        "accounts": [
            {"name": a["name"], "balance": a["current"], "available": a["available"], "type": a["type"]}
            for a in accounts
        ]
    })


# ── Time Tracking ───────────────────────────────────────────────────────────


@app.post("/api/v1/time/entries", dependencies=[Depends(check_auth)])
async def time_entries(req: TimeFetchRequest):
    """Fetch time entries from Toggl or Clockify."""
    try:
        from .time_tracking import TimeTracker
    except ImportError:
        return _err("Time tracking module not available", 500)

    hourly = Decimal(str(req.hourly_rate)).quantize(Decimal("0.01")) if req.hourly_rate else None
    tracker = TimeTracker(source=req.source, hourly_rate=hourly)

    entries = tracker.fetch_entries(days_back=req.days, billable_only=req.billable_only)
    summary = tracker.summarize_by_client(entries, hourly_rate=hourly)

    return _ok({
        "entry_count": summary["entry_count"],
        "total_hours": summary["total_hours"],
        "total_amount": float(summary["total_amount"]),
        "by_client": {
            client: {
                "hours": data["hours"],
                "amount": float(data["amount"]),
            }
            for client, data in summary["by_client"].items()
        },
        "entries": [
            {
                "description": e.description,
                "project": e.project,
                "hours": e.hours,
                "billable": e.billable,
            }
            for e in entries[:100]
        ],
    })


@app.post("/api/v1/time/invoice", dependencies=[Depends(check_auth)])
async def time_to_invoice(req: TimeInvoiceRequest):
    """Create an invoice from tracked time entries."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from .time_tracking import TimeTracker
    except Exception as e:
        return _err(f"Error: {e}", 500)

    hourly = Decimal(str(req.hourly_rate)).quantize(Decimal("0.01")) if req.hourly_rate else None
    tracker = TimeTracker(source=req.source, hourly_rate=hourly)

    entries = tracker.fetch_entries(days_back=req.days)
    invoice_data = tracker.generate_invoice_data(entries, client_filter=req.client)

    if not invoice_data:
        return _err("No time entries found for the given filter", 404)

    if req.no_preview:
        invoicer = Invoicer(cfg, ledger)
        result = invoicer.create(
            client=invoice_data["client"],
            description=invoice_data["description"],
            amount=invoice_data["amount"],
        )
        return _ok({
            "invoice_created": True,
            "invoice_number": result["number"],
            "client": invoice_data["client"],
            "amount": float(invoice_data["amount"]),
            "hours": invoice_data["entries"]["total_hours"],
            "preview": False,
        })
    else:
        return _ok({
            "invoice_created": False,
            "preview": True,
            "client": invoice_data["client"],
            "amount": float(invoice_data["amount"]),
            "description": invoice_data["description"],
            "hours": invoice_data["entries"]["total_hours"],
            "entry_count": invoice_data["entries"]["entry_count"],
        })


# ── Retainers ───────────────────────────────────────────────────────────────


@app.get("/api/v1/retainers", dependencies=[Depends(check_auth)])
async def list_retainers():
    """List all configured retainers."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    invoicer = Invoicer(cfg, Ledger(cfg))
    retainers = invoicer._load_retainers()

    return _ok({
        "retainers": [
            {
                "id": rid,
                "client": r["client"],
                "description": r["description"],
                "amount": float(r["amount"]),
                "interval": r["interval"],
                "last_invoiced": r.get("last_invoiced"),
                "next_invoice": r.get("next_invoice"),
            }
            for rid, r in retainers.items()
        ]
    })


@app.post("/api/v1/retainers", dependencies=[Depends(check_auth)])
async def add_retainer(req: RetainerRequest):
    """Add a recurring retainer configuration."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    invoicer = Invoicer(cfg, Ledger(cfg))
    retainer_cfg = RetainerConfig(
        client=req.client,
        description=req.description,
        amount=Decimal(str(req.amount)).quantize(Decimal("0.01")),
        interval=req.interval,
        day_of_month=req.day_of_month,
        stripe_recurring=req.stripe_recurring,
    )

    info = invoicer.save_retainer(retainer_cfg)

    return _ok({
        "id": info["id"],
        "client": info["client"],
        "description": info["description"],
        "amount": float(info["amount"]),
        "interval": info["interval"],
        "next_invoice": info["next_invoice"],
    })


@app.post("/api/v1/retainers/process", dependencies=[Depends(check_auth)])
async def process_retainers(preview: bool = Query(True)):
    """Process due retainers and generate invoices."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Error: {e}", 500)

    results = invoicer.process_retainers(preview=preview)
    return _ok({
        "preview": preview,
        "invoices_due": len(results),
        "invoices": [
            {
                "client": r.get("client"),
                "amount": float(r.get("amount", 0)),
                "invoice_number": r.get("number"),
                "preview": r.get("preview", True),
            }
            for r in results
        ],
    })


# ── Notifications ───────────────────────────────────────────────────────────


@app.post("/api/v1/notify/check", dependencies=[Depends(check_auth)])
async def notify_check():
    """Check everything and return alerts."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from .notify import Notifier
    except Exception as e:
        return _err(f"Error: {e}", 500)

    notifier = Notifier(cfg)
    results = notifier.send_digest(ledger)

    return _ok({
        "alerts": {
            "tax_deadlines": results["tax_deadlines"],
            "unpaid_invoices": results["unpaid_invoices"],
            "ledger_health": results["ledger_health"],
        },
        "total_alerts": sum(len(v) for v in results.values()),
    })


# ── Run ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", "8100"))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
