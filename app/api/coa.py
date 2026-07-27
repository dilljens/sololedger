"""Chart of Accounts API — read accounts from Beancount ledger."""
from fastapi import APIRouter, Depends
from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/coa")


@router.get("", dependencies=[Depends(check_auth)])
async def list_accounts():
    """List all accounts from the Beancount ledger with balances."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        balances = ledger.all_balances()

        accounts = [
            {"account": acct, "balance": bal}
            for acct, bal in sorted(balances.items())
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

        roots = {"Assets": [], "Liabilities": [], "Equity": [], "Income": [], "Expenses": []}

        for acct, bal in sorted(balances.items()):
            parts = acct.split(":")
            if parts[0] in roots:
                roots[parts[0]].append({
                    "account": acct,
                    "balance": bal,
                    "depth": len(parts) - 1,
                })

        return _ok({
            "tree": [{"root": k, "accounts": v} for k, v in roots.items() if v],
            "count": sum(len(v) for v in roots.values()),
        })
    except Exception as e:
        return _err(str(e), 500)
