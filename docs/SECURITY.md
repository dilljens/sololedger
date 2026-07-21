# SoloLedger Security

## Authentication

SoloLedger supports three auth methods, configured via environment variables:

| Method | Env Var | Notes |
|--------|---------|-------|
| **Google OAuth** | `GOOGLE_CLIENT_ID` | Token verified server-side against Google's `tokeninfo` endpoint. Requires `GOOGLE_CLIENT_ID` to be set. |
| **Email/password** | (built-in) | Always active unless `API_KEYS` is set and `GOOGLE_CLIENT_ID` is unset (see below). Passwords hashed with PBKDF2-SHA256 (100k iterations, random salt). Stored in `users.json`. |
| **API keys** | `API_KEYS` | Comma-separated static keys prefixed with `sl_`. Stored in env var only. Keys authenticate via `Authorization: Bearer <key>`. |

When `GOOGLE_CLIENT_ID` is set, Google OAuth is the primary login and email/password signup is also available.
When only `API_KEYS` is set (no `GOOGLE_CLIENT_ID`), the app enters "API key mode" — email/password routes are unavailable and the session-based UI is not accessible.

## Token Storage (XSS Risk)

Session tokens, user profile data, and LLM API keys (OpenAI/Anthropic) are stored in **localStorage**:

| Key | Contents |
|-----|----------|
| `sololedger_session` | Random session token (32 bytes url-safe base64) |
| `sololedger_user` | User email, name, avatar URL (JSON) |
| `sololedger_llm_key` | LLM provider API key (OpenAI / Anthropic) |

**Risk:** localStorage is accessible to any JavaScript running on the same origin. A single XSS vulnerability (injected script, third-party CDN compromise, SVG upload, etc.) would allow an attacker to exfiltrate all stored tokens and API keys. This is a [known trade-off](https://owasp.org/www-community/vulnerabilities/Information_exposure_through_query_strings_in_url) for SPAs without a backend-for-frontend (BFF) proxy.

**Mitigations already in place:**
- `escapeHtml()` helper in `api.js` for safe DOM insertion
- No session token in URL query strings
- Tokens are short-lived (in-memory session map) though currently without an explicit expiry

**Recommendations for production:**
1. **Set `API_KEYS`** env var and **remove `GOOGLE_CLIENT_ID`** to disable email/password auth entirely, switching to API-key-only mode. This eliminates session storage in localStorage (API keys are held by the caller, not the browser).
2. **Add a Content-Security-Policy** header to restrict script sources.
3. **Implement session expiry** — session tokens currently live until the server process restarts.
4. **Use HTTPS** — without TLS, localStorage values and auth tokens are trivially intercepted on any network path.

## Environment Variables

The following environment variables carry secrets. None are hardcoded in the repository — all are read from `os.environ` at runtime.

| Env Var | Purpose |
|---------|---------|
| `API_KEYS` | Comma-separated static API keys for server-to-server access |
| `GOOGLE_CLIENT_ID` | Google OAuth client ID |
| `STRIPE_SECRET_KEY` | Stripe API key (payments) |
| `STRIPE_WEBHOOK_SECRET` | Stripe webhook signing secret |
| `PLAID_CLIENT_ID` / `PLAID_SECRET` / `PLAID_ACCESS_TOKEN` | Plaid bank feed credentials |
| `OPENAI_API_KEY` / `ANTHROPIC_API_KEY` | LLM provider keys (marketing, categorizer) |
| `SL_LLM_API_KEY` | Alternative LLM key for categorizer |
| `CLOCKIFY_API_KEY` / `TOGGL_API_TOKEN` | Time tracking integrations |
| `NOTIFY_SMTP_PASSWORD` | SMTP password for email notifications |

**Recommendation:** Use a secrets manager or `.env` file (not committed) in development. In production, inject via the orchestration platform (Docker secrets, Kubernetes secrets, systemd `EnvironmentFile=` with `0600` permissions).

## Production Checklist

- [ ] Set `API_KEYS` and unset `GOOGLE_CLIENT_ID` for API-key-only mode
- [ ] Enable HTTPS (reverse proxy with certbot/Let's Encrypt or cloud LB)
- [ ] Set a restrictive `Content-Security-Policy` header
- [ ] Use environment secrets (not config files) for all credentials
- [ ] Review `users.json` permissions — should be readable only by the app user
- [ ] Configure regular log rotation (session tokens logged in request logs)
