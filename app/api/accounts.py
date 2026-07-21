"""Account, transfer, reimbursement, and split routes."""
import datetime
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ledger import Ledger
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


@router.get("/accounts", dependencies=[Depends(check_auth)])
async def api_accounts():
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    data = ledger.registered_accounts()

    data["cards"] = []
    for card_cfg in getattr(cfg, 'cards', []):
        bal = ledger.account_balance(card_cfg.account)
        data["cards"].append({
            "account": card_cfg.account,
            "name": card_cfg.name,
            "type": card_cfg.type,
            "balance": float(bal),
            "last_four": card_cfg.last_four or "",
        })
    return _ok(data)


@router.post("/transfer", dependencies=[Depends(check_auth)])
async def api_transfer(req: TransferRequest):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
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
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
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
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    txn_date = datetime.date.fromisoformat(req.date) if req.date else datetime.date.today()
    source = req.source or cfg.checking_account
    personal = req.total - req.business

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
