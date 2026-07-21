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

# Mount web UI
_web_dir = Path(__file__).resolve().parent.parent.parent / "web"
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
from . import subscriptions, settings

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


if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("API_PORT", 8100))
    uvicorn.run("app.api:app", host="0.0.0.0", port=port, reload=True)
