"""SoloLedger REST API — modular router package."""
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(
    title="SoloLedger API",
    description="Self-hosted accounting, invoicing, and tax API for your consulting LLC.",
    version="0.3.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── Web UI static files ──
_web_dir = Path(__file__).resolve().parent.parent.parent / "web"

# Landing page at root
from fastapi.responses import FileResponse as FR, HTMLResponse

_landing_html = _web_dir / "landing.html"

@app.get("/")
async def landing_page():
    """Serve the landing page."""
    if _landing_html.exists():
        return FR(str(_landing_html))
    return HTMLResponse("<h1>SoloLedger</h1><p><a href='/app/'>Launch App</a></p>")

_project_root = Path(__file__).resolve().parent.parent.parent

@app.get("/deploy.sh")
async def deploy_script():
    """Serve the one-command deploy script."""
    # Serve from web/ directory (inside Docker container at /app/web/)
    deploy_sh = _web_dir / "deploy.sh"
    if deploy_sh.exists():
        resp = FR(str(deploy_sh), media_type="text/x-shellscript")
        resp.headers["Content-Type"] = "text/x-shellscript"
        return resp
    return HTMLResponse("deploy.sh not found", status_code=404)

# Dynamic JS serving through API route — prevents CDN caching
_js_dir = _web_dir / "js"

@app.get("/api/v1/_js/{rest_of_path:path}")
async def serve_js(rest_of_path: str):
    """Serve JS files through API path so Cloudflare treats them as dynamic."""
    file_path = (_js_dir / rest_of_path).resolve()
    _js_root = _js_dir.resolve()
    if not str(file_path).startswith(str(_js_root)):
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Forbidden", status_code=403)
    if not file_path.exists() or not file_path.is_file():
        from fastapi.responses import PlainTextResponse
        return PlainTextResponse("Not Found", status_code=404)
    resp = FR(file_path)
    resp.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    return resp

# Mount web UI (for HTML, CSS, images — non-JS static assets)
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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8100))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
