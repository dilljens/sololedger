"""Health, status, and dashboard routes."""
import datetime

from fastapi import APIRouter, Depends

from ..ledger import Ledger
from .deps import (
    check_auth,
    get_config,
    _err,
    _ok,
    _api_keys_env,
    _sessions,
    GOOGLE_CLIENT_ID,
)
from .shared import _decimal_to_float

router = APIRouter(prefix="/api/v1")


@router.get("/health", dependencies=[Depends(check_auth)])
async def health():
    """Simple health check — returns OK if the API is running."""
    return _ok({"status": "ok", "timestamp": datetime.datetime.now().isoformat()})


@router.get("/public/status")
async def public_status():
    """Public endpoint to check if the app needs first-run setup.

    Returns only non-sensitive info — safe to call without auth.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        try:
            cash = _decimal_to_float(ledger.cash_balance())
        except Exception:
            cash = 0.0
        has_data = cash > 0 or ledger.net_income() != 0
        return _ok({
            "needs_setup": False,
            "has_data": has_data,
            "has_auth": bool(_api_keys_env or GOOGLE_CLIENT_ID or _sessions),
            "auth_methods": {
                "local": True,
                "google": bool(GOOGLE_CLIENT_ID),
            },
        })
    except Exception as e:
        import sys
        print(f"⚠ Public status check failed: {e}", file=sys.stderr)
        return _ok({
            "needs_setup": True,
            "has_data": False,
            "has_auth": False,
            "auth_methods": {"local": True, "google": False},
        })


@router.get("/status", dependencies=[Depends(check_auth)])
async def get_status():
    """Get financial dashboard: cash, P&L, upcoming deadlines."""
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    entity_label = "S-Corp (1120-S)" if entity_type == "scorp" else "SMLLC (Schedule C)"

    cash = _decimal_to_float(ledger.cash_balance())
    revenue = _decimal_to_float(ledger.gross_revenue())
    expenses = _decimal_to_float(ledger.total_expenses())
    net = _decimal_to_float(ledger.net_income())

    from ..taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger)
    if net > 0:
        est = taxer.quarterly_estimate(ledger.net_income())
        tax_info = {
            "annual_total_tax": _decimal_to_float(est["annual_total_tax"]),
            "already_paid": _decimal_to_float(est["already_paid"]),
            "suggested_payment": _decimal_to_float(est["suggested_payment"]),
            "note": est["note"],
        }
    else:
        tax_info = {"annual_total_tax": 0, "already_paid": 0, "suggested_payment": 0, "note": "No tax due"}

    deadlines = taxer.deadline_info()
    errors = ledger.check()

    return _ok({
        "entity_type": entity_type,
        "entity_label": entity_label,
        "cash": cash,
        "gross_revenue": revenue,
        "total_expenses": expenses,
        "net_profit": net,
        "tax": tax_info,
        "deadlines": deadlines["deadlines"],
        "ledger_errors": len(errors),
    })


@router.get("/dashboard", dependencies=[Depends(check_auth)])
async def get_dashboard():
    """Combined dashboard — all data in one call (faster than /status + /invoices/ar + ...).

    Returns everything needed for the web app dashboard page:
    cash, P&L, AR, tax estimate, deadlines, and recent transactions.
    """
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    entity_type = getattr(cfg, 'entity_type', 'smllc')
    entity_label = "S-Corp (1120-S)" if entity_type == "scorp" else "SMLLC (Schedule C)"

    cash = _decimal_to_float(ledger.cash_balance())
    revenue = _decimal_to_float(ledger.gross_revenue())
    expenses = _decimal_to_float(ledger.total_expenses())
    net = _decimal_to_float(ledger.net_income())
    ar_bal = _decimal_to_float(ledger.account_balance(cfg.ar_account))

    from ..taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger)
    if net > 0:
        est = taxer.quarterly_estimate(ledger.net_income())
        tax_info = {
            "annual_total_tax": _decimal_to_float(est["annual_total_tax"]),
            "already_paid": _decimal_to_float(est["already_paid"]),
            "suggested_payment": _decimal_to_float(est["suggested_payment"]),
            "note": est["note"],
        }
    else:
        tax_info = {"annual_total_tax": 0, "already_paid": 0, "suggested_payment": 0, "note": "No tax due"}

    deadlines = taxer.deadline_info()
    errors = ledger.check()

    txns = []
    for entry in ledger.entries:
        if not hasattr(entry, "date") or not hasattr(entry, "postings"):
            continue
        for posting in entry.postings:
            txns.append({
                "date": str(entry.date),
                "payee": getattr(entry, "payee", "") or "",
                "description": getattr(entry, "narration", "") or "",
                "account": posting.account,
                "amount": float(posting.units.number) if posting.units else 0,
            })
    txns.sort(key=lambda x: (x["date"], x["account"]), reverse=True)

    return _ok({
        "entity_type": entity_type,
        "entity_label": entity_label,
        "cash": cash,
        "gross_revenue": revenue,
        "total_expenses": expenses,
        "net_profit": net,
        "ar": ar_bal,
        "tax": tax_info,
        "deadlines": deadlines["deadlines"],
        "ledger_errors": len(errors),
        "recent_transactions": txns[:15],
    })
