"""Time tracking routes."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..invoice import Invoicer
from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config, require_plan

router = APIRouter(prefix="/api/v1")


class TimeFetchRequest(BaseModel):
    source: str = "toggl"
    days: int = 7
    hourly_rate: Optional[float] = None
    billable_only: bool = True


class TimeInvoiceRequest(TimeFetchRequest):
    client: Optional[str] = None
    no_preview: bool = False


@router.post("/time/entries", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def time_entries(req: TimeFetchRequest):
    try:
        from ..time_tracking import TimeTracker
    except ImportError:
        return _err("Time tracking module not available", 500)

    hourly = Decimal(str(req.hourly_rate)).quantize(Decimal("0.01")) if req.hourly_rate else None
    tracker = TimeTracker(source=req.source, hourly_rate=hourly)

    entries = tracker.fetch_entries(days_back=req.days, billable_only=req.billable_only)
    summary = tracker.summarize_by_client(entries, hourly_rate=hourly)

    return _ok({
        "entry_count": summary["entry_count"],
        "total_hours": summary["total_hours"],
        "total_amount": float(summary["total_amount"]),
        "by_client": {
            client: {
                "hours": data["hours"],
                "amount": float(data["amount"]),
            }
            for client, data in summary["by_client"].items()
        },
        "entries": [
            {
                "description": e.description,
                "project": e.project,
                "hours": e.hours,
                "billable": e.billable,
            }
            for e in entries[:100]
        ],
    })


@router.post("/time/invoice", dependencies=[Depends(check_auth)])
async def time_to_invoice(req: TimeInvoiceRequest):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..time_tracking import TimeTracker
    except Exception as e:
        return _err(f"Error: {e}", 500)

    hourly = Decimal(str(req.hourly_rate)).quantize(Decimal("0.01")) if req.hourly_rate else None
    tracker = TimeTracker(source=req.source, hourly_rate=hourly)

    entries = tracker.fetch_entries(days_back=req.days)
    invoice_data = tracker.generate_invoice_data(entries, client_filter=req.client)

    if not invoice_data:
        return _err("No time entries found for the given filter", 404)

    if req.no_preview:
        invoicer = Invoicer(cfg, ledger)
        result = invoicer.create(
            client=invoice_data["client"],
            description=invoice_data["description"],
            amount=invoice_data["amount"],
        )
        return _ok({
            "invoice_created": True,
            "invoice_number": result["number"],
            "client": invoice_data["client"],
            "amount": float(invoice_data["amount"]),
            "hours": invoice_data["entries"]["total_hours"],
            "preview": False,
        })
    else:
        return _ok({
            "invoice_created": False,
            "preview": True,
            "client": invoice_data["client"],
            "amount": float(invoice_data["amount"]),
            "description": invoice_data["description"],
            "hours": invoice_data["entries"]["total_hours"],
            "entry_count": invoice_data["entries"]["entry_count"],
        })
