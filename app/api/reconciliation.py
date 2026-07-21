"""Reconciliation, check, backup, and setup routes."""
import datetime
import os
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ledger import Ledger
from .deps import _err, _ok, _PROJECT_ROOT, check_auth, get_config

router = APIRouter(prefix="/api/v1")


class SetupRequest(BaseModel):
    name: str
    owner: str
    state: str
    ein: str = ""
    email: str = ""


@router.get("/reconciliation", dependencies=[Depends(check_auth)])
async def get_reconciliation():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from ..reconciliation import Reconciliation

    rec = Reconciliation(cfg, ledger)
    checking_bal = float(ledger.account_balance(cfg.checking_account))
    uncleared = rec.uncleared_transactions(account=cfg.checking_account, days_back=365)

    total_uncleared = sum(t["amount"] for t in uncleared)

    return _ok({
        "ledger_balance": checking_bal,
        "uncleared_count": len(uncleared),
        "uncleared_total": round(total_uncleared, 2),
        "cleared_balance": round(checking_bal - total_uncleared, 2),
        "uncleared": uncleared[:50],
        "balance_date": datetime.date.today().isoformat(),
    })


@router.get("/check", dependencies=[Depends(check_auth)])
async def api_check():
    try:
        cfg = get_config()
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
        import toml

        config_data = {
            "business": {
                "name": req.name,
                "owner": req.owner,
                "state": req.state,
                "ein": req.ein or "XX-XXXXXXX",
                "address": "",
                "phone": "",
                "email": req.email,
            },
            "ledger": {"path": "ledger/main.beancount"},
            "accounts": {
                "checking": "Assets:Bank:BusinessChecking",
                "ar": "Assets:AccountsReceivable",
                "income": "Income:Consulting",
                "owner_draws": "Equity:OwnerDraws",
            },
            "notifications": {"desktop_enabled": False, "email_enabled": False},
            "banking": {"plaid_enabled": False},
        }

        with open(config_path, "w") as f:
            toml.dump(config_data, f)

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
