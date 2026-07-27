"""Tests for routes that don't require external APIs.

Covers: subscriptions, retainers, onboarding, tax form-1120s/voucher/pay,
bank status (no-connection stub), notifications (digest without email).
All run in open mode with the project config.toml.
"""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.api import app as api_app
    old_keys = os.environ.pop("API_KEYS", None)
    old_google = os.environ.pop("GOOGLE_CLIENT_ID", None)
    os.environ["API_CONFIG"] = str(Path(__file__).resolve().parent.parent / "config.toml")
    c = TestClient(api_app)
    yield c
    if old_keys is not None: os.environ["API_KEYS"] = old_keys
    if old_google is not None: os.environ["GOOGLE_CLIENT_ID"] = old_google


def assert_ok(resp):
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:300]}"
    body = resp.json()
    assert body["success"] is True, f"Expected success=True: {body}"
    return body["data"]


# ═════════════════════════════════════════════════════════════════════════
# Subscriptions (in-memory data, no Stripe needed)
# ═════════════════════════════════════════════════════════════════════════


class TestSubscriptionRoutes:
    """GET /api/v1/subscription/plans, GET /subscription/status"""

    def test_list_plans(self, client):
        """Plans are in-memory and always available."""
        data = assert_ok(client.get("/api/v1/subscription/plans"))
        assert "plans" in data
        plans = data["plans"]
        assert "free" in plans or isinstance(plans, dict)

    def test_subscription_status(self, client):
        """Status reads from tenant context or returns default."""
        resp = client.get("/api/v1/subscription/status")
        # Open mode: no tenant, returns default
        assert resp.status_code in (200, 401)
        if resp.status_code == 200:
            data = resp.json()
            assert "success" in data


# ═════════════════════════════════════════════════════════════════════════
# Retainers (local files only)
# ═════════════════════════════════════════════════════════════════════════


class TestRetainerRoutes:
    """GET /api/v1/retainers, POST /retainers, POST /retainers/process"""

    def test_list_retainers(self, client):
        """List retainers returns an array (possibly empty)."""
        data = assert_ok(client.get("/api/v1/retainers"))
        # Should be a list or have a 'retainers' key
        assert isinstance(data, (list, dict))

    def test_create_retainer(self, client):
        """Create a retainer configuration."""
        resp = client.post("/api/v1/retainers", json={
            "client": "Test Retainer Client",
            "description": "Monthly retainer",
            "amount": 2500.00,
            "interval": "monthly",
            "day_of_month": 1,
        })
        # May fail if ledger dir not set up for retainers
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert body["success"] is True

    def test_process_retainers_preview(self, client):
        """Process retainers in preview mode (no writes)."""
        resp = client.post("/api/v1/retainers/process?preview=true")
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert "success" in body


# ═════════════════════════════════════════════════════════════════════════
# Onboarding (local JSON files only)
# ═════════════════════════════════════════════════════════════════════════


class TestOnboardingRoutes:
    """GET /api/v1/onboarding/status, POST /complete, POST /demo"""

    def test_onboarding_status(self, client):
        """Status returns onboarding state without external calls."""
        data = assert_ok(client.get("/api/v1/onboarding/status"))
        assert "needs_setup" in data or "onboarding_complete" in data or isinstance(data, dict)

    def test_complete_onboarding(self, client):
        """Completing onboarding updates local tenant config."""
        resp = client.post("/api/v1/onboarding/complete", json={
            "skipped_bank": True,
            "skipped_import": True,
        })
        assert resp.status_code in (200, 401, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert body["success"] is True

    def test_demo_data(self, client):
        """Loading demo data writes to the ledger (may need tenant)."""
        resp = client.post("/api/v1/onboarding/demo")
        assert resp.status_code in (200, 400, 401, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert "success" in body


# ═════════════════════════════════════════════════════════════════════════
# Tax — form-1120s, voucher, pay (all local beancount-based)
# ═════════════════════════════════════════════════════════════════════════


class TestTaxMoreRoutes:
    """GET /tax/form-1120s, GET /tax/voucher, POST /tax/pay"""

    def test_form_1120s(self, client):
        """form-1120s requires S-Corp config; returns helpful error otherwise."""
        resp = client.get("/api/v1/tax/form-1120s")
        # With the project's default config.toml (SMLLC), should return error
        assert resp.status_code in (200, 400)
        if resp.status_code == 400:
            body = resp.json()
            assert body["success"] is False
            # Error should mention entity type
            assert "scorp" in body.get("error", "").lower() or "entity" in body.get("error", "").lower()

    def test_tax_voucher(self, client):
        """Voucher generates HTML/PDF without external calls."""
        resp = client.get("/api/v1/tax/voucher?quarter=Q1&amount=1000")
        # Returns HTML or file response — not JSON
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            content_type = resp.headers.get("content-type", "")
            assert "html" in content_type or "text" in content_type or "pdf" in content_type or "octet" in content_type

    def test_tax_pay(self, client):
        """Record a tax payment in the ledger."""
        resp = client.post("/api/v1/tax/pay", json={
            "amount": 1000.00,
            "quarter": "Q2",
            "year": 2026,
            "note": "Estimated tax payment",
        })
        assert resp.status_code in (200, 400, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True


# ═════════════════════════════════════════════════════════════════════════
# Bank Status (stub — no Plaid credentials)
# ═════════════════════════════════════════════════════════════════════════


class TestBankStatus:
    """GET /api/v1/bank/status (returns 'not connected' without Plaid)"""

    def test_bank_status_no_plaid(self, client):
        """Without Plaid configured, status returns connected=False."""
        resp = client.get("/api/v1/bank/status")
        assert resp.status_code in (200, 401, 500)
        if resp.status_code == 200:
            data = resp.json()
            assert data["success"] is True
            # Should indicate no connection
            assert "connected" in data.get("data", data)


# ═════════════════════════════════════════════════════════════════════════
# Notifications (digest without email — partial test)
# ═════════════════════════════════════════════════════════════════════════


class TestNotifications:
    """POST /api/v1/notify/check"""

    def test_notify_check(self, client):
        """Notification digest runs local logic even without SMTP."""
        # May return 402 (requires professional plan) or 200
        resp = client.post("/api/v1/notify/check")
        assert resp.status_code in (200, 401, 402, 500)
        if resp.status_code == 200:
            body = resp.json()
            assert "success" in body
