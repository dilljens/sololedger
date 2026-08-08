"""Receipt and category routes."""
import os
import tempfile
from datetime import date as _date
from decimal import Decimal
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, Query, UploadFile, HTTPException
from pydantic import BaseModel

from ..ledger import Ledger, validate_account
from .deps import (_read_upload, _err, _ok, check_auth, get_config, require_plan,
                   _tenant_db_for_current, enforce_free_cap, increment_usage,
                   FREE_RECEIPT_SCANS_PER_MONTH)

router = APIRouter(prefix="/api/v1")


class CategoryLearnRequest(BaseModel):
    merchant: str
    account: str
    correct: bool = False


class LineItemUpdate(BaseModel):
    coa_account: Optional[str] = None
    is_personal: Optional[bool] = None
    is_reimbursable: Optional[bool] = None


class ReceiptCommitRequest(BaseModel):
    source: Optional[str] = None


def _valid_coa_account(account: str) -> bool:
    """Strict CoA shape check — same rules Beancount enforces on account names."""
    return validate_account(account) is None


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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 500)


@router.get("/receipts/match", dependencies=[Depends(check_auth)])
async def receipt_match(amount: float = Query(0), merchant: str = Query("")):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except HTTPException:
        raise
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
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from ..receipts import ReceiptScanner
    except ImportError:
        return _err("Receipt scanner not available", 500)

    scanner = ReceiptScanner(cfg)
    docs = scanner.list_attached(year=year or "")
    return _ok({"documents": docs, "count": len(docs)})


# ── Line-item reconciliation (per-line CoA assignment + commit) ──────────


@router.get("/receipts/{receipt_id}", dependencies=[Depends(check_auth)])
async def get_receipt(receipt_id: int):
    """Get one vendor receipt with its line items (for line-item reconciling)."""
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..db import get_db, get_tenant_db_path
    tenant_dir = get_tenant_db_path(cfg)
    if not tenant_dir:
        return _err("No tenant directory configured", 500)
    db = get_db(tenant_dir)

    receipt = db.execute(
        "SELECT * FROM vendor_receipts WHERE id = ?", (receipt_id,)
    ).fetchone()
    if not receipt:
        return _err("Receipt not found", 404)

    items = db.execute(
        "SELECT id, description, quantity, unit_price_cents, total_cents,"
        "       coa_account, is_personal, is_reimbursable, sort_order"
        " FROM vendor_receipt_items WHERE receipt_id = ? ORDER BY sort_order, id",
        (receipt_id,),
    ).fetchall()

    return _ok({
        "receipt": {k: receipt[k] for k in receipt.keys()},
        "items": [dict(i) for i in items],
    })


@router.put("/receipts/{receipt_id}/items/{item_id}", dependencies=[Depends(check_auth)])
async def update_receipt_item(receipt_id: int, item_id: int, req: LineItemUpdate):
    """Assign a CoA account / personal / reimbursable flag to one line item."""
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..db import get_db, get_tenant_db_path
    tenant_dir = get_tenant_db_path(cfg)
    if not tenant_dir:
        return _err("No tenant directory configured", 500)
    db = get_db(tenant_dir)

    # The item must belong to the named receipt (guard against cross-receipt ids)
    item = db.execute(
        "SELECT * FROM vendor_receipt_items WHERE id = ? AND receipt_id = ?",
        (item_id, receipt_id),
    ).fetchone()
    if not item:
        return _err("Line item not found for this receipt", 404)

    if req.coa_account is not None and req.coa_account != "" and not _valid_coa_account(req.coa_account):
        return _err(f"Invalid account: {req.coa_account}", 400)

    updates, params = [], []
    if req.coa_account is not None:
        updates.append("coa_account = ?")
        params.append(req.coa_account or None)
    if req.is_personal is not None:
        updates.append("is_personal = ?")
        params.append(1 if req.is_personal else 0)
    if req.is_reimbursable is not None:
        updates.append("is_reimbursable = ?")
        params.append(1 if req.is_reimbursable else 0)
    if not updates:
        return _err("Nothing to update", 400)

    params.append(item_id)
    db.execute(f"UPDATE vendor_receipt_items SET {', '.join(updates)} WHERE id = ?", params)
    db.commit()

    return _ok({
        "receipt_id": receipt_id,
        "item_id": item_id,
        "coa_account": req.coa_account if req.coa_account is not None else (item["coa_account"] or None),
        "is_personal": req.is_personal if req.is_personal is not None else bool(item["is_personal"]),
        "is_reimbursable": req.is_reimbursable if req.is_reimbursable is not None else bool(item["is_reimbursable"]),
        "updated": True,
    })


@router.post("/receipts/{receipt_id}/commit", dependencies=[Depends(check_auth)])
async def commit_receipt(receipt_id: int, req: ReceiptCommitRequest):
    """Commit assigned line items to the Beancount ledger.

    Generates ONE split transaction per distinct CoA account assigned to the
    receipt's line items (personal items excluded), balanced against a source
    account (default: the configured checking account).
    """
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..db import get_db, get_tenant_db_path
    tenant_dir = get_tenant_db_path(cfg)
    if not tenant_dir:
        return _err("No tenant directory configured", 500)
    db = get_db(tenant_dir)

    receipt = db.execute(
        "SELECT * FROM vendor_receipts WHERE id = ?", (receipt_id,)
    ).fetchone()
    if not receipt:
        return _err("Receipt not found", 404)

    # Atomic claim — only one commit may pass this transition. A read-then-
    # check would let two concurrent commits both pass and double-post.
    claimed = db.execute(
        "UPDATE vendor_receipts SET status = 'committing'"
        " WHERE id = ? AND status IN ('pending', 'categorized')",
        (receipt_id,),
    )
    db.commit()
    if claimed.rowcount == 0:
        return _err("Receipt is already committed to the ledger", 409)

    items = db.execute(
        "SELECT * FROM vendor_receipt_items WHERE receipt_id = ? ORDER BY sort_order, id",
        (receipt_id,),
    ).fetchall()

    assigned = [i for i in items if i["coa_account"]]
    if not assigned:
        return _err("No line items have been assigned an account yet", 400)

    # Group totals by account (business items only — personal items stay out
    # of the ledger; the owner handles them separately).
    totals: dict[str, int] = {}
    unassigned_cents = 0
    personal_cents = 0
    for i in items:
        if i["is_personal"]:
            personal_cents += i["total_cents"] or 0
            continue
        acct = i["coa_account"]
        if acct:
            totals[acct] = totals.get(acct, 0) + (i["total_cents"] or 0)
        else:
            unassigned_cents += i["total_cents"] or 0

    if not totals:
        return _err("No non-personal line items have an assigned account", 400)

    total_cents = sum(totals.values())
    if total_cents <= 0:
        return _err("Assigned line items total to zero — nothing to commit", 400)

    source = req.source or cfg.checking_account
    postings = [(acct, f"{cents / 100:.2f} USD") for acct, cents in totals.items()]
    postings.append((source, f"-{total_cents / 100:.2f} USD"))

    receipt_date = receipt["receipt_date"] or _date.today().isoformat()
    try:
        from datetime import date as _d
        txn_date = _d.fromisoformat(receipt_date)
    except ValueError:
        txn_date = _date.today()

    merchant = receipt["merchant"] or f"Receipt #{receipt_id}"
    ledger = Ledger(cfg)
    try:
        entry = ledger.append(
            date=txn_date,
            payee=merchant,
            narration=f"Receipt commit: {merchant}",
            postings=postings,
        )
        ledger.reload(force=True)
    except Exception as e:
        # release the claim so a corrected commit can retry (no double-post)
        db.execute(
            "UPDATE vendor_receipts SET status = 'pending'"
            " WHERE id = ? AND status = 'committing'", (receipt_id,)
        )
        db.commit()
        return _err(str(e), 400)

    db.execute(
        "UPDATE vendor_receipts SET status = 'committed'"
        " WHERE id = ? AND status = 'committing'", (receipt_id,)
    )
    db.commit()

    return _ok({
        "receipt_id": receipt_id,
        "total": total_cents / 100,
        "accounts": {acct: cents / 100 for acct, cents in totals.items()},
        "source": source,
        "date": txn_date.isoformat(),
        "entry": entry.strip(),
        "personal_excluded": personal_cents / 100,
        "unassigned_excluded": unassigned_cents / 100,
    })
