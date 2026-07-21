"""Notification routes."""
from fastapi import APIRouter, Depends

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config, require_plan

router = APIRouter(prefix="/api/v1")


@router.post("/notify/check", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def notify_check():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
        from ..notify import Notifier
    except Exception as e:
        return _err(f"Error: {e}", 500)

    notifier = Notifier(cfg)
    results = notifier.send_digest(ledger)

    return _ok({
        "alerts": {
            "tax_deadlines": results["tax_deadlines"],
            "unpaid_invoices": results["unpaid_invoices"],
            "ledger_health": results["ledger_health"],
        },
        "total_alerts": sum(len(v) for v in results.values()),
    })
