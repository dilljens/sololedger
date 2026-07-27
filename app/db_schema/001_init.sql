-- 001: Initial metadata schema
-- Core tables for feature metadata, import tracking, and vendor receipts.

CREATE TABLE IF NOT EXISTS schema_migrations (
    version     INTEGER PRIMARY KEY,
    applied_at  TEXT NOT NULL DEFAULT (datetime('now')),
    name        TEXT NOT NULL
);

-- Track all import operations (Plaid, OFX, CSV, etc.)
CREATE TABLE IF NOT EXISTS import_batches (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    source      TEXT NOT NULL,          -- 'plaid', 'ofx', 'csv', 'citi', 'wave', 'amazon'
    account     TEXT,                   -- Beancount account imported into
    filename    TEXT,                   -- Original filename (for file imports)
    status      TEXT NOT NULL DEFAULT 'pending',  -- pending, preview, committed, failed
    stats       TEXT,                   -- JSON blob: {imported, skipped, errors}
    actor       TEXT,                   -- Who/what triggered this import
    created_at  TEXT NOT NULL DEFAULT (datetime('now')),
    committed_at TEXT
);

-- Fingerprinted transaction records for cross-source dedup
CREATE TABLE IF NOT EXISTS imported_transactions (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    batch_id        INTEGER REFERENCES import_batches(id),
    source          TEXT NOT NULL,      -- 'plaid', 'ofx', 'csv', 'citi', 'wave', 'amazon'
    account         TEXT NOT NULL,      -- Beancount account
    external_id     TEXT,               -- Source's own ID (Plaid txn id, etc.)
    date            TEXT NOT NULL,      -- ISO date
    amount_cents    INTEGER NOT NULL,   -- Amount in cents (positive = debit)
    description     TEXT NOT NULL DEFAULT '',
    fingerprint     TEXT NOT NULL,       -- SHA256(source, account, date, amount_cents, description_prefix)
    UNIQUE(fingerprint)
);

CREATE INDEX idx_imported_txns_fingerprint ON imported_transactions(fingerprint);
CREATE INDEX idx_imported_txns_batch ON imported_transactions(batch_id);

-- Vendor receipts (Amazon orders, uploaded PDFs, etc.)
CREATE TABLE IF NOT EXISTS vendor_receipts (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    vendor          TEXT NOT NULL,      -- 'amazon', 'receipt_scan', etc.
    source_id       TEXT,               -- Vendor's order/receipt ID
    external_ref    TEXT,               -- Original filename or URL
    receipt_date    TEXT,               -- ISO date
    merchant        TEXT,
    total_cents     INTEGER,            -- Total in cents
    currency        TEXT NOT NULL DEFAULT 'USD',
    raw_json        TEXT,               -- Raw vendor data (JSON blob)
    schema_version  TEXT,               -- SHA fingerprint of parser schema
    status          TEXT NOT NULL DEFAULT 'pending',  -- pending, categorized, committed, error
    actor           TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    UNIQUE(vendor, source_id)
);

CREATE TABLE IF NOT EXISTS vendor_receipt_items (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    receipt_id      INTEGER NOT NULL REFERENCES vendor_receipts(id) ON DELETE CASCADE,
    description     TEXT NOT NULL,
    quantity        REAL DEFAULT 1,
    unit_price_cents INTEGER,
    total_cents     INTEGER NOT NULL,
    coa_account     TEXT,               -- Beancount account (null until assigned)
    is_personal     INTEGER DEFAULT 0,  -- 1 = personal expense, not business
    is_reimbursable INTEGER DEFAULT 0,  -- 1 = client-reimbursable
    sort_order      INTEGER DEFAULT 0
);

CREATE INDEX idx_vri_receipt ON vendor_receipt_items(receipt_id);

-- Link vendor receipt items to Beancount transactions
CREATE TABLE IF NOT EXISTS transaction_receipt_links (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    transaction_date TEXT NOT NULL,     -- Beancount transaction date
    txn_payee       TEXT,               -- Beancount transaction payee
    receipt_item_id INTEGER NOT NULL REFERENCES vendor_receipt_items(id) ON DELETE CASCADE,
    receipt_id      INTEGER NOT NULL REFERENCES vendor_receipts(id) ON DELETE CASCADE,
    created_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

-- Categorization rules (port from Accounting)
CREATE TABLE IF NOT EXISTS categorization_rules (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    kind            TEXT NOT NULL DEFAULT 'pattern',  -- 'pattern', 'semantic'
    matcher_type    TEXT NOT NULL DEFAULT 'substring', -- 'regex', 'substring', 'eq', 'range'
    pattern         TEXT NOT NULL,
    target_account  TEXT NOT NULL,
    priority        INTEGER NOT NULL DEFAULT 0,
    is_active       INTEGER NOT NULL DEFAULT 1,
    description     TEXT,
    created_at      TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at      TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE INDEX idx_cr_active_priority ON categorization_rules(is_active, priority);

-- Reconciliation marks (soft-lock for reconciled transactions)
CREATE TABLE IF NOT EXISTS reconciliation_marks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    account         TEXT NOT NULL,
    statement_date  TEXT NOT NULL,      -- statement period end date
    balance_cents   INTEGER,            -- statement closing balance
    reconciled_at   TEXT NOT NULL DEFAULT (datetime('now')),
    notes           TEXT,
    UNIQUE(account, statement_date)
);

-- Feature flags (per-tenant feature enablement)
CREATE TABLE IF NOT EXISTS feature_flags (
    feature         TEXT PRIMARY KEY,
    enabled         INTEGER NOT NULL DEFAULT 0,
    config_json     TEXT
);
