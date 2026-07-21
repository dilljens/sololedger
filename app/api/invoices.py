"""Invoice routes."""
import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from ..invoice import Invoicer
from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config
from .shared import _decimal_to_float

router = APIRouter(prefix="/api/v1")


class InvoiceCreateRequest(BaseModel):
    client: str
    description: str
    amount: float
    date: Optional[str] = None
    due_days: int = 30
    generate_pdf: bool = True
    payment_link: bool = False
    client_email: Optional[str] = None
    recurring: Optional[str] = None


class MarkInvoicePaidRequest(BaseModel):
    amount: Optional[float] = None
    date: Optional[str] = None
    source_account: Optional[str] = None


@router.post("/invoices", dependencies=[Depends(check_auth)])
async def create_invoice(req: InvoiceCreateRequest):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    inv_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()

    result = invoicer.create(
        client=req.client,
        description=req.description,
        amount=Decimal(str(req.amount)).quantize(Decimal("0.01")),
        invoice_date=inv_date,
        due_days=req.due_days,
        generate_pdf=req.generate_pdf,
        payment_link=req.payment_link,
        client_email=req.client_email,
        recurring=req.recurring,
    )

    return _ok({
        "number": result["number"],
        "date": result["date"],
        "due": result.get("due"),
        "client": result["client"],
        "description": result["description"],
        "amount": float(result["amount"]),
        "payment_url": result.get("payment_url"),
        "pdf_path": Path(result.get("pdf_path", "")).name if result.get("pdf_path") else None,
        "status": result["status"],
    })


@router.get("/invoices", dependencies=[Depends(check_auth)])
async def list_invoices(year: Optional[int] = Query(None), ar_only: bool = Query(False)):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    invoices = invoicer.list(year=year, ar_only=ar_only)
    return _ok({
        "invoices": [
            {
                "date": str(i["date"]),
                "client": i["client"],
                "description": i["description"],
                "amount": float(i["amount"]),
                "paid": i.get("paid", False),
            }
            for i in invoices
        ],
        "total": len(invoices),
    })


@router.get("/invoices/ar", dependencies=[Depends(check_auth)])
async def accounts_receivable():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    info = invoicer.check_ar()
    return _ok({
        "total_ar": float(info["total_ar"]),
        "invoice_count": info["invoice_count"],
        "overdue_count": info["overdue_count"],
        "estimated_overdue_amount": float(info["estimated_overdue_amount"]),
    })


@router.post("/invoices/{number}/pay", dependencies=[Depends(check_auth)])
async def mark_invoice_paid(number: str, req: MarkInvoicePaidRequest):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        invoicer = Invoicer(cfg, ledger)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    try:
        pay_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
        amt = Decimal(str(req.amount)).quantize(Decimal("0.01")) if req.amount else None
        result = invoicer.mark_paid(
            invoice_number=number,
            amount=amt,
            date=pay_date,
            source_account=req.source_account,
        )
    except ValueError as e:
        return _err(str(e), 404)

    return _ok(result)


@router.get("/invoices/{number}/pdf", dependencies=[Depends(check_auth)])
async def get_invoice_pdf(number: str):
    if "/" in number or "\\" in number or ".." in number:
        raise HTTPException(status_code=400, detail="Invalid invoice number")
    from fastapi.responses import FileResponse
    cfg = get_config()
    inv_dir = cfg.invoices_dir.resolve()
    pdf_path = (inv_dir / f"{number}.pdf").resolve()
    html_path = (inv_dir / f"{number}.html").resolve()
    if not str(pdf_path).startswith(str(inv_dir)):
        raise HTTPException(status_code=403, detail="Invalid invoice number")
    if pdf_path.exists():
        return FileResponse(str(pdf_path), media_type="application/pdf", filename=f"{number}.pdf")
    if html_path.exists():
        return FileResponse(str(html_path), media_type="text/html", filename=f"{number}.html")
    return _err(f"Invoice '{number}' not found. Generate it with 'llc invoice create'.", 404)
