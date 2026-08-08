---
status: completed
kind: plan
area: security, ai-secret
author: AI
created: 2026-07-27
---

# Project: ai-secret — Security Hardening for Agent Access

**Goal:** Prevent LLM agents from reading secret values while preserving their ability to *use* secrets. Implement the capability-sealed pattern from the CapSeal paper: the LLM gets constrained action capabilities, not bearer credentials.

**Location:** `/home/dillon/_code/oh-my-agent/mcp/machine-context/ai_secret/cli.py`

---

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  LLM Agent                                                  │
│  Cannot: get, set, delete secrets                            │
│  Can:    exec <name> -- <cmd>   (subprocess, env injection) │
│          proxy <name> <method> <path>   (HTTP API calls)    │
│          check <name>              (health status only)       │
│          list                     (names, never values)       │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
┌─────────────────────────────────────────────────────────────┐
│  ai-secret                                                  │
│  - Reads encrypted value from disk (0600)                   │
│  - NEVER prints it to stdout when called by non-TTY         │
│  - For `exec`: injects as env var to subprocess             │
│  - For `proxy`: reads value, makes HTTP call, returns body  │
│  - Audits every operation                                   │
└─────────────────────────┬───────────────────────────────────┘
                          │
                          ▼
                  ┌───────────────┐
                  │  External API  │
                  │  (Stripe, etc.)│
                  └───────────────┘
```

**The LLM never sees the key.** In any scenario. Not via environment, not via stdout, not via error messages.

---

## Pre-resolved Decisions

| Decision | Rationale |
|----------|-----------|
| **Block `get` on non-TTY** | The simplest fix. Human at keyboard = allowed. AI pipeline = denied. |
| **Add `proxy` subcommand** | Universal HTTP proxy works with ANY API key. No per-service integration needed. |
| **Scope field becomes ACL** | Current `scope` is a text description. Change to a comma-separated permission list. |
| **`exec` stays unchanged** | Already secure — subprocess injection never leaks to caller. |
| **Audit all denials** | Every blocked `get` attempt gets logged so the user can investigate. |
| **Backward compatibility** | All existing commands work for humans. Restrictions only apply to non-interactive sessions. |

---

## Requirements

- [x] R1: `ai-secret get <name>` returns an error when stdin is not a TTY (agent context)
- [x] R2: `ai-secret proxy <name> GET /v1/customers` makes HTTP calls using the secret without exposing it
- [x] R3: Registry `scope` field supports machine-readable permissions: `exec`, `proxy`, `proxy:GET`, `check`
- [x] R4: `ai-secret list` shows scope/permissions in a glanceable format
- [x] R5: All denied operations are logged to audit trail
- [x] R6: `proxy` command works for any HTTP API key with configurable base URL and auth header format
- [x] R7: `--reason` is required for any non-TTY secret usage (already done for `get`)
- [x] R8: Error messages never leak the secret value or parts of it
- [x] R9: Tests covering TTY detection, proxy calls, scope enforcement, audit logging
- [x] R10: Existing functionality unchanged for TTY users

---

## Track A: Block `get` on Non-TTY `[x]`

**Description:** The `get` command is the primary leak vector. When called by an AI agent (non-interactive), it should hard-reject.

- 📏 Scope: ~1 file, ~30 lines changed

### Phase A1: TTY detection and enforcement `[x]`
- 🏷 Priority: **critical**
- 🔁 Max turns: 2
- [x] Add `_is_interactive()` helper: returns True only when stdin is a real TTY
- [x] Modify `cmd_get` to check interactivity before printing
- [x] Non-TTY get returns error: `"get requires an interactive terminal. Use 'exec' or 'proxy' instead."`
- [x] Audit log the denial attempt
- [x] Update `--help` text for `get` to mention TTY requirement
- ✅ Checkpoint: `echo "test" | ai-secret get stripe_key --reason "x"` → error
- ✅ Checkpoint: `ai-secret get stripe_key --reason "test"` (real TTY) → works as before

### Phase A2: Extend to `set` and `delete` `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 2
- [x] Apply the same TTY check to `set` (but allow `--stdin` with explicit override)
- [x] Apply TTY check to `delete` (but allow `--yes` with explicit override)
- [x] Update help text for all three commands
- ✅ Checkpoint: Non-TTY `set`, `delete`, `get` all produce clear error messages

---

## Track B: Registry Scope as ACL `[x]`

**Description:** The `scope` field in registry.toml is currently a free-text description. Change it to a structured permission list that controls what operations are allowed.

- 📏 Scope: ~1 file, ~50 lines changed

### Phase B1: Scope format `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 2
- [x] Define scope format: comma-separated keywords: `exec`, `proxy`, `proxy:GET`, `proxy:POST`, `check`
- [x] Add `_scope_allows(entry, permission)` helper
- [x] Default scope if missing: `"exec, proxy:GET"` (safe default — can execute and read-only API proxy)
- [x] Update `cmd_exec` to check scope before executing
- [x] Update `cmd_proxy` (will be built in Track C) to check scope
- [x] Update `cmd_check` (always allowed — health only)
- ✅ Checkpoint: Registry entry with `scope = "exec"` allows exec but rejects proxy:POST

### Phase B2: List display update `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 1
- [x] Show scope permissions in `ai-secret list` in a compact, readable format
- ✅ Checkpoint: `ai-secret list` shows `exec,proxy` instead of free-text description

---

## Track C: Proxy Subcommand `[x]`

**Description:** A universal HTTP proxy that lets the LLM make API calls without ever seeing the key. Works for ANY HTTP API. No per-service integration needed.

- 📏 Scope: ~1 file, ~100 lines

### Phase C1: Registry config for proxy `[x]`
- 🏷 Priority: **critical**
- 🔁 Max turns: 3
- [x] Define optional registry fields for proxy support:
  - `proxy_base = "https://api.stripe.com/v1"` — base URL
  - `proxy_auth = "Bearer"` — auth header type (`Bearer`, `Basic`, `Token`, or `custom:Prefix`)
  - `proxy_header = "Authorization"` — header name (default: Authorization)
- [x] These are optional — if not set, the user must provide `--base-url` on the command line
- [x] Update `_write_toml_entry` in register command to prompt for proxy config
- ✅ Checkpoint: Registry entry with `proxy_base` and `proxy_auth` configured

### Phase C2: `proxy` command implementation `[x]`
- 🏷 Priority: **critical**
- 🔁 Max turns: 5
- [x] Command signature: `ai-secret proxy <name> <method> <path> [--body <json>] [--base-url <url>]`
- [x] Flow:
  1. Resolve secret from registry + stored value
  2. Check scope allows `proxy` or `proxy:<METHOD>`
  3. Construct URL from `proxy_base` (registry) or `--base-url` (CLI)
  4. Add auth header using `proxy_auth` format
  5. Make HTTP request via `curl` subprocess or `urllib`
  6. Return response body to caller
  7. If response is JSON, print it (most common case)
  8. If binary, print content type hint and save to temp file
- [x] The secret NEVER appears in:
  - stdout (only the API response)
  - stderr (only progress/errors)
  - error messages (mask the key)
  - the URL (query params, never in path)
- [x] Audit log the request: method, path, status code, not the key
- [x] Support `--dry-run` to show what URL the proxy would call (without the auth header visible)
- ✅ Checkpoint: `ai-secret proxy stripe_key GET /v1/customers` returns Stripe customer list

### Phase C3: Error handling `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 2
- [x] HTTP errors (4xx/5xx): return error with status code, mask any key references in the body
- [x] Network errors: clear error message, no key exposure
- [x] Invalid secret name: standard registry error
- [x] Scope denial: clear message mentioning allowed scopes
- ✅ Checkpoint: All error paths tested

---

## Track D: Audit & Testing `[x]`

**Description:** Ensure all changes are tested and the audit trail captures everything.

- 📏 Scope: ~2 files, ~80 lines

### Phase D1: Tests `[x]`
- 🏷 Priority: high
- 🔁 Max turns: 3
- [x] Mock TTY detection for testing
- [x] Test: non-TTY `get` is blocked
- [x] Test: TTY `get` works
- [x] Test: `proxy` with valid secret returns API response
- [x] Test: `proxy` with invalid auth returns error
- [x] Test: scope enforcement (exec-only secret rejects proxy)
- [x] Test: audit log entries for get denials and proxy calls
- [x] Run existing tests to confirm no regressions
- ✅ Checkpoint: `python -m pytest tests/test_secret.py -v` — all pass

### Phase D2: Documentation `[x]`
- 🏷 Priority: medium
- 🔁 Max turns: 2
- [x] Update `--help` for all modified commands
- [x] Add `proxy` section to docs
- [x] Document scope format in registry docs
- [x] Note: this replaces direct `get` usage for all AI agents
- ✅ Checkpoint: `ai-secret --help` shows accurate, up-to-date information

---

## Progress

| Phase | Status |
|-------|--------|
| A1: Block `get` on non-TTY | `[x]` |
| A2: Extend to `set` and `delete` | `[x]` |
| B1: Scope format and enforcement | `[x]` |
| B2: List display update | `[x]` |
| C1: Registry config for proxy | `[x]` |
| C2: `proxy` command implementation | `[x]` |
| C3: Error handling | `[x]` |
| D1: Tests | `[x]` |
| D2: Documentation | `[x]` |
