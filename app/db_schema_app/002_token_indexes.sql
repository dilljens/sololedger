-- 002: Index verify/reset token lookups (auth flows scan by token)
CREATE INDEX IF NOT EXISTS idx_users_verify_token ON users(verify_token);
CREATE INDEX IF NOT EXISTS idx_users_reset_token ON users(reset_token);
