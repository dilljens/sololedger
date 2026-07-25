"""Onboarding routes."""
import os
from pathlib import Path

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .deps import _current_tenant, _err, _load_tenants, _ok, _save_tenants, check_auth

router = APIRouter(prefix="/api/v1")


class OnboardingCompleteRequest(BaseModel):
    skipped_bank: bool = False
    skipped_import: bool = False


@router.get("/onboarding/status", dependencies=[Depends(check_auth)])
async def onboarding_status():
    tenant = _current_tenant.get()
    if not tenant:
        return _ok({"needs_onboarding": True})

    complete = tenant.get("onboarding_complete", False)
    # Template ships with sample data, so skip onboarding for new users
    needs_onboarding = not complete

    return _ok({
        "needs_onboarding": needs_onboarding,
        "has_transactions": True,
        "plaid_available": bool(os.environ.get("PLAID_CLIENT_ID") and os.environ.get("PLAID_SECRET")),
    })


@router.post("/onboarding/complete", dependencies=[Depends(check_auth)])
async def onboarding_complete(req: OnboardingCompleteRequest):
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    tenants = _load_tenants()
    email = tenant["email"]
    if email in tenants:
        tenants[email]["onboarding_complete"] = True
        _save_tenants(tenants)

    return _ok({"onboarding_complete": True})


@router.post("/onboarding/demo", dependencies=[Depends(check_auth)])
async def onboarding_demo():
    """Load demo data into the tenant's ledger for testing."""
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    tdir = Path(tenant["ledger_dir"]) if tenant.get("ledger_dir") else None
    if not tdir or not tdir.exists():
        return _err("No ledger found", 400)

    from ..ledger import Ledger
    from ..config import Config
    cfg_path = tdir / "config.toml"
    if not cfg_path.exists():
        return _err("No config found", 400)

    cfg = Config(str(cfg_path))
    ledger = Ledger(cfg)

    # Write demo transactions
    demo_txns = """2026-01-01 * "Opening balance"
  Assets:Bank:BusinessChecking  25000.00 USD
  Equity:OwnerDraws

2026-01-15 * "Acme Consulting — Invoice #001" "Web development retainer"
  Assets:AccountsReceivable  5000.00 USD
  Income:Consulting

2026-02-01 * "Office rent"
  Expenses:Occupancy  2000.00 USD
  Assets:Bank:BusinessChecking

2026-02-15 * "Client payment received" "Acme Consulting — Invoice #001"
  Assets:Bank:BusinessChecking  5000.00 USD
  Assets:AccountsReceivable

2026-03-01 * "AWS hosting"
  Expenses:Software:SaaS  150.00 USD
  Assets:Bank:BusinessChecking

2026-03-15 * "Quarterly estimated tax payment"
  Expenses:Taxes:Federal  3000.00 USD
  Assets:Bank:BusinessChecking

2026-04-01 * "Adobe Creative Suite"
  Expenses:Software:SaaS  55.00 USD
  Assets:Bank:BusinessChecking

2026-04-15 * "Invoice #002 — Website consulting"
  Assets:AccountsReceivable  3500.00 USD
  Income:Consulting

2026-05-01 * "Office supplies"
  Expenses:OfficeSupplies  200.00 USD
  Assets:Bank:BusinessChecking

2026-05-15 * "Client payment received"
  Assets:Bank:BusinessChecking  3500.00 USD
  Assets:AccountsReceivable
"""
    txn_file = tdir / "transactions.beancount"
    txn_file.write_text(demo_txns)

    return _ok({"imported": 10, "message": "Demo data loaded — 10 sample transactions"})
