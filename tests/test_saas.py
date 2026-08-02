"""Tests for the multi-tenant SaaS layer: email verification, password
reset, plan gating / free-tier caps, and admin endpoints."""
import datetime
import os
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import appdb
from app.api import app as api_app
from app.api import deps


@pytest.fixture
def closed_client(isolated_environment):
    """TestClient with auth FAIL-CLOSED (no open mode, no API keys)."""
    for var in ("SOLOLEDGER_OPEN_MODE", "API_KEYS", "GOOGLE_CLIENT_ID", "ADMIN_API_KEY"):
        os.environ.pop(var, None)
    return TestClient(api_app)


@pytest.fixture
def open_client(isolated_environment):
    """TestClient in explicit open (demo) mode."""
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    yield TestClient(api_app)
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


@pytest.fixture
def verify_required_client(isolated_environment, monkeypatch):
    """Fail-closed client with email verification required and no mail
    transport — the signup response carries the verify token (dev path)."""
    for var in ("SOLOLEDGER_OPEN_MODE", "API_KEYS"):
        os.environ.pop(var, None)
    monkeypatch.setenv("SOLOLEDGER_REQUIRE_EMAIL_VERIFY", "true")
    return TestClient(api_app)


# ── Email verification ────────────────────────────────────────────────────


class TestEmailVerification:
    def test_signup_requires_verification(self, verify_required_client):
        resp = verify_required_client.post(
            "/api/v1/auth/signup",
            json={"email": "verify@example.com", "password": "password123", "name": "Verify"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data.get("verify_required") is True
        token = data.get("verify_token")
        assert token, "dev path must return the verify token"

        # Not verified yet → no tenant, and signin is blocked
        assert appdb.get_tenant("verify@example.com") is None
        signin = verify_required_client.post(
            "/api/v1/auth/signin",
            json={"email": "verify@example.com", "password": "password123"},
        )
        assert signin.status_code == 403, signin.text

        # Verify the email → workspace provisioned
        ok = verify_required_client.get(f"/api/v1/auth/verify-email?token={token}")
        assert ok.status_code == 200, ok.text
        tenant = appdb.get_tenant("verify@example.com")
        assert tenant is not None
        assert tenant["status"] == "pending"

        # Now signin works
        signin2 = verify_required_client.post(
            "/api/v1/auth/signin",
            json={"email": "verify@example.com", "password": "password123"},
        )
        assert signin2.status_code == 200, signin2.text

    def test_bad_verify_token_rejected(self, verify_required_client):
        resp = verify_required_client.get("/api/v1/auth/verify-email?token=nope")
        assert resp.status_code == 400, resp.text

    def test_signup_auto_verifies_without_transport(self, closed_client):
        """Without verification configured, signup provisions immediately."""
        resp = closed_client.post(
            "/api/v1/auth/signup",
            json={"email": "auto@example.com", "password": "password123", "name": "Auto"},
        )
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data.get("token")  # logged straight in
        assert appdb.get_tenant("auto@example.com") is not None
        assert appdb.get_user("auto@example.com")["email_verified"] == 1


# ── Password reset ────────────────────────────────────────────────────────


class TestPasswordReset:
    def test_reset_flow(self, closed_client):
        # Signup (auto-verified)
        closed_client.post(
            "/api/v1/auth/signup",
            json={"email": "reset@example.com", "password": "password123", "name": "Reset"},
        )
        # Forgot → returns 200 (no enumeration), sets a reset token
        resp = closed_client.post("/api/v1/auth/forgot-password", json={"email": "reset@example.com"})
        assert resp.status_code == 200
        user = appdb.get_user("reset@example.com")
        assert user["reset_token"]

        # Reset with the token
        resp = closed_client.post("/api/v1/auth/reset-password", json={
            "token": user["reset_token"], "password": "newpassword456",
        })
        assert resp.status_code == 200, resp.text

        # Old password fails, new works
        old = closed_client.post(
            "/api/v1/auth/signin", json={"email": "reset@example.com", "password": "password123"})
        assert old.status_code == 401
        new = closed_client.post(
            "/api/v1/auth/signin", json={"email": "reset@example.com", "password": "newpassword456"})
        assert new.status_code == 200

    def test_forgot_unknown_email_no_enumeration(self, closed_client):
        resp = closed_client.post("/api/v1/auth/forgot-password", json={"email": "nobody@example.com"})
        assert resp.status_code == 200, resp.text


# ── Plan gating ───────────────────────────────────────────────────────────


def _make_tenant(email: str, plan: str = "free", status: str = "active",
                 trial_ends: str = "") -> dict:
    from app.api.deps import create_tenant
    appdb.create_user(email, password_hash="x", name="Tenant", email_verified=True)
    tenant = create_tenant(email, "Tenant")
    appdb.update_tenant(email, plan=plan, status=status, trial_ends=trial_ends)
    return appdb.get_tenant(email)


class TestPlanGating:
    def test_free_cannot_access_professional(self, closed_client, monkeypatch):
        tenant = _make_tenant("free@example.com", plan="free", status="active")
        session = appdb.create_session("free-tok", "free@example.com", name="Free")
        resp = closed_client.get(
            "/api/v1/bank/accounts", headers={"Authorization": "Bearer free-tok"})
        assert resp.status_code == 402, resp.text

    def test_professional_can_access(self, closed_client):
        _make_tenant("pro@example.com", plan="professional", status="active")
        appdb.create_session("pro-tok", "pro@example.com", name="Pro")
        resp = closed_client.get(
            "/api/v1/bank/accounts", headers={"Authorization": "Bearer pro-tok"})
        # No Plaid configured → not a 402 (plan passed; config error instead)
        assert resp.status_code != 402, resp.text

    def test_trial_grants_professional(self, closed_client):
        future = (datetime.datetime.now(datetime.timezone.utc) + datetime.timedelta(days=7)).isoformat()
        _make_tenant("trial@example.com", plan="free", status="active", trial_ends=future)
        appdb.create_session("trial-tok", "trial@example.com", name="Trial")
        resp = closed_client.get(
            "/api/v1/bank/accounts", headers={"Authorization": "Bearer trial-tok"})
        assert resp.status_code != 402, resp.text

    def test_past_due_loses_paid_access(self, closed_client):
        _make_tenant("late@example.com", plan="business", status="past_due")
        appdb.create_session("late-tok", "late@example.com", name="Late")
        resp = closed_client.get(
            "/api/v1/bank/accounts", headers={"Authorization": "Bearer late-tok"})
        assert resp.status_code == 402, resp.text

    def test_free_invoice_cap(self, closed_client, sample_config):
        """A free tenant cannot create more than FREE_MAX_INVOICES."""
        tenant = _make_tenant("invc@example.com", plan="free", status="active")
        appdb.create_session("invc-tok", "invc@example.com", name="Invc")

        from app.invoice import Invoicer
        from app.ledger import Ledger
        from app.config import Config
        from app.api.deps import FREE_MAX_INVOICES

        # Seed the tenant ledger to the cap (template may already have sample invoices)
        cfg = Config(str(Path(tenant["ledger_dir"]) / "config.toml"))
        ledger = Ledger(cfg)
        inv = Invoicer(cfg, ledger)
        existing = len(inv.list_invoices())
        main = Path(tenant["ledger_dir"]) / "main.beancount"
        with open(main, "a") as f:
            for i in range(FREE_MAX_INVOICES - existing):
                f.write(
                    f'2026-01-{(i % 28) + 1:02d} * "Client {i}" "Invoice {i}"\n'
                    f'  {cfg.ar_account:45s}  100.00 USD\n'
                    f'  {cfg.income_account:45s}  -100.00 USD\n\n'
                )
        ledger.reload(force=True)
        assert len(inv.list_invoices()) >= FREE_MAX_INVOICES

        resp = closed_client.post(
            "/api/v1/invoices",
            headers={"Authorization": "Bearer invc-tok"},
            json={"client": "Over", "description": "Over the cap", "amount": 100.0},
        )
        assert resp.status_code == 402, resp.text


# ── Admin ─────────────────────────────────────────────────────────────────


class TestAdmin:
    def test_admin_disabled_without_key(self, closed_client):
        resp = closed_client.get("/api/v1/admin/tenants")
        assert resp.status_code == 404, resp.text

    def test_admin_list_and_stats(self, closed_client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        _make_tenant("admin@example.com", plan="business", status="active")
        appdb.create_user("plain@example.com", password_hash="x", name="Plain", email_verified=True)

        headers = {"Authorization": "Bearer admin-secret"}
        resp = closed_client.get("/api/v1/admin/tenants", headers=headers)
        assert resp.status_code == 200, resp.text
        data = resp.json()["data"]
        assert data["count"] >= 1
        assert any(t["email"] == "admin@example.com" for t in data["tenants"])

        stats = closed_client.get("/api/v1/admin/stats", headers=headers)
        assert stats.status_code == 200
        assert stats.json()["data"]["tenants"] >= 1

        # Wrong key rejected
        bad = closed_client.get("/api/v1/admin/tenants", headers={"Authorization": "Bearer wrong"})
        assert bad.status_code == 401

    def test_admin_deprovision(self, closed_client, monkeypatch):
        monkeypatch.setenv("ADMIN_API_KEY", "admin-secret")
        tenant = _make_tenant("gone@example.com", plan="free", status="active")
        headers = {"Authorization": "Bearer admin-secret"}
        resp = closed_client.post("/api/v1/admin/tenants/gone@example.com/deprovision", headers=headers)
        assert resp.status_code == 200, resp.text
        assert appdb.get_tenant("gone@example.com") is None
        assert appdb.get_user("gone@example.com") is None


# ── Sessions are DB-backed ────────────────────────────────────────────────


class TestDbSessions:
    def test_session_survives_reload(self, closed_client):
        """Sessions live in the DB — a fresh process/worker sees them."""
        from app import appdb
        appdb.create_user("db@example.com", password_hash="x", name="DB", email_verified=True)
        appdb.create_session("db-tok", "db@example.com", name="DB")
        # Simulate a fresh worker: read from a NEW connection
        assert appdb.get_session("db-tok") is not None
        assert appdb.get_session("db-tok")["email"] == "db@example.com"
        # Deleted sessions vanish
        appdb.delete_session("db-tok")
        assert appdb.get_session("db-tok") is None
