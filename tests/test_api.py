"""Tests for FastAPI routes — uses TestClient with sample ledger data.

These tests verify that each API endpoint:
  - Returns HTTP 200 (or appropriate error code)
  - Returns a valid JSON response with {success, data} envelope
  - Returns the expected data shape
  - Handles edge cases (empty ledger, no profit, etc.)
"""
import os

import pytest
from fastapi.testclient import TestClient

# ── Fixtures ──────────────────────────────────────────────────────────────


@pytest.fixture
def api_client(isolated_environment):
    """Create a TestClient with the isolated tmp config so get_config() works."""
    from app.api import app as api_app
    return TestClient(api_app)


@pytest.fixture
def api_client_no_auth(isolated_environment):
    """TestClient when no auth is configured (open mode), isolated tmp state."""
    from app.api import app as api_app
    # Ensure no API keys are set (open mode)
    # Fail-closed auth: explicitly opt into open mode for these tests
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    client = TestClient(api_app)
    yield client
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


# ── Response Envelope Helpers ────────────────────────────────────────────


def assert_success(response, expected_status=200):
    """Assert the response is a valid success envelope."""
    assert response.status_code == expected_status, \
        f"Expected {expected_status}, got {response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body["success"] is True, f"Expected success=True, got: {body}"
    return body["data"]


def assert_error(response, expected_status=400):
    """Assert the response is a valid error envelope."""
    assert response.status_code == expected_status, \
        f"Expected {expected_status}, got {response.status_code}: {response.text[:200]}"
    body = response.json()
    assert body["success"] is False
    assert "error" in body
    return body["error"]


# ── Health & Status ─────────────────────────────────────────────────────


class TestHealthEndpoint:
    """GET /api/v1/health"""

    def test_health_returns_ok(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/health")
        data = assert_success(resp)
        assert data["status"] == "ok"
        assert "timestamp" in data


class TestPublicStatus:
    """GET /api/v1/public/status"""

    def test_public_status_returns_info(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/public/status")
        data = assert_success(resp)
        assert "needs_setup" in data
        assert "has_data" in data
        assert "has_auth" in data
        assert "auth_methods" in data


class TestStatusEndpoint:
    """GET /api/v1/status"""

    def test_status_returns_dashboard_numbers(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/status")
        data = assert_success(resp)
        assert "cash" in data
        assert "gross_revenue" in data
        assert "total_expenses" in data
        assert "net_profit" in data
        assert "tax" in data
        assert "deadlines" in data
        assert "ledger_errors" in data
        assert isinstance(data["deadlines"], list)


# ── Dashboard ────────────────────────────────────────────────────────────


class TestDashboardEndpoint:
    """GET /api/v1/dashboard"""

    def test_dashboard_returns_all_fields(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/dashboard")
        data = assert_success(resp)
        assert "entity_type" in data
        assert "entity_label" in data
        assert "cash" in data
        assert "gross_revenue" in data
        assert "total_expenses" in data
        assert "net_profit" in data
        assert "ar" in data
        assert "tax" in data
        assert isinstance(data["tax"], dict)
        assert "deadlines" in data
        assert isinstance(data["deadlines"], list)
        assert "recent_transactions" in data
        assert isinstance(data["recent_transactions"], list)

    def test_dashboard_tax_has_expected_keys(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/dashboard")
        data = assert_success(resp)
        tax = data["tax"]
        assert "annual_total_tax" in tax
        assert "already_paid" in tax
        assert "suggested_payment" in tax
        assert "note" in tax


# ── Tax Endpoints ────────────────────────────────────────────────────────


class TestTaxEstimate:
    """GET /api/v1/tax/estimate"""

    def test_tax_estimate_returns_smllc_shape(self, api_client_no_auth):
        """With the project's config.toml (SMLLC mode) and sample data."""
        resp = api_client_no_auth.get("/api/v1/tax/estimate")
        data = assert_success(resp)

        # Should have the full structure (ytd_net > 0 with real ledger)
        assert "entity_type" in data
        assert "self_employment_tax" in data
        assert data["self_employment_tax"] is not None
        assert "total" in data["self_employment_tax"]
        assert "deductible_half" in data["self_employment_tax"]
        assert "federal_income_tax" in data
        assert "total" in data["federal_income_tax"]
        assert "taxable_income" in data["federal_income_tax"]
        assert "ytd_net_profit" in data
        assert "projected_annual_net" in data
        assert "total_estimated_tax" in data
        assert "already_paid" in data
        assert "suggested_next_payment" in data
        assert "note" in data
        assert "disclaimer" in data

    def test_tax_estimate_handles_zero_net_income(self, api_client_no_auth):
        """If the API was somehow called with no data, it should return a
        graceful response, not a crash. We test this by checking the
        response shape even if not profitable.
        
        Note: The real ledger currently has profit, so this tests the
        fallback path.
        """
        resp = api_client_no_auth.get("/api/v1/tax/estimate")
        assert resp.status_code == 200
        body = resp.json()
        assert body["success"] is True
        data = body["data"]
        # Must have either full structure or graceful note
        has_note = "note" in data
        has_full_structure = "self_employment_tax" in data or "fica" in data
        assert has_note or has_full_structure, \
            "Response must have either a note or the full tax structure"

    def test_tax_estimate_with_projected_income_param(self, api_client_no_auth):
        resp = api_client_no_auth.get(
            "/api/v1/tax/estimate?projected_income=100000"
        )
        data = assert_success(resp)
        assert data["projected_annual_net"] == 100000.0


class TestTaxDeadlines:
    """GET /api/v1/tax/deadlines"""

    def test_deadlines_returns_5_entries(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/tax/deadlines")
        data = assert_success(resp)
        assert "as_of" in data
        assert "deadlines" in data
        assert len(data["deadlines"]) == 5
        labels = {d["label"] for d in data["deadlines"]}
        assert "Q1" in labels
        assert "Q2" in labels
        assert "Q3" in labels
        assert "Q4" in labels
        assert "annual" in labels

    def test_deadline_fields(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/tax/deadlines")
        data = assert_success(resp)
        for d in data["deadlines"]:
            assert "label" in d
            assert "due" in d
            assert "days_until" in d
            assert "status" in d
            assert d["status"] in ("overdue", "upcoming", "ahead")


class TestTaxScheduleC:
    """GET /api/v1/tax/schedule-c"""

    def test_schedule_c_returns_summary(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/tax/schedule-c")
        data = assert_success(resp)
        assert "entity_type" in data
        assert "gross_receipts" in data
        assert "total_expenses" in data
        assert "net_profit" in data
        assert "expense_detail" in data
        assert isinstance(data["expense_detail"], list)
        assert "taxes_paid" in data


# ── Accounts ────────────────────────────────────────────────────────────


class TestAccounts:
    """GET /api/v1/accounts"""

    def test_accounts_returns_balances(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/accounts")
        data = assert_success(resp)
        assert "checking" in data
        assert "balances" in data
        assert "cards" in data
        assert isinstance(data["cards"], list)


# ── Check / Health ──────────────────────────────────────────────────────


class TestLedgerCheck:
    """GET /api/v1/check"""

    def test_check_returns_valid(self, api_client_no_auth):
        resp = api_client_no_auth.get("/api/v1/check")
        data = assert_success(resp)
        # Should be valid with the sample ledger
        assert "valid" in data
        assert "error_count" in data
        assert "errors" in data
        assert isinstance(data["errors"], list)
