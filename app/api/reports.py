"""Report routes."""
from typing import Optional

from fastapi import APIRouter, Depends, Query

from ..ledger import Ledger
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


@router.get("/reports/expenses", dependencies=[Depends(check_auth)])
async def get_expenses_report(year: Optional[int] = Query(None), format: str = Query("json")):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from ..reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)

    if format == "csv":
        csv_data = rg.expenses_csv(year=year)
        from fastapi.responses import PlainTextResponse
        filename = f"expenses-{year or 'all'}.csv"
        return PlainTextResponse(csv_data, media_type="text/csv",
                                 headers={"Content-Disposition": f"attachment; filename={filename}"})

    summary = rg.expenses_summary(year=year)
    return _ok({"year": year or "all", "total": sum(s["amount"] for s in summary), "categories": summary})


@router.get("/reports/profit-loss", dependencies=[Depends(check_auth)])
async def get_profit_loss(year: Optional[int] = Query(None)):
    try:
        cfg = get_config()
        ledger = Ledger(cfg)
    except Exception as e:
        return _err(f"Ledger error: {e}", 500)

    from ..reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)
    pl = rg.profit_loss(year=year)
    return _ok(pl)
