-- 001: Global app database — users, sessions, tenants, webhook dedup.
-- Per-tenant accounting data lives in each tenant's feature.db; this
-- database only holds account/session/billing state.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    name        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS users (
    email                TEXT PRIMARY KEY,
    password_hash        TEXT NOT NULL,
    name                 TEXT NOT NULL,
    created              TEXT NOT NULL,
    email_verified       INTEGER NOT NULL DEFAULT 0,
    verify_token         TEXT,
    verify_token_expires TEXT,
    reset_token          TEXT,
    reset_token_expires  TEXT
);

CREATE TABLE IF NOT EXISTS sessions (
    token      TEXT PRIMARY KEY,
    email      TEXT NOT NULL REFERENCES users(email) ON DELETE CASCADE,
    name       TEXT NOT NULL DEFAULT '',
    picture    TEXT NOT NULL DEFAULT '',
    method     TEXT NOT NULL DEFAULT 'local',
    created    TEXT NOT NULL,
    expires_at TEXT NOT NULL
);
CREATE INDEX idx_sessions_email ON sessions(email);
CREATE INDEX idx_sessions_expires ON sessions(expires_at);

CREATE TABLE IF NOT EXISTS tenants (
    email                   TEXT PRIMARY KEY REFERENCES users(email) ON DELETE CASCADE,
    user_id                 TEXT NOT NULL,
    name                    TEXT NOT NULL,
    plan                    TEXT NOT NULL DEFAULT 'free',
    status                  TEXT NOT NULL DEFAULT 'pending',  -- pending, active, past_due, canceled
    stripe_customer_id      TEXT NOT NULL DEFAULT '',
    stripe_subscription_id  TEXT NOT NULL DEFAULT '',
    ledger_dir              TEXT NOT NULL,
    created                 TEXT NOT NULL,
    trial_ends              TEXT NOT NULL DEFAULT '',
    onboarding_complete     INTEGER NOT NULL DEFAULT 0,
    plaid_access_token      TEXT NOT NULL DEFAULT ''
);
CREATE INDEX idx_tenants_stripe_customer ON tenants(stripe_customer_id);

-- Stripe event dedup (webhooks are retried and may arrive more than once)
CREATE TABLE IF NOT EXISTS webhook_events (
    event_id     TEXT PRIMARY KEY,
    event_type   TEXT NOT NULL,
    processed_at TEXT NOT NULL
);
