-- 002: Usage counters for free-tier caps (receipt scans/month, etc.)
CREATE TABLE IF NOT EXISTS usage_counts (
    bucket  TEXT PRIMARY KEY,   -- e.g. 'receipt_scan:2026-08'
    count   INTEGER NOT NULL DEFAULT 0
);
