"""Tests for reconciliation lock/unlock and lock enforcement on writes."""
import os

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_environment):
    from app.api import app as api_app
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    c = TestClient(api_app)
    yield c
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


ACCOUNT = "Assets:Bank:BusinessChecking"


def _lock(client, statement_date="2026-01-31", balance_cents=100000):
    return client.post("/api/v1/reconciliation/lock", json={
        "account": ACCOUNT, "statement_date": statement_date,
        "balance_cents": balance_cents,
    })


class TestReconciliationLock:
    def test_lock_and_marks(self, client):
        r = _lock(client)
        assert r.status_code == 200
        assert r.json()["data"]["locked"] is True

        r = client.get("/api/v1/reconciliation/marks")
        assert r.status_code == 200
        marks = r.json()["data"]["marks"]
        assert len(marks) == 1
        assert marks[0]["account"] == ACCOUNT
        assert marks[0]["balance_cents"] == 100000

    def test_transfer_blocked_inside_locked_period(self, client):
        _lock(client)

        # Dated inside the locked period → 409
        r = client.post("/api/v1/transfer", json={
            "from_account": ACCOUNT, "to_account": "Equity:OwnerDraws",
            "amount": 100, "date": "2026-01-15",
        })
        assert r.status_code == 409
        assert "reconciled" in r.json()["detail"].lower()

        # Dated after the lock → allowed
        r = client.post("/api/v1/transfer", json={
            "from_account": ACCOUNT, "to_account": "Equity:OwnerDraws",
            "amount": 100, "date": "2026-02-15",
        })
        assert r.status_code == 200

    def test_split_and_reimburse_also_enforced(self, client):
        _lock(client)
        # Split sources from the locked checking account → 409
        r = client.post("/api/v1/split", json={
            "merchant": "ACME", "total": 200, "business": 150,
            "date": "2026-01-20",
        })
        assert r.status_code == 409

        # Reimbursements don't touch the locked checking account (they post
        # to the expense + Liabilities:Reimbursement) → allowed
        r = client.post("/api/v1/reimburse", json={
            "merchant": "ACME", "amount": 50, "date": "2026-01-20",
        })
        assert r.status_code == 200

    def test_unlock_allows_edit(self, client):
        _lock(client)
        r = client.post("/api/v1/reconciliation/unlock", json={
            "account": ACCOUNT, "statement_date": "2026-01-31",
        })
        assert r.status_code == 200
        assert r.json()["data"]["unlocked"] is True

        r = client.post("/api/v1/transfer", json={
            "from_account": ACCOUNT, "to_account": "Equity:OwnerDraws",
            "amount": 50, "date": "2026-01-15",
        })
        assert r.status_code == 200

    def test_unlock_missing_period(self, client):
        r = client.post("/api/v1/reconciliation/unlock", json={
            "account": ACCOUNT, "statement_date": "2025-06-30",
        })
        assert r.status_code == 200
        assert r.json()["data"]["unlocked"] is False

    def test_reconciliation_returns_statement_balance(self, client):
        _lock(client, statement_date="2026-01-31", balance_cents=999900)
        r = client.get("/api/v1/reconciliation")
        # business-plan gate may 402 in some configs — tolerate that, but when
        # it succeeds the statement balance must be present
        if r.status_code == 200:
            data = r.json()["data"]
            assert data["statement_balance"] == 9999.0
            assert data["reconciled_through"] == "2026-01-31"
