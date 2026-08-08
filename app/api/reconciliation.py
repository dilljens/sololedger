"""Reconciliation, check, backup, and setup routes."""
import datetime
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from ..db import get_db, get_tenant_db_path
from ..ledger import Ledger
from .deps import _err, _ok, _PROJECT_ROOT, check_auth, get_config, require_plan

router = APIRouter(prefix="/api/v1")


class SetupRequest(BaseModel):
    name: str
    owner: str
    state: str
    ein: str = ""
    email: str = ""


class LockRequest(BaseModel):
    account: str
    statement_date: str
    balance_cents: int = 0
    notes: str = ""


class UnlockRequest(BaseModel):
    account: str
    statement_date: str


@router.get("/reconciliation", dependencies=[Depends(check_auth), Depends(require_plan("business"))])
async def get_reconciliation():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from ..reconciliation import Reconciliation

    rec = Reconciliation(cfg, ledger)
    checking_bal = float(ledger.account_balance(cfg.checking_account))
    uncleared = rec.uncleared_transactions(account=cfg.checking_account, days_back=365)

    total_uncleared = sum(t["amount"] for t in uncleared)

    # Difference: statement balance (if a lock exists for this account) vs the
    # current cleared balance. With no lock yet, statement balance == ledger
    # balance and the difference is just the uncleared total.
    tenant_dir = get_tenant_db_path(cfg)
    db = get_db(tenant_dir) if tenant_dir else None
    marks = db.reconciliation_marks(account=cfg.checking_account) if db else []
    latest_mark = marks[0] if marks else None

    return _ok({
        "ledger_balance": checking_bal,
        "uncleared_count": len(uncleared),
        "uncleared_total": round(total_uncleared, 2),
        "cleared_balance": round(checking_bal - total_uncleared, 2),
        "statement_balance": (latest_mark["balance_cents"] / 100) if latest_mark and latest_mark.get("balance_cents") is not None else None,
        "statement_date": latest_mark["statement_date"] if latest_mark else None,
        "reconciled_through": latest_mark["statement_date"] if latest_mark else None,
        "difference": None,  # computed client-side as statement - cleared when both present
        "uncleared": uncleared[:50],
        "balance_date": datetime.date.today().isoformat(),
    })


@router.post("/reconciliation/lock", dependencies=[Depends(check_auth), Depends(require_plan("business"))])
async def lock_reconciliation(req: LockRequest):
    """Soft-lock a reconciled period — transactions dated <= statement_date
    for this account can no longer be modified via the API."""
    try:
        # statement_date must be a real ISO date: is_period_locked compares
        # lexicographically, so any other format would mis-enforce.
        datetime.date.fromisoformat(req.statement_date)
    except ValueError:
        return _err("statement_date must be YYYY-MM-DD", 400)
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)
        result = db.lock_period(req.account, req.statement_date,
                                balance_cents=req.balance_cents, notes=req.notes)
        return _ok(result)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 500)


@router.post("/reconciliation/unlock", dependencies=[Depends(check_auth), Depends(require_plan("business"))])
async def unlock_reconciliation(req: UnlockRequest):
    """Remove a reconciliation lock for a period."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)
        result = db.unlock_period(req.account, req.statement_date)
        return _ok(result)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 500)


@router.get("/reconciliation/marks", dependencies=[Depends(check_auth), Depends(require_plan("business"))])
async def reconciliation_marks_list(account: Optional[str] = None):
    """List reconciliation locks, optionally filtered by account."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _ok({"marks": [], "count": 0})
        db = get_db(tenant_dir)
        marks = db.reconciliation_marks(account=account)
        return _ok({"marks": marks, "count": len(marks)})
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 500)


@router.get("/check", dependencies=[Depends(check_auth)])
async def api_check():
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    errors = ledger.check()
    if not errors:
        return _ok({"valid": True, "error_count": 0, "errors": []})
    return _ok({
        "valid": False,
        "error_count": len(errors),
        "errors": [
            {
                "file": str(getattr(e, 'source', {}).get('filename', '?')),
                "line": getattr(e, 'source', {}).get('first_line', 0),
                "message": getattr(e, 'message', str(e)),
            }
            for e in errors[:50]
        ],
    })


@router.post("/backup", dependencies=[Depends(check_auth)])
async def api_backup():
    try:
        cfg = get_config()
    except HTTPException:
        raise
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..backup import Backup
    b = Backup(cfg)
    result = b.commit(quiet=True)
    return _ok(result)


@router.post("/setup", dependencies=[Depends(check_auth)])
async def setup_business(req: SetupRequest):
    config_path = os.environ.get("API_CONFIG", "")
    if not config_path:
        config_path = str(_PROJECT_ROOT / "config.toml")

    try:
        from ..setup import write_business_config, init_ledger
    except ImportError:
        # Fallback uses the shared generator (includes the mandatory [tax]
        # section, unlike the old hand-built dict which 500'd on load).
        from ..config import generate_config_toml

        config_data = generate_config_toml(name=req.name, owner=req.owner,
                                           email=req.email, state=req.state,
                                           ledger_path="ledger/main.beancount")

        with open(config_path, "w") as f:
            f.write(config_data)

        ledger_dir = Path(config_path).parent / "ledger"
        ledger_dir.mkdir(parents=True, exist_ok=True)
        today = datetime.date.today().isoformat()[:4]

        (ledger_dir / "main.beancount").write_text(
            f";; SoloLedger — {req.name}\n"
            f";; Auto-generated {datetime.date.today().isoformat()}\n"
            f"\n"
            f"{today}-01-01 open Assets:Bank:BusinessChecking\n"
            f"{today}-01-01 open Assets:AccountsReceivable\n"
            f"{today}-01-01 open Equity:OwnerDraws\n"
            f"{today}-01-01 open Income:Consulting\n"
            f"{today}-01-01 open Expenses:Software:SaaS\n"
            f"{today}-01-01 open Expenses:BankFees\n"
            f"{today}-01-01 open Liabilities:CreditCard\n"
        )
        (ledger_dir / "transactions.beancount").write_text(";; Transactions\n")
        (ledger_dir / "accounts.beancount").write_text(";; Account tree\n")

    return _ok({"status": "configured", "business": req.name, "state": req.state})
