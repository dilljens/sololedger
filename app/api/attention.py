"""Attention/alerts route."""
from fastapi import APIRouter, Depends

from ..invoice import Invoicer
from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


@router.get("/attention", dependencies=[Depends(check_auth)])
async def get_attention():
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(str(e), 500)

    items = []

    try:
        from ..taxes import TaxEstimator
        taxer = TaxEstimator(cfg, ledger)
        deadlines = taxer.deadline_info()
        for dl in deadlines["deadlines"][:3]:
            if dl["status"] in ("overdue", "upcoming"):
                items.append({
                    "type": "deadline",
                    "severity": "critical" if dl["status"] == "overdue" else "warning",
                    "label": dl["label"],
                    "detail": f"Due {dl['due']} ({dl['days_until']} days)",
                })
    except Exception as e:
        import sys
        print(f"⚠ Deadline info failed: {e}", file=sys.stderr)

    try:
        errors = ledger.check()
        if errors:
            items.append({
                "type": "ledger",
                "severity": "critical",
                "label": f"Ledger has {len(errors)} error(s)",
                "detail": errors[0][:120],
            })
    except Exception as e:
        import sys
        print(f"⚠ Ledger check for alerts failed: {e}", file=sys.stderr)

    try:
        net = ledger.net_income()
        if net <= 0:
            items.append({
                "type": "no_income",
                "severity": "info",
                "label": "No income recorded yet",
                "detail": "Import transactions or create an invoice to get started.",
            })
    except Exception as e:
        import sys
        print(f"⚠ Net income check for alerts failed: {e}", file=sys.stderr)

    try:
        invoicer = Invoicer(cfg, ledger)
        ar = invoicer.check_ar()
        if ar.get("overdue_count", 0) > 0:
            items.append({
                "type": "overdue_invoices",
                "severity": "critical",
                "label": f"{ar['overdue_count']} overdue invoice(s)",
                "detail": f"${ar['estimated_overdue_amount']:,.2f} total overdue",
            })
    except Exception as e:
        import sys
        print(f"⚠ AR check for alerts failed: {e}", file=sys.stderr)

    return _ok({"items": items, "count": len(items)})
