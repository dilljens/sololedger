"""Tests for Amazon order history importer."""
import csv
import io
import json
import os
import zipfile

import pytest

from app.db import TenantDB


@pytest.fixture
def db(tmp_path):
    """Fresh TenantDB for each test."""
    _db = TenantDB(tmp_path)
    yield _db
    _db.close()


@pytest.fixture
def sample_csv():
    """A minimal Amazon order history CSV."""
    return """Order ID,Order Date,Order Status,Title,Quantity,Item Total,Total Amount,Payment Method,Currency
ORD-001,2026-01-15T10:00:00Z,Shipped,Widget A,1,12.99,12.99,Visa - 9642,USD
ORD-001,2026-01-15T10:00:00Z,Shipped,Widget B,2,24.50,12.99,Visa - 9642,USD
ORD-002,2026-01-20T14:30:00Z,Shipped,Gadget,1,89.99,89.99,Mastercard - 5299,USD
ORD-003,2026-02-01T09:00:00Z,Cancelled,Old Item,1,5.00,5.00,Visa - 9642,USD
ORD-004,2026-02-05T16:00:00Z,Shipped,Book,3,45.00,45.00,,USD
"""


# ── Helper tests ────────────────────────────────────────────────────────


class TestHelpers:
    """Test Amazon parser helper functions."""

    def test_to_cents_normal(self):
        from app.importers.amazon import _to_cents
        assert _to_cents("12.99") == 1299
        assert _to_cents("0.00") == 0
        assert _to_cents("100.00") == 10000

    def test_to_cents_empty(self):
        from app.importers.amazon import _to_cents
        assert _to_cents("") is None
        assert _to_cents("Not Available") is None
        assert _to_cents("-") is None
        assert _to_cents(None) is None

    def test_to_cents_negative_quote(self):
        from app.importers.amazon import _to_cents
        # Amazon uses '-12' to quote negative values in Excel
        assert _to_cents("'-12.00'") == -1200

    def test_to_cents_thousands_separator(self):
        from app.importers.amazon import _to_cents
        assert _to_cents("1,060.53") == 106053

    def test_truncate_date(self):
        from app.importers.amazon import _truncate_date
        assert _truncate_date("2026-01-15T10:00:00Z") == "2026-01-15"
        assert _truncate_date("2026-01-15") == "2026-01-15"

    def test_payment_card_mask(self):
        from app.importers.amazon import _payment_card_mask
        assert _payment_card_mask("Visa - 9642") == "9642"
        assert _payment_card_mask("Mastercard 5299") == "5299"
        assert _payment_card_mask("") == ""


# ── CSV parsing tests ──────────────────────────────────────────────────


class TestParseOrders:
    """Test Amazon CSV parsing logic."""

    def test_parse_single_order(self, sample_csv, tmp_path):
        from app.importers.amazon import _read_csv, _parse_orders
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)
        rows = _read_csv(str(csv_path))
        orders = _parse_orders(rows)

        assert "ORD-001" in orders
        order = orders["ORD-001"]
        assert order["receipt"]["merchant"] == "Amazon.com"
        assert order["receipt"]["total_cents"] == 1299
        assert order["receipt"]["receipt_date"] == "2026-01-15"
        assert order["receipt"]["currency"] == "USD"
        assert len(order["items"]) == 2

    def test_parse_skips_cancelled(self, sample_csv, tmp_path):
        from app.importers.amazon import _read_csv, _parse_orders
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)
        rows = _read_csv(str(csv_path))
        orders = _parse_orders(rows)

        assert "ORD-003" not in orders, "Cancelled order should be skipped"

    def test_payment_card_detected(self, sample_csv, tmp_path):
        from app.importers.amazon import _read_csv, _parse_orders
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)
        rows = _read_csv(str(csv_path))
        orders = _parse_orders(rows)

        assert orders["ORD-001"]["payment_mask"] == "9642"
        assert orders["ORD-002"]["payment_mask"] == "5299"

    def test_read_from_zip(self, sample_csv, tmp_path):
        from app.importers.amazon import _read_csv
        zip_path = tmp_path / "orders.zip"
        with zipfile.ZipFile(zip_path, "w") as zf:
            zf.writestr("Order History.csv", sample_csv)
        rows = _read_csv(str(zip_path))
        assert len(rows) == 5


# ── Import tests ──────────────────────────────────────────────────────


class TestImportAmazon:
    """Test full import pipeline."""

    def test_import_inserts_orders(self, sample_csv, tmp_path, db):
        from app.importers.amazon import import_amazon_csv
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        result = import_amazon_csv(db, str(csv_path))

        assert result["imported"] == 3  # ORD-001, ORD-002, ORD-004
        assert result["errors"] == 0
        assert result["cancelled"] == 1  # ORD-003 is cancelled

        # Check DB
        receipts = db.execute("SELECT * FROM vendor_receipts").fetchall()
        assert len(receipts) == 3

        items = db.execute("SELECT * FROM vendor_receipt_items").fetchall()
        # ORD-001 has 2 items, ORD-002 has 1, ORD-004 has 1
        assert len(items) == 4

    def test_import_idempotent(self, sample_csv, tmp_path, db):
        """Re-importing should not duplicate."""
        from app.importers.amazon import import_amazon_csv
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        import_amazon_csv(db, str(csv_path))
        result = import_amazon_csv(db, str(csv_path))

        assert result["imported"] == 3  # Updates, not duplicates
        receipts = db.execute("SELECT * FROM vendor_receipts").fetchall()
        assert len(receipts) == 3

    def test_card_filter(self, sample_csv, tmp_path, db):
        from app.importers.amazon import import_amazon_csv
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        result = import_amazon_csv(db, str(csv_path), card_filter=["9642"])
        assert result["imported"] == 1  # ORD-001 (ORD-004 has no payment mask, filtered out)
        assert result["skipped"] == 2  # ORD-002 filtered (5299), ORD-004 filtered (no mask)
        assert result["cancelled"] == 1  # ORD-003

    def test_dry_run(self, sample_csv, tmp_path, db):
        from app.importers.amazon import import_amazon_csv
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        result = import_amazon_csv(db, str(csv_path), dry_run=True)
        assert result["imported"] == 3

        receipts = db.execute("SELECT * FROM vendor_receipts").fetchall()
        assert len(receipts) == 0  # Nothing written

    def test_preview(self, sample_csv, tmp_path):
        from app.importers.amazon import preview_amazon_csv
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        preview = preview_amazon_csv(str(csv_path))
        assert preview["order_count"] == 3  # excludes cancelled
        assert preview["item_count"] == 4
        assert len(preview["payment_masks"]) == 2
        assert "9642" in preview["payment_masks"]
        assert "5299" in preview["payment_masks"]


# ── API tests ──────────────────────────────────────────────────────────


class TestAmazonAPI:
    """Test Amazon import API endpoints."""

    @pytest.fixture
    def api_client(self, isolated_environment):
        from app.api import app as api_app
        from fastapi.testclient import TestClient
        os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
        client = TestClient(api_app)
        yield client
        os.environ.pop("SOLOLEDGER_OPEN_MODE", None)

    def test_preview_endpoint(self, sample_csv, tmp_path, api_client):
        csv_path = tmp_path / "orders.csv"
        csv_path.write_text(sample_csv)

        with open(str(csv_path), "rb") as f:
            resp = api_client.post(
                "/api/v1/import/amazon/preview",
                files={"file": ("orders.csv", f, "text/csv")},
            )

        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["order_count"] == 3
