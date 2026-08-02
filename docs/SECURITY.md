# SoloLedger Security

SoloLedger is a multi-tenant SaaS: every account gets an isolated workspace
(its own Beancount ledger + SQLite metadata DB under `SOLOLEDGER_DATA_DIR/ledgers/<user_id>/`),
and paid features are gated by plan + billing status.

## Authentication

| Method | Env Var | Notes |
|--------|---------|-------|
| **Email/password** | (built-in) | Always available. PBKDF2-SHA256 (100k iterations, random salt). Requires **email verification** before the workspace is provisioned. |
| **Google OAuth** | `GOOGLE_CLIENT_ID` | ID token verified server-side against Google's `tokeninfo`; requires `email_verified=true` in the token. Creates a verified user + tenant directly. |
| **API keys** | `API_KEYS` | Comma-separated static keys for server-to-server access. Bearer auth, no tenant (owner scope). |

**Auth is fail-closed.** Unauthenticated access is denied unless
`SOLOLEDGER_OPEN_MODE=true` is set — an explicit opt-in for open (demo)
deployments. Never set it in production.

**Signup flow (production):**
1. `POST /auth/signup` creates an *unverified* user and emails a verification
   link (Resend). No workspace is provisioned yet — this blocks signup spam.
2. `GET /auth/verify-email?token=...` marks the email verified and provisions
   the isolated tenant workspace.
3. Paid access additionally requires a **card on file**: `POST
   /subscription/create-checkout` opens Stripe Checkout with a 14-day trial
   (`trial_period_days`), collecting the card before any paid feature unlocks.

When `RESEND_API_KEY` is not configured and `SOLOLEDGER_REQUIRE_EMAIL_VERIFY`
is not set, signup auto-verifies (development / test mode only).

## Session & Data Storage

Sessions, users, and tenants live in a **global SQLite database**
(`<SOLOLEDGER_DATA_DIR>/app.db`) — multi-worker safe. Per-tenant accounting
data (Beancount files, `feature.db`, statement documents) lives under the
tenant's ledger directory, which is confined to `SOLOLEDGER_DATA_DIR`.

| Store | Location | Notes |
|-------|----------|-------|
| users / sessions / tenants | `app.db` (SQLite) | sessions expire after 30 days, enforced on every request; password reset invalidates all sessions |
| tenant ledger | `<DATA_DIR>/ledgers/<user_id>/` | Beancount files + config |
| tenant metadata | `<DATA_DIR>/ledgers/<user_id>/feature.db` | imports, receipts, rules, reconciliation marks, usage counters |
| statement documents | `<tenant>/documents/statements/` | per-tenant (never the process CWD) |

The **browser** stores the session token in `localStorage`
(`auth_token` / `sololedger_session`) — accessible to any same-origin JS, so
XSS = token theft. The `escapeHtml()` helper, CSP headers, and server-side
session validation are the mitigations.

## Multi-tenancy

- Every request resolves the caller's tenant from the session → the tenant's
  `config.toml` and `feature.db`. A non-owner session with no tenant is 403.
- Tenant `ledger_dir` is validated with `is_relative_to(SOLOLEDGER_DATA_DIR)`
  (no string-prefix bypass).
- Plan gating: `require_plan()` checks plan level AND billing status
  (`past_due`/`canceled`/`suspended` drops to free; an active trial grants
  Professional). Free tier has usage caps (10 invoices, 5 receipt scans/mo)
  enforced in the tenant DB.
- Plaid access tokens are per-tenant; the global env token is owner-only.
- LLM settings are per-tenant.

## Admin

`/api/v1/admin/*` (list tenants, tenant detail, cancel, deprovision, stats)
requires `Authorization: Bearer $ADMIN_API_KEY`. When `ADMIN_API_KEY` is
unset the routes return 404.

## Environment Variables (secrets)

| Env Var | Purpose |
|---------|---------|
| `ADMIN_API_KEY` | Bearer token for `/api/v1/admin/*` |
| `STRIPE_SECRET_KEY` / `STRIPE_WEBHOOK_SECRET` | Stripe API + webhook signing secret (webhooks ALWAYS verified) |
| `RESEND_API_KEY` | Transactional email (verification, password reset) |
| `GOOGLE_CLIENT_ID` | Google OAuth |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` / `PLAID_ACCESS_TOKEN` | Plaid bank feeds |
| `API_KEYS` | Server-to-server API keys (owner scope) |
| `SOLOLEDGER_DATA_DIR` | Where app.db + tenant ledgers live (must be a persistent volume in Docker) |

None are hardcoded — all read from `os.environ`. Inject via secrets manager,
Docker secrets, or systemd `EnvironmentFile=` with `0600` permissions.

## Production Checklist

- [x] Fail-closed auth (open mode requires explicit `SOLOLEDGER_OPEN_MODE=true`)
- [x] Email verification required for new accounts
- [x] Card required for paid plans (Stripe Checkout trial captures the card)
- [x] Stripe webhook signature verification (no dev-mode bypass)
- [x] Webhook idempotency (event-id dedup)
- [x] Free-tier usage caps (invoices, receipt scans)
- [x] Session expiry (30 days, per request) + password-reset session revocation
- [x] CORS locked down (`CORS_ORIGINS`), docs disabled outside open mode
- [x] Upload size caps (25 MB) + zip/PDF bomb guards
- [x] Persistent volume for `SOLOLEDGER_DATA_DIR` in Docker (accounts survive rebuilds)
- [ ] HTTPS (reverse proxy / Let's Encrypt)
- [ ] Restrictive `Content-Security-Policy` (present in the SPA; verify after deploy)
- [ ] Regular log rotation (do not log Bearer tokens)
- [ ] Backups of `SOLOLEDGER_DATA_DIR` (off-site; `app/backup.py` covers ledger/config)
