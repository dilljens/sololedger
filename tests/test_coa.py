"""Tests for Chart of Accounts API."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.api import app as api_app
    old_keys = os.environ.pop("API_KEYS", None)
    old_google = os.environ.pop("GOOGLE_CLIENT_ID", None)
    os.environ["API_CONFIG"] = str(
        Path(__file__).resolve().parent.parent / "config.toml"
    )
    c = TestClient(api_app)
    yield c
    if old_keys is not None:
        os.environ["API_KEYS"] = old_keys
    if old_google is not None:
        os.environ["GOOGLE_CLIENT_ID"] = old_google


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
