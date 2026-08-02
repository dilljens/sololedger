"""SoloLedger REST API — modular router package."""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Interactive docs (OpenAPI schema) expose every endpoint to anonymous
# callers. They're enabled in explicit open mode and local dev, disabled in
# authenticated deployments.
_docs_enabled = os.environ.get("SOLOLEDGER_DOCS", "").lower() in ("1", "true", "yes") or \
    os.environ.get("SOLOLEDGER_OPEN_MODE", "").lower() in ("1", "true", "yes") or \
    os.environ.get("ENV", "") == "development"

app = FastAPI(
    title="SoloLedger API",
    description="Self-hosted accounting, invoicing, and tax API for your consulting LLC.",
    version="0.4.0",
    docs_url="/docs" if _docs_enabled else None,
    redoc_url="/redoc" if _docs_enabled else None,
    openapi_url="/openapi.json" if _docs_enabled else None,
)

# CORS is locked down: same-origin by default (the web UI is served from
# this app). Cross-origin clients must opt in via CORS_ORIGINS (comma-
# separated). Wildcard + credentials is never allowed — browsers reject it
# and it widens the trust boundary for Bearer-token auth.
_cors_origins = [
    o.strip()
    for o in os.environ.get("CORS_ORIGINS", "").split(",")
    if o.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Web UI static files ──
_web_dir = Path(__file__).resolve().parent.parent.parent / "web"

# Dynamic JS serving through API route — prevents CDN caching
from fastapi.responses import FileResponse
_js_dir = _web_dir / "js"

@app.get("/api/v1/_js/{rest_of_path:path}")
async def serve_js(rest_of_path: str):
    """Serve JS files through API path so Cloudflare treats them as dynamic."""
    file_path = (_js_dir / rest_of_path).resolve()
    _js_root = _js_dir.resolve()
    if not (file_path == _js_root or file_path.is_relative_to(_js_root)):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Forbidden", status_code=403)
    if not file_path.exists() or not file_path.is_file():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Not Found", status_code=404)
    resp = FileResponse(file_path)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

# Mount web UI — serves web/ directory for both Vue and classic apps.
# Vue app at /app/ (index.html), classic app at /app/index-classic.html.
if _web_dir.exists():
    from fastapi.staticfiles import StaticFiles
    app.mount("/app", StaticFiles(directory=str(_web_dir), html=True), name="web")

# Register tenant middleware
from . import deps
app.middleware("http")(deps.tenant_middleware)

# Import and include all routers
from . import health, auth, invoices, taxes, banking, time_tracking
from . import retainers, notifications, receipts, reports, expenses
from . import mileage, accounts, reconciliation, attention, onboarding
from . import subscriptions, settings, payroll
from . import amazon, coa, rules, imports as import_routes

app.include_router(health.router)
app.include_router(auth.router)
app.include_router(invoices.router)
app.include_router(taxes.router)
app.include_router(banking.router)
app.include_router(time_tracking.router)
app.include_router(retainers.router)
app.include_router(notifications.router)
app.include_router(receipts.router)
app.include_router(reports.router)
app.include_router(expenses.router)
app.include_router(mileage.router)
app.include_router(accounts.router)
app.include_router(reconciliation.router)
app.include_router(attention.router)
app.include_router(onboarding.router)
app.include_router(subscriptions.router)
app.include_router(settings.router)
app.include_router(payroll.router)
app.include_router(amazon.router)
app.include_router(import_routes.router)
app.include_router(coa.router)
app.include_router(rules.router)


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8100))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
