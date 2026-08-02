"""Shared dependencies for API route modules."""
import contextvars
import datetime
import hashlib
import json
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

from ..config import Config

# ── Data paths (always relative to project root, not CWD) ───
# SOLOLEDGER_DATA_DIR overrides the data root (used by tests to isolate
# sessions/users/tenants/ledgers from the repo).

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
_DATA_DIR = Path(os.environ.get("SOLOLEDGER_DATA_DIR", str(_PROJECT_ROOT)))

# ── Auth ─────────────────────────────────────────────────────

security = HTTPBearer(auto_error=False)

GOOGLE_CLIENT_ID = os.environ.get("GOOGLE_CLIENT_ID", "")

_SESSIONS_PATH = _DATA_DIR / "sessions.json"

_sessions: dict[str, dict] = {}

# Serialize all JSON-store reads-modify-writes so concurrent requests
# (logins, signups, webhooks) can't lose updates or corrupt the file.
_json_lock = threading.RLock()


def _atomic_write_json(path: Path, data: dict):
    """Write a JSON dict atomically (temp file + rename) under a lock."""
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=2))
    os.replace(tmp, path)


def _load_sessions() -> dict[str, dict]:
    """Load sessions from disk. Called once at module init."""
    if _SESSIONS_PATH.exists():
        try:
            data: dict = json.loads(_SESSIONS_PATH.read_text())
            # Only keep sessions under 30 days old
            now = datetime.datetime.now(datetime.timezone.utc)
            cutoff = now - datetime.timedelta(days=30)
            fresh = {}
            for token, info in data.items():
                created = info.get("created", "")
                if created:
                    try:
                        ct = datetime.datetime.fromisoformat(created)
                        if ct < cutoff:
                            continue  # expired
                    except (ValueError, TypeError):
                        pass
                fresh[token] = info
            return fresh
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_sessions():
    """Persist sessions to disk (atomic, locked)."""
    with _json_lock:
        _atomic_write_json(_SESSIONS_PATH, _sessions)


# Load persisted sessions on startup
_sessions = _load_sessions()

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

    Enforced on every request (not just at module load), so expired or
    stolen tokens stop working even on long-running servers.
    """
    info = _sessions.get(token)
    if not info:
        return False
    created = info.get("created", "")
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

_USERS_PATH = _DATA_DIR / "users.json"


def _load_users() -> dict:
    if _USERS_PATH.exists():
        try:
            return json.loads(_USERS_PATH.read_text())
        except (json.JSONDecodeError, OSError):
            return {}
    return {}


def _save_users(users: dict):
    with _json_lock:
        _atomic_write_json(_USERS_PATH, users)


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
    with _json_lock:
        _atomic_write_json(_TENANTS_PATH, tenants)


def _tenant_dir(user_id: str) -> Path:
    return _DATA_DIR / "ledgers" / user_id


def _generate_tenant_config(email: str, name: str) -> str:
    """Generate a complete tenant config.toml (includes the [tax] section)."""
    from ..config import generate_config_toml
    return generate_config_toml(name=name, owner=name, email=email)


def create_tenant(email: str, name: str = "") -> dict:
    """Create a new tenant with an isolated ledger directory.

    Held under the JSON-store lock so two concurrent signups with the same
    email can't race (double user_id, orphan dirs, lost update).
    """
    with _json_lock:
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

        trial_end = datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=14)
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
            "trial_ends": trial_end.isoformat(),
            "onboarding_complete": True,  # template has sample data, skip onboarding
            "plaid_access_token": "",
        }
        tenants[email] = tenant
        _save_tenants(tenants)
        return tenant


def resolve_email_from_token(token: str) -> Optional[str]:
    """Extract user email from any token (session, API key)."""
    if token in _sessions and _session_valid(token):
        return _sessions[token].get("email", "")
    if _valid_api_keys and token in _valid_api_keys:
        return "api-key-user"
    return None


_current_email: contextvars.ContextVar[str | None] = contextvars.ContextVar("current_email", default=None)


async def tenant_middleware(request: Request, call_next):
    """Resolve tenant from auth token or session for the current request.

    Sets _current_tenant and _current_email for use by get_config(),
    require_plan(), and the email-based tenant guards.
    """
    from app.api.deps import _current_tenant, _current_email, _load_tenants, _sessions, _valid_api_keys, _session_valid

    tenant = None
    email = None
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if _sessions and token in _sessions and _session_valid(token):
            email = _sessions[token].get("email", "")
            tenants = _load_tenants()
            tenant = tenants.get(email)
        elif _valid_api_keys and token in _valid_api_keys:
            pass  # Global API key — no specific tenant
    _current_tenant.set(tenant)
    _current_email.set(email)
    response = await call_next(request)
    return response


# ── Tenant-aware Config ────────────────────────────────────

def get_config() -> Config:
    """Load Config for the current tenant, falling back to main config.

    The tenant ledger_dir is confined to the project root via an exact
    containment check (is_relative_to, not a string-prefix check), so a
    tenant cannot point its config at a sibling directory.

    When no tenant is resolved, the main config is served only to
    unauthenticated (open-mode) requests, the global API key, or the
    owner's own session email — never to an arbitrary authenticated user.
    """
    tenant = _current_tenant.get()
    if tenant:
        tdir = Path(tenant["ledger_dir"]).resolve()
        project_root = _PROJECT_ROOT.resolve()
        if not (tdir == project_root or tdir.is_relative_to(project_root)):
            raise HTTPException(status_code=403, detail="Tenant ledger_dir is outside project root")
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


def get_plan() -> str:
    """Get the plan name for the current tenant. 'free' if no tenant."""
    tenant = _current_tenant.get()
    if tenant:
        return tenant.get("plan", "free")
    return "free"


def require_plan(min_plan: str):
    """Dependency: require a minimum plan level to access an endpoint.

    Plans (in order): free < professional < business
    Users with an active trial period get the professional plan level.
    """
    PLAN_ORDER = {"free": 0, "professional": 1, "business": 2}
    min_level = PLAN_ORDER.get(min_plan, 0)

    def _check():
        tenant = _current_tenant.get()
        if not tenant:
            return  # open mode — allow all
        user_plan = tenant.get("plan", "free")
        effective_level = PLAN_ORDER.get(user_plan, 0)

        # Active trial grants professional-level access
        if effective_level < 1:
            trial_ends = tenant.get("trial_ends", "")
            if trial_ends:
                try:
                    ends = datetime.datetime.fromisoformat(trial_ends)
                    if ends > datetime.datetime.now(datetime.timezone.utc):
                        effective_level = 1  # trial = professional access
                except (ValueError, TypeError):
                    pass

        if effective_level < min_level:
            days_left = ""
            if user_plan == "free":
                trial_ends = tenant.get("trial_ends", "")
                if trial_ends:
                    try:
                        ends = datetime.datetime.fromisoformat(trial_ends)
                        remaining = (ends - datetime.datetime.now(datetime.timezone.utc)).days
                        if remaining > 0:
                            days_left = f" ({remaining} days left in trial)"
                    except (ValueError, TypeError):
                        pass

            raise HTTPException(
                status_code=402,
                detail=f"Upgrade to {min_plan} plan required{days_left}",
            )
    return _check


def check_auth(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
):
    """Check auth: API key, session token, or explicit open mode.

    Fail-closed: unauthenticated access requires SOLOLEDGER_OPEN_MODE=true
    to be explicitly set. Session tokens are validated for age on every
    request.
    """
    if _is_open_mode():
        return  # explicitly-opened demo mode

    if credentials is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    token = credentials.credentials

    if _valid_api_keys and token in _valid_api_keys:
        return

    if _sessions and token in _sessions and _session_valid(token):
        return

    raise HTTPException(status_code=403, detail="Invalid or expired token")


# ── response helpers ────────────────────────────────────────

def _ok(data: dict, status_code: int = 200):
    """Standard success envelope."""
    return JSONResponse({"success": True, "data": data}, status_code=status_code)


def _err(msg: str, status_code: int = 400):
    """Standard error envelope."""
    return JSONResponse({"success": False, "error": msg}, status_code=status_code)
