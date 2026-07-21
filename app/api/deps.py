"""Shared dependencies for API route modules."""
import contextvars
import datetime
import hashlib
import json
import os
import secrets
import shutil
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from ..config import Config

# ── Data paths (always relative to project root, not CWD) ───

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = _PROJECT_ROOT

# ── Auth ─────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

_sessions: dict[str, dict] = {}

_api_keys_env = os.environ.get("API_KEYS", "")
_valid_api_keys = [k.strip() for k in _api_keys_env.split(",") if k.strip()] if _api_keys_env else []

# ── Built-in user store (email/password) ────────────────────

_USERS_PATH = _DATA_DIR / "users.json"


def _load_users() -> dict:
    if _USERS_PATH.exists():
        try:
            return json.loads(_USERS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_users(users: dict):
    _USERS_PATH.write_text(json.dumps(users, indent=2))


def _hash_password(password: str) -> str:
    salt = secrets.token_hex(16)
    h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
    return f"{salt}:{h.hex()}"


def _verify_password(password: str, stored: str) -> bool:
    try:
        salt, hsh = stored.split(":", 1)
        h = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), 100_000)
        return h.hex() == hsh
    except (ValueError, TypeError):
        return False


# ── Multi-tenant store ─────────────────────────────────────

_current_tenant: contextvars.ContextVar[dict | None] = contextvars.ContextVar("current_tenant", default=None)

_TENANTS_PATH = _DATA_DIR / "tenants.json"


def _load_tenants() -> dict:
    if _TENANTS_PATH.exists():
        try:
            return json.loads(_TENANTS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_tenants(tenants: dict):
    _TENANTS_PATH.write_text(json.dumps(tenants, indent=2))


def _tenant_dir(user_id: str) -> Path:
    return _DATA_DIR / "ledgers" / user_id


def _generate_tenant_config(email: str, name: str) -> str:
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
        "ledger_dir": str(tdir),
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
        "trial_ends": "",
        "onboarding_complete": False,
        "plaid_access_token": "",
    }
    tenants[email] = tenant
    _save_tenants(tenants)
    return tenant


def resolve_email_from_token(token: str) -> Optional[str]:
    """Extract user email from any token (session, API key)."""
    if token in _sessions:
        return _sessions[token].get("email", "")
    if _valid_api_keys and token in _valid_api_keys:
        return "api-key-user"
    return None


async def tenant_middleware(request: Request, call_next):
    """Resolve tenant from auth token or session for the current request.

    Sets _current_tenant for use by get_config() and require_plan().
    """
    from app.api.deps import _current_tenant, _load_tenants, _sessions, _valid_api_keys

    tenant = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _sessions and token in _sessions:
            email = _sessions[token].get("email", "")
            tenants = _load_tenants()
            tenant = tenants.get(email)
        elif _valid_api_keys and token in _valid_api_keys:
            pass  # Global API key — no specific tenant
    _current_tenant.set(tenant)
    response = await call_next(request)
    return response


# ── Tenant-aware Config ────────────────────────────────────

def get_config() -> Config:
    """Load Config for the current tenant, falling back to main config."""
    tenant = _current_tenant.get()
    if tenant:
        tdir = Path(tenant["ledger_dir"]).resolve()
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
    """
    PLAN_ORDER = {"free": 0, "professional": 1, "business": 2}
    min_level = PLAN_ORDER.get(min_plan, 0)

    def _check():
        tenant = _current_tenant.get()
        if not tenant:
            return  # open mode — allow all
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
        return  # open mode — no auth needed

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    if _valid_api_keys and token in _valid_api_keys:
        return

    if _sessions and token in _sessions:
        return

    raise HTTPException(status_code=403, detail="Invalid or expired token")


# ── response helpers ────────────────────────────────────────

def _ok(data: dict, status_code: int = 200):
    """Standard success envelope."""
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


def _err(msg: str, status_code: int = 400):
    """Standard error envelope."""
    return JSONResponse({"success": False, "error": msg}, status_code=status_code)
