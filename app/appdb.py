"""Global application database — users, sessions, tenants, webhook dedup.

The old JSON-file stores (users.json / sessions.json / tenants.json) were
not multi-worker safe (a per-process in-memory session dict meant >1 uvicorn
worker produced intermittent 401s) and could corrupt under concurrent
read-modify-write. This module replaces them with a single SQLite database
at <DATA_DIR>/app.db, serialized by a write lock.

Per-tenant accounting data stays in each tenant's feature.db; this database
only holds account/session/billing state.

Usage:
    from app import appdb
    user = appdb.get_user(email)
    appdb.create_session(token, email=email, name=name, method="local")
    appdb.update_tenant(email, plan="professional")
"""
import datetime
import os
import sqlite3
import threading
from pathlib import Path

_SCHEMA_DIR = Path(__file__).resolve().parent / "db_schema_app"

_write_lock = threading.RLock()
_conn: sqlite3.Connection | None = None


def db_path() -> Path:
    data_dir = Path(os.environ.get("SOLOLEDGER_DATA_DIR", str(Path(__file__).resolve().parent.parent)))
    return data_dir / "app.db"


def get_conn() -> sqlite3.Connection:
    """Get the shared app-database connection (created lazily, migrated)."""
    global _conn
    if _conn is None:
        path = db_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(path), check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute("PRAGMA busy_timeout=5000")
        _conn = conn
        migrate(conn)
        _migrate_legacy_json(conn)
    return _conn


def _migrate_legacy_json(conn: sqlite3.Connection):
    """One-time import of the pre-SaaS JSON stores (users.json /
    sessions.json / tenants.json) into the DB, if the DB is empty and the
    legacy files exist. Lets existing self-hosted installs keep their
    accounts and workspaces."""
    from pathlib import Path
    data_dir = Path(os.environ.get("SOLOLEDGER_DATA_DIR", str(Path(__file__).resolve().parent.parent)))

    count = conn.execute("SELECT count(*) AS c FROM users").fetchone()["c"]
    if count > 0:
        return  # DB already populated

    import json as _json

    users_path = data_dir / "users.json"
    tenants_path = data_dir / "tenants.json"
    sessions_path = data_dir / "sessions.json"

    users: dict = {}
    tenants: dict = {}
    sessions: dict = {}

    for path, dest in ((users_path, users), (tenants_path, tenants), (sessions_path, sessions)):
        if path.exists():
            try:
                data = _json.loads(path.read_text())
                if isinstance(data, dict):
                    dest.update(data)
            except (json.JSONDecodeError, OSError):
                pass

    if not users and not tenants and not sessions:
        return

    with _write_lock:
        with conn:
            for email, u in users.items():
                conn.execute(
                    "INSERT OR IGNORE INTO users (email, password_hash, name, created, email_verified)"
                    " VALUES (?, ?, ?, ?, 1)",
                    (email.lower(), u.get("password_hash", "") or u.get("password", ""),
                     u.get("name", ""), u.get("created", _now())),
                )
            for email, t in tenants.items():
                conn.execute(
                    "INSERT OR IGNORE INTO tenants (email, user_id, name, plan, status,"
                    " stripe_customer_id, stripe_subscription_id, ledger_dir, created,"
                    " trial_ends, onboarding_complete, plaid_access_token)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (email.lower(), t.get("user_id", ""), t.get("name", ""),
                     t.get("plan", "free"), t.get("status", "active"),
                     t.get("stripe_customer_id", ""), t.get("stripe_subscription_id", ""),
                     t.get("ledger_dir", ""), t.get("created", _now()),
                     t.get("trial_ends", ""), int(t.get("onboarding_complete", 0)),
                     t.get("plaid_access_token", "")),
                )
            for token, s in sessions.items():
                conn.execute(
                    "INSERT OR IGNORE INTO sessions (token, email, name, picture, method, created, expires_at)"
                    " VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (token, s.get("email", "").lower(), s.get("name", ""), s.get("picture", ""),
                     s.get("method", "local"), s.get("created", _now()),
                     _add_iso(30) if s.get("created") else _add_iso(30)),
                )
    # Keep the legacy files (harmless); the DB is now authoritative.


def migrate(conn: sqlite3.Connection):
    """Apply pending schema migrations (001_init.sql)."""
    applied = set()
    try:
        rows = conn.execute("SELECT version FROM schema_migrations").fetchall()
        applied = {r["version"] for r in rows}
    except sqlite3.OperationalError:
        pass  # table doesn't exist yet

    for sql_file in sorted(_SCHEMA_DIR.glob("[0-9]*_*.sql")):
        version = int(sql_file.stem.split("_", 1)[0])
        if version in applied:
            continue
        raw = sql_file.read_text()
        # Drop comment lines first — a semicolon inside a comment would
        # otherwise split the script mid-statement.
        statements = [
            s.strip()
            for s in "\n".join(
                line for line in raw.splitlines() if not line.strip().startswith("--")
            ).split(";")
            if s.strip()
        ]
        with conn:  # one transaction per migration
            for stmt in statements:
                conn.execute(stmt)
            conn.execute(
                "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                (version, sql_file.name),
            )


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _add_iso(days: int) -> str:
    return (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=days)).isoformat()


# ── Users ─────────────────────────────────────────────────────────────────

def _row_to_dict(row: sqlite3.Row | None) -> dict | None:
    return dict(row) if row is not None else None


def get_user(email: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM users WHERE email = ?", (email.lower(),)).fetchone()
    return _row_to_dict(row)


def create_user(email: str, password_hash: str, name: str,
                email_verified: bool = False, verify_token: str = "",
                verify_token_expires: str = "") -> dict:
    conn = get_conn()
    email = email.lower()
    with _write_lock:
        with conn:
            conn.execute(
                "INSERT INTO users (email, password_hash, name, created, email_verified,"
                " verify_token, verify_token_expires) VALUES (?, ?, ?, ?, ?, ?, ?)",
                (email, password_hash, name, _now(), int(email_verified),
                 verify_token, verify_token_expires or (_add_iso(1) if verify_token else "")),
            )
    return get_user(email)


def update_user(email: str, **fields) -> dict | None:
    """Update arbitrary user columns (verified columns only)."""
    allowed = {"name", "password_hash", "email_verified", "verify_token",
               "verify_token_expires", "reset_token", "reset_token_expires"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_user(email)
    conn = get_conn()
    with _write_lock:
        with conn:
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE users SET {sets} WHERE email = ?",
                         (*updates.values(), email.lower()))
    return get_user(email)


def all_users() -> dict[str, dict]:
    rows = get_conn().execute("SELECT * FROM users").fetchall()
    return {r["email"]: dict(r) for r in rows}


def get_user_by_verify_token(token: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM users WHERE verify_token = ?", (token,)
    ).fetchone()
    return _row_to_dict(row)


def get_user_by_reset_token(token: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM users WHERE reset_token = ?", (token,)
    ).fetchone()
    return _row_to_dict(row)


# ── Sessions ──────────────────────────────────────────────────────────────

def create_session(token: str, email: str, name: str = "", picture: str = "",
                   method: str = "local", ttl_days: int = 30) -> dict:
    conn = get_conn()
    email = email.lower()
    with _write_lock:
        with conn:
            conn.execute(
                "INSERT INTO sessions (token, email, name, picture, method, created, expires_at)"
                " VALUES (?, ?, ?, ?, ?, ?, ?)",
                (token, email, name, picture, method, _now(), _add_iso(ttl_days)),
            )
    return {"token": token, "email": email, "name": name, "picture": picture,
            "method": method, "created": _now()}


def get_session(token: str) -> dict | None:
    """Return the session if it exists and has not expired."""
    row = get_conn().execute(
        "SELECT * FROM sessions WHERE token = ?", (token,)
    ).fetchone()
    if row is None:
        return None
    expires = row["expires_at"] or ""
    try:
        if datetime.datetime.fromisoformat(expires) < datetime.datetime.now(datetime.timezone.utc):
            delete_session(token)  # expired — clean up
            return None
    except (ValueError, TypeError):
        return None
    return dict(row)


def delete_session(token: str):
    conn = get_conn()
    with _write_lock:
        with conn:
            conn.execute("DELETE FROM sessions WHERE token = ?", (token,))


def delete_sessions_for_user(email: str):
    conn = get_conn()
    with _write_lock:
        with conn:
            conn.execute("DELETE FROM sessions WHERE email = ?", (email.lower(),))


def all_sessions() -> dict[str, dict]:
    rows = get_conn().execute("SELECT * FROM sessions").fetchall()
    return {r["token"]: dict(r) for r in rows}


# ── Tenants ───────────────────────────────────────────────────────────────

def get_tenant(email: str) -> dict | None:
    row = get_conn().execute("SELECT * FROM tenants WHERE email = ?", (email.lower(),)).fetchone()
    return _row_to_dict(row)


def create_tenant_row(email: str, user_id: str, name: str, ledger_dir: str,
                      plan: str = "free", status: str = "pending",
                      trial_days: int = 0) -> dict:
    """Insert a tenant row.

    trial_days defaults to 0: a trial only starts when the tenant completes
    Stripe Checkout (card collected). New signups get the free tier until
    they subscribe — paid access requires email verification AND a card.
    """
    conn = get_conn()
    email = email.lower()
    trial_ends = _add_iso(trial_days) if trial_days else ""
    with _write_lock:
        with conn:
            conn.execute(
                "INSERT OR IGNORE INTO tenants (email, user_id, name, plan, status,"
                " stripe_customer_id, stripe_subscription_id, ledger_dir, created,"
                " trial_ends, onboarding_complete, plaid_access_token)"
                " VALUES (?, ?, ?, ?, ?, '', '', ?, ?, ?, 0, '')",
                (email, user_id, name, plan, status, ledger_dir, _now(), trial_ends),
            )
    return get_tenant(email)


def update_tenant(email: str, **fields) -> dict | None:
    """Update tenant columns (validated keys only)."""
    allowed = {"name", "plan", "status", "stripe_customer_id", "stripe_subscription_id",
               "ledger_dir", "trial_ends", "onboarding_complete", "plaid_access_token"}
    updates = {k: v for k, v in fields.items() if k in allowed}
    if not updates:
        return get_tenant(email)
    conn = get_conn()
    with _write_lock:
        with conn:
            sets = ", ".join(f"{k} = ?" for k in updates)
            conn.execute(f"UPDATE tenants SET {sets} WHERE email = ?",
                         (*updates.values(), email.lower()))
    return get_tenant(email)


def all_tenants() -> dict[str, dict]:
    rows = get_conn().execute("SELECT * FROM tenants").fetchall()
    return {r["email"]: dict(r) for r in rows}


def find_tenant_by_stripe_customer(customer_id: str) -> str | None:
    row = get_conn().execute(
        "SELECT email FROM tenants WHERE stripe_customer_id = ?", (customer_id,)
    ).fetchone()
    return row["email"] if row else None


def delete_tenant(email: str):
    conn = get_conn()
    with _write_lock:
        with conn:
            conn.execute("DELETE FROM tenants WHERE email = ?", (email.lower(),))


# ── Webhook idempotency ───────────────────────────────────────────────────

def mark_event_processed(event_id: str, event_type: str) -> bool:
    """Record a webhook event id. Returns True if newly processed, False if
    this event id was already seen (Stripe retries duplicates)."""
    conn = get_conn()
    with _write_lock:
        with conn:
            cur = conn.execute(
                "INSERT OR IGNORE INTO webhook_events (event_id, event_type, processed_at)"
                " VALUES (?, ?, ?)",
                (event_id, event_type, _now()),
            )
    return cur.rowcount > 0


def event_already_processed(event_id: str) -> bool:
    row = get_conn().execute(
        "SELECT 1 FROM webhook_events WHERE event_id = ?", (event_id,)
    ).fetchone()
    return row is not None
