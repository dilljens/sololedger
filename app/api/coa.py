"""Chart of Accounts API — read accounts from Beancount ledger, add new ones."""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from ..ledger import Ledger, validate_account
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/coa")


class AccountUpdate(BaseModel):
    currency: str = "USD"
    date: Optional[str] = None
    name: Optional[str] = None
    tag: Optional[str] = None


@router.get("", dependencies=[Depends(check_auth)])
async def list_accounts():
    """List all accounts from the Beancount ledger with balances.

    Includes opened-but-empty accounts (Open directive, no postings yet)
    at balance 0.0 so the chart is complete, not just the active accounts.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        balances = ledger.all_balances()
        opened = ledger.opened_accounts()

        accounts = [
            {"account": acct, "balance": balances.get(acct, 0.0)}
            for acct in sorted(opened | set(balances))
        ]

        return _ok({
            "accounts": accounts,
            "count": len(accounts),
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/tree", dependencies=[Depends(check_auth)])
async def account_tree():
    """Get accounts in tree format (Assets, Liabilities, Equity, Income, Expenses)."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        balances = ledger.all_balances()
        opened = ledger.opened_accounts()

        roots = {"Assets": [], "Liabilities": [], "Equity": [], "Income": [], "Expenses": []}

        for acct in sorted(opened | set(balances)):
            parts = acct.split(":")
            if parts[0] in roots:
                roots[parts[0]].append({
                    "account": acct,
                    "balance": balances.get(acct, 0.0),
                    "depth": len(parts) - 1,
                })

        return _ok({
            "tree": [{"root": k, "accounts": v} for k, v in roots.items() if v],
            "count": sum(len(v) for v in roots.values()),
        })
    except Exception as e:
        return _err(str(e), 500)


@router.get("/{account}", dependencies=[Depends(check_auth)])
async def get_account(account: str):
    """Get a single account and its balance (0.0 when opened but empty)."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        opened = ledger.opened_accounts()
        if account not in opened and account not in ledger.all_balances():
            return _err(f"Account not found: {account}", 404)
        return _ok({"account": account, "balance": ledger.balance(account) or 0.0})
    except Exception as e:
        return _err(str(e), 500)


@router.put("/{account}", dependencies=[Depends(check_auth)])
async def update_account(account: str, req: AccountUpdate):
    """Open a new account (or confirm an existing one) in the ledger.

    For an account that does not exist yet, appends a Beancount open
    directive (with optional name/tag metadata). For an existing account,
    returns it unchanged — in-place metadata editing of an existing open
    directive is out of scope (append-only ledger).
    """
    err = validate_account(account)
    if err:
        return _err(err, 400)

    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    if account in ledger.opened_accounts():
        return _ok({
            "account": account,
            "balance": ledger.balance(account) or 0.0,
            "created": False,
            "already_exists": True,
        })

    try:
        txn_date = datetime.date.fromisoformat(req.date) if req.date else None
    except ValueError:
        return _err("Invalid date — use YYYY-MM-DD", 400)

    meta = {}
    if req.name:
        meta["name"] = req.name
    if req.tag:
        meta["tag"] = req.tag

    try:
        entry = ledger.open_account(account, currency=req.currency or "USD",
                                    date=txn_date, meta=meta)
        ledger.reload(force=True)
    except Exception as e:
        return _err(f"Failed to open account: {e}", 500)

    return _ok({
        "account": account,
        "balance": ledger.balance(account),
        "created": True,
        "entry": entry.strip(),
    })
