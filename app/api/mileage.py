"""Mileage tracking routes."""
import datetime
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from ..ledger import Ledger
from ..mileage import MileageTracker
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1")


class MileageAddRequest(BaseModel):
    date: str
    miles: float
    purpose: str
    client: Optional[str] = ""
    start_odo: Optional[float] = 0.0
    end_odo: Optional[float] = 0.0
    route: Optional[str] = ""
    notes: Optional[str] = ""
    post_to_ledger: Optional[bool] = True


@router.get("/mileage/trips", dependencies=[Depends(check_auth)])
async def api_mileage_list(
    year: Optional[int] = Query(None),
    limit: int = Query(50),
):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    trips = tracker.list_trips(year=year, limit=limit)
    return _ok({"trips": trips, "count": len(trips), "total": tracker.trip_count})


@router.post("/mileage/add", dependencies=[Depends(check_auth)])
async def api_mileage_add(req: MileageAddRequest):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    trip = tracker.add_trip(
        date=req.date, miles=req.miles, purpose=req.purpose,
        client=req.client or "", start_odo=req.start_odo or 0.0,
        end_odo=req.end_odo or 0.0, route=req.route or "",
        notes=req.notes or "", post_to_ledger=req.post_to_ledger,
    )
    return _ok({
        "id": trip.id,
        "date": trip.date,
        "miles": trip.miles,
        "deduction": float(trip.deduction),
        "purpose": trip.purpose,
    })


@router.get("/mileage/report", dependencies=[Depends(check_auth)])
async def api_mileage_report(year: Optional[int] = Query(None)):
    if year is None:
        year = datetime.date.today().year
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)
    ledger = Ledger(cfg)
    tracker = MileageTracker(cfg, ledger)
    report = tracker.yearly_report(year)
    return _ok(report)
