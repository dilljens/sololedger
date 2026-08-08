"""Statement intake API — upload, list, and retrieve filed PDF statements.

Complements the single POST /import/statement/file route with a dedicated
statements surface: POST /statements/upload (same filing pipeline), plus
GET /statements and GET /statements/{id} for the filed-statement index.
"""
import os
import tempfile
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, Depends, File, Form, UploadFile

from ..db import get_db, get_tenant_db_path
from ..statements import file_statement, get_filed_statement, list_filed_statements
from .deps import _read_upload, _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/statements")


@router.post("/upload", dependencies=[Depends(check_auth)])
async def upload_statement(
    file: UploadFile = File(...),
    institution: Optional[str] = Form(None),
    account_mask: Optional[str] = Form(None),
    period: Optional[str] = Form(None),
):
    """Upload a PDF statement — classify, file to canonical layout, record."""
    tmp_path = None
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        db = get_db(tenant_dir) if tenant_dir else None
        if db is None:
            return _err("No tenant directory configured", 500)

        suffix = Path(file.filename or "statement.pdf").suffix.lower()
        with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
            content = await _read_upload(file)
            tmp.write(content)
            tmp_path = tmp.name

        result = file_statement(
            db, tmp_path, institution=institution, account_mask=account_mask,
            period=period, base_dir=cfg.project_root, filename=file.filename,
        )
        if not result.get("success"):
            return _err(result.get("error", "Filing failed"), 400)

        # Attach the batch id so the caller can GET /statements/{id}.
        row = db.execute(
            "SELECT id FROM import_batches WHERE source='statement'"
            " ORDER BY id DESC LIMIT 1"
        ).fetchone()
        result["id"] = row["id"] if row else None
        return _ok(result)
    except Exception as e:
        return _err(str(e), 400)
    finally:
        if tmp_path:
            os.unlink(tmp_path)


@router.get("", dependencies=[Depends(check_auth)])
async def list_statements():
    """List filed statements, newest first."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        db = get_db(tenant_dir) if tenant_dir else None
        if db is None:
            return _ok({"statements": [], "count": 0})
        statements = list_filed_statements(db, base_dir=cfg.project_root)
        return _ok({"statements": statements, "count": len(statements)})
    except Exception as e:
        return _err(str(e), 500)


@router.get("/{statement_id}", dependencies=[Depends(check_auth)])
async def get_statement(statement_id: int):
    """Get one filed statement by id (includes its on-disk path)."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        db = get_db(tenant_dir) if tenant_dir else None
        if db is None:
            return _err("No tenant directory configured", 500)
        statement = get_filed_statement(db, statement_id, base_dir=cfg.project_root)
        if statement is None:
            return _err("Statement not found", 404)
        return _ok(statement)
    except Exception as e:
        return _err(str(e), 500)
