"""Tests for Citi CSV importer."""
import csv
import io

import pytest

from app.db import TenantDB


CITI_CSV = """Time period of report:,"Apr. 01, 2026 (09:00 AM) to Apr. 30, 2026 (09:00 AM)"
,,
Date,Description,Debit,Credit,Category,Name,Card
"Apr 02, 2026",STARBUCKS SEATTLE WA,5.50,,Restaurants,JAMES,Card-9642
"Apr 05, 2026","BIG PURCHASE 1234567890","2,144.83",,Groceries,JAMES,Card-9642
"Apr 12, 2026",COMFORT INNS TUALATIN OR,,200.00,Travel,JAMES,Card-9642
"Apr 15, 2026",AMAZON.COM,89.99,,Shopping,JULIE,Card-0375
"Apr 18, 2026",JULIE EXPENSE,35.00,,General Mdse,JULIE,Card-0375
"""


@pytest.fixture
def db(tmp_path):
    _db = TenantDB(tmp_path)
    yield _db
    _db.close()


@pytest.fixture
def citi_csv(tmp_path):
    path = tmp_path / "citi.csv"
    path.write_text(CITI_CSV)
    return path


# ─── Helpers ──────────────────────────────────────────────────────────────


class TestHelpers:
    def test_parse_date(self):
        from app.importers.citi import _parse_citi_date
        assert _parse_citi_date("Apr 02, 2026") == "2026-04-02"
        assert _parse_citi_date("Dec 31, 2025") == "2025-12-31"

    def test_parse_amount(self):
        from app.importers.citi import _parse_citi_amount_cents
        assert _parse_citi_amount_cents("5.50") == 550
        assert _parse_citi_amount_cents("2,144.83") == 214483
        assert _parse_citi_amount_cents("200.00") == 20000
        assert _parse_citi_amount_cents("") == 0
        assert _parse_citi_amount_cents("$50.00") == 5000


# ─── Detection ────────────────────────────────────────────────────────────


class TestDetection:
    def test_looks_like_citi_csv(self, citi_csv):
        from app.importers.citi import looks_like_citi_csv
        assert looks_like_citi_csv(str(citi_csv))

    def test_not_citi_csv(self, tmp_path):
        from app.importers.citi import looks_like_citi_csv
        f = tmp_path / "random.csv"
        f.write_text("a,b,c\n1,2,3")
        assert not looks_like_citi_csv(str(f))


# ─── Parser ──────────────────────────────────────────────────────────────


class TestParser:
    def test_parses_all_rows(self, citi_csv):
        from app.importers.citi import parse_citi_csv
        txns = parse_citi_csv(str(citi_csv))
        assert len(txns) == 5

    def test_charges_positive(self, citi_csv):
        from app.importers.citi import parse_citi_csv
        txns = parse_citi_csv(str(citi_csv))
        by_desc = {t["merchant_raw"]: t for t in txns}
        assert by_desc["STARBUCKS SEATTLE WA"]["amount_cents"] == 550
        assert by_desc["BIG PURCHASE 1234567890"]["amount_cents"] == 214483

    def test_refunds_negative(self, citi_csv):
        from app.importers.citi import parse_citi_csv
        txns = parse_citi_csv(str(citi_csv))
        by_desc = {t["merchant_raw"]: t for t in txns}
        assert by_desc["COMFORT INNS TUALATIN OR"]["amount_cents"] == -20000

    def test_card_and_category(self, citi_csv):
        from app.importers.citi import parse_citi_csv
        txns = parse_citi_csv(str(citi_csv))
        by_desc = {t["merchant_raw"]: t for t in txns}
        assert by_desc["STARBUCKS SEATTLE WA"]["card"] == "Card-9642"
        assert by_desc["AMAZON.COM"]["card"] == "Card-0375"
        assert by_desc["STARBUCKS SEATTLE WA"]["citi_category"] == "Restaurants"


# ─── Import ──────────────────────────────────────────────────────────────


class TestImport:
    def test_import_inserts(self, citi_csv, db):
        from app.importers.citi import import_citi_csv
        result = import_citi_csv(db, str(citi_csv))
        assert result["imported"] == 5
        assert result["errors"] == 0

        txns = db.execute("SELECT * FROM imported_transactions").fetchall()
        assert len(txns) == 5

    def test_import_idempotent(self, citi_csv, db):
        from app.importers.citi import import_citi_csv
        import_citi_csv(db, str(citi_csv))
        result = import_citi_csv(db, str(citi_csv))
        assert result["imported"] == 0  # all skipped
        assert result["skipped_duplicates"] == 5

    def test_dry_run(self, citi_csv, db):
        from app.importers.citi import import_citi_csv
        result = import_citi_csv(db, str(citi_csv), dry_run=True)
        assert result["imported"] == 5
        txns = db.execute("SELECT * FROM imported_transactions").fetchall()
        assert len(txns) == 0

    def test_preview(self, citi_csv):
        from app.importers.citi import preview_citi_csv
        preview = preview_citi_csv(str(citi_csv))
        assert preview["total"] == 5
        assert len(preview["cards"]) == 2
        assert "Card-9642" in preview["cards"]
        assert "Card-0375" in preview["cards"]


class TestAPI:
    @pytest.fixture
    def api_client(self, isolated_environment):
        from app.api import app as api_app
        from fastapi.testclient import TestClient
        import os
        os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
        client = TestClient(api_app)
        yield client
        os.environ.pop("SOLOLEDGER_OPEN_MODE", None)

    def test_preview_endpoint(self, citi_csv, api_client):
        with open(str(citi_csv), "rb") as f:
            resp = api_client.post(
                "/api/v1/import/citi/preview",
                files={"file": ("citi.csv", f, "text/csv")},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
        assert data["data"]["total"] == 5

    def test_import_endpoint(self, citi_csv, api_client):
        with open(str(citi_csv), "rb") as f:
            resp = api_client.post(
                "/api/v1/import/citi/import",
                files={"file": ("citi.csv", f, "text/csv")},
                data={"account": "citi", "dry_run": "false"},
            )
        assert resp.status_code == 200
        data = resp.json()
        assert data["success"] is True
