"""Shared dependencies for API route modules."""
import contextvars
import datetime
import hashlib
import os
import secrets
import shutil
import threading
import time
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, Depends, Request
from fastapi.responses import JSONResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials

from .. import appdb
from ..config import Config

# ── Data paths (always relative to project root, not CWD) ───
# SOLOLEDGER_DATA_DIR overrides the data root (used by tests to isolate
# sessions/users/tenants/ledgers from the repo).

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = Path(os.environ.get("SOLOLEDGER_DATA_DIR", str(_PROJECT_ROOT)))

# ── Auth ─────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

# ── Auth posture ─────────────────────────────────────────────────
# Auth is FAIL-CLOSED: an unauthenticated request is rejected unless the
# operator explicitly opts into open mode. This prevents a deployment that
# forgets to configure API keys / Google OAuth from silently exposing the
# whole ledger to the internet.

_SESSION_MAX_AGE = datetime.timedelta(days=30)


def _is_open_mode() -> bool:
    """Explicit open (no-auth demo) mode — opt-in via SOLOLEDGER_OPEN_MODE=true."""
    return os.environ.get("SOLOLEDGER_OPEN_MODE", "").lower() in ("1", "true", "yes")


def _session_valid(token: str) -> bool:
    """A token is valid only if it exists and is younger than _SESSION_MAX_AGE.

    Backed by the app database (multi-worker safe) and enforced on every
    request, so expired or stolen tokens stop working even on long-running
    servers.
    """
    session = appdb.get_session(token)
    if session is None:
        return False
    created = session.get("created", "")
    try:
        created_dt = datetime.datetime.fromisoformat(created)
    except (ValueError, TypeError):
        return False
    return datetime.datetime.now(datetime.timezone.utc) - created_dt <= _SESSION_MAX_AGE


# ── Rate limiting (in-memory sliding window) ────────────────────

_RATE_WINDOW_SECONDS = 15 * 60  # 15 minutes
_RATE_MAX_ATTEMPTS = 20          # attempts per window per client
_rate_attempts: dict[str, list[float]] = {}
_rate_lock = threading.Lock()


def _rate_limited(client_key: str) -> bool:
    """Record an attempt for client_key; True if the client is over the limit."""
    now = time.time()
    with _rate_lock:
        # Prevent unbounded growth: occasionally drop fully-expired keys
        if len(_rate_attempts) > 4096:
            _rate_attempts.clear()
        attempts = _rate_attempts.setdefault(client_key, [])
        attempts[:] = [t for t in attempts if now - t < _RATE_WINDOW_SECONDS]
        if len(attempts) >= _RATE_MAX_ATTEMPTS:
            return True
        attempts.append(now)
        return False


def _client_ip(request: Request) -> str:
    """Best-effort client IP for rate limiting."""
    fwd = request.headers.get("x-forwarded-for", "")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


# ── Upload hardening ────────────────────────────────────────────
# Uploads are read fully into memory by the parsers, so cap their size to
# prevent memory-exhaustion DoS. Also reject unexpected content types.

MAX_UPLOAD_BYTES = 25 * 1024 * 1024  # 25 MB


class UploadTooLarge(HTTPException):
    def __init__(self):
        super().__init__(status_code=413, detail=f"Upload exceeds {MAX_UPLOAD_BYTES // (1024 * 1024)} MB limit")


async def _read_upload(file, max_bytes: int = MAX_UPLOAD_BYTES) -> bytes:
    """Read an UploadFile into memory with a hard size cap.

    Reads in chunks so an oversized upload is rejected without ever being
    buffered in full. Raise UploadTooLarge (413) when over the cap.
    """
    chunks = []
    total = 0
    while True:
        chunk = await file.read(1024 * 1024)  # 1 MB at a time
        if not chunk:
            break
        total += len(chunk)
        if total > max_bytes:
            raise UploadTooLarge()
        chunks.append(chunk)
    return b"".join(chunks)


_api_keys_env = os.environ.get("API_KEYS", "")
_valid_api_keys = [k.strip() for k in _api_keys_env.split(",") if k.strip()] if _api_keys_env else []

# ── Built-in user store (email/password) ────────────────────
# DB-backed (app.db) — the old users.json is replaced. Kept names match the
# previous dict interface so route modules don't change.

_json_lock = threading.RLock()  # kept for compat; DB has its own write lock


def _load_users() -> dict:
    """All users as {email: user_dict}."""
    return appdb.all_users()


def _save_users(users: dict):
    """Replace all users with the given dict (transactional)."""
    conn = appdb.get_conn()
    with _json_lock:
        with conn:
            conn.execute("DELETE FROM users")
            for email, u in users.items():
                conn.execute(
                    "INSERT INTO users (email, password_hash, name, created, email_verified,"
                    " verify_token, verify_token_expires, reset_token, reset_token_expires)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (email.lower(), u.get("password_hash", ""), u.get("name", ""),
                     u.get("created", ""), int(u.get("email_verified", 0)),
                     u.get("verify_token", ""), u.get("verify_token_expires", ""),
                     u.get("reset_token", ""), u.get("reset_token_expires", "")),
                )


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


def _load_tenants() -> dict:
    """All tenants as {email: tenant_dict}."""
    return appdb.all_tenants()


def _save_tenants(tenants: dict):
    """Replace all tenants with the given dict (transactional)."""
    conn = appdb.get_conn()
    with _json_lock:
        with conn:
            conn.execute("DELETE FROM tenants")
            for email, t in tenants.items():
                conn.execute(
                    "INSERT INTO tenants (email, user_id, name, plan, status,"
                    " stripe_customer_id, stripe_subscription_id, ledger_dir, created,"
                    " trial_ends, onboarding_complete, plaid_access_token)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (email.lower(), t.get("user_id", ""), t.get("name", ""),
                     t.get("plan", "free"), t.get("status", "pending"),
                     t.get("stripe_customer_id", ""), t.get("stripe_subscription_id", ""),
                     t.get("ledger_dir", ""), t.get("created", ""),
                     t.get("trial_ends", ""), int(t.get("onboarding_complete", 0)),
                     t.get("plaid_access_token", "")),
                )


def _tenant_dir(user_id: str) -> Path:
    return _DATA_DIR / "ledgers" / user_id


def _generate_tenant_config(email: str, name: str) -> str:
    """Generate a complete tenant config.toml (includes the [tax] section)."""
    from ..config import generate_config_toml
    return generate_config_toml(name=name, owner=name, email=email)


def create_tenant(email: str, name: str = "") -> dict:
    """Create a new tenant with an isolated ledger directory.

    Idempotent (returns the existing tenant). The tenant row lives in
    app.db; the ledger files in <DATA_DIR>/ledgers/<user_id>/.
    """
    existing = appdb.get_tenant(email)
    if existing:
        return existing

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

    appdb.create_tenant_row(
        email=email, user_id=user_id, name=display_name,
        ledger_dir=str(tdir), plan="free", status="pending",
    )
    return appdb.get_tenant(email)


def resolve_email_from_token(token: str) -> Optional[str]:
    """Extract user email from any token (session, API key)."""
    session = appdb.get_session(token)
    if session:
        return session.get("email", "")
    if _valid_api_keys and token in _valid_api_keys:
        return "api-key-user"
    return None


_current_email: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_email", default=None)


async def tenant_middleware(request: Request, call_next):
    """Resolve tenant from auth token or session for the current request.

    Sets _current_tenant and _current_email for use by get_config(),
    require_plan(), and the email-based tenant guards. Reads the session
    from app.db so sessions work across uvicorn workers.
    """
    from app.api.deps import _current_tenant, _current_email, _valid_api_keys

    tenant = None
    email = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        session = appdb.get_session(token)
        if session:
            email = session.get("email", "")
            tenant = appdb.get_tenant(email)
        elif _valid_api_keys and token in _valid_api_keys:
            pass  # Global API key — no specific tenant
    _current_tenant.set(tenant)
    _current_email.set(email)
    response = await call_next(request)
    return response


# ── Tenant-aware Config ────────────────────────────────────

def get_config() -> Config:
    """Load Config for the current tenant, falling back to main config.

    The tenant ledger_dir is confined to the data root (SOLOLEDGER_DATA_DIR,
    which defaults to the project root when unset) via an exact containment
    check (is_relative_to, not a string-prefix check), so a tenant cannot
    point its config at a sibling directory. Tenant ledgers are created
    under the data root by create_tenant(), so this is the correct boundary
    for both self-hosted (project root) and SaaS (/data volume) installs.

    When no tenant is resolved, the main config is served only to
    unauthenticated (open-mode) requests, the global API key, or the
    owner's own session email — never to an arbitrary authenticated user.
    """
    tenant = _current_tenant.get()
    if tenant:
        tdir = Path(tenant["ledger_dir"]).resolve()
        data_root = _DATA_DIR.resolve()
        if not (tdir == data_root or tdir.is_relative_to(data_root)):
            raise HTTPException(status_code=403, detail="Tenant ledger_dir is outside data root")
        cfg_path = tdir / "config.toml"
        if cfg_path.exists():
            try:
                return Config(str(cfg_path))
            except Exception as e:
                raise HTTPException(status_code=500, detail=f"Tenant config load failed: {e}")

    # No tenant: fall back to main config only for the owner's own email.
    email = _current_email.get()
    if email and not _is_owner_email(email):
        raise HTTPException(status_code=403, detail="Account has no provisioned workspace")

    # Fallback: main config (open mode / admin / owner)
    config_path = os.environ.get("API_CONFIG")
    try:
        return Config(config_path)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Config load failed: {e}")


def _is_owner_email(email: str) -> bool:
    """True when the email matches the main config's business email.

    Lets the owner's own session reach the repo-root ledger (self-hosted
    single-tenant path) while every other authenticated user must have a
    provisioned tenant.
    """
    try:
        cfg = Config(os.environ.get("API_CONFIG"))
        owner = getattr(cfg, "email", "") or ""
        return email.lower() == owner.lower()
    except Exception:
        return False


PLAN_ORDER = {"free": 0, "professional": 1, "business": 2}


def get_plan() -> str:
    """Get the plan name for the current tenant. 'free' if no tenant."""
    tenant = _current_tenant.get()
    if tenant:
        return tenant.get("plan", "free")
    return "free"


def _tenant_effective_level(tenant: dict) -> int:
    """Effective plan level for a tenant, considering status and trial.

    - 'active' status: full plan level
    - an active trial grants professional level
    - 'past_due' / 'canceled' / 'pending': paid levels revoked (free only)
    """
    plan = tenant.get("plan", "free")
    status = tenant.get("status", "active")
    level = PLAN_ORDER.get(plan, 0)

    if status in ("past_due", "canceled", "suspended"):
        return 0  # billing problem → paid features off

    if level < 1:
        trial_ends = tenant.get("trial_ends", "")
        if trial_ends:
            try:
                ends = datetime.datetime.fromisoformat(trial_ends)
                if ends > datetime.datetime.now(datetime.timezone.utc):
                    level = 1  # trial = professional access
            except (ValueError, TypeError):
                pass
    return level


def require_plan(min_plan: str):
    """Dependency: require a minimum plan level to access an endpoint.

    Plans (in order): free < professional < business
    Users with an active trial get professional-level access. Tenants whose
    billing is in trouble (past_due/canceled) are dropped to free.
    """
    min_level = PLAN_ORDER.get(min_plan, 0)

    def _check():
        tenant = _current_tenant.get()
        if not tenant:
            return  # open mode / owner — allow all
        effective_level = _tenant_effective_level(tenant)

        if effective_level < min_level:
            raise HTTPException(
                status_code=402,
                detail=f"Upgrade to {min_plan} plan required",
            )
    return _check


# ── Free-tier usage caps ──────────────────────────────────────────────
# Free tenants get a monthly allowance on a few metered features (receipt
# scans). Paid tenants are unlimited. Counters live in the tenant DB.

FREE_RECEIPT_SCANS_PER_MONTH = 5
FREE_MAX_INVOICES = 10


def _tenant_db_for_current() -> Optional[object]:
    """Resolve the current tenant's feature.db (or None in open mode)."""
    tenant = _current_tenant.get()
    if not tenant:
        return None
    try:
        from ..db import get_db
        return get_db(Path(tenant["ledger_dir"]))
    except Exception:
        return None


def _usage_bucket(name: str, period: str) -> str:
    return f"{name}:{period}"


def usage_count(db, name: str, period: str) -> int:
    """Current usage counter value for a bucket (0 if none)."""
    try:
        row = db.execute(
            "SELECT count FROM usage_counts WHERE bucket = ?",
            (_usage_bucket(name, period),),
        ).fetchone()
        return row["count"] if row else 0
    except Exception:
        return 0


def increment_usage(db, name: str, period: str) -> int:
    """Increment a usage counter; returns the new count."""
    bucket = _usage_bucket(name, period)
    try:
        db.execute(
            "INSERT INTO usage_counts (bucket, count) VALUES (?, 1) "
            "ON CONFLICT(bucket) DO UPDATE SET count = count + 1",
            (bucket,),
        )
        db.commit()
        return usage_count(db, name, period)
    except Exception:
        return 0


def enforce_free_cap(name: str, cap: int, db=None, detail: str = ""):
    """Dependency-usable check: free tenants are capped, paid tenants free.

    Raises 402 when a free tenant is at/over the cap. Returns True when
    the request may proceed (no tenant / paid tenant / under cap).
    """
    tenant = _current_tenant.get()
    if not tenant:
        return True  # open mode / owner
    if _tenant_effective_level(tenant) > 0:
        return True  # paid or trial — unlimited
    if db is None:
        db = _tenant_db_for_current()
    if db is None:
        return True
    now = datetime.datetime.now(datetime.timezone.utc)
    period = now.strftime("%Y-%m")
    if usage_count(db, name, period) >= cap:
        raise HTTPException(status_code=402, detail=detail or f"Free plan limited to {cap} per month")
    return True


def check_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Check auth: API key, session token, or explicit open mode.

    Fail-closed: unauthenticated access requires SOLOLEDGER_OPEN_MODE=true
    to be explicitly set. Session tokens are validated for age on every
    request (DB-backed, multi-worker safe).
    """
    if _is_open_mode():
        return  # explicitly-opened demo mode

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    if _valid_api_keys and token in _valid_api_keys:
        return

    if _session_valid(token):
        return

    raise HTTPException(status_code=403, detail="Invalid or expired token")


# ── response helpers ────────────────────────────────────────

def _ok(data: dict, status_code: int = 200):
    """Standard success envelope."""
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


def _err(msg: str, status_code: int = 400):
    """Standard error envelope."""
    return JSONResponse({"success": False, "error": msg}, status_code=status_code)
