"""Tests for Chart of Accounts API."""
import os
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_environment):
    from app.api import app as api_app
    # Fail-closed auth: explicitly opt into open mode for these tests
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    c = TestClient(api_app)
    yield c
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


class TestCOA:
    def test_list_accounts(self, client):
        resp = client.get("/api/v1/coa")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "accounts" in data["data"]
        assert data["data"]["count"] > 0

    def test_account_tree(self, client):
        resp = client.get("/api/v1/coa/tree")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert len(data["data"]["tree"]) > 0
