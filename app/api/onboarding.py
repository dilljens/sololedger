"""Onboarding routes."""
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
    return _ok({
        "needs_onboarding": not complete,
        "has_ledger_data": False,
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
