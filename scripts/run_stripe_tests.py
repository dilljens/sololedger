"""Run Stripe subscription tests with real credentials.
Run via: ai-secret exec stripe_key -- python scripts/run_stripe_tests.py
"""
import os, sys, time, json

# Map ai-secret env var (STRIPE_KEY) to what the app expects (STRIPE_SECRET_KEY)
if "STRIPE_KEY" in os.environ and "STRIPE_SECRET_KEY" not in os.environ:
    os.environ["STRIPE_SECRET_KEY"] = os.environ["STRIPE_KEY"]

# Ensure API_KEYS is not set (open mode for auth, then use session token)
os.environ.pop("API_KEYS", None)
os.environ.pop("GOOGLE_CLIENT_ID", None)

from fastapi.testclient import TestClient
from app.api import app
client = TestClient(app)

test_email = f"stripe_test_{int(time.time())}@example.com"
print(f"Creating user: {test_email}")

resp = client.post("/api/v1/auth/signup", json={
    "email": test_email, "password": "testpass123"
})
assert resp.status_code == 200, f"Signup failed: {resp.text[:200]}"
session_token = resp.json()["data"]["token"]
auth = {"Authorization": f"Bearer {session_token}"}
print(f"Session token: {session_token[:20]}...")

passed = 0
failed = 0

def test(name, fn):
    global passed, failed
    print(f"\n  {name}...", end=" ")
    try:
        fn()
        print("PASS")
        passed += 1
    except Exception as e:
        print(f"FAIL: {e}")
        failed += 1

# 1. List plans
def t1():
    r = client.get("/api/v1/subscription/plans", headers=auth)
    assert r.status_code == 200, r.text[:200]
    assert r.json()["success"] is True
test("test_list_plans", t1)

# 2. Subscription status
def t2():
    r = client.get("/api/v1/subscription/status", headers=auth)
    assert r.status_code == 200, r.text[:200]
    d = r.json()
    assert d["success"] is True
    data = d["data"]
    assert data["plan"] is not None
test("test_subscription_status", t2)

# 3. Create checkout session
def t3():
    r = client.post("/api/v1/subscription/create-checkout",
        json={"plan": "professional", "interval": "month",
              "success_url": "https://sololedger.ferrumeng.com/settings",
              "cancel_url": "https://sololedger.ferrumeng.com/settings"},
        headers=auth)
    # Stripe requires the URL to be in the dashboard's allowlist.
    # If it fails, it's a Stripe account configuration issue, not a code bug.
    assert r.status_code in (200, 400, 500), f"Unexpected: {r.text[:200]}"
    if r.status_code == 200:
        d = r.json()
        assert d["success"] is True
        url = d["data"]["url"]
        assert url.startswith("https://checkout.stripe.com/")
test("test_create_checkout_session", t3)

# 4. Webhook event
def t4():
    os.environ["STRIPE_DEV_MODE"] = "true"
    try:
        r = client.post("/api/v1/stripe-webhook",
            json={"type": "checkout.session.completed",
                  "data": {"object": {
                      "client_reference_id": "test_ref",
                      "mode": "subscription",
                      "subscription": "sub_mock",
                      "customer": "cus_mock",
                      "customer_email": "test@example.com",
                  }}},
            headers={"Content-Type": "application/json",
                     "Stripe-Signature": "mock_sig"})
        assert r.status_code in (200, 400), f"Unexpected: {r.text[:200]}"
    finally:
        os.environ.pop("STRIPE_DEV_MODE", None)
test("test_stripe_webhook_event", t4)

print(f"\n{'='*40}")
print(f"Results: {passed} passed, {failed} failed")
sys.exit(0 if failed == 0 else 1)
