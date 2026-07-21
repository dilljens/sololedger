"""Retainer routes."""
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..invoice import Invoicer, RetainerConfig
from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config
from .shared import _decimal_to_float

router = APIRouter(prefix="/api/v1")


class RetainerRequest(BaseModel):
    client: str
    description: str
    amount: float
    interval: str = "monthly"
    day_of_month: int = 1
    stripe_recurring: bool = False


@router.get("/retainers", dependencies=[Depends(check_auth)])
async def list_retainers():
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    invoicer = Invoicer(cfg, Ledger(cfg))
    retainers = invoicer.list_retainers()

    return _ok({
        "retainers": [
            {
                "id": rid,
                "client": r["client"],
                "description": r["description"],
                "amount": float(r["amount"]),
                "interval": r["interval"],
                "last_invoiced": r.get("last_invoiced"),
                "next_invoice": r.get("next_invoice"),
            }
            for rid, r in retainers.items()
        ]
    })


@router.post("/retainers", dependencies=[Depends(check_auth)])
async def add_retainer(req: RetainerRequest):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    invoicer = Invoicer(cfg, Ledger(cfg))
    retainer_cfg = RetainerConfig(
        client=req.client,
        description=req.description,
        amount=Decimal(str(req.amount)).quantize(Decimal("0.01")),
        interval=req.interval,
        day_of_month=req.day_of_month,
        stripe_recurring=req.stripe_recurring,
    )

    info = invoicer.save_retainer(retainer_cfg)

    return _ok({
        "id": info["id"],
        "client": info["client"],
        "description": info["description"],
        "amount": float(info["amount"]),
        "interval": info["interval"],
        "next_invoice": info["next_invoice"],
    })


@router.post("/retainers/process", dependencies=[Depends(check_auth)])
async def process_retainers(preview: bool = Query(True)):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Error: {e}", 500)

    results = invoicer.process_retainers(preview=preview)
    return _ok({
        "preview": preview,
        "invoices_due": len(results),
        "invoices": [
            {
                "client": r.get("client"),
                "amount": float(r.get("amount", 0)),
                "invoice_number": r.get("number"),
                "preview": r.get("preview", True),
            }
            for r in results
        ],
    })
