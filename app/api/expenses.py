"""Expense import routes."""
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


@router.post("/expenses/import", dependencies=[Depends(check_auth)])
async def import_expenses(
    file: UploadFile = File(...),
    preview: bool = Form(False),
):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    from ..expenses import ExpenseImporter

    _ext = Path(file.filename or ".csv").suffix.lower()
    suffix = _ext if _ext in (".csv", ".qbo", ".ofx", ".ofx.gz") else ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        importer = ExpenseImporter(cfg, ledger)
        results = importer.import_csv(tmp_path, preview=preview)

        income_count = sum(1 for r in results if r["type"] == "income")
        expense_count = sum(1 for r in results if r["type"] == "expense")
        total = sum(r["amount"] for r in results)

        return _ok({
            "imported": len(results),
            "income_count": income_count,
            "expense_count": expense_count,
            "net_total": float(total),
            "preview": preview,
            "transactions": [
                {
                    "date": r["date"],
                    "description": r["description"],
                    "amount": float(r["amount"]),
                    "type": r["type"],
                    "account": r["account"],
                }
                for r in results
            ],
        })
    finally:
        os.unlink(tmp_path)


@router.post("/import/csv", dependencies=[Depends(check_auth)])
async def import_csv(
    file: UploadFile = File(...),
    preview: bool = Form(False),
):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Config/ledger error: {e}", 500)

    from ..importer import Importer

    _ext = Path(file.filename or ".csv").suffix.lower()
    suffix = _ext if _ext in (".csv", ".qbo") else ".csv"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        imp = Importer(cfg, ledger)
        results = imp.import_csv(tmp_path, preview=preview)
        return _ok({
            "imported": len(results),
            "preview": preview,
            "transactions": [
                {"date": r["date"], "description": r["description"],
                 "amount": float(r["amount"]), "type": r["type"], "account": r["account"]}
                for r in results
            ],
        })
    finally:
        os.unlink(tmp_path)


@router.post("/ofx/import", dependencies=[Depends(check_auth)])
async def api_ofx_import(
    file: UploadFile = File(...),
    account: Optional[str] = Form(None),
    preview: bool = Form(False),
):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..ofx_import import OfxImporter
    from ..ledger import Ledger

    ledger = Ledger(cfg)
    importer = OfxImporter(cfg, ledger)

    _ext = Path(file.filename or ".ofx").suffix.lower() if file.filename else ".ofx"
    suffix = _ext if _ext in (".ofx", ".qfx", ".ofx.gz") else ".ofx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        result = importer.import_file(
            tmp_path,
            account=account or cfg.checking_account,
            preview=preview,
        )
        result.pop("transactions", None)
        return _ok(result)
    finally:
        os.unlink(tmp_path)
