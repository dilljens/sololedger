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

    def test_get_single_account(self, client):
        resp = client.get("/api/v1/coa/Assets:Bank:BusinessChecking")
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["account"] == "Assets:Bank:BusinessChecking"

        resp = client.get("/api/v1/coa/Does:Not:Exist")
        assert resp.status_code == 404

    def test_put_opens_new_account(self, client):
        resp = client.put("/api/v1/coa/Expenses:Marketing",
                          json={"name": "Marketing", "tag": "advertising"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["created"] is True

        resp = client.get("/api/v1/coa")
        accounts = [a["account"] for a in resp.json()["data"]["accounts"]]
        assert "Expenses:Marketing" in accounts

        # opened-but-empty account appears in the tree at balance 0
        resp = client.get("/api/v1/coa/tree")
        tree = resp.json()["data"]["tree"]
        expenses = next(g for g in tree if g["root"] == "Expenses")
        assert any(a["account"] == "Expenses:Marketing" and a["balance"] == 0.0
                   for a in expenses["accounts"])

    def test_put_existing_account_is_noop(self, client):
        resp = client.put("/api/v1/coa/Expenses:Software:SaaS", json={"name": "SaaS"})
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["already_exists"] is True
        assert data["created"] is False

    def test_put_invalid_account(self, client):
        resp = client.put("/api/v1/coa/NotAnAccount", json={})
        assert resp.status_code == 400

        resp = client.put("/api/v1/coa/Expenses:lowercase", json={})
        assert resp.status_code == 400

        resp = client.put("/api/v1/coa/Expenses:Has Space", json={})
        assert resp.status_code == 400
