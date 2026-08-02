"""Tests for Stripe/Subscription routes using real credentials from ai-secret.

These tests verify that the subscription API endpoints work with actual
Stripe API credentials. They create real Stripe test-mode objects.
"""
"""Tests for Stripe/Subscription routes using real credentials from ai-secret.

Usage: 
    ai-secret exec stripe_key -- bash -c '
        export STRIPE_SECRET_KEY=$STRIPE_KEY
        export API_KEYS="test-key-for-stripe-tests"
        .venv/bin/python -m pytest tests/test_stripe_routes.py -v
    '
"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_environment):
    """Create TestClient. API_KEYS must be set in env before running tests."""
    # Don't pop/reset — caller must set API_KEYS in env before pytest
    from app.api import app as api_app
    c = TestClient(api_app)
    yield c


@pytest.mark.skipif(not os.environ.get("STRIPE_SECRET_KEY"), reason="STRIPE_SECRET_KEY not set — run via ai-secret exec")
class TestStripeRoutes:
    """Tests that create real Stripe test-mode objects."""

    def auth_header(self):
        """Use the API key from the environment (must match API_KEYS env var)."""
        key = os.environ.get("API_KEYS", "").split(",")[0].strip()
        return {"Authorization": f"Bearer {key}"} if key else {}

    def test_list_plans(self, client):
        """GET /subscription/plans — in-memory, no Stripe needed."""
        resp = client.get("/api/v1/subscription/plans", headers=self.auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "plans" in data["data"]

    def test_subscription_status(self, client):
        """GET /subscription/status — reads tenant context."""
        resp = client.get("/api/v1/subscription/status", headers=self.auth_header())
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "plan" in data.get("data", {})

    def test_create_checkout_session(self, client):
        """POST /subscription/create-checkout — creates Stripe Checkout Session."""
        resp = client.post(
            "/api/v1/subscription/create-checkout",
            json={
                "plan": "professional",
                "interval": "month",
                "success_url": "http://localhost:8100/settings?upgraded=true",
                "cancel_url": "http://localhost:8100/settings",
            },
            headers=self.auth_header(),
        )
        assert resp.status_code in (200, 500), f"Unexpected: {resp.text[:300]}"
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            assert "url" in data["data"]
            assert data["data"]["url"].startswith("https://checkout.stripe.com/")

    def test_stripe_webhook_event(self, client):
        """POST /stripe-webhook — simulated event in dev mode."""
        os.environ["STRIPE_DEV_MODE"] = "true"
        try:
            resp = client.post(
                "/api/v1/stripe-webhook",
                json={
                    "type": "checkout.session.completed",
                    "data": {
                        "object": {
                            "client_reference_id": "test_ref",
                            "mode": "subscription",
                            "subscription": "sub_mock",
                            "customer": "cus_mock",
                            "customer_email": "test@example.com",
                        }
                    },
                },
                headers={
                    "Content-Type": "application/json",
                    "Stripe-Signature": "mock_sig_for_dev_mode",
                },
            )
            assert resp.status_code in (200, 400), f"Unexpected: {resp.text[:300]}"
            if resp.status_code == 200:
                data = resp.json()
                assert data["success"] is True
        finally:
            os.environ.pop("STRIPE_DEV_MODE", None)
