"""Categorization rules API — CRUD for pattern-based rules."""
from fastapi import APIRouter, Depends, Form
from pydantic import BaseModel
from typing import Optional

from ..db import get_db, get_tenant_db_path
from .deps import _err, _ok, check_auth, get_config

router = APIRouter(prefix="/api/v1/rules")


class RuleCreate(BaseModel):
    matcher_type: str = "substring"  # regex, substring, eq, range
    pattern: str
    target_account: str
    priority: int = 0
    is_active: bool = True
    description: Optional[str] = None


class RuleUpdate(BaseModel):
    matcher_type: Optional[str] = None
    pattern: Optional[str] = None
    target_account: Optional[str] = None
    priority: Optional[int] = None
    is_active: Optional[bool] = None
    description: Optional[str] = None


@router.get("", dependencies=[Depends(check_auth)])
async def list_rules():
    """List all categorization rules."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        rules = db.execute(
            "SELECT * FROM categorization_rules ORDER BY priority ASC, created_at DESC"
        ).fetchall()
        return _ok({"rules": [dict(r) for r in rules], "count": len(rules)})
    except Exception as e:
        return _err(str(e), 500)


@router.post("", dependencies=[Depends(check_auth)])
async def create_rule(rule: RuleCreate):
    """Create a new categorization rule."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        db.execute(
            """INSERT INTO categorization_rules (matcher_type, pattern, target_account, priority, is_active, description)
               VALUES (?, ?, ?, ?, ?, ?)""",
            (rule.matcher_type, rule.pattern, rule.target_account, rule.priority, int(rule.is_active), rule.description),
        )
        db.commit()
        rule_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]
        return _ok({"id": rule_id})
    except Exception as e:
        return _err(str(e), 500)


@router.put("/{rule_id}", dependencies=[Depends(check_auth)])
async def update_rule(rule_id: int, rule: RuleUpdate):
    """Update a categorization rule."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        fields = []
        values = []
        for key, col in [("matcher_type", "matcher_type"), ("pattern", "pattern"),
                         ("target_account", "target_account"), ("priority", "priority"),
                         ("is_active", "is_active"), ("description", "description")]:
            val = getattr(rule, key, None)
            if val is not None:
                fields.append(f"{col} = ?")
                values.append(int(val) if key == "is_active" else val)

        if not fields:
            return _err("No fields to update", 400)

        values.append(rule_id)
        db.execute(
            f"UPDATE categorization_rules SET {', '.join(fields)}, updated_at = datetime('now') WHERE id = ?",
            values,
        )
        db.commit()
        return _ok({"updated": True})
    except Exception as e:
        return _err(str(e), 500)


@router.delete("/{rule_id}", dependencies=[Depends(check_auth)])
async def delete_rule(rule_id: int):
    """Delete a categorization rule."""
    try:
        cfg = get_config()
        tenant_dir = get_tenant_db_path(cfg)
        if not tenant_dir:
            return _err("No tenant directory configured", 500)
        db = get_db(tenant_dir)

        db.execute("DELETE FROM categorization_rules WHERE id = ?", (rule_id,))
        db.commit()
        return _ok({"deleted": True})
    except Exception as e:
        return _err(str(e), 500)


@router.post("/test", dependencies=[Depends(check_auth)])
async def test_rule(merchant: str = Form(""), pattern: str = Form(""), matcher_type: str = Form("substring")):
    """Test how a pattern matches against a merchant name."""
    import re
    try:
        upper_merchant = merchant.upper()
        upper_pattern = pattern.upper()

        if matcher_type == "regex":
            matches = bool(re.search(upper_pattern, upper_merchant))
        elif matcher_type == "eq":
            matches = upper_merchant == upper_pattern
        elif matcher_type == "substring":
            matches = upper_pattern in upper_merchant
        elif matcher_type == "range":
            matches = False  # Range requires amount context
        else:
            return _err(f"Unknown matcher type: {matcher_type}", 400)

        return _ok({"merchant": merchant, "pattern": pattern, "matcher_type": matcher_type, "matches": matches})
    except Exception as e:
        return _err(str(e), 500)
