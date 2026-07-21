"""Receipt and category routes."""
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile
from pydantic import BaseModel

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config, require_plan

router = APIRouter(prefix="/api/v1")


class CategoryLearnRequest(BaseModel):
    merchant: str
    account: str
    correct: bool = False


@router.post("/receipts/scan", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def scan_receipt(
    file: UploadFile = File(...),
    preview: bool = Form(True),
):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..receipts import ReceiptScanner

    _ext = Path(file.filename or ".pdf").suffix.lower()
    suffix = _ext if _ext in (".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp") else ".pdf"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        scanner = ReceiptScanner(cfg)
        result = scanner.process_file(tmp_path, preview=preview)

        return _ok({
            "success": result.get("success", False),
            "merchant": result.get("merchant"),
            "date": result.get("date"),
            "total": float(result["total"]) if result.get("total") else None,
            "line_items": result.get("line_items", []),
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


@router.get("/receipts/match", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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
                            "match_score": round(float(1.0 - abs(pos_amt - Decimal(str(amount))) / max(pos_amt, Decimal("0.01"))), 3),
                        })

    txns.sort(key=lambda x: -x["match_score"])
    return _ok({"matches": txns[:5], "receipt_amount": amount})


@router.get("/receipts/list", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
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
