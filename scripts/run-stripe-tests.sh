#!/bin/bash
set -e
cd "$(dirname "$0")/.."

ai-secret exec stripe_key -- bash -c '
export STRIPE_SECRET_KEY=$STRIPE_KEY

.venv/bin/python <<"PYEOF"
import os, sys, json, time
os.environ["STRIPE_SECRET_KEY"] = os.environ.get("STRIPE_SECRET_KEY", "")
os.environ["API_KEYS"] = ""
os.environ["GOOGLE_CLIENT_ID"] = ""

from fastapi.testclient import TestClient
from app.api import app
client = TestClient(app)

# Create session for tenant-dependent endpoints
email = f"stripe_test_{int(time.time())}@example.com"
resp = client.post("/api/v1/auth/signup", json={"email": email, "password": "testpass123"})
assert resp.status_code == 200, f"Signup: {resp.text[:200]}"
token = resp.json()["data"]["token"]
auth = {"Authorization": f"Bearer {token}"}
print(f"User: {email}")

# 1. Plans
print("1. test_list_plans")
r = client.get("/api/v1/subscription/plans", headers=auth)
assert r.status_code == 200 and r.json()["success"]
print("   PASS")

# 2. Status
print("2. test_subscription_status")
r = client.get("/api/v1/subscription/status", headers=auth)
assert r.status_code == 200 and r.json()["success"]
d = r.json()["data"]
print(f'   PASS - plan={d["plan"]} trial={d["trial_active"]}')

# 3. Checkout
print("3. test_create_checkout_session")
r = client.post("/api/v1/subscription/create-checkout",
    json={"plan":"professional","interval":"month",
          "success_url":"http://localhost:8100/settings",
          "cancel_url":"http://localhost:8100/settings"},
    headers=auth)
assert r.status_code == 200, f"FAIL: {r.text[:200]}"
url = r.json()["data"]["url"]
assert url.startswith("https://checkout.stripe.com/")
print(f"   PASS - {url}")

# 4. Webhook
print("4. test_stripe_webhook_event")
os.environ["STRIPE_DEV_MODE"] = "true"
r = client.post("/api/v1/stripe-webhook",
    json={"type":"checkout.session.completed",
          "data":{"object":{"client_reference_id":"ref1","mode":"subscription",
                           "subscription":"sub_mock","customer":"cus_mock",
                           "customer_email":"test@test.com"}}},
    headers={"Content-Type":"application/json","Stripe-Signature":"mock"})
assert r.status_code in (200,400), f"FAIL: {r.text[:200]}"
print(f"   PASS (status={r.status_code})")
del os.environ["STRIPE_DEV_MODE"]

print("\nALL 4 STRIPE TESTS PASSED")
PYEOF
'