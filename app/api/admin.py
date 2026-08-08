"""Admin routes — operator-only tenant management.

Protected by the ADMIN_API_KEY env var (Bearer token). When it is not set,
the routes are disabled (404) so a misconfigured deployment can't expose
them. Open mode / tenant sessions are never granted admin access.
"""
import os
import shutil
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.security import HTTPBearer

from .. import appdb
from .deps import _err, _ok

router = APIRouter(prefix="/api/v1/admin")

_admin_bearer = HTTPBearer(auto_error=False)


def _admin_key() -> str:
    """Read the admin key lazily so it can be set at runtime / in tests."""
    return os.environ.get("ADMIN_API_KEY", "")


def _admin_enabled() -> bool:
    return bool(_admin_key())


def require_admin(credentials=Depends(_admin_bearer)):
    """Dependency: Bearer token must match ADMIN_API_KEY. Disabled → 404."""
    if not _admin_enabled():
        raise HTTPException(status_code=404, detail="Not found")
    if credentials is None or credentials.credentials != _admin_key():
        raise HTTPException(status_code=401, detail="Invalid admin credentials")
    return True


@router.get("/tenants", dependencies=[Depends(require_admin)])
async def list_tenants():
    """List all tenants with plan/status (no secrets)."""
    tenants = appdb.all_tenants()
    return _ok({
        "count": len(tenants),
        "tenants": [
            {
                "email": t["email"],
                "name": t["name"],
                "plan": t["plan"],
                "status": t["status"],
                "created": t["created"],
                "trial_ends": t["trial_ends"],
                "onboarding_complete": bool(t["onboarding_complete"]),
                "stripe_subscription_id": t["stripe_subscription_id"],
                "ledger_dir": t["ledger_dir"],
            }
            for t in sorted(tenants.values(), key=lambda x: x["created"], reverse=True)
        ],
    })


@router.get("/tenants/{email}", dependencies=[Depends(require_admin)])
async def tenant_detail(email: str):
    tenant = appdb.get_tenant(email.lower())
    if not tenant:
        return _err("Tenant not found", 404)
    return _ok({
        "email": tenant["email"],
        "name": tenant["name"],
        "plan": tenant["plan"],
        "status": tenant["status"],
        "created": tenant["created"],
        "trial_ends": tenant["trial_ends"],
        "stripe_customer_id": tenant["stripe_customer_id"],
        "stripe_subscription_id": tenant["stripe_subscription_id"],
        "onboarding_complete": bool(tenant["onboarding_complete"]),
        "ledger_dir": tenant["ledger_dir"],
        "has_plaid": bool(tenant.get("plaid_access_token")),
    })


@router.post("/tenants/{email}/cancel", dependencies=[Depends(require_admin)])
async def cancel_tenant(email: str):
    """Cancel a tenant's subscription and drop them to free."""
    tenant = appdb.get_tenant(email.lower())
    if not tenant:
        return _err("Tenant not found", 404)

    sub_id = tenant.get("stripe_subscription_id", "")
    if sub_id and os.environ.get("STRIPE_SECRET_KEY"):
        try:
            import stripe as stripe_lib
            stripe_lib.api_key = os.environ["STRIPE_SECRET_KEY"]
            stripe_lib.Subscription.cancel(sub_id)
        except Exception as e:
            return _err(f"Stripe cancel failed: {e}", 500)

    appdb.update_tenant(email.lower(), plan="free", status="canceled",
                        stripe_subscription_id="", trial_ends="")
    return _ok({"canceled": True, "email": email.lower()})


@router.post("/tenants/{email}/deprovision", dependencies=[Depends(require_admin)])
async def deprovision_tenant(email: str):
    """Permanently remove a tenant: cancel billing, delete the ledger dir
    and the tenant row (user + sessions cascade)."""
    tenant = appdb.get_tenant(email.lower())
    if not tenant:
        return _err("Tenant not found", 404)

    # Cancel billing first
    sub_id = tenant.get("stripe_subscription_id", "")
    if sub_id and os.environ.get("STRIPE_SECRET_KEY"):
        try:
            import stripe as stripe_lib
            stripe_lib.api_key = os.environ["STRIPE_SECRET_KEY"]
            stripe_lib.Subscription.cancel(sub_id)
        except Exception:
            pass

    ledger_dir = Path(tenant["ledger_dir"])
    if ledger_dir.exists() and ledger_dir.is_relative_to(Path(os.environ.get("SOLOLEDGER_DATA_DIR", str(Path(__file__).resolve().parent.parent.parent)))):
        shutil.rmtree(ledger_dir, ignore_errors=True)

    appdb.delete_tenant(email.lower())
    appdb.delete_api_keys_for_user(email.lower())
    from ..appdb import get_conn
    with get_conn():
        get_conn().execute("DELETE FROM users WHERE email = ?", (email.lower(),))  # cascades sessions
    return _ok({"deprovisioned": True, "email": email.lower()})


@router.get("/stats", dependencies=[Depends(require_admin)])
async def admin_stats():
    """High-level platform stats (no PII beyond counts)."""
    tenants = appdb.all_tenants()
    users = appdb.all_users()
    plans: dict[str, int] = {}
    statuses: dict[str, int] = {}
    for t in tenants.values():
        plans[t["plan"]] = plans.get(t["plan"], 0) + 1
        statuses[t["status"]] = statuses.get(t["status"], 0) + 1
    return _ok({
        "users": len(users),
        "tenants": len(tenants),
        "plans": plans,
        "statuses": statuses,
        "verified_users": sum(1 for u in users.values() if u.get("email_verified")),
    })
