"""Tests for Wave CSV importer."""
import pytest
from app.db import TenantDB

WAVE_CSV = """Date,Description,Amount,Account Type,Account Name
2026-01-15,Client Payment,5000.00,Income,Consulting
2026-01-20,Office Supplies,-150.00,Expense,Office
2026-02-01,Hosting,-29.99,Expense,Software
2026-02-15,Client Payment,7500.00,Income,Consulting
"""


@pytest.fixture
def db(tmp_path):
    _db = TenantDB(tmp_path)
    yield _db
    _db.close()


@pytest.fixture
def wave_csv(tmp_path):
    p = tmp_path / "wave.csv"
    p.write_text(WAVE_CSV)
    return p


class TestWaveImport:
    def test_parse_csv(self, wave_csv):
        from app.importers.wave import parse_wave_csv
        txns = parse_wave_csv(str(wave_csv))
        assert len(txns) == 4
        assert txns[0]["description"] == "Client Payment"
        assert txns[0]["amount_cents"] == 500000
        assert txns[1]["amount_cents"] == -15000

    def test_import(self, wave_csv, db):
        from app.importers.wave import import_wave_csv
        result = import_wave_csv(db, str(wave_csv))
        assert result["imported"] == 4
        txns = db.execute("SELECT * FROM imported_transactions").fetchall()
        assert len(txns) == 4

    def test_dry_run(self, wave_csv, db):
        from app.importers.wave import import_wave_csv
        result = import_wave_csv(db, str(wave_csv), dry_run=True)
        assert result["imported"] == 4
        txns = db.execute("SELECT * FROM imported_transactions").fetchall()
        assert len(txns) == 0

    def test_idempotent(self, wave_csv, db):
        from app.importers.wave import import_wave_csv
        import_wave_csv(db, str(wave_csv))
        result = import_wave_csv(db, str(wave_csv))
        assert result["imported"] == 0
        assert result["skipped"] == 4
