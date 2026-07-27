# Findings: Comprehensive Testing & Receipt Verification

## Environment State (as of 2026-07-25)

### Installed (via `.venv`)
| Dependency | Status | Version |
|------------|--------|---------|
| beancount | ✅ | 3.2.3 |
| fastapi | ✅ | 0.139.2 |
| pdfplumber | ✅ | 0.11.10 |
| pillow | ✅ | 12.3.0 |
| playwright | ✅ | 1.61.0 |
| pytest-playwright | ✅ | 0.8.0 |
| python-multipart | ✅ | 0.0.32 |
| pydantic | ✅ | 2.13.4 |

### Missing
| Dependency | Status | Impact |
|------------|--------|--------|
| pytesseract | ❌ | **Image OCR fails silently** — `_extract_image()` catches `ImportError`, returns `""`, scan returns `"No text could be extracted"` |
| Playwright browsers | ✅ | Chromium 1228 installed at `~/.cache/ms-playwright/` |

### Test Suite
- **104 tests, all passing** via `.venv/bin/python -m pytest tests/ -q`
- `tests/e2e/` directory **does not exist** (referenced in CI + pyproject.toml)
- **Zero test coverage for receipt scanner or receipt API endpoints**

## Root Cause: "Take Image" Not Working

The user clicked "📸 Capture Receipt" → "📷 Take Photo or Upload", selected a photo, and "nothing happened." The root cause:

1. **`pytesseract` is not installed** in the venv
2. `ReceiptScanner._extract_image()` does `import pytesseract`, gets `ImportError`, returns `""`
3. `scan()` checks `if not raw_text.strip():` → returns `{"success": False, "error": "No text could be extracted from the receipt"}`
4. The API returns `{"success": False, "error": "No text could be extracted from the receipt"}`
5. JS catch handler shows `⚠ No text could be extracted from the receipt` in the preview div

The user likely saw a brief spinner ("Scanning receipt...") followed by a subtle error line and didn't register it.

### Secondary Risks
- **Plan gating**: Receipt endpoints require `require_plan("professional")` — in open mode (no `API_KEYS`/`GOOGLE_CLIENT_ID`) this is bypassed, but if either env var is set, free-tier users get HTTP 402
- **30s timeout**: Large photos may time out `apiFetch`'s 30s limit
- **JS catch message**: The error div appears inside `#receipt-result` which may not be prominent enough

## Pre-resolved Decisions

| Decision | Rationale |
|----------|-----------|
| **Use `.venv/bin/python` and `.venv/bin/pip`** for all commands | System Python is PEP 668 locked, venv has all deps |
| **Tests live in `tests/` for unit, `tests/e2e/` for Playwright** | Follows existing pyproject.toml marker config |
| **Receipt tests use `FastAPI TestClient`** | Consistent with existing `test_api.py` pattern |
| **E2E tests use `pytest-playwright` marker** | Existing `@pytest.mark.e2e` marker already configured in pyproject.toml |
| **Server lifecycle fixture for E2E** | Start uvicorn as subprocess on random port, same as the (never-created) original e2e plan |
| **Test receipt scanner with synthetic text** | Avoid needing actual receipt images; test regex parser with known strings |
| **Test image OCR with a generated test image** | Create a small PNG with known text using Pillow, then verify OCR extracts it |
| **Verify with a real JPEG photo** | Use a real camera photo as final manual verification step |

## Scope Boundaries

| In scope | Out of scope |
|----------|-------------|
| Install pytesseract & verify OCR | Refactoring receipt JS to use event delegation |
| Write ReceiptScanner unit tests | Fixing service worker / PWA issues |
| Write receipt API endpoint tests | Adding new receipt features |
| Create E2E tests for all pages | Fixing UI audit items (accessibility, etc.) |
| Manually verify receipt capture flow | Database migration or config changes |
| Fix any bugs found during testing | Adding receipt support for non-Professional plans |
