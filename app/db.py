"""SQLite metadata layer — per-tenant database for feature metadata.

Provides connection management, migration support, and common queries.
The Beancount ledger remains the source of truth for accounting data;
this database stores supporting metadata (import history, vendor receipts,
categorization rules, reconciliation state).

Usage:
    from app.db import get_db, get_tenant_db_path
    db = get_db(tenant_dir)        # Per-tenant database
    db.execute("SELECT ...")       # Returns sqlite3.Row objects
    db.migrate()                   # Apply pending migrations
"""
import os
import sqlite3
import hashlib
from pathlib import Path
from typing import Optional

_SCHEMA_DIR = Path(__file__).resolve().parent / "db_schema"


class TenantDB:
    """SQLite database for a single tenant's feature metadata.

    Creates the database in the tenant's ledger directory (alongside
    their Beancount files). Runs pending migrations on init.
    """

    def __init__(self, tenant_dir: str | Path, readonly: bool = False):
        self.db_path = Path(tenant_dir).resolve() / "feature.db"
        self.readonly = readonly
        self._conn: Optional[sqlite3.Connection] = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self._conn = self._connect()
            if not self.readonly:
                self.migrate()
        return self._conn

    def _connect(self) -> sqlite3.Connection:
        """Open or create the SQLite database."""
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        uri = f"file:{self.db_path}"
        if self.readonly:
            uri += "?mode=ro"
        conn = sqlite3.connect(uri, uri=True, check_same_thread=False)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA journal_mode=WAL")
        conn.execute("PRAGMA foreign_keys=ON")
        # Concurrent async requests share this connection; wait for the
        # write lock instead of erroring with "database is locked".
        conn.execute("PRAGMA busy_timeout=5000")
        conn.execute("PRAGMA synchronous=NORMAL")
        return conn

    def close(self):
        if self._conn:
            self._conn.close()
            self._conn = None

    # ── Migrations ────────────────────────────────────────────────────

    def migrate(self):
        """Apply all pending migrations in order.

        Each migration is applied inside a single transaction: the version
        row is written in the SAME transaction as the DDL, so a mid-script
        failure rolls everything back and the migration can safely re-run
        on the next boot. (executescript issues an implicit COMMIT first,
        so we apply statement-by-statement inside the transaction.)
        """
        applied = self._applied_versions()
        for sql_file in sorted(_SCHEMA_DIR.glob("[0-9]*_*.sql")):
            version = int(sql_file.stem.split("_", 1)[0])
            if version in applied:
                continue
            statements = [s.strip() for s in sql_file.read_text().split(";") if s.strip()]
            try:
                with self._conn:  # one transaction per migration
                    for stmt in statements:
                        self._conn.execute(stmt)
                    self._conn.execute(
                        "INSERT INTO schema_migrations (version, name) VALUES (?, ?)",
                        (version, sql_file.name),
                    )
            except sqlite3.Error as e:
                raise RuntimeError(f"Migration {sql_file.name} failed: {e}") from e

    def _applied_versions(self) -> set[int]:
        try:
            rows = self.conn.execute("SELECT version FROM schema_migrations")
            return {r["version"] for r in rows.fetchall()}
        except sqlite3.OperationalError:
            # schema_migrations table doesn't exist yet
            return set()

    def reset(self):
        """Drop all user tables and re-run migrations (for testing)."""
        if self._conn:
            self._conn.execute("PRAGMA foreign_keys=OFF")
            tables = self._conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
                " AND name NOT LIKE 'sqlite_%' AND name NOT LIKE 'schema_%'"
            ).fetchall()
            for t in tables:
                try:
                    self._conn.execute(f"DROP TABLE IF EXISTS \"{t['name']}\"")
                except sqlite3.OperationalError:
                    pass  # table may have been cascade-dropped
            self._conn.execute("DELETE FROM schema_migrations WHERE version > 0")
            self._conn.execute("PRAGMA foreign_keys=ON")
            self._conn.commit()
            self.migrate()

    # ── Query helpers ─────────────────────────────────────────────────

    def execute(self, sql: str, params=()):
        """Execute a query and return rows."""
        return self.conn.execute(sql, params)

    def executemany(self, sql: str, params_list):
        """Execute a statement against many parameter sets."""
        return self.conn.executemany(sql, params_list)

    def commit(self):
        self.conn.commit()

    # ── Convenience: fingerprinting ───────────────────────────────────

    @staticmethod
    def fingerprint(source: str, account: str, date: str, amount_cents: int, description: str) -> str:
        """Create a deterministic identity fingerprint for dedup.

        `source` is intentionally EXCLUDED from the identity: the same
        transaction imported from a second source (OFX → CSV → Plaid) must
        produce the same fingerprint so cross-source duplicates are
        detected instead of silently double-posted. The source is stored
        in the row itself.
        """
        key = f"{account}|{date}|{amount_cents}|{description[:40]}"
        return hashlib.sha256(key.encode()).hexdigest()[:32]


# ── Module-level helpers ───────────────────────────────────────────────

import threading as _threading

_active_dbs: dict[str, TenantDB] = {}
_dbs_lock = _threading.Lock()


def get_db(tenant_dir: str | Path | None = None) -> TenantDB:
    """Get or create a TenantDB for the given directory.

    Caches instances by path so the same DB isn't opened twice (the cache
    is lock-guarded so concurrent requests can't create two instances for
    the same path). If tenant_dir is None, uses the project root's data
    directory.
    """
    if tenant_dir is None:
        tenant_dir = Path(__file__).resolve().parent.parent / "data"
    path = str(Path(tenant_dir).resolve())
    with _dbs_lock:
        if path not in _active_dbs:
            _active_dbs[path] = TenantDB(path)
        return _active_dbs[path]


def get_tenant_db_path(cfg) -> Optional[str]:
    """Resolve the tenant directory from a Config object.

    Returns None if no ledger dir is configured (e.g. during tests).
    """
    try:
        return str(cfg.ledger_dir.resolve()) if cfg.ledger_dir else None
    except Exception:
        return None


def make_fingerprint(source: str, account: str, date: str, amount_cents: int, description: str) -> str:
    """Convenience wrapper for TenantDB.fingerprint."""
    return TenantDB.fingerprint(source, account, date, amount_cents, description)
