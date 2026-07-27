"""Tests for Categorization Rules API."""
import os
from pathlib import Path
import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client():
    from app.api import app as api_app
    old_keys = os.environ.pop("API_KEYS", None)
    old_google = os.environ.pop("GOOGLE_CLIENT_ID", None)
    c = TestClient(api_app)
    yield c
    if old_keys is not None:
        os.environ["API_KEYS"] = old_keys
    if old_google is not None:
        os.environ["GOOGLE_CLIENT_ID"] = old_google


class TestRulesAPI:
    def test_create_rule(self, client):
        resp = client.post("/api/v1/rules", json={
            "pattern": "AMAZON",
            "target_account": "Expenses:Software:SaaS",
            "matcher_type": "substring",
            "priority": 1,
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "id" in data["data"]

    def test_list_rules(self, client):
        resp = client.get("/api/v1/rules")
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert "rules" in data["data"]

    def test_test_rule_endpoint(self, client):
        resp = client.post("/api/v1/rules/test", data={
            "merchant": "AMAZON WEB SERVICES",
            "pattern": "AMAZON",
            "matcher_type": "substring",
        })
        assert resp.status_code == 200
        data = resp.json()
        assert data["data"]["matches"] is True

    def test_delete_rule(self, client):
        # Create first
        create = client.post("/api/v1/rules", json={
            "pattern": "TEST", "target_account": "Expenses:Test", "matcher_type": "substring"
        })
        rule_id = create.json()["data"]["id"]

        # Then delete
        resp = client.delete(f"/api/v1/rules/{rule_id}")
        assert resp.status_code == 200
        assert resp.json()["success"] is True
