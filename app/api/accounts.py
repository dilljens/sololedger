"""Account, transfer, reimbursement, and split routes."""
import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db, get_tenant_db_path
from ..ledger import Ledger, validate_account
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


class TransferRequest(BaseModel):
    from_account: str
    to_account: str
    amount: float
    date: Optional[str] = None
    description: Optional[str] = "Transfer"


class ReimbursementRequest(BaseModel):
    amount: float
    merchant: str
    account: Optional[str] = "Expenses:Miscellaneous"
    date: Optional[str] = None


class SplitRequest(BaseModel):
    merchant: str
    total: float
    business: float
    account: Optional[str] = "Expenses:Miscellaneous"
    date: Optional[str] = None
    source: Optional[str] = None


def _reject_if_locked(date_iso: str, *accounts: str):
    """Raise 409 if a write would touch a reconciled (locked) period.

    A reconciliation mark with statement_date D means everything through D
    has been verified for that account; edits dated <= D would silently
    break the reconciled balance, so they are rejected at the API boundary.
    """
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return
        db = get_db(tenant_dir)
    except Exception:
        return  # no tenant DB → no locks → nothing to enforce
    for account in accounts:
        if db.is_period_locked(account, date_iso):
            raise HTTPException(
                status_code=409,
                detail=f"Account {account} is reconciled through this date —"
                       f" unlock it (reconciliation) before editing transactions"
                       f" on or before {date_iso}.",
            )


@router.get("/accounts", dependencies=[Depends(check_auth)])
async def api_accounts():
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    data = ledger.registered_accounts()

    data["cards"] = []
    return _ok(data)


@router.post("/transfer", dependencies=[Depends(check_auth)])
async def api_transfer(req: TransferRequest):
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    for acct in (req.from_account, req.to_account):
        err = validate_account(acct)
        if err:
            return _err(err, 400)
    _reject_if_locked(txn_date.isoformat(), req.from_account, req.to_account)
    ledger.transfer(
        date=txn_date,
        from_account=req.from_account,
        to_account=req.to_account,
        amount=Decimal(str(req.amount)),
        description=req.description or "Transfer",
    )
    ledger.reload(force=True)
    return _ok({
        "from": req.from_account,
        "to": req.to_account,
        "amount": req.amount,
        "date": txn_date.isoformat(),
    })


@router.post("/reimburse", dependencies=[Depends(check_auth)])
async def api_reimburse(req: ReimbursementRequest):
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    expense_acct = req.account or "Expenses:Miscellaneous"
    err = validate_account(expense_acct)
    if err:
        return _err(err, 400)
    _reject_if_locked(txn_date.isoformat(), expense_acct,
                      "Liabilities:Reimbursement")
    ledger.reimbursement(
        date=txn_date,
        merchant=req.merchant,
        amount=Decimal(str(req.amount)),
        expense_account=req.account or "Expenses:Miscellaneous",
    )
    ledger.reload(force=True)
    return _ok({
        "merchant": req.merchant,
        "amount": req.amount,
        "account": req.account or "Expenses:Miscellaneous",
        "date": txn_date.isoformat(),
    })


@router.post("/split", dependencies=[Depends(check_auth)])
async def api_split(req: SplitRequest):
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    source = req.source or cfg.checking_account
    expense_acct = req.account or "Expenses:Miscellaneous"
    for acct in (source, expense_acct):
        err = validate_account(acct)
        if err:
            return _err(err, 400)
    personal = req.total - req.business
    locked_accounts = [source, expense_acct]
    if personal > 0:
        locked_accounts.append("Equity:OwnerDraws")
    _reject_if_locked(txn_date.isoformat(), *locked_accounts)

    if personal > 0:
        postings = [
            (req.account or "Expenses:Miscellaneous", f"{req.business:.2f} USD"),
            ("Equity:OwnerDraws", f"{personal:.2f} USD"),
            (source, f"-{req.total:.2f} USD"),
        ]
    else:
        postings = [
            (req.account or "Expenses:Miscellaneous", f"{req.total:.2f} USD"),
            (source, f"-{req.total:.2f} USD"),
        ]

    ledger.append(
        date=txn_date,
        payee=req.merchant,
        narration=f"Split: ${req.business:.2f} business, ${personal:.2f} personal",
        postings=postings,
    )
    ledger.reload(force=True)
    return _ok({
        "merchant": req.merchant,
        "total": req.total,
        "business": req.business,
        "personal": personal,
        "account": req.account or "Expenses:Miscellaneous",
    })
