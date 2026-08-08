-- Cross-source duplicate warnings.
--
-- imported_transactions has UNIQUE(fingerprint): the same transaction
-- imported from a second source collides on the fingerprint and is
-- silently skipped. This table records those collisions so the API can
-- surface them for review (GET /import/duplicates). One row per
-- (fingerprint, attempted_source) to keep the log bounded.
CREATE TABLE IF NOT EXISTS duplicate_warnings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    fingerprint TEXT NOT NULL,
    existing_source TEXT NOT NULL,
    attempted_source TEXT NOT NULL,
    account TEXT NOT NULL,
    date TEXT NOT NULL,
    amount_cents INTEGER NOT NULL,
    description TEXT DEFAULT '',
    seen_at TEXT DEFAULT (datetime('now')),
    UNIQUE(fingerprint, attempted_source)
);
CREATE INDEX IF NOT EXISTS idx_dup_warnings_fingerprint ON duplicate_warnings(fingerprint);
