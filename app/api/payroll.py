"""Payroll API routes — import Gusto CSV and get payroll summaries."""
import datetime
import io
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from fastapi.datastructures import UploadFile as UploadFileType


class PayrollDisburseRequest(BaseModel):
    date: str
    amount: float
    bank: Optional[str] = None

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


@router.post("/payroll/import", dependencies=[Depends(check_auth)])
async def payroll_import(file: UploadFile = File(...), preview: bool = Form(False)):
    """Upload and import a Gusto payroll CSV.

    The CSV is parsed and journal entries are appended to the ledger.
    Set preview=true to parse without writing.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..payroll import PayrollImporter
    except Exception as e:
        return _err(f"Payroll error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    if entity_type != "scorp":
        return _err("Payroll import requires entity_type='scorp' in config.toml [entity] section.", 400)

    if not file.filename or not file.filename.lower().endswith('.csv'):
        return _err("Upload a CSV file (Gusto payroll export).", 400)

    try:
        content = await file.read()
        # Write to temp file for PayrollImporter
        import tempfile
        with tempfile.NamedTemporaryFile(suffix='.csv', delete=False, mode='wb') as tmp:
            tmp.write(content)
            tmp_path = tmp.name

        importer = PayrollImporter(cfg, ledger)
        results = importer.import_gusto_csv(tmp_path, preview=preview)

        import os
        os.unlink(tmp_path)
    except Exception as e:
        return _err(f"Failed to process CSV: {e}", 500)

    total_gross = sum(r.get("gross", 0) for r in results if "gross" in r)
    total_net = sum(r.get("net", 0) for r in results if "net" in r)
    total_er = sum(r.get("total_employer_taxes", 0) for r in results if "total_employer_taxes" in r)
    imported = sum(1 for r in results if not r.get("skipped") and "error" not in r)
    errors = [r["error"] for r in results if "error" in r]

    return _ok({
        "imported": imported,
        "preview": preview,
        "total_gross": total_gross,
        "total_net": total_net,
        "total_employer_taxes": total_er,
        "errors": errors,
        "rows": [
            {
                "date": r.get("date"),
                "employee": r.get("employee"),
                "gross": r.get("gross"),
                "net": r.get("net"),
                "skipped": r.get("skipped", False),
            }
            for r in results
        ],
    })


@router.get("/payroll/summary", dependencies=[Depends(check_auth)])
async def payroll_summary():
    """Get YTD payroll summary from the ledger."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    if entity_type != "scorp":
        return _ok({
            "entity_type": "smllc",
            "note": "Payroll is for S-Corp mode only.",
            "total_gross": 0,
            "total_net": 0,
            "total_employer_taxes": 0,
        })

    # Pull payroll totals from the ledger expense accounts
    gross = float(ledger.account_balance("Expenses:Payroll:GrossWages"))
    er_ss = float(ledger.account_balance("Expenses:Payroll:EmployerSocialSecurity"))
    er_med = float(ledger.account_balance("Expenses:Payroll:EmployerMedicare"))
    er_futa = float(ledger.account_balance("Expenses:Payroll:FUTA"))
    er_suta = float(ledger.account_balance("Expenses:Payroll:SUTA"))
    total_er = er_ss + er_med + er_futa + er_suta

    return _ok({
        "entity_type": "scorp",
        "total_gross": gross,
        "total_employer_taxes": round(total_er, 2),
        "employer_breakdown": {
            "social_security": er_ss,
            "medicare": er_med,
            "futa": er_futa,
            "suta": er_suta,
        },
    })


@router.post("/payroll/disburse", dependencies=[Depends(check_auth)])
async def payroll_disburse(req: PayrollDisburseRequest):
    """Record net pay disbursement from business bank to owner."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..payroll import PayrollImporter
    except Exception as e:
        return _err(f"Payroll error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    if entity_type != "scorp":
        return _err("Payroll requires entity_type='scorp'.", 400)

    try:
        pay_date = datetime.date.fromisoformat(req.date)
    except ValueError:
        return _err(f"Invalid date: {req.date}. Use YYYY-MM-DD.", 400)

    amount = Decimal(str(req.amount)).quantize(Decimal("0.01"))
    if amount <= 0:
        return _err("Amount must be positive.", 400)

    importer = PayrollImporter(cfg, ledger)
    result = importer.payroll_disburse(
        pay_date=pay_date,
        net_pay=amount,
        bank_account=req.bank,
    )

    return _ok({
        "date": result["date"],
        "amount": result["net_pay"],
        "bank_account": result["bank_account"],
    })
