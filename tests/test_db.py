"""Tests for SQLite metadata layer — migrations, queries, helpers."""
import os
import tempfile
from pathlib import Path

import pytest

from app.db import TenantDB, get_db, make_fingerprint


class TestTenantDB:
    """Test TenantDB lifecycle, migrations, and query interface."""

    @pytest.fixture
    def db(self, tmp_path):
        """Create a fresh TenantDB in a temp directory."""
        _db = TenantDB(tmp_path)
        yield _db
        _db.close()

    def test_init_creates_db_file(self, db):
        """After migration, the feature.db file should exist."""
        db.migrate()  # ensure migration runs
        assert db.db_path.exists(), "DB file not created after migration"
        assert db.db_path.name == "feature.db"

    def test_migration_runs_tables_exist(self, db):
        """After migration, all core tables should exist."""
        tables = {
            r["name"]
            for r in db.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }
        expected = {
            "schema_migrations", "import_batches", "imported_transactions",
            "vendor_receipts", "vendor_receipt_items", "transaction_receipt_links",
            "categorization_rules", "reconciliation_marks", "feature_flags",
        }
        missing = expected - tables
        assert not missing, f"Missing tables: {missing}"

    def test_migration_recorded(self, db):
        """Migration version should be recorded in schema_migrations."""
        rows = db.execute("SELECT version, name FROM schema_migrations").fetchall()
        assert len(rows) == 1
        assert rows[0]["version"] == 1
        assert "001" in rows[0]["name"]

    def test_migration_idempotent(self, db):
        """Running migrate() again should not fail."""
        db.migrate()  # second run
        rows = db.execute("SELECT count(*) as cnt FROM schema_migrations").fetchall()
        assert rows[0]["cnt"] == 1, "Migration recorded twice!"

    def test_reset_drops_and_remigrates(self, db):
        """reset() should drop all tables and re-apply migrations."""
        # Insert some data
        db.execute("INSERT INTO feature_flags (feature, enabled) VALUES (?, ?)", ("test", 1))
        db.commit()

        # Reset
        db.reset()

        # Data should be gone
        rows = db.execute("SELECT * FROM feature_flags").fetchall()
        assert len(rows) == 0

        # Migration should be re-recorded
        versions = db.execute("SELECT count(*) as cnt FROM schema_migrations").fetchall()
        assert versions[0]["cnt"] == 1

    def test_insert_and_query(self, db):
        """Basic CRUD operations work."""
        # Insert an import batch
        db.execute(
            "INSERT INTO import_batches (source, account, filename, status) VALUES (?, ?, ?, ?)",
            ("test", "Assets:Bank", "test.ofx", "committed"),
        )
        db.commit()

        rows = db.execute("SELECT * FROM import_batches").fetchall()
        assert len(rows) == 1
        assert rows[0]["source"] == "test"
        assert rows[0]["account"] == "Assets:Bank"
        assert rows[0]["status"] == "committed"
        assert rows[0]["id"] == 1

    def test_fingerprint_unique(self, db):
        """Fingerprint should be deterministic and cross-source identical."""
        fp1 = make_fingerprint("plaid", "Assets:Bank", "2026-01-15", 5000, "Coffee")
        fp2 = make_fingerprint("plaid", "Assets:Bank", "2026-01-15", 5000, "Coffee")
        fp3 = make_fingerprint("ofx", "Assets:Bank", "2026-01-15", 5000, "Coffee")

        assert fp1 == fp2, "Fingerprint not deterministic"
        # The same transaction from a different source must collide so
        # cross-source duplicates are detected (source is not part of the
        # identity fingerprint).
        assert fp1 == fp3, "Same transaction from different source should collide"

    def test_imported_transaction_dedup(self, db):
        """Inserting the same fingerprint twice should violate UNIQUE."""
        fp = make_fingerprint("test", "Assets:Bank", "2026-01-15", 1000, "Dupe test")
        db.execute(
            "INSERT INTO imported_transactions (source, account, date, amount_cents, description, fingerprint) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            ("test", "Assets:Bank", "2026-01-15", 1000, "Dupe test", fp),
        )
        db.commit()

        with pytest.raises(Exception):
            db.execute(
                "INSERT INTO imported_transactions (source, account, date, amount_cents, description, fingerprint) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("test", "Assets:Bank", "2026-01-15", 1000, "Dupe test", fp),
            )
            db.commit()

    def test_get_db_caching(self, tmp_path):
        """get_db should cache TenantDB instances by path."""
        db1 = get_db(str(tmp_path))
        db2 = get_db(str(tmp_path))
        assert db1 is db2, "get_db returned different instances for same path"
        db1.close()

    def test_get_db_default_path(self, tmp_path):
        """get_db() with a known path should create the db there."""
        db_path = tmp_path / "data"
        db_path.mkdir(parents=True, exist_ok=True)
        db = get_db(str(db_path))
        db.migrate()
        assert db.db_path.exists()
        db.close()

    def test_vendor_receipts_cascade(self, db):
        """Deleting a vendor receipt should cascade to its items."""
        db.execute(
            "INSERT INTO vendor_receipts (vendor, source_id, merchant, total_cents) VALUES (?, ?, ?, ?)",
            ("test_vendor", "ORD-001", "Test Store", 5000),
        )
        receipt_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

        db.execute(
            "INSERT INTO vendor_receipt_items (receipt_id, description, total_cents) VALUES (?, ?, ?)",
            (receipt_id, "Item 1", 2500),
        )
        db.execute(
            "INSERT INTO vendor_receipt_items (receipt_id, description, total_cents) VALUES (?, ?, ?)",
            (receipt_id, "Item 2", 2500),
        )
        db.commit()

        # Delete the receipt
        db.execute("DELETE FROM vendor_receipts WHERE id = ?", (receipt_id,))
        db.commit()

        # Items should be gone
        items = db.execute("SELECT * FROM vendor_receipt_items WHERE receipt_id = ?", (receipt_id,)).fetchall()
        assert len(items) == 0, "CASCADE delete didn't remove items"
