"""Subscription / SaaS routes — Stripe checkout with trial + card capture,
billing portal, and signature-verified webhooks with idempotent processing.

Tier model (usage-first hybrid, per market research):
  free          $0     — capped invoices/receipts, basic imports, tax estimates
  professional  $19/mo — bank sync, receipt OCR, all importers, tax schedule-c
  business      $45/mo — reconciliation, exports, multi-entity

Signup requires email verification; paid access requires a card on file,
which Stripe Checkout collects at trial start (trial_period_days) so the
card is verified before any paid features are unlocked.
"""
import datetime
import os

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .. import appdb
from .deps import _current_tenant, _err, _ok, check_auth

router = APIRouter(prefix="/api/v1")

PLANS = {
    "free": {"name": "Free", "price_monthly": 0, "price_annual": 0},
    "professional": {"name": "Professional", "price_monthly": 1900, "price_annual": 15000},  # $19/mo, $150/yr
    "business": {"name": "Business", "price_monthly": 4500, "price_annual": 40000},           # $45/mo, $400/yr
}

TRIAL_DAYS = 14


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

    trial_ends = tenant.get("trial_ends", "")
    trial_active = False
    if trial_ends:
        try:
            ends = datetime.datetime.fromisoformat(trial_ends)
            trial_active = ends > datetime.datetime.now(datetime.timezone.utc)
        except (ValueError, TypeError):
            pass

    return _ok({
        "plan": tenant.get("plan", "free"),
        "status": tenant.get("status", "active"),
        "trial_ends": trial_ends,
        "trial_active": trial_active,
        "trial_days_remaining": (ends - datetime.datetime.now(datetime.timezone.utc)).days if trial_active else 0,
        "stripe_customer_id": bool(tenant.get("stripe_customer_id")),
        "stripe_subscription_id": tenant.get("stripe_subscription_id", ""),
        "email": tenant.get("email", ""),
    })


@router.post("/subscription/create-checkout", dependencies=[Depends(check_auth)])
async def create_subscription_checkout(req: CreateCheckoutRequest):
    """Start a paid plan. Collects the card via Stripe Checkout and begins a
    14-day trial (charged at trial end). Card capture verifies the payment
    method before paid features unlock."""
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not stripe_key:
        return _err("Stripe not configured. Set STRIPE_SECRET_KEY.", 503)

    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    if req.plan not in PLANS or req.plan == "free":
        return _err(f"Unknown or non-billable plan: {req.plan}", 400)

    plan_info = PLANS[req.plan]
    if req.interval not in ("month", "year"):
        return _err("Interval must be 'month' or 'year'", 400)

    price_cents = plan_info["price_annual"] if req.interval == "year" else plan_info["price_monthly"]

    base_url = os.environ.get("APP_URL", "http://localhost:8100").rstrip("/")

    # Validate redirect URLs: they must be relative paths so an attacker
    # can't smuggle an off-origin URL into the Stripe redirect.
    if not req.success_url.startswith("/") or not req.cancel_url.startswith("/"):
        return _err("Redirect URLs must be relative paths", 400)

    try:
        import stripe as stripe_lib
        stripe_lib.api_key = stripe_key

        customer_id = tenant.get("stripe_customer_id", "")
        if not customer_id:
            customer = stripe_lib.Customer.create(
                email=tenant["email"], metadata={"user_id": tenant["user_id"]}
            )
            customer_id = customer.id
            appdb.update_tenant(tenant["email"], stripe_customer_id=customer_id)

        # New subscribers get a trial that starts immediately; the card is
        # collected up front and charged at trial end. Existing subscribers
        # (already have a subscription) just get a fresh checkout without
        # another trial.
        already_subscribed = bool(tenant.get("stripe_subscription_id"))
        checkout_kwargs = {}
        if not already_subscribed:
            checkout_kwargs["subscription_data"] = {"trial_period_days": TRIAL_DAYS}

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
            **checkout_kwargs,
        )
        return _ok({"url": session.url, "session_id": session.id, "trial_days": None if already_subscribed else TRIAL_DAYS})
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
        stripe_lib.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        session = stripe_lib.billing_portal.Session.create(
            customer=customer_id,
            return_url=base_url + "/settings",
        )
        return _ok({"url": session.url})
    except Exception as e:
        return _err(f"Stripe error: {e}", 500)


# ── Webhook ───────────────────────────────────────────────────────────────


@router.post("/stripe-webhook", include_in_schema=False)
async def stripe_webhook(request: Request):
    payload = await request.body()
    sig_header = request.headers.get("stripe-signature", "")

    import stripe as stripe_lib
    secret = os.environ.get("STRIPE_WEBHOOK_SECRET", "")

    if not secret:
        return _err("Stripe webhook secret not configured. Set STRIPE_WEBHOOK_SECRET.", 503)

    try:
        event = stripe_lib.Webhook.construct_event(payload, sig_header, secret)
    except stripe_lib.error.SignatureVerificationError:
        return _err("Invalid signature", 400)
    except Exception:
        return _err("Invalid webhook payload", 400)

    # Idempotency: Stripe retries delivery; a duplicate event id must not
    # re-apply side effects.
    if not appdb.mark_event_processed(event["id"], event["type"]):
        return _ok({"received": True, "event": event["type"], "duplicate": True})

    event_type = event["type"]
    data = event["data"]["object"]

    def _find_email(obj) -> str:
        return (
            obj.get("customer_details", {}).get("email", "")
            or obj.get("customer_email", "")
            or obj.get("email", "")
        )

    if event_type == "checkout.session.completed":
        email = _find_email(data)
        plan = data.get("metadata", {}).get("plan", "professional")
        sub_id = data.get("subscription", "")
        customer_id = data.get("customer", "")

        if not email:
            customer_id = data.get("customer", "")
            email = appdb.find_tenant_by_stripe_customer(customer_id) or ""

        if email and appdb.get_tenant(email):
            updates = {
                "plan": plan,
                "status": "active",
                "stripe_subscription_id": sub_id or "",
                "stripe_customer_id": customer_id or "",
            }
            # Trial end comes from the subscription object when available
            if data.get("mode") == "subscription" and data.get("subscription"):
                try:
                    sub = stripe_lib.Subscription.retrieve(data["subscription"])
                    if sub.trial_end:
                        updates["trial_ends"] = datetime.datetime.fromtimestamp(
                            sub.trial_end, datetime.timezone.utc
                        ).isoformat()
                except Exception:
                    pass
            appdb.update_tenant(email, **updates)

    elif event_type == "customer.subscription.updated":
        customer_id = data.get("customer", "")
        status = data.get("status", "active")
        metadata = data.get("metadata", {})
        plan = metadata.get("plan", "")
        trial_end = data.get("trial_end")

        email = appdb.find_tenant_by_stripe_customer(customer_id)
        if email:
            updates = {
                "status": status,
                "stripe_subscription_id": data.get("id", ""),
            }
            if plan and plan in PLANS:
                updates["plan"] = plan if status == "active" else "free"
            if trial_end:
                updates["trial_ends"] = datetime.datetime.fromtimestamp(
                    trial_end, datetime.timezone.utc
                ).isoformat()
            appdb.update_tenant(email, **updates)

    elif event_type == "customer.subscription.deleted":
        customer_id = data.get("customer", "")
        email = appdb.find_tenant_by_stripe_customer(customer_id)
        if email:
            appdb.update_tenant(email, plan="free", status="canceled",
                                stripe_subscription_id="", trial_ends="")

    elif event_type == "invoice.paid":
        customer_id = data.get("customer", "")
        email = appdb.find_tenant_by_stripe_customer(customer_id)
        if email:
            appdb.update_tenant(email, status="active",
                                stripe_subscription_id=data.get("subscription", "") or "")

    elif event_type == "invoice.payment_failed":
        customer_id = data.get("customer", "")
        email = appdb.find_tenant_by_stripe_customer(customer_id)
        if email:
            appdb.update_tenant(email, status="past_due")

    return _ok({"received": True, "event": event_type})
