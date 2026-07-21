"""SoloLedger REST API — wraps all CLI modules as JSON endpoints.

Run with:
    uvicorn app.api:app --reload --port 8100

Or with Docker:
    docker compose up api

Authentication (two modes):
    1. API key — via header: Authorization: Bearer YOUR_API_KEY
       Set API_KEYS env var as a comma-separated list of valid keys.
    2. Google OAuth — sign in with Google from the web UI.
       Set GOOGLE_CLIENT_ID env var to enable.
    If neither is configured, API runs in "open" mode (no auth).

Public endpoints (no auth needed):
    GET  /api/v1/public/status     — Basic setup status (no sensitive data)

Authenticated endpoints:
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

import contextvars
import datetime
import hashlib
import json
import os
import secrets
import shutil
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

import requests as http_requests
from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile, Depends, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from pydantic import BaseModel

from .config import Config
from .ledger import Ledger
from .invoice import Invoicer, RetainerConfig
from .ofx_import import OfxImporter
from .mileage import MileageTracker

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

# Google OAuth config
GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# In-memory session store
# {token: {"email": str, "name": str, "picture": str, "method": str}}
_sessions: dict[str, dict] = {}

# Read API_KEYS once at startup
_api_keys_env = os.environ.get("API_KEYS", "")
_valid_api_keys = [k.strip() for k in _api_keys_env.split(",") if k.strip()] if _api_keys_env else []


# ── Data paths (always relative to project root, not CWD) ───

_PROJECT_ROOT = Path(__file__).resolve().parent.parent
_DATA_DIR = _PROJECT_ROOT

# ── Built-in user store (email/password) ────────────────────

_USERS_PATH = _DATA_DIR / "users.json"


def _load_users() -> dict:
    if _USERS_PATH.exists():
        try:
            return json.loads(_USERS_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_users(users: dict):
    _USERS_PATH.write_text(json.dumps(users, indent=2))


def _hash_password(password: str) -> str:
    """Hash a password with PBKDF2-SHA256 and a random salt."""
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    """Verify a password against a stored hash."""
    try:
        salt, hsh = stored.split(":", 1)
        h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return h.hex() == hsh
    except Exception:
        return False


# ── Multi-tenant store ─────────────────────────────────────

_current_tenant: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_tenant", default=None)

_TENANTS_PATH = _DATA_DIR / "tenants.json"


def _load_tenants() -> dict:
    if _TENANTS_PATH.exists():
        try:
            return json.loads(_TENANTS_PATH.read_text())
        except Exception:
            return {}
    return {}


def _save_tenants(tenants: dict):
    _TENANTS_PATH.write_text(json.dumps(tenants, indent=2))


def _tenant_dir(user_id: str) -> Path:
    return _DATA_DIR / "ledgers" / user_id


def create_tenant(email: str, name: str = "") -> dict:
    """Create a new tenant with an isolated ledger directory."""
    tenants = _load_tenants()
    if email in tenants:
        return tenants[email]

    user_id = secrets.token_hex(16)
    tdir = _tenant_dir(user_id)
    tdir.mkdir(parents=True, exist_ok=True)

    # Copy template ledger
    template_dir = _PROJECT_ROOT / "ledger"
    if template_dir.exists():
        for fname in ["accounts.beancount", "transactions.beancount"]:
            src = template_dir / fname
            if src.exists():
                shutil.copy2(src, tdir / fname)

    (tdir / "main.beancount").write_text(
        f'include "accounts.beancount"\ninclude "transactions.beancount"\n'
    )

    display_name = name or email.split("@")[0]
    config_toml = _generate_tenant_config(email, display_name)
    (tdir / "config.toml").write_text(config_toml.strip())

    tenant = {
        "user_id": user_id,
        "email": email,
        "name": display_name,
        "plan": "free",
        "status": "active",
        "stripe_customer_id": "",
        "stripe_subscription_id": "",
        "ledger_dir": str(_tenant_dir(user_id)),
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "trial_ends": "",
        "onboarding_complete": False,
        "plaid_access_token": "",
    }
    tenants[email] = tenant
    _save_tenants(tenants)
    return tenant


def _generate_tenant_config(email: str, name: str) -> str:
    import configparser
    today = datetime.date.today().isoformat()
    return f'''# SoloLedger — {name}
# Auto-generated {today}

[business]
name = "{name}"
owner = "{name}"
state = "WY"
ein = "XX-XXXXXXX"
address = ""
phone = ""
email = "{email}"

[ledger]
path = "main.beancount"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

[tax]
state = "WY"
standard_deduction = 14600
[[tax.brackets]]
rate = 0.10
floor = 0
ceiling = 11925
[[tax.brackets]]
rate = 0.12
floor = 11926
ceiling = 48475
[[tax.brackets]]
rate = 0.22
floor = 48476
ceiling = 103350
[[tax.brackets]]
rate = 0.24
floor = 103351
ceiling = 197300
[[tax.brackets]]
rate = 0.32
floor = 197301
ceiling = 250525
[[tax.brackets]]
rate = 0.35
floor = 250526
ceiling = 626350
[[tax.brackets]]
rate = 0.37
floor = 626351
ceiling = 999999999
[tax.self_employment]
rate_social_security = 0.124
rate_medicare = 0.029
ss_wage_base = 184800
deduction_ratio = 0.9235
safe_harbor_percent = 1.00
safe_harbor_percent_high_income = 1.10
safe_harbor_threshold = 150000
[tax.quarter_dates]
q1 = [4, 15]
q2 = [6, 15]
q3 = [9, 15]
q4 = [1, 15]

[payments]
stripe_enabled = false

[notifications]
desktop_enabled = false
email_enabled = false
remind_days_before = 7
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = ""
smtp_password = ""
alert_email = ""

[banking]
plaid_enabled = false
'''


def resolve_email_from_token(token: str) -> str | None:
    """Extract user email from any token (session, API key)."""
    if token in _sessions:
        return _sessions[token].get("email", "")
    if _valid_api_keys and token in _valid_api_keys:
        return "api-key-user"
    return None


# ── Tenant middleware ──────────────────────────────────────

@app.middleware("http")
async def tenant_middleware(request: Request, call_next):
    """Resolve the current tenant from the auth token before each request."""
    _current_tenant.set(None)
    auth = request.headers.get("authorization", "")
    if auth.startswith("Bearer "):
        token = auth[7:]
        email = resolve_email_from_token(token)
        if email:
            try:
                tenants = _load_tenants()
                if email in tenants:
                    t = tenants[email]
                    # Backfill missing fields
                    if "onboarding_complete" not in t:
                        t["onboarding_complete"] = True
                    if "plaid_access_token" not in t:
                        t["plaid_access_token"] = ""
                    _current_tenant.set(t)
                elif email != "api-key-user":
                    # Auto-create tenant on first request
                    tenant = create_tenant(email)
                    _current_tenant.set(tenant)
            except Exception as e:
                print(f"[tenant_middleware] Failed to resolve tenant for {email}: {e}")
    response = await call_next(request)
    return response


# ── Tenant-aware Config ────────────────────────────────────

def get_config() -> Config:
    """Load Config for the current tenant, falling back to main config."""
    tenant = _current_tenant.get()
    if tenant:
        tdir = Path(tenant["ledger_dir"]).resolve()
        # Sandbox: tenant dir must be within the project data directory
        if not str(tdir).startswith(str(_PROJECT_ROOT.resolve())):
            raise HTTPException(status_code=403, detail="Tenant ledger_dir is outside project root")
        cfg_path = tdir / "config.toml"
        if cfg_path.exists():
            try:
                return Config(str(cfg_path))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Tenant config load failed: {e}")

    # Fallback: main config (open mode / admin)
    config_path = os.environ.get("API_CONFIG")
    try:
        return Config(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config load failed: {e}")


def get_plan() -> str:
    """Get the plan name for the current tenant. 'free' if no tenant."""
    tenant = _current_tenant.get()
    if tenant:
        return tenant.get("plan", "free")
    return "free"


def require_plan(min_plan: str):
    """Dependency: require a minimum plan level to access an endpoint.

    Plans (in order): free < professional < business
    Usage: @app.get(..., dependencies=[Depends(require_plan("professional"))])
    """
    PLAN_ORDER = {"free": 0, "professional": 1, "business": 2}
    min_level = PLAN_ORDER.get(min_plan, 0)

    def _check():
        tenant = _current_tenant.get()
        if not tenant:
            # Open mode — allow all
            return
        user_plan = tenant.get("plan", "free")
        if PLAN_ORDER.get(user_plan, 0) < min_level:
            raise HTTPException(
                status_code=402,
                detail=f"Upgrade to {min_plan} plan required",
            )

    return _check


def check_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Check auth: API key, Google session token, or open mode."""
    if not _api_keys_env and not GOOGLE_CLIENT_ID:
        return

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    if _valid_api_keys and token in _valid_api_keys:
        return

    if _sessions and token in _sessions:
        return

    raise HTTPException(status_code=403, detail="Invalid or expired token")


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


class TaxPayRequest(BaseModel):
    amount: float
    quarter: str = ""  # e.g. "Q1", "Q2", "Q3", "Q4"
    year: int = 0
    note: str = "Estimated tax payment"


class CategoryLearnRequest(BaseModel):
    merchant: str
    account: str
    correct: bool = False


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


# ── Public status (no auth) ─────────────────────────────────


@app.get("/api/v1/public/status")
async def public_status():
    """Public endpoint to check if the app needs first-run setup.

    Returns only non-sensitive info — safe to call without auth.
    """
    try:
        cfg = get_config()
        # Check if ledger has data
        ledger = Ledger(cfg)
        try:
            cash = _decimal_to_float(ledger.cash_balance())
        except Exception:
            cash = 0.0
        has_data = cash > 0 or ledger.net_income() != 0
        return _ok({
            "needs_setup": False,
            "has_data": has_data,
            "has_auth": bool(_api_keys_env or GOOGLE_CLIENT_ID or _sessions),
            "auth_methods": {
                "local": True,  # email/password always available
                "google": bool(GOOGLE_CLIENT_ID),
            },
        })
    except Exception:
        return _ok({
            "needs_setup": True,
            "has_data": False,
            "has_auth": False,
            "auth_methods": {"local": True, "google": False},
        })


# ── Auth endpoints ──────────────────────────────────────────


class GoogleAuthRequest(BaseModel):
    credential: str


@app.post("/api/v1/auth/google")
async def auth_google(req: GoogleAuthRequest):
    """Verify a Google ID token and create a session.

    Accepts credential from Google Identity Services (One Tap / Sign In
    With Google). Returns a session token the frontend uses as Bearer.
    """
    if not GOOGLE_CLIENT_ID:
        return _err("Google sign-in not configured on this server", 501)

    try:
        resp = http_requests.post(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": req.credential},
            timeout=10,
        )
        if resp.status_code != 200:
            return _err("Token verification failed", 401)

        info = resp.json()
        aud = info.get("aud", "")
        if aud != GOOGLE_CLIENT_ID:
            return _err("Token audience mismatch", 401)

        email = info.get("email", "")
        if not email:
            return _err("Email not provided in token", 401)

        # Create a session
        token = secrets.token_urlsafe(32)
        _sessions[token] = {
            "email": email,
            "name": info.get("name", email),
            "picture": info.get("picture", ""),
        }

        return _ok({
            "token": token,
            "user": {
                "email": email,
                "name": info.get("name", email),
                "picture": info.get("picture", ""),
            },
        })
    except http_requests.RequestException as e:
        return _err(f"Failed to verify token: {e}", 502)


@app.get("/api/v1/auth/me", dependencies=[Depends(check_auth)])
async def auth_me(request: Request):
    """Return current user info if authenticated.

    Works for both API key and Google session auth.
    """
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("Not authenticated", 401)

    token = auth_header[7:]

    # Check Google session
    if token in _sessions:
        return _ok(_sessions[token])

    # Check API key — minimal info
    if _valid_api_keys and token in _valid_api_keys:
        return _ok({"email": "api-key-user", "name": "API Key", "picture": ""})

    return _err("Not authenticated", 401)


@app.get("/api/v1/auth/google/config")
async def auth_google_config():
    """Return the Google OAuth client ID for the frontend.

    No auth required — the frontend uses this to configure the
    Google Sign-In button.
    """
    return _ok({
        "client_id": GOOGLE_CLIENT_ID,
        "enabled": bool(GOOGLE_CLIENT_ID),
    })


# ── Built-in email/password auth ────────────────────────────


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


@app.post("/api/v1/auth/signup")
async def auth_signup(req: SignupRequest):
    """Create a new account with email and password.

    Requires a valid email and a password (minimum 6 characters).
    Returns a session token on success.
    """
    email = req.email.strip().lower()
    if not email or "@" not in email:
        return _err("Valid email required", 400)
    if len(req.password) < 6:
        return _err("Password must be at least 6 characters", 400)

    users = _load_users()
    if email in users:
        return _err("An account with this email already exists", 409)

    name = req.name.strip() or email.split("@")[0]

    users[email] = {
        "password": _hash_password(req.password),
        "name": name,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _save_users(users)

    # Auto-create tenant
    create_tenant(email, name)

    # Create session
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "email": email,
        "name": name,
        "picture": "",
        "method": "local",
    }

    return _ok({
        "token": token,
        "user": {"email": email, "name": name, "picture": ""},
    })


class SigninRequest(BaseModel):
    email: str
    password: str


@app.post("/api/v1/auth/signin")
async def auth_signin(req: SigninRequest):
    """Sign in with email and password.

    Returns a session token on success.
    """
    email = req.email.strip().lower()
    if not email:
        return _err("Email required", 400)

    users = _load_users()
    user = users.get(email)
    if not user:
        return _err("Invalid email or password", 401)

    if not _verify_password(req.password, user["password"]):
        return _err("Invalid email or password", 401)

    # Create session
    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "email": email,
        "name": user.get("name", email.split("@")[0]),
        "picture": "",
        "method": "local",
    }

    return _ok({
        "token": token,
        "user": {
            "email": email,
            "name": user.get("name", email.split("@")[0]),
            "picture": "",
        },
    })


@app.post("/api/v1/auth/logout", dependencies=[Depends(check_auth)])
async def auth_logout(request: Request):
    """Log out — invalidate the current session token."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token in _sessions:
            del _sessions[token]
    return _ok({"logged_out": True})


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


@app.get("/api/v1/dashboard", dependencies=[Depends(check_auth)])
async def get_dashboard():
    """Combined dashboard — all data in one call (faster than /status + /invoices/ar + ...).

    Returns everything needed for the web app dashboard page:
    cash, P&L, AR, tax estimate, deadlines, and recent transactions.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    cash = _decimal_to_float(ledger.cash_balance())
    revenue = _decimal_to_float(ledger.gross_revenue())
    expenses = _decimal_to_float(ledger.total_expenses())
    net = _decimal_to_float(ledger.net_income())
    ar_bal = _decimal_to_float(ledger.account_balance(cfg.ar_account))

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

    deadlines = taxer.deadline_info()
    errors = ledger.check()

    # Recent transactions
    txns = []
    for entry in ledger.entries:
        if not hasattr(entry, "date") or not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            txns.append({
                "date": str(entry.date),
                "payee": getattr(entry, "payee", "") or "",
                "description": getattr(entry, "narration", "") or "",
                "account": posting.account,
                "amount": float(posting.units.number) if posting.units else 0,
            })
    txns.sort(key=lambda x: (x["date"], x["account"]), reverse=True)

    return _ok({
        "cash": cash,
        "gross_revenue": revenue,
        "total_expenses": expenses,
        "net_profit": net,
        "ar": ar_bal,
        "tax": tax_info,
        "deadlines": deadlines["deadlines"],
        "ledger_errors": len(errors),
        "recent_transactions": txns[:15],
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
        # Return only filename, not full path
        "pdf_path": Path(result.get("pdf_path", "")).name if result.get("pdf_path") else None,
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


class MarkInvoicePaidRequest(BaseModel):
    amount: Optional[float] = None
    date: Optional[str] = None
    source_account: Optional[str] = None


@app.post("/api/v1/invoices/{number}/pay", dependencies=[Depends(check_auth)])
async def mark_invoice_paid(number: str, req: MarkInvoicePaidRequest):
    """Mark an invoice as paid — records a payment transaction in the ledger.

    Creates: checking_account +amount ; AR_account -amount
    If amount is omitted, looks up the invoice amount from the ledger.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    # Find the invoice amount from the ledger
    invoice_amount = req.amount
    if invoice_amount is None:
        invoices = invoicer.list()
        for inv in invoices:
            inv_num = inv.get("date", "") + "-" + inv.get("client", "")
            # Match by number pattern
            if inv.get("_number") == number or number in inv.get("_key", ""):
                invoice_amount = float(inv["amount"])
                break
        if invoice_amount is None:
            return _err(f"Invoice {number} not found or amount required", 404)

    pay_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    amt = Decimal(str(invoice_amount)).quantize(Decimal("0.01"))
    source = req.source_account or cfg.checking_account

    entry = ledger.append(
        date=pay_date,
        payee=f"Payment — Invoice {number}",
        narration=f"Payment received for invoice {number}",
        postings=[
            (source, f"{amt:.2f} USD"),
            (cfg.ar_account, f"-{amt:.2f} USD"),
        ],
    )

    return _ok({
        "paid": True,
        "amount": float(amt),
        "date": pay_date.isoformat(),
        "invoice": number,
    })


@app.get("/api/v1/invoices/{number}/pdf", dependencies=[Depends(check_auth)])
async def get_invoice_pdf(number: str):
    """Download an invoice PDF by invoice number."""
    # Prevent path traversal — reject separators and parent-dir references
    if "/" in number or "\\" in number or ".." in number:
        raise HTTPException(status_code=400, detail="Invalid invoice number")
    from fastapi.responses import FileResponse
    cfg = get_config()
    inv_dir = cfg.invoices_dir.resolve()
    pdf_path = (inv_dir / f"{number}.pdf").resolve()
    html_path = (inv_dir / f"{number}.html").resolve()
    # Ensure resolved path stays within invoices_dir
    if not str(pdf_path).startswith(str(inv_dir)):
        raise HTTPException(status_code=403, detail="Invalid invoice number")
    if pdf_path.exists():
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"{number}.pdf")
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html", filename=f"{number}.html")
    return _err(f"Invoice '{number}' not found. Generate it with 'llc invoice create'.", 404)


@app.get("/api/v1/reconciliation", dependencies=[Depends(check_auth)])
async def get_reconciliation():
    """Get reconciliation data: ledger balance vs. uncleared transactions.

    Returns a list of uncleared transactions and current balances.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    checking_bal = float(ledger.account_balance(cfg.checking_account))
    uncleared = []

    for entry in ledger.entries:
        if not hasattr(entry, "date") or not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            if posting.account == cfg.checking_account:
                amt = float(posting.units.number) if posting.units else 0
                date_str = str(entry.date)
                payee = getattr(entry, "payee", "") or ""
                nar = getattr(entry, "narration", "") or ""
                # Find the other side of this transaction
                other_account = ""
                for other in entry.postings:
                    if other.account != cfg.checking_account:
                        other_account = other.account
                uncleared.append({
                    "date": date_str,
                    "payee": payee,
                    "description": nar,
                    "amount": amt,
                    "account": other_account,
                    "id": f"{date_str}-{payee}-{amt}",
                })

    uncleared.sort(key=lambda x: x["date"], reverse=True)
    total_uncleared = sum(t["amount"] for t in uncleared)

    return _ok({
        "ledger_balance": checking_bal,
        "uncleared_count": len(uncleared),
        "uncleared_total": round(abs(total_uncleared), 2),
        "cleared_balance": round(checking_bal - total_uncleared, 2),
        "uncleared": uncleared[:50],
        "balance_date": datetime.date.today().isoformat(),
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
    _ext = Path(file.filename or ".csv").suffix.lower()
    suffix = _ext if _ext in (".csv", ".qbo", ".ofx", ".ofx.gz") else ".csv"
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


@app.post("/api/v1/receipts/scan", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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

    _ext = Path(file.filename or ".pdf").suffix.lower()
    suffix = _ext if _ext in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp") else ".pdf"
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


@app.get("/api/v1/categories/suggest", dependencies=[Depends(check_auth)])
async def category_suggest(merchant: str = Query("")):
    """Suggest a category for a merchant based on learned patterns."""
    try:
        cfg = get_config()
        from .categorizer import Categorizer
        cat = Categorizer(cfg)
        result = cat.suggest_with_confidence(merchant.upper())
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


@app.post("/api/v1/categories/learn", dependencies=[Depends(check_auth)])
async def category_learn(req: CategoryLearnRequest):
    """Teach the categorizer that a merchant maps to an account.

    Send JSON: {"merchant": "AMAZON", "account": "Expenses:Supplies", "correct": false}
    Set correct=true to override all previous suggestions for this merchant.
    """
    merchant = req.merchant
    account = req.account
    correct = req.correct
    try:
        cfg = get_config()
        from .categorizer import Categorizer
        cat = Categorizer(cfg)
        if correct:
            cat.correct(merchant.upper(), account)
        else:
            cat.learn(merchant.upper(), account)
        return _ok({"merchant": merchant.upper(), "account": account, "learned": True})
    except Exception as e:
        return _err(str(e), 500)


@app.get("/api/v1/receipts/match", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def receipt_match(amount: float = Query(0), merchant: str = Query("")):
    """Match a scanned receipt against recent uncleared bank transactions.

    Finds bank transactions within a small threshold of the receipt amount.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    threshold = Decimal("0.50")
    txns = []
    for entry in ledger.entries:
        if not hasattr(entry, "date") or not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            if posting.account.startswith("Assets:Bank"):
                amt = Decimal(str(posting.units.number)) if posting.units else Decimal("0")
                if amt < 0:
                    pos_amt = abs(amt)
                    if abs(pos_amt - Decimal(str(amount))) <= threshold:
                        desc = getattr(entry, "payee", "") or getattr(entry, "narration", "") or ""
                        txns.append({
                            "date": str(entry.date),
                            "description": desc,
                            "amount": float(pos_amt),
                            "account": posting.account,
                            "match_score": round(float(1.0 - abs(pos_amt - Decimal(str(amount))) / max(pos_amt, Decimal("0.01"))), 3),
                        })

    txns.sort(key=lambda x: -x["match_score"])
    return _ok({"matches": txns[:5], "receipt_amount": amount})


# ── Tax ─────────────────────────────────────────────────────────────────────


@app.get("/api/v1/tax/estimate", dependencies=[Depends(check_auth)])
async def tax_estimate(projected_income: Optional[float] = Query(None)):
    """Calculate estimated quarterly tax payment."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
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

    from .disclaimer import TAX_DISCLAIMER
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
        "disclaimer": TAX_DISCLAIMER,
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


@app.get("/api/v1/tax/voucher", dependencies=[Depends(check_auth)])
async def tax_voucher(quarter: str = Query("Q3"), amount: Optional[float] = Query(None)):
    """Generate a printable 1040-ES payment voucher PDF.

    The IRS still accepts estimated tax payments via mail with Form 1040-ES.
    This generates a printable voucher with your business info and the amount.
    """
    # Validate quarter — only Q1–Q4 allowed
    if quarter not in ("Q1", "Q2", "Q3", "Q4"):
        raise HTTPException(status_code=400, detail="Quarter must be Q1, Q2, Q3, or Q4")

    cfg = get_config()
    ledger = Ledger(cfg)

    if amount is None:
        from .taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
        net = ledger.net_income()
        if net > 0:
            est = taxer.quarterly_estimate(net)
            amount = float(est["suggested_payment"])
        else:
            amount = 0.0

    from pathlib import Path
    from jinja2 import Environment, FileSystemLoader, select_autoescape

    env = Environment(loader=FileSystemLoader(str(cfg.project_root / "templates")),
                      autoescape=select_autoescape(['html', 'xml']))
    template = env.get_template("voucher.html")

    html = template.render(
        business=cfg,
        quarter=quarter,
        year=str(datetime.date.today().year),
        amount=amount,
        today=datetime.date.today().isoformat(),
    )

    pdf_dir = cfg.output_dir / "vouchers"
    pdf_dir.mkdir(parents=True, exist_ok=True)
    pdf_path = pdf_dir / f"1040-ES-{quarter}-{datetime.date.today().year}.pdf"

    try:
        from weasyprint import HTML
        HTML(string=html).write_pdf(str(pdf_path))
    except ImportError:
        # Fall back to HTML
        pdf_path = pdf_path.with_suffix(".html")
        pdf_path.write_text(html)

    from fastapi.responses import FileResponse
    return FileResponse(str(pdf_path), media_type="application/pdf" if pdf_path.suffix == ".pdf" else "text/html",
                        filename=pdf_path.name)


@app.post("/api/v1/tax/pay", dependencies=[Depends(check_auth)])
async def tax_pay(req: TaxPayRequest):
    """Record an estimated tax payment in the ledger.

    After paying the IRS (via Direct Pay, EFTPS, or mail), call this to
    record the payment and update your dashboard.
    """
    from decimal import Decimal
    import datetime

    cfg = get_config()
    ledger = Ledger(cfg)

    amt = Decimal(str(req.amount)).quantize(Decimal("0.01"))
    quarter_str = f" {req.quarter}" if req.quarter else ""
    year_str = f" {req.year}" if req.year else f" {datetime.date.today().year}"

    narration = f"Estimated tax payment{quarter_str}{year_str}"
    if req.note and req.note != "Estimated tax payment":
        narration = req.note

    postings = [
        ("Expenses:Taxes:Federal", f"{amt:.2f} USD"),
        (cfg.checking_account, f"-{amt:.2f} USD"),
    ]

    ledger.append(
        date=datetime.date.today(),
        payee="IRS",
        narration=narration,
        postings=postings,
    )

    # Recalculate remaining
    ledger.reload(force=True)
    net = ledger.net_income()
    from .taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
    est = taxer.quarterly_estimate(net) if net > 0 else {}

    return _ok({
        "recorded": True,
        "amount": float(amt),
        "narration": narration,
        "already_paid": float(est.get("already_paid", 0)) if est else 0,
        "remaining": float(est.get("remaining", 0)) if est else 0,
        "suggested_next": float(est.get("suggested_payment", 0)) if est else 0,
    })


# ── Bank / Plaid ────────────────────────────────────────────────────────────


@app.post("/api/v1/bank/sync", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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


@app.get("/api/v1/bank/accounts", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_accounts():
    """List connected bank accounts and balances."""
    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    tenant = _current_tenant.get()
    access_token = (tenant or {}).get("plaid_access_token", "") or os.environ.get("PLAID_ACCESS_TOKEN", "")
    if not access_token:
        return _err("No bank connected. Use the 'Connect Bank' button in the Import page.", 400)

    feed = PlaidFeed(access_token=access_token)
    accounts = feed.fetch_accounts()

    return _ok({
        "accounts": [
            {"name": a["name"], "balance": a["current"], "available": a["available"], "type": a["type"]}
            for a in accounts
        ]
    })


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


@app.get("/api/v1/bank/link-token", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_link_token():
    """Generate a Plaid Link token so the frontend can open Plaid Link.

    The frontend uses this token to initialize the Plaid Link widget,
    which lets the user select their bank and authenticate.
    """
    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    result = PlaidFeed.generate_link_token()
    if "error" in result:
        return _err(result["error"], 500)
    return _ok(result)


class ExchangeTokenRequest(BaseModel):
    public_token: str
    accounts: list[str] = []


@app.post("/api/v1/bank/exchange-token", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_exchange_token(req: ExchangeTokenRequest):
    """Exchange a Plaid public token for an access token and store it.

    Called after the user completes Plaid Link in the browser.
    Stores the access token securely in the user's tenant config.
    """
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    try:
        import plaid
        from plaid.api import plaid_api
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

        client_id = os.environ.get("PLAID_CLIENT_ID", "")
        secret = os.environ.get("PLAID_SECRET", "")
        plaid_env = os.environ.get("PLAID_ENV", "sandbox")

        if not client_id or not secret:
            return _err("PLAID_CLIENT_ID and PLAID_SECRET must be set", 500)

        host_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        configuration = plaid.Configuration(
            host=host_map.get(plaid_env, plaid.Environment.Sandbox),
            api_key={"clientId": client_id, "secret": secret, "plaidVersion": "2020-09-14"},
        )
        api_client = plaid.ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)

        exchange_request = ItemPublicTokenExchangeRequest(public_token=req.public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response.access_token

        # Store in tenant config
        tenants = _load_tenants()
        email = tenant["email"]
        if email in tenants:
            tenants[email]["plaid_access_token"] = access_token
            _save_tenants(tenants)

        return _ok({"connected": True, "item_id": exchange_response.item_id})
    except Exception as e:
        return _err(f"Failed to exchange token: {e}", 500)


@app.get("/api/v1/bank/status", dependencies=[Depends(check_auth)])
async def bank_status():
    """Check if the user has a bank connected via Plaid."""
    tenant = _current_tenant.get()
    access_token = (tenant or {}).get("plaid_access_token", "")
    has_main_token = bool(os.environ.get("PLAID_ACCESS_TOKEN", ""))

    if access_token:
        try:
            from .bank_feed import PlaidFeed
            feed = PlaidFeed(access_token=access_token)
            accounts = feed.fetch_accounts()
            return _ok({
                "connected": True,
                "account_count": len(accounts),
                "accounts": [
                    {"name": a["name"], "mask": a.get("mask", ""), "type": a["type"], "balance": a["current"]}
                    for a in accounts[:5]
                ],
            })
        except Exception:
            return _ok({"connected": True, "account_count": 0, "accounts": []})

    if has_main_token:
        return _ok({"connected": True, "account_count": -1, "accounts": [], "note": "Using global PLAID_ACCESS_TOKEN"})

    return _ok({"connected": False, "account_count": 0, "accounts": []})


# ── Time Tracking ───────────────────────────────────────────────────────────


@app.post("/api/v1/time/entries", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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


@app.post("/api/v1/notify/check", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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


# ── Stripe Webhook (for auto-reconciliation) ────────────────────────────────


@app.post("/api/v1/webhooks/stripe", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Receive Stripe webhook events for payment auto-reconciliation.

    When a checkout.session.completed event arrives, this records the
    payment in the ledger and marks the invoice as paid.

    Set STRIPE_WEBHOOK_SECRET env var to enable signature verification.
    Configure the webhook URL in Stripe Dashboard → Webhooks.
    """
    import hashlib
    import hmac

    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")
    webhook_secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    dev_mode = os.environ.get("STRIPE_DEV_MODE", "").lower() in ("1", "true", "yes")

    if webhook_secret:
        try:
            from stripe import Webhook
            event = Webhook.construct_event(payload, sig_header, webhook_secret)
        except Exception as e:
            return {"success": False, "error": f"Signature verification failed: {e}"}
    elif dev_mode:
        # Unsigned mode only for local development — explicitly opt in
        import json
        event = json.loads(payload)
    else:
        return _err("Stripe webhook secret not configured. Set STRIPE_WEBHOOK_SECRET, or set STRIPE_DEV_MODE=true for development.", 503)

    event_type = event.get("type", "")
    if event_type != "checkout.session.completed":
        return _ok({"received": True, "event": event_type, "action": "ignored"})

    session = event.get("data", {}).get("object", {})
    invoice_number = (session.get("metadata") or {}).get("invoice_number", "")
    client = (session.get("metadata") or {}).get("client", "Stripe Payment")
    amount_total = Decimal(str(session.get("amount_total", 0))) / Decimal("100")

    if not invoice_number:
        return _ok({"received": True, "action": "no_invoice_metadata"})

    # Record the payment in the ledger
    try:
        cfg = get_config()
        ledger = Ledger(cfg)

        # Check if this payment was already recorded (idempotency)
        payment_id = session.get("id", "")
        for entry in ledger.entries:
            if hasattr(entry, "narration") and payment_id in entry.narration:
                return _ok({"received": True, "action": "already_recorded", "payment_id": payment_id})

        postings = [
            (cfg.checking_account, f"{amount_total:.2f} USD"),
            (cfg.ar_account, f"-{amount_total:.2f} USD"),
        ]
        ledger.append(
            date=datetime.date.today(),
            payee=f"Stripe payment — {client}",
            narration=f"Stripe payment {payment_id} for invoice {invoice_number}",
            postings=postings,
        )

        return _ok({
            "received": True,
            "action": "recorded",
            "invoice_number": invoice_number,
            "amount": float(amount_total),
            "payment_id": payment_id,
        })
    except Exception as e:
        return _err(f"Payment recording failed: {e}", 500)


# ── Reports ────────────────────────────────────────────────────────────────


@app.get("/api/v1/reports/expenses", dependencies=[Depends(check_auth)])
async def get_expenses_report(year: Optional[int] = Query(None), format: str = Query("json")):
    """Get expense report as JSON or CSV."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from .reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)

    if format == "csv":
        csv_data = rg.expenses_csv(year=year)
        from fastapi.responses import PlainTextResponse
        filename = f"expenses-{year or 'all'}.csv"
        return PlainTextResponse(csv_data, media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})

    summary = rg.expenses_summary(year=year)
    return _ok({"year": year or "all", "total": sum(s["amount"] for s in summary), "categories": summary})


@app.get("/api/v1/reports/profit-loss", dependencies=[Depends(check_auth)])
async def get_profit_loss(year: Optional[int] = Query(None)):
    """Get profit and loss summary."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from .reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)
    pl = rg.profit_loss(year=year)
    return _ok(pl)


# ── Import ─────────────────────────────────────────────────────────────────


@app.post("/api/v1/import/csv", dependencies=[Depends(check_auth)])
async def import_csv(
    file: UploadFile = File(...),
    preview: bool = Form(False),
):
    """Import transactions from a generic CSV file."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    from .importer import Importer

    _ext = Path(file.filename or ".csv").suffix.lower()
    suffix = _ext if _ext in (".csv", ".qbo") else ".csv"
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        imp = Importer(cfg, ledger)
        results = imp.import_csv(tmp_path, preview=preview)
        return _ok({
            "imported": len(results),
            "preview": preview,
            "transactions": [
                {"date": r["date"], "description": r["description"],
                 "amount": float(r["amount"]), "type": r["type"], "account": r["account"]}
                for r in results
            ],
        })
    finally:
        os.unlink(tmp_path)


# ── OFX Import ──────────────────────────────────────────────────────────────


@app.post("/api/v1/ofx/import", dependencies=[Depends(check_auth)])
async def api_ofx_import(
    file: UploadFile = File(...),
    account: Optional[str] = Form(None),
    preview: bool = Form(False),
):
    """Import bank transactions from an OFX/QFX file upload."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    ledger = Ledger(cfg)
    importer = OfxImporter(cfg, ledger)

    # Save uploaded file temporarily
    _ext = Path(file.filename or ".ofx").suffix.lower() if file.filename else ".ofx"
    suffix = _ext if _ext in (".ofx", ".qfx", ".ofx.gz") else ".ofx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = importer.import_file(
            tmp_path,
            account=account or cfg.checking_account,
            preview=preview,
        )
        result.pop("transactions", None)  # too large for response
        return _ok(result)
    finally:
        os.unlink(tmp_path)


# ── Mileage Tracking ────────────────────────────────────────────────────────


@app.get("/api/v1/mileage/trips", dependencies=[Depends(check_auth)])
async def api_mileage_list(
    year: Optional[int] = Query(None),
    limit: int = Query(50),
):
    """List logged mileage trips."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    trips = tracker.list_trips(year=year, limit=limit)
    return _ok({"trips": trips, "count": len(trips), "total": tracker.trip_count})


# Pydantic model for mileage add
class MileageAddRequest(BaseModel):
    date: str
    miles: float
    purpose: str
    client: Optional[str] = ""
    start_odo: Optional[float] = 0.0
    end_odo: Optional[float] = 0.0
    route: Optional[str] = ""
    notes: Optional[str] = ""
    post_to_ledger: Optional[bool] = True


@app.post("/api/v1/mileage/add", dependencies=[Depends(check_auth)])
async def api_mileage_add(req: MileageAddRequest):
    """Log a business trip."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    trip = tracker.add_trip(
        date=req.date, miles=req.miles, purpose=req.purpose,
        client=req.client or "", start_odo=req.start_odo or 0.0,
        end_odo=req.end_odo or 0.0, route=req.route or "",
        notes=req.notes or "", post_to_ledger=req.post_to_ledger,
    )
    return _ok({
        "id": trip.id,
        "date": trip.date,
        "miles": trip.miles,
        "deduction": float(trip.deduction),
        "purpose": trip.purpose,
    })


@app.get("/api/v1/mileage/report", dependencies=[Depends(check_auth)])
async def api_mileage_report(year: Optional[int] = Query(None)):
    """Yearly mileage summary for tax purposes."""
    if year is None:
        year = datetime.date.today().year
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    report = tracker.yearly_report(year)
    return _ok(report)


# ── Accounts / Transfer / Reimbursement ────────────────────────────────────


@app.get("/api/v1/accounts", dependencies=[Depends(check_auth)])
async def api_accounts():
    """List all registered accounts with balances."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    data = ledger.registered_accounts()

    # Add configured cards
    data["cards"] = []
    for card_cfg in getattr(cfg, 'cards', []):
        bal = ledger.account_balance(card_cfg.account)
        data["cards"].append({
            "account": card_cfg.account,
            "name": card_cfg.name,
            "type": card_cfg.type,
            "balance": float(bal),
            "last_four": card_cfg.last_four or "",
        })
    return _ok(data)


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: float
    date: Optional[str] = None
    description: Optional[str] = "Transfer"


@app.post("/api/v1/transfer", dependencies=[Depends(check_auth)])
async def api_transfer(req: TransferRequest):
    """Transfer money between accounts."""
    from decimal import Decimal
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    ledger.transfer(
        date=txn_date,
        from_account=req.from_account,
        to_account=req.to_account,
        amount=Decimal(str(req.amount)),
        description=req.description or "Transfer",
    )
    ledger.reload(force=True)
    return _ok({
        "from": req.from_account,
        "to": req.to_account,
        "amount": req.amount,
        "date": txn_date.isoformat(),
    })


class ReimbursementRequest(BaseModel):
    amount: float
    merchant: str
    account: Optional[str] = "Expenses:Miscellaneous"
    date: Optional[str] = None


@app.post("/api/v1/reimburse", dependencies=[Depends(check_auth)])
async def api_reimburse(req: ReimbursementRequest):
    """Record a business expense paid from personal funds."""
    from decimal import Decimal
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    ledger.reimbursement(
        date=txn_date,
        merchant=req.merchant,
        amount=Decimal(str(req.amount)),
        expense_account=req.account or "Expenses:Miscellaneous",
    )
    ledger.reload(force=True)
    return _ok({
        "merchant": req.merchant,
        "amount": req.amount,
        "account": req.account or "Expenses:Miscellaneous",
        "date": txn_date.isoformat(),
    })


class SplitRequest(BaseModel):
    merchant: str
    total: float
    business: float
    account: Optional[str] = "Expenses:Miscellaneous"
    date: Optional[str] = None
    source: Optional[str] = None


@app.post("/api/v1/split", dependencies=[Depends(check_auth)])
async def api_split(req: SplitRequest):
    """Split a transaction between business and personal."""
    from decimal import Decimal
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    source = req.source or cfg.checking_account
    personal = req.total - req.business

    if personal > 0:
        postings = [
            (req.account or "Expenses:Miscellaneous", f"{req.business:.2f} USD"),
            ("Equity:OwnerDraws", f"{personal:.2f} USD"),
            (source, f"-{req.total:.2f} USD"),
        ]
    else:
        postings = [
            (req.account or "Expenses:Miscellaneous", f"{req.total:.2f} USD"),
            (source, f"-{req.total:.2f} USD"),
        ]

    entry = ledger.append(
        date=txn_date,
        payee=req.merchant,
        narration=f"Split: ${req.business:.2f} business, ${personal:.2f} personal",
        postings=postings,
    )
    ledger.reload(force=True)
    return _ok({
        "merchant": req.merchant,
        "total": req.total,
        "business": req.business,
        "personal": personal,
        "account": req.account or "Expenses:Miscellaneous",
    })


# ── Ledger Check ───────────────────────────────────────────────────────────


@app.get("/api/v1/check", dependencies=[Depends(check_auth)])
async def api_check():
    """Validate the Beancount ledger and return errors."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    errors = ledger.check()
    if not errors:
        return _ok({"valid": True, "error_count": 0, "errors": []})
    return _ok({
        "valid": False,
        "error_count": len(errors),
        "errors": [
            {
                "file": str(getattr(e, 'source', {}).get('filename', '?')),
                "line": getattr(e, 'source', {}).get('first_line', 0),
                "message": getattr(e, 'message', str(e)),
            }
            for e in errors[:50]
        ],
    })


# ── Receipt List (attached documents) ──────────────────────────────────────


@app.get("/api/v1/receipts/list", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def api_receipt_list(year: Optional[str] = Query(None)):
    """List all receipt documents attached to the ledger."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from .receipts import ReceiptScanner
    except ImportError:
        return _err("Receipt scanner not available", 500)

    scanner = ReceiptScanner(cfg)
    docs = scanner.list_attached(year=year or "")
    return _ok({"documents": docs, "count": len(docs)})


# ── Backup ─────────────────────────────────────────────────────────────────


@app.post("/api/v1/backup", dependencies=[Depends(check_auth)])
async def api_backup():
    """Commit and push ledger changes to git."""
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from .backup import Backup
    b = Backup(cfg)
    result = b.commit(quiet=True)
    return _ok(result)


# ── Setup (first-run wizard) ────────────────────────────────────────────────


class SetupRequest(BaseModel):
    name: str
    owner: str
    state: str
    ein: str = ""
    email: str = ""


@app.post("/api/v1/setup", dependencies=[Depends(check_auth)])
async def setup_business(req: SetupRequest):
    """First-run setup — configure the business and create initial accounts.

    Called from the web onboarding wizard after the user enters their
    business details. Writes config.toml and opens standard accounts.
    """
    config_path = os.environ.get("API_CONFIG", "")
    if not config_path:
        config_path = str(_PROJECT_ROOT / "config.toml")

    try:
        from .setup import write_business_config, init_ledger
    except ImportError:
        # Fallback inline setup
        import toml

        config_data = {
            "business": {
                "name": req.name,
                "owner": req.owner,
                "state": req.state,
                "ein": req.ein or "XX-XXXXXXX",
                "address": "",
                "phone": "",
                "email": req.email,
            },
            "ledger": {"path": "ledger/main.beancount"},
            "accounts": {
                "checking": "Assets:Bank:BusinessChecking",
                "ar": "Assets:AccountsReceivable",
                "income": "Income:Consulting",
                "owner_draws": "Equity:OwnerDraws",
            },
            "notifications": {"desktop_enabled": False, "email_enabled": False},
            "banking": {"plaid_enabled": False},
        }

        with open(config_path, "w") as f:
            toml.dump(config_data, f)

        # Create initial ledger with standard accounts
        ledger_dir = Path(config_path).parent / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()[:4]

        (ledger_dir / "main.beancount").write_text(
            f";; SoloLedger — {req.name}\n"
            f";; Auto-generated {datetime.date.today().isoformat()}\n"
            f"\n"
            f"{today}-01-01 open Assets:Bank:BusinessChecking\n"
            f"{today}-01-01 open Assets:AccountsReceivable\n"
            f"{today}-01-01 open Equity:OwnerDraws\n"
            f"{today}-01-01 open Income:Consulting\n"
            f"{today}-01-01 open Expenses:Software:SaaS\n"
            f"{today}-01-01 open Expenses:BankFees\n"
            f"{today}-01-01 open Liabilities:CreditCard\n"
        )
        (ledger_dir / "transactions.beancount").write_text(";; Transactions\n")
        (ledger_dir / "accounts.beancount").write_text(";; Account tree\n")

    return _ok({"status": "configured", "business": req.name, "state": req.state})


# ── Subscription management ──────────────────────────────────

PLANS = {
    "free": {"name": "Free", "price_monthly": 0, "price_annual": 0},
    "professional": {"name": "Professional", "price_monthly": 2400, "price_annual": 24000},  # $24/mo, $240/yr
    "business": {"name": "Business", "price_monthly": 5900, "price_annual": 59000},  # $59/mo, $590/yr
}


class CreateCheckoutRequest(BaseModel):
    plan: str = "professional"
    interval: str = "month"
    success_url: str = "/settings?upgraded=true"
    cancel_url: str = "/settings"


@app.post("/api/v1/subscription/create-checkout", dependencies=[Depends(check_auth)])
async def create_subscription_checkout(req: CreateCheckoutRequest):
    """Create a Stripe Checkout Session for a paid plan.

    Links the subscription to the current user's tenant.
    Requires STRIPE_SECRET_KEY env var.
    """
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return _err("Stripe not configured. Set STRIPE_SECRET_KEY.", 503)

    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    if req.plan not in PLANS:
        return _err(f"Unknown plan: {req.plan}", 400)

    plan_info = PLANS[req.plan]
    if req.interval not in ("month", "year"):
        return _err("Interval must be 'month' or 'year'", 400)

    price_cents = plan_info["price_annual"] if req.interval == "year" else plan_info["price_monthly"]

    # Build absolute URLs
    base_url = os.environ.get("APP_URL", f"http://localhost:8100")

    try:
        import stripe as stripe_lib

        # Find or create Stripe customer
        customer_id = tenant.get("stripe_customer_id", "")
        if not customer_id:
            customer = stripe_lib.Customer.create(email=tenant["email"], metadata={"user_id": tenant["user_id"]})
            customer_id = customer.id
            tenants = _load_tenants()
            if tenant["email"] in tenants:
                tenants[tenant["email"]]["stripe_customer_id"] = customer_id
                _save_tenants(tenants)

        session = stripe_lib.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"SoloLedger {plan_info['name']}",
                        "description": f"{plan_info['name']} plan — {req.interval}ly",
                    },
                    "unit_amount": price_cents,
                    "recurring": {"interval": req.interval, "interval_count": 1},
                },
                "quantity": 1,
            }],
            metadata={
                "plan": req.plan,
                "interval": req.interval,
                "user_id": tenant["user_id"],
                "email": tenant["email"],
            },
            success_url=base_url + req.success_url,
            cancel_url=base_url + req.cancel_url,
        )
        return _ok({"url": session.url, "session_id": session.id})
    except Exception as e:
        return _err(f"Stripe error: {e}", 500)


@app.get("/api/v1/subscription/plans", dependencies=[Depends(check_auth)])
async def list_plans():
    """List available subscription plans with pricing."""
    return _ok({
        "plans": {
            key: {
                "name": val["name"],
                "price_monthly": val["price_monthly"] / 100,
                "price_annual": val["price_annual"] / 100,
            }
            for key, val in PLANS.items()
        },
        "current_plan": (_current_tenant.get() or {}).get("plan", "free"),
    })


@app.get("/api/v1/subscription/status", dependencies=[Depends(check_auth)])
async def subscription_status():
    """Get the current user's subscription status and plan details."""
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    return _ok({
        "plan": tenant.get("plan", "free"),
        "status": tenant.get("status", "active"),
        "stripe_customer_id": bool(tenant.get("stripe_customer_id")),
        "stripe_subscription_id": tenant.get("stripe_subscription_id", ""),
        "email": tenant.get("email", ""),
    })


@app.post("/api/v1/subscription/portal", dependencies=[Depends(check_auth)])
async def billing_portal():
    """Create a Stripe Customer Portal session for managing the subscription."""
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return _err("Stripe not configured", 503)

    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    customer_id = tenant.get("stripe_customer_id", "")
    if not customer_id:
        return _err("No Stripe customer record. Subscribe first.", 400)

    base_url = os.environ.get("APP_URL", "http://localhost:8100")

    try:
        import stripe as stripe_lib
        session = stripe_lib.billing_portal.Session.create(
            customer=customer_id,
            return_url=base_url + "/settings",
        )
        return _ok({"url": session.url})
    except Exception as e:
        return _err(f"Stripe error: {e}", 500)


@app.post("/api/v1/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    """Stripe webhook — handle subscription lifecycle events.

    Events handled:
      - checkout.session.completed → activate plan
      - invoice.paid → confirm active status
      - customer.subscription.updated → plan changes
      - customer.subscription.deleted → downgrade to free

    Set STRIPE_WEBHOOK_SECRET for signature verification.
    """
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    import stripe as stripe_lib
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    dev_mode = os.environ.get("STRIPE_DEV_MODE", "").lower() in ("1", "true", "yes")

    if secret:
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig_header, secret)
        except stripe_lib.error.SignatureVerificationError:
            return _err("Invalid signature", 400)
    elif dev_mode:
        # Unsigned mode only for local development — explicitly opt in
        event = json.loads(payload)
    else:
        return _err("Stripe webhook secret not configured. Set STRIPE_WEBHOOK_SECRET, or set STRIPE_DEV_MODE=true for development.", 503)

    event_type = event["type"]
    data = event["data"]["object"]

    def _get_email(obj) -> str:
        """Extract email from various Stripe object shapes."""
        return (
            obj.get("customer_details", {}).get("email", "")
            or obj.get("customer_email", "")
            or obj.get("email", "")
        )

    def _update_tenant(email: str, updates: dict):
        tenants = _load_tenants()
        if email in tenants:
            tenants[email].update(updates)
            _save_tenants(tenants)

    def _find_tenant_by_customer(customer_id: str) -> str | None:
        """Find a tenant email by Stripe customer ID."""
        tenants = _load_tenants()
        for email, t in tenants.items():
            if t.get("stripe_customer_id") == customer_id:
                return email
        return None

    if event_type == "checkout.session.completed":
        email = _get_email(data)
        plan = data.get("metadata", {}).get("plan", "professional")
        sub_id = data.get("subscription", "")
        customer_id = data.get("customer", "")

        if email:
            _update_tenant(email, {
                "plan": plan,
                "status": "active",
                "stripe_subscription_id": sub_id or "",
                "stripe_customer_id": customer_id or "",
            })

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer", "")
        status = data.get("status", "active")
        items = data.get("items", {}).get("data", [])
        metadata = data.get("metadata", {})
        plan = metadata.get("plan", "professional")

        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {
                "plan": plan if status == "active" else "free",
                "status": status,
                "stripe_subscription_id": data.get("id", ""),
            })

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {
                "plan": "free",
                "status": "canceled",
                "stripe_subscription_id": "",
            })

    elif event_type == "invoice.paid":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            sub_id = data.get("subscription", "")
            _update_tenant(email, {
                "status": "active",
                "stripe_subscription_id": sub_id or "",
            })

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {"status": "past_due"})

    return _ok({"received": True, "event": event_type})


# ── Attention / Alerts ────────────────────────────────────────


@app.get("/api/v1/attention", dependencies=[Depends(check_auth)])
async def get_attention():
    """Return items needing the user's attention — overdue invoices,
    upcoming deadlines, uncategorized transactions, ledger errors."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(str(e), 500)

    items = []

    # Deadline info
    try:
        from .taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
        deadlines = taxer.deadline_info()
        for dl in deadlines["deadlines"][:3]:
            if dl["status"] in ("overdue", "upcoming"):
                items.append({
                    "type": "deadline",
                    "severity": "critical" if dl["status"] == "overdue" else "warning",
                    "label": dl["label"],
                    "detail": f"Due {dl['due']} ({dl['days_until']} days)",
                })
    except Exception:
        pass

    # Ledger errors
    try:
        errors = ledger.check()
        if errors:
            items.append({
                "type": "ledger",
                "severity": "critical",
                "label": f"Ledger has {len(errors)} error(s)",
                "detail": errors[0][:120],
            })
    except Exception:
        pass

    # No net income warning
    try:
        net = ledger.net_income()
        if net <= 0:
            items.append({
                "type": "no_income",
                "severity": "info",
                "label": "No income recorded yet",
                "detail": "Import transactions or create an invoice to get started.",
            })
    except Exception:
        pass

    # AR (overdue invoices)
    try:
        invoicer = Invoicer(cfg, ledger)
        ar = invoicer.check_ar()
        if ar.get("overdue_count", 0) > 0:
            items.append({
                "type": "overdue_invoices",
                "severity": "critical",
                "label": f"{ar['overdue_count']} overdue invoice(s)",
                "detail": f"${ar['estimated_overdue_amount']:,.2f} total overdue",
            })
    except Exception:
        pass

    return _ok({"items": items, "count": len(items)})


# ── Onboarding ────────────────────────────────────────────────


@app.get("/api/v1/onboarding/status", dependencies=[Depends(check_auth)])
async def onboarding_status():
    """Check if the current user has completed onboarding."""
    tenant = _current_tenant.get()
    if not tenant:
        return _ok({"needs_onboarding": True})

    complete = tenant.get("onboarding_complete", False)
    return _ok({
        "needs_onboarding": not complete,
        "has_ledger_data": False,  # checked below
    })


class OnboardingCompleteRequest(BaseModel):
    skipped_bank: bool = False
    skipped_import: bool = False


@app.post("/api/v1/onboarding/complete", dependencies=[Depends(check_auth)])
async def onboarding_complete(req: OnboardingCompleteRequest):
    """Mark onboarding as complete for the current user."""
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    tenants = _load_tenants()
    email = tenant["email"]
    if email in tenants:
        tenants[email]["onboarding_complete"] = True
        _save_tenants(tenants)

    return _ok({"onboarding_complete": True})


# ── LLM Settings ──────────────────────────────────────────────

_llm_settings_path: Optional[Path] = None


def _get_llm_settings_path():
    global _llm_settings_path
    if _llm_settings_path is None:
        try:
            cfg = get_config()
            _llm_settings_path = cfg.project_root / "llm_settings.json"
        except Exception:
            _llm_settings_path = _DATA_DIR / "llm_settings.json"
    return _llm_settings_path


class LlmSettingsRequest(BaseModel):
    api_key: Optional[str] = None
    backend: Optional[str] = None
    model: Optional[str] = None


@app.get("/api/v1/settings/llm", dependencies=[Depends(check_auth)])
async def get_llm_settings():
    """Get current LLM configuration (key is masked)."""
    settings_path = _get_llm_settings_path()
    config = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text())
        except Exception:
            pass

    # Mask the API key
    key = config.get("api_key", "")
    if key and len(key) > 8:
        config["api_key"] = key[:8] + "••••••••••"
    elif key:
        config["api_key"] = "••••••••••"

    return _ok({
        "backend": config.get("backend", os.environ.get("SL_LLM_BACKEND", "openai")),
        "model": config.get("model", os.environ.get("SL_LLM_MODEL", "")),
        "api_key_configured": bool(config.get("api_key") or os.environ.get("SL_LLM_API_KEY")),
        "api_key": config.get("api_key", ""),
    })


@app.post("/api/v1/settings/llm", dependencies=[Depends(check_auth)])
async def set_llm_settings(req: LlmSettingsRequest):
    """Save LLM configuration to server.

    Stores backend, model, and API key so AI features
    (categorization, receipt scanning, content) can use them.
    """
    settings_path = _get_llm_settings_path()
    config = {}
    if settings_path.exists():
        try:
            config = json.loads(settings_path.read_text())
        except Exception:
            pass

    # Merge: only update provided fields
    if req.api_key is not None:
        config["api_key"] = req.api_key if req.api_key else ""
    if req.backend is not None:
        config["backend"] = req.backend
    if req.model is not None:
        config["model"] = req.model if req.model else ""

    settings_path.write_text(json.dumps(config, indent=2))

    return _ok({
        "saved": True,
        "backend": config.get("backend", "openai"),
        "model": config.get("model", ""),
        "api_key_configured": bool(config.get("api_key")),
    })


# ── Run ─────────────────────────────────────────────────────────────────────


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", "8100"))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
