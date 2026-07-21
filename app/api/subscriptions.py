"""Subscription / SaaS routes."""
import json
import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .deps import _current_tenant, _err, _load_tenants, _ok, _save_tenants, check_auth

router = APIRouter(prefix="/api/v1")

PLANS = {
    "free": {"name": "Free", "price_monthly": 0, "price_annual": 0},
    "professional": {"name": "Professional", "price_monthly": 2400, "price_annual": 24000},
    "business": {"name": "Business", "price_monthly": 5900, "price_annual": 59000},
}


class CreateCheckoutRequest(BaseModel):
    plan: str = "professional"
    interval: str = "month"
    success_url: str = "/settings?upgraded=true"
    cancel_url: str = "/settings"


@router.get("/subscription/plans", dependencies=[Depends(check_auth)])
async def list_plans():
    return _ok({
        "plans": {
            key: {
                "name": val["name"],
                "price_monthly": val["price_monthly"] / 100,
                "price_annual": val["price_annual"] / 100,
            }
            for key, val in PLANS.items()
        },
        "current_plan": (_current_tenant.get() or {}).get("plan", "free"),
    })


@router.get("/subscription/status", dependencies=[Depends(check_auth)])
async def subscription_status():
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    return _ok({
        "plan": tenant.get("plan", "free"),
        "status": tenant.get("status", "active"),
        "stripe_customer_id": bool(tenant.get("stripe_customer_id")),
        "stripe_subscription_id": tenant.get("stripe_subscription_id", ""),
        "email": tenant.get("email", ""),
    })


@router.post("/subscription/create-checkout", dependencies=[Depends(check_auth)])
async def create_subscription_checkout(req: CreateCheckoutRequest):
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return _err("Stripe not configured. Set STRIPE_SECRET_KEY.", 503)

    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    if req.plan not in PLANS:
        return _err(f"Unknown plan: {req.plan}", 400)

    plan_info = PLANS[req.plan]
    if req.interval not in ("month", "year"):
        return _err("Interval must be 'month' or 'year'", 400)

    price_cents = plan_info["price_annual"] if req.interval == "year" else plan_info["price_monthly"]

    base_url = os.environ.get("APP_URL", "http://localhost:8100")

    try:
        import stripe as stripe_lib

        customer_id = tenant.get("stripe_customer_id", "")
        if not customer_id:
            customer = stripe_lib.Customer.create(email=tenant["email"], metadata={"user_id": tenant["user_id"]})
            customer_id = customer.id
            tenants = _load_tenants()
            if tenant["email"] in tenants:
                tenants[tenant["email"]]["stripe_customer_id"] = customer_id
                _save_tenants(tenants)

        session = stripe_lib.checkout.Session.create(
            mode="subscription",
            customer=customer_id,
            line_items=[{
                "price_data": {
                    "currency": "usd",
                    "product_data": {
                        "name": f"SoloLedger {plan_info['name']}",
                        "description": f"{plan_info['name']} plan — {req.interval}ly",
                    },
                    "unit_amount": price_cents,
                    "recurring": {"interval": req.interval, "interval_count": 1},
                },
                "quantity": 1,
            }],
            metadata={
                "plan": req.plan,
                "interval": req.interval,
                "user_id": tenant["user_id"],
                "email": tenant["email"],
            },
            success_url=base_url + req.success_url,
            cancel_url=base_url + req.cancel_url,
        )
        return _ok({"url": session.url, "session_id": session.id})
    except Exception as e:
        return _err(f"Stripe error: {e}", 500)


@router.post("/subscription/portal", dependencies=[Depends(check_auth)])
async def billing_portal():
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return _err("Stripe not configured", 503)

    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    customer_id = tenant.get("stripe_customer_id", "")
    if not customer_id:
        return _err("No Stripe customer record. Subscribe first.", 400)

    base_url = os.environ.get("APP_URL", "http://localhost:8100")

    try:
        import stripe as stripe_lib
        session = stripe_lib.billing_portal.Session.create(
            customer=customer_id,
            return_url=base_url + "/settings",
        )
        return _ok({"url": session.url})
    except Exception as e:
        return _err(f"Stripe error: {e}", 500)


@router.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    import stripe as stripe_lib
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")
    dev_mode = os.environ.get("STRIPE_DEV_MODE", "").lower() in ("1", "true", "yes")

    if secret:
        try:
            event = stripe_lib.Webhook.construct_event(payload, sig_header, secret)
        except stripe_lib.error.SignatureVerificationError:
            return _err("Invalid signature", 400)
    elif dev_mode:
        event = json.loads(payload)
    else:
        return _err("Stripe webhook secret not configured. Set STRIPE_WEBHOOK_SECRET, or set STRIPE_DEV_MODE=true for development.", 503)

    event_type = event["type"]
    data = event["data"]["object"]

    def _get_email(obj) -> str:
        return (
            obj.get("customer_details", {}).get("email", "")
            or obj.get("customer_email", "")
            or obj.get("email", "")
        )

    def _update_tenant(email: str, updates: dict):
        tenants = _load_tenants()
        if email in tenants:
            tenants[email].update(updates)
            _save_tenants(tenants)

    def _find_tenant_by_customer(customer_id: str) -> str | None:
        tenants = _load_tenants()
        for email, t in tenants.items():
            if t.get("stripe_customer_id") == customer_id:
                return email
        return None

    if event_type == "checkout.session.completed":
        email = _get_email(data)
        plan = data.get("metadata", {}).get("plan", "professional")
        sub_id = data.get("subscription", "")
        customer_id = data.get("customer", "")

        if email:
            _update_tenant(email, {
                "plan": plan,
                "status": "active",
                "stripe_subscription_id": sub_id or "",
                "stripe_customer_id": customer_id or "",
            })

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer", "")
        status = data.get("status", "active")
        items = data.get("items", {}).get("data", [])
        metadata = data.get("metadata", {})
        plan = metadata.get("plan", "professional")

        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {
                "plan": plan if status == "active" else "free",
                "status": status,
                "stripe_subscription_id": data.get("id", ""),
            })

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {
                "plan": "free",
                "status": "canceled",
                "stripe_subscription_id": "",
            })

    elif event_type == "invoice.paid":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            sub_id = data.get("subscription", "")
            _update_tenant(email, {
                "status": "active",
                "stripe_subscription_id": sub_id or "",
            })

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer", "")
        email = _find_tenant_by_customer(customer_id)
        if email:
            _update_tenant(email, {"status": "past_due"})

    return _ok({"received": True, "event": event_type})
