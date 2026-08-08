-- Per-tenant API keys — long-lived credentials for the remote CLI
-- (`llc --api URL --token <key>`). Scoped to exactly one tenant (email),
-- revocable, and only the SHA-256 hash is stored (the plaintext key is
-- returned once at creation and never again).
CREATE TABLE IF NOT EXISTS api_keys (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    key_hash TEXT NOT NULL UNIQUE,
    prefix TEXT NOT NULL,
    email TEXT NOT NULL,
    name TEXT DEFAULT '',
    created TEXT NOT NULL,
    last_used TEXT DEFAULT '',
    expires_at TEXT DEFAULT '',
    active INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_api_keys_email ON api_keys(email);
