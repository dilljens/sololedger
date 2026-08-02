"""Receipt and category routes."""
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from ..ledger import Ledger
from .deps import (_read_upload, _err, _ok, check_auth, get_config, require_plan,
                   _tenant_db_for_current, enforce_free_cap, increment_usage,
                   FREE_RECEIPT_SCANS_PER_MONTH)

router = APIRouter(prefix="/api/v1")


class CategoryLearnRequest(BaseModel):
    merchant: str
    account: str
    correct: bool = False


@router.post("/receipts/scan", dependencies=[Depends(check_auth)])
async def scan_receipt(
    file: UploadFile = File(...),
    preview: bool = Form(True),
):
    """Scan a receipt. Free tier: 5 commits/month; paid: unlimited.

    Preview scans don't count toward the cap (nothing is written).
    """
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    # Free-tier cap applies only to committed (non-preview) scans
    if not preview:
        enforce_free_cap("receipt_scan", FREE_RECEIPT_SCANS_PER_MONTH,
                         detail=f"Free plan limited to {FREE_RECEIPT_SCANS_PER_MONTH} receipt scans/month")

    from ..receipts import ReceiptScanner

    _ext = Path(file.filename or ".pdf").suffix.lower()
    suffix = _ext if _ext in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp") else ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await _read_upload(file)
        tmp.write(content)
        tmp_path = tmp.name

    try:
        scanner = ReceiptScanner(cfg)
        result = scanner.process_file(tmp_path, preview=preview)

        # Only count committed scans (preview is free)
        if result.get("success") and result.get("appended") and not preview:
            db = _tenant_db_for_current()
            if db is not None:
                import datetime as _dt
                increment_usage(db, "receipt_scan", _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m"))

        return _ok({
            "success": result.get("success", False),
            "merchant": result.get("merchant"),
            "date": result.get("date"),
            "total": float(result["total"]) if result.get("total") else None,
            "line_items": [
                {"description": i.get("description", ""), "amount": float(i["amount"]) if i.get("amount") else None}
                for i in result.get("line_items", [])
            ],
            "appended": result.get("appended", False),
        })
    finally:
        os.unlink(tmp_path)


@router.get("/categories/suggest", dependencies=[Depends(check_auth)])
async def category_suggest(merchant: str = Query("")):
    try:
        cfg = get_config()
        from ..categorizer import Categorizer
        cat = Categorizer(cfg)
        result = cat.suggest_with_confidence(merchant.upper())
        return _ok(result)
    except Exception as e:
        return _err(str(e), 500)


@router.post("/categories/learn", dependencies=[Depends(check_auth)])
async def category_learn(req: CategoryLearnRequest):
    merchant = req.merchant
    account = req.account
    correct = req.correct
    try:
        cfg = get_config()
        from ..categorizer import Categorizer
        cat = Categorizer(cfg)
        if correct:
            cat.correct(merchant.upper(), account)
        else:
            cat.learn(merchant.upper(), account)
        return _ok({"merchant": merchant.upper(), "account": account, "learned": True})
    except Exception as e:
        return _err(str(e), 500)


@router.get("/receipts/match", dependencies=[Depends(check_auth)])
async def receipt_match(amount: float = Query(0), merchant: str = Query("")):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    threshold = Decimal("0.50")
    txns = []
    for entry in ledger.entries:
        if not hasattr(entry, "date") or not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            if posting.account.startswith("Assets:Bank"):
                amt = Decimal(str(posting.units.number)) if posting.units else Decimal("0")
                if amt < 0:
                    pos_amt = abs(amt)
                    if abs(pos_amt - Decimal(str(amount))) <= threshold:
                        desc = getattr(entry, "payee", "") or getattr(entry, "narration", "") or ""
                        txns.append({
                            "date": str(entry.date),
                            "description": desc,
                            "amount": float(pos_amt),
                            "account": posting.account,
                            "match_score": round(1.0 - abs(float(pos_amt) - amount) / max(float(pos_amt), 0.01), 3),
                        })

    txns.sort(key=lambda x: -x["match_score"])
    return _ok({"matches": txns[:5], "receipt_amount": amount})


@router.get("/receipts/list", dependencies=[Depends(check_auth)])
async def api_receipt_list(year: Optional[str] = Query(None)):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from ..receipts import ReceiptScanner
    except ImportError:
        return _err("Receipt scanner not available", 500)

    scanner = ReceiptScanner(cfg)
    docs = scanner.list_attached(year=year or "")
    return _ok({"documents": docs, "count": len(docs)})
