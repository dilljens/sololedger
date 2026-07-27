"""Amazon Order History import API endpoints."""
import tempfile
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..db import get_db, get_tenant_db_path
from ..importers.amazon import import_amazon_csv, preview_amazon_csv
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/import/amazon")


@router.post("/preview", dependencies=[Depends(check_auth)])
async def preview_import(file: UploadFile = File(...)):
    """Preview an Amazon order history CSV/zip without importing."""
    try:
        suffix = Path(file.filename or "orders.csv").suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        preview = preview_amazon_csv(tmp_path)
        return _ok(preview)
    except Exception as e:
        return _err(str(e), 400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.post("/import", dependencies=[Depends(check_auth)])
async def run_import(
    file: UploadFile = File(...),
    card_filter: str = Form(""),
    dry_run: bool = Form(False),
):
    """Import Amazon order history. Card filter can be comma-separated masks."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        filters = [m.strip() for m in card_filter.split(",") if m.strip()] if card_filter else None

        suffix = Path(file.filename or "orders.csv").suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await file.read()
            tmp.write(content)
            tmp_path = tmp.name

        result = import_amazon_csv(db, tmp_path, card_filter=filters, dry_run=dry_run)
        return _ok(result)
    except Exception as e:
        return _err(str(e), 400)
    finally:
        Path(tmp_path).unlink(missing_ok=True)


@router.get("/orders", dependencies=[Depends(check_auth)])
async def list_orders(limit: int = 50, offset: int = 0):
    """List imported Amazon orders."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        orders = db.execute(
            "SELECT id, source_id, receipt_date, merchant, total_cents, currency, status, created_at "
            "FROM vendor_receipts WHERE vendor = 'amazon' "
            "ORDER BY receipt_date DESC LIMIT ? OFFSET ?",
            (limit, offset),
        ).fetchall()

        total = db.execute(
            "SELECT count(*) as cnt FROM vendor_receipts WHERE vendor = 'amazon'"
        ).fetchone()["cnt"]

        return _ok({
            "orders": [dict(o) for o in orders],
            "total": total,
            "limit": limit,
            "offset": offset,
        })
    except Exception as e:
        return _err(str(e), 500)
