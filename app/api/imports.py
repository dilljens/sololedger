"""Import API endpoints — OFX, Citi CSV, and generic import tracking.

Consolidates import-related endpoints under /api/v1/import/.
OFX import was previously in expenses.py; this module extends it
with SQLite tracking for cross-source dedup.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import HTTPException, APIRouter, Depends, File, Form, UploadFile

from ..db import get_db, get_tenant_db_path
from ..ledger import Ledger
from .deps import _read_upload, _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/import")


# ── OFX/QFX import (enhanced with SQLite tracking) ──────────────────────


@router.post("/ofx", dependencies=[Depends(check_auth)])
async def import_ofx(
    file: UploadFile = File(...),
    account: Optional[str] = Form(None),
    preview: bool = Form(False),
):
    """Import an OFX/QFX bank statement.

    Parses the file, deduplicates by FITID and cross-source fingerprint
    (checked before the ledger append), and appends to Beancount ledger.
    """
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        db = get_db(tenant_dir) if tenant_dir else None
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    from ..ofx_import import OfxImporter

    ledger = Ledger(cfg)
    importer = OfxImporter(cfg, ledger)

    suffix = Path(file.filename or ".ofx").suffix.lower() if file.filename else ".ofx"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        content = await _read_upload(file)
        tmp.write(content)
        tmp_path = tmp.name

    try:
        # Dedup (FITID + cross-source fingerprint) happens inside the
        # importer BEFORE any ledger write; the importer records the
        # fingerprint trail itself.
        result = importer.import_file(
            tmp_path,
            account=account or cfg.checking_account,
            preview=preview,
            db=db,
        )

        result.pop("transactions", None)  # Don't return full list in response
        return _ok(result)
    finally:
        os.unlink(tmp_path)


# ── Citi CSV import ──────────────────────────────────────────────────────


@router.post("/citi/preview", dependencies=[Depends(check_auth)])
async def preview_citi(file: UploadFile = File(...)):
    """Preview a Citi credit-card CSV without importing."""
    try:
        from ..importers.citi import preview_citi_csv

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name

        preview = preview_citi_csv(tmp_path)
        return _ok(preview)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 400)
    finally:
        os.unlink(tmp_path)


@router.post("/citi/import", dependencies=[Depends(check_auth)])
async def run_citi_import(
    file: UploadFile = File(...),
    account: str = Form("citi"),
    dry_run: bool = Form(False),
):
    """Import a Citi credit-card CSV."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from ..importers.citi import import_citi_csv
        from ..ledger import Ledger

        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name

        result = import_citi_csv(db, tmp_path, account_label=account, dry_run=dry_run,
                                 ledger=Ledger(cfg), cfg=cfg)
        return _ok(result)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 400)
    finally:
        os.unlink(tmp_path)


# ── Wave CSV import ──────────────────────────────────────────────────────


@router.post("/wave/preview", dependencies=[Depends(check_auth)])
async def preview_wave(file: UploadFile = File(...)):
    """Preview a Wave Accounting CSV export."""
    try:
        from ..importers.wave import parse_wave_csv
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name
        txns = parse_wave_csv(tmp_path)
        return _ok({"total": len(txns), "sample": txns[:10]})
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 400)
    finally:
        os.unlink(tmp_path)


@router.post("/wave/import", dependencies=[Depends(check_auth)])
async def run_wave_import(
    file: UploadFile = File(...),
    dry_run: bool = Form(False),
):
    """Import a Wave Accounting CSV."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)
        from ..importers.wave import import_wave_csv
        from ..ledger import Ledger
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name
        result = import_wave_csv(db, tmp_path, dry_run=dry_run,
                                 ledger=Ledger(cfg), cfg=cfg)
        return _ok(result)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 400)
    finally:
        os.unlink(tmp_path)


# ── Statement filing ─────────────────────────────────────────────────────


@router.post("/statement/file", dependencies=[Depends(check_auth)])
async def file_statement(
    file: UploadFile = File(...),
    institution: Optional[str] = Form(None),
    account_mask: Optional[str] = Form(None),
    period: Optional[str] = Form(None),
):
    """File a PDF bank/credit-card statement."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        db = get_db(tenant_dir) if tenant_dir else None

        suffix = Path(file.filename or "statement.pdf").suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name

        from ..statements import file_statement as fs
        result = fs(db, tmp_path, institution=institution, account_mask=account_mask, period=period)
        return _ok(result)
    except HTTPException:
        raise
    except Exception as e:
        return _err(str(e), 400)
    finally:
        os.unlink(tmp_path)



# ── Reconciliation locking ────────────────────────────────────────────────


@router.post("/reconciliation/lock", dependencies=[Depends(check_auth)])
async def lock_reconciliation(
    account: str = Form(...),
    statement_date: str = Form(...),
    balance_cents: int = Form(0),
):
    """Lock a period's transactions for reconciliation."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        db.execute(
            "INSERT OR REPLACE INTO reconciliation_marks (account, statement_date, balance_cents) VALUES (?, ?, ?)",
            (account, statement_date, balance_cents),
        )
        db.commit()
        return _ok({"account": account, "statement_date": statement_date, "locked": True})
    except Exception as e:
        return _err(str(e), 500)


@router.get("/reconciliation/status", dependencies=[Depends(check_auth)])
async def reconciliation_status():
    """List reconciliation locks."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        marks = db.execute(
            "SELECT * FROM reconciliation_marks ORDER BY statement_date DESC"
        ).fetchall()
        return _ok({"marks": [dict(m) for m in marks]})
    except Exception as e:
        return _err(str(e), 500)
