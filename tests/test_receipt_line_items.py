"""Tests for the line-item receipt reconciler — per-line CoA assignment + commit."""
import os
import uuid

import pytest
from fastapi.testclient import TestClient


@pytest.fixture
def client(isolated_environment):
    from app.api import app as api_app
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    c = TestClient(api_app)
    yield c
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


def _db():
    from app.config import Config
    from app.db import get_db, get_tenant_db_path
    cfg = Config(os.environ["API_CONFIG"])
    return get_db(get_tenant_db_path(cfg))


def _seed_receipt(db, merchant="Test Co", total_cents=15000, personal_item=False):
    source_id = f"{merchant}-{total_cents}-{uuid.uuid4().hex[:8]}"
    db.execute(
        "INSERT INTO vendor_receipts"
        " (vendor, source_id, receipt_date, merchant, total_cents, currency, status)"
        " VALUES ('test', ?, ?, ?, ?, 'USD', 'pending')",
        (source_id, "2026-07-10", merchant, total_cents),
    )
    rid = db.execute("SELECT last_insert_rowid()").fetchone()[0]
    for i, cents in enumerate([7500, 7500]):
        db.execute(
            "INSERT INTO vendor_receipt_items"
            " (receipt_id, description, quantity, unit_price_cents, total_cents, is_personal, sort_order)"
            " VALUES (?, ?, 1, ?, ?, ?, ?)",
            (rid, f"Item {i + 1}", cents, cents,
             1 if (personal_item and i == 1) else 0, i),
        )
    db.commit()
    return rid


class TestLineItemReconciler:
    def test_assign_and_commit_split(self, client):
        db = _db()
        rid = _seed_receipt(db)
        items = db.execute(
            "SELECT id FROM vendor_receipt_items WHERE receipt_id = ?", (rid,)
        ).fetchall()
        i1, i2 = items[0]["id"], items[1]["id"]

        r = client.put(f"/api/v1/receipts/{rid}/items/{i1}",
                       json={"coa_account": "Expenses:Software:SaaS"})
        assert r.status_code == 200, r.text
        assert r.json()["data"]["coa_account"] == "Expenses:Software:SaaS"

        r = client.put(f"/api/v1/receipts/{rid}/items/{i2}",
                       json={"coa_account": "Expenses:Supplies"})
        assert r.status_code == 200

        r = client.post(f"/api/v1/receipts/{rid}/commit", json={})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 150.0
        assert data["accounts"] == {"Expenses:Software:SaaS": 75.0,
                                    "Expenses:Supplies": 75.0}

        # Already committed → 409
        r = client.post(f"/api/v1/receipts/{rid}/commit", json={})
        assert r.status_code == 409

        # The ledger file received the split transaction
        tx_file = os.path.join(os.path.dirname(os.environ["API_CONFIG"]),
                               "transactions.beancount")
        with open(tx_file) as f:
            content = f.read()
        assert "Test Co" in content
        assert "Expenses:Software:SaaS" in content
        assert "Expenses:Supplies" in content

    def test_personal_items_excluded(self, client):
        db = _db()
        rid = _seed_receipt(db, merchant="Personal Mix", personal_item=True)
        items = db.execute(
            "SELECT id FROM vendor_receipt_items WHERE receipt_id = ?", (rid,)
        ).fetchall()
        r = client.put(f"/api/v1/receipts/{rid}/items/{items[0]['id']}",
                       json={"coa_account": "Expenses:Software:SaaS"})
        assert r.status_code == 200

        r = client.post(f"/api/v1/receipts/{rid}/commit", json={})
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["total"] == 75.0
        assert data["personal_excluded"] == 75.0

    def test_flags_on_item(self, client):
        db = _db()
        rid = _seed_receipt(db)
        items = db.execute(
            "SELECT id FROM vendor_receipt_items WHERE receipt_id = ?", (rid,)
        ).fetchall()
        r = client.put(f"/api/v1/receipts/{rid}/items/{items[0]['id']}",
                       json={"is_reimbursable": True})
        assert r.status_code == 200
        assert r.json()["data"]["is_reimbursable"] is True

    def test_commit_requires_assignment(self, client):
        db = _db()
        rid = _seed_receipt(db)
        r = client.post(f"/api/v1/receipts/{rid}/commit", json={})
        assert r.status_code == 400

    def test_item_must_belong_to_receipt(self, client):
        r = client.put("/api/v1/receipts/999999/items/999999",
                       json={"coa_account": "Expenses:Software:SaaS"})
        assert r.status_code == 404

    def test_invalid_account_rejected(self, client):
        db = _db()
        rid = _seed_receipt(db)
        items = db.execute(
            "SELECT id FROM vendor_receipt_items WHERE receipt_id = ?", (rid,)
        ).fetchall()
        r = client.put(f"/api/v1/receipts/{rid}/items/{items[0]['id']}",
                       json={"coa_account": "NotAnAccount"})
        assert r.status_code == 400

    def test_injection_account_rejected(self, client):
        """A coa_account containing directive text must be rejected — it
        would otherwise inject arbitrary Beancount into the ledger."""
        db = _db()
        rid = _seed_receipt(db)
        items = db.execute(
            "SELECT id FROM vendor_receipt_items WHERE receipt_id = ?", (rid,)
        ).fetchall()
        evil = ('Expenses:Supplies\n2026-07-11 * "Injected" "fake txn"\n'
                '  Assets:Bank:BusinessChecking  9999.00 USD\n'
                '  Expenses:Miscellaneous  -9999.00 USD\n  ;')
        r = client.put(f"/api/v1/receipts/{rid}/items/{items[0]['id']}",
                       json={"coa_account": evil})
        assert r.status_code == 400

        # same guard at the commit boundary: assign a valid account, then an
        # evil source account → the ledger-level validation rejects it (400)
        r = client.put(f"/api/v1/receipts/{rid}/items/{items[0]['id']}",
                       json={"coa_account": "Expenses:Software:SaaS"})
        assert r.status_code == 200
        r = client.post(f"/api/v1/receipts/{rid}/commit",
                        json={"source": "Assets:Bank:\n  Expenses:Evil  1.00 USD\n  Assets:Bank  -1.00 USD"})
        assert r.status_code == 400, r.text
        # claim was released — a clean commit still works
        r = client.post(f"/api/v1/receipts/{rid}/commit", json={})
        assert r.status_code == 200, r.text
