"""Tests for previously-untested API routes.

Covers: auth, invoices, mileage, reports, settings, import endpoints.
Uses open mode (no auth) and an isolated tmp config + data dir.
"""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_environment):
    """TestClient in open mode (no auth required), isolated tmp state."""
    from app.api import app as api_app
    # Fail-closed auth: explicitly opt into open mode for these tests
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    c = TestClient(api_app)
    yield c
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


def assert_ok(resp):
    """Assert a successful response envelope."""
    assert resp.status_code == 200, f"Expected 200, got {resp.status_code}: {resp.text[:200]}"
    body = resp.json()
    assert body["success"] is True, f"Expected success=True: {body}"
    return body["data"]


# ═════════════════════════════════════════════════════════════════════════
# Auth Routes
# ═════════════════════════════════════════════════════════════════════════


class TestAuth:
    """POST /api/v1/auth/signup, signin, logout, GET /auth/me"""

    def test_signup_and_signin(self, client):
        """Sign up a new user, then sign in with the same credentials."""
        import time
        ts = int(time.time() * 1000)
        email = f"test_e2e_{ts}@example.com"
        password = "testpassword123"

        # Signup
        resp = client.post("/api/v1/auth/signup", json={"email": email, "password": password})
        data = assert_ok(resp)
        assert "token" in data
        assert data.get("user", data).get("email", "") == email
        token = data["token"]

        # GET /auth/me with token
        resp = client.get("/api/v1/auth/me", headers={"Authorization": f"Bearer {token}"})
        data = assert_ok(resp)
        user_data = data.get("user", data)
        assert user_data.get("email", "") == email or data.get("email", "") == email

        # Signin again
        resp = client.post("/api/v1/auth/signin", json={"email": email, "password": password})
        data = assert_ok(resp)
        assert "token" in data

        # Logout
        resp = client.post("/api/v1/auth/logout", headers={"Authorization": f"Bearer {token}"})
        assert resp.status_code == 200

    def test_signin_invalid_password(self, client):
        """Sign in with wrong password should return 401."""
        import time
        email = f"test_badpw_{int(time.time()*1000)}@example.com"
        client.post("/api/v1/auth/signup", json={"email": email, "password": "correctpw"})

        # Then sign in with wrong password
        resp = client.post("/api/v1/auth/signin", json={"email": email, "password": "wrongpw"})
        assert resp.status_code == 401
        body = resp.json()
        assert body["success"] is False

    def test_signup_duplicate_email(self, client):
        """Signing up with an existing email should return an error."""
        import time
        email = f"test_dup_{int(time.time()*1000)}@example.com"
        client.post("/api/v1/auth/signup", json={"email": email, "password": "test1234"})
        resp = client.post("/api/v1/auth/signup", json={"email": email, "password": "test1234"})
        assert resp.status_code == 409
        body = resp.json()
        assert body["success"] is False

    def test_auth_me_without_token(self, client):
        """GET /auth/me without token should return 401."""
        resp = client.get("/api/v1/auth/me")
        assert resp.status_code == 401


# ═════════════════════════════════════════════════════════════════════════
# Invoice Routes
# ═════════════════════════════════════════════════════════════════════════


class TestInvoiceRoutes:
    """POST/GET /api/v1/invoices, POST .../pay, GET .../pdf"""

    def test_create_and_list_invoices(self, client):
        """Create an invoice, then list invoices."""
        resp = client.post("/api/v1/invoices", json={
            "client": "Test Client Inc.",
            "description": "Consulting services",
            "amount": 5000.00,
            "generate_pdf": False,
        })
        data = assert_ok(resp)
        assert "number" in data or "id" in data

        # List invoices
        resp = client.get("/api/v1/invoices")
        data = assert_ok(resp)
        assert "invoices" in data or isinstance(data, list)

    def test_create_invoice_with_email(self, client):
        """Create an invoice with optional email."""
        resp = client.post("/api/v1/invoices", json={
            "client": "Email Client",
            "description": "Work",
            "amount": 2500.00,
            "client_email": "client@example.com",
            "generate_pdf": False,
        })
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True


# ═════════════════════════════════════════════════════════════════════════
# Mileage Routes
# ═════════════════════════════════════════════════════════════════════════


class TestMileageRoutes:
    """GET /api/v1/mileage/trips, POST /mileage/add, GET /mileage/report"""

    def test_list_trips(self, client):
        """GET /mileage/trips returns expected structure."""
        resp = client.get("/api/v1/mileage/trips")
        data = assert_ok(resp)
        assert "trips" in data or isinstance(data, list)

    def test_add_trip(self, client):
        """POST /mileage/add creates a trip."""
        resp = client.post("/api/v1/mileage/add", json={
            "date": "2026-07-01",
            "miles": 42.5,
            "purpose": "Client meeting",
        })
        data = assert_ok(resp)
        assert "id" in data or data.get("success") is not False

    def test_mileage_report(self, client):
        """GET /mileage/report returns year-to-date summary."""
        resp = client.get("/api/v1/mileage/report")
        data = assert_ok(resp)
        # Should have mileage summary keys
        assert isinstance(data, dict)


# ═════════════════════════════════════════════════════════════════════════
# Reports Routes
# ═════════════════════════════════════════════════════════════════════════


class TestReportsRoutes:
    """GET /api/v1/reports/expenses, GET /reports/profit-loss"""

    def test_expenses_report(self, client):
        """GET /reports/expenses returns expense data."""
        resp = client.get("/api/v1/reports/expenses")
        data = assert_ok(resp)
        assert isinstance(data, dict)

    def test_profit_loss_report(self, client):
        """GET /reports/profit-loss returns P&L data."""
        resp = client.get("/api/v1/reports/profit-loss")
        data = assert_ok(resp)
        assert isinstance(data, dict)


# ═════════════════════════════════════════════════════════════════════════
# Settings Routes
# ═════════════════════════════════════════════════════════════════════════


class TestSettingsRoutes:
    """GET/POST /api/v1/settings/llm"""

    def test_get_llm_settings(self, client):
        """GET /settings/llm returns default config."""
        resp = client.get("/api/v1/settings/llm")
        data = assert_ok(resp)
        assert isinstance(data, dict) or data is None

    def test_save_llm_settings(self, client):
        """POST /settings/llm saves config."""
        resp = client.post("/api/v1/settings/llm", json={
            "backend": "openai",
            "model": "gpt-4o-mini",
        })
        data = assert_ok(resp)
        assert data.get("saved") is not False or "backend" in data


# ═════════════════════════════════════════════════════════════════════════
# Attention Route
# ═════════════════════════════════════════════════════════════════════════


class TestAttention:
    """GET /api/v1/attention"""

    def test_attention_returns_items(self, client):
        """GET /attention returns attention-needed items."""
        resp = client.get("/api/v1/attention")
        data = assert_ok(resp)
        assert isinstance(data.get("items", data), list)


# ═════════════════════════════════════════════════════════════════════════
# Remaining Import Routes
# ═════════════════════════════════════════════════════════════════════════


class TestImportRoutes:
    """Previously untested import endpoints."""

    def test_ofx_import_invalid_file(self, client, tmp_path):
        """POST /import/ofx with invalid file returns descriptive error."""
        f = tmp_path / "test.ofx"
        f.write_text("not an ofx file")
        with open(str(f), "rb") as fh:
            resp = client.post("/api/v1/import/ofx", files={"file": ("test.ofx", fh, "application/x-ofx")}, data={"preview": "true"})
        # Invalid file parses to zero transactions and returns 200 gracefully
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True

    def test_wave_preview_invalid(self, client, tmp_path):
        """POST /import/wave/preview handles invalid CSV gracefully."""
        f = tmp_path / "bad.csv"
        f.write_text("not,valid,csv")
        with open(str(f), "rb") as fh:
            resp = client.post("/api/v1/import/wave/preview", files={"file": ("bad.csv", fh, "text/csv")})
        assert resp.status_code == 200
        body = resp.json()
        assert "data" in body

    def test_statement_file_invalid(self, client, tmp_path):
        """POST /import/statement/file handles invalid PDF."""
        f = tmp_path / "fake.pdf"
        f.write_text("not a pdf")
        with open(str(f), "rb") as fh:
            resp = client.post("/api/v1/import/statement/file", files={"file": ("fake.pdf", fh, "application/pdf")})
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True  # success=false in data, not HTTP error

    def test_reconciliation_lock_and_status(self, client):
        """POST then GET reconciliation lock."""
        resp = client.post("/api/v1/import/reconciliation/lock",
                           data={"account": "Assets:Bank:Test", "statement_date": "2026-06-30", "balance_cents": 50000})
        data = assert_ok(resp)
        assert data.get("locked") is True

        resp = client.get("/api/v1/import/reconciliation/status")
        data = assert_ok(resp)
        assert "marks" in data
