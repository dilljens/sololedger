"""Tests for import history and cross-source duplicate flagging."""
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


def _seed_trail(db, fp, source, account="Assets:Bank:BusinessChecking",
                date="2026-01-15", amount_cents=12345, description="ACME STORE"):
    db.execute(
        "INSERT OR IGNORE INTO imported_transactions"
        " (source, account, date, amount_cents, description, fingerprint)"
        " VALUES (?, ?, ?, ?, ?, ?)",
        (source, account, date, amount_cents, description[:200], fp),
    )
    db.commit()


class TestImportHistory:
    def test_history_returns_batches(self, client):
        db = _db()
        db.execute(
            "INSERT INTO import_batches (source, account, filename, status)"
            " VALUES (?, ?, ?, ?)",
            ("ofx", "Assets:Bank:BusinessChecking", "stmt.ofx", "committed"),
        )
        db.commit()

        r = client.get("/api/v1/import/history")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] >= 1
        sources = {b["source"] for b in data["batches"]}
        assert "ofx" in sources

    def test_history_limit(self, client):
        r = client.get("/api/v1/import/history?limit=1")
        assert r.status_code == 200
        assert len(r.json()["data"]["batches"]) <= 1


class TestImportDuplicates:
    def test_no_duplicates_by_default(self, client):
        fp = f"fp-unique-{uuid.uuid4().hex}"
        _seed_trail(_db(), fp, "ofx")
        r = client.get("/api/v1/import/duplicates")
        assert r.status_code == 200
        data = r.json()["data"]
        assert data["count"] == 0
        assert all(d["fingerprint"] != fp for d in data["duplicates"])

    def test_cross_source_flagging(self, client):
        db = _db()
        fp = f"fp-x-{uuid.uuid4().hex}"
        _seed_trail(db, fp, "ofx")

        # Same transaction attempted from a different source → flagged
        status = db.classify_fingerprint(fp, "citi_csv", "Assets:Bank:BusinessChecking",
                                         "2026-01-15", 12345, "ACME STORE")
        assert status == "cross_source"

        r = client.get("/api/v1/import/duplicates")
        data = r.json()["data"]
        assert data["count"] == 1
        dup = data["duplicates"][0]
        assert dup["fingerprint"] == fp
        assert dup["existing_source"] == "ofx"
        assert "citi_csv" in dup["attempted_sources"]

        # Same source re-attempt → still classified cross_source (it IS a
        # duplicate), but no NEW warning row (UNIQUE keeps the log bounded)
        assert db.classify_fingerprint(fp, "citi_csv", "Assets:Bank:BusinessChecking",
                                       "2026-01-15", 12345, "ACME STORE") == "cross_source"
        r = client.get("/api/v1/import/duplicates")
        assert r.json()["data"]["count"] == 1

    def test_same_source_not_flagged(self, client):
        db = _db()
        fp = f"fp-s-{uuid.uuid4().hex}"
        _seed_trail(db, fp, "wave")
        assert db.classify_fingerprint(fp, "wave", "wave",
                                       "2026-02-01", 500, "DUES") == "same_source"
        r = client.get("/api/v1/import/duplicates")
        assert all(d["fingerprint"] != fp for d in r.json()["data"]["duplicates"])

    def test_wave_import_dedups_against_ofx_fingerprint(self, client):
        """End-to-end: a txn already imported from OFX is skipped by Wave.

        The fingerprint account must be the canonical beancount account in
        BOTH importers, or the same transaction imported from two sources
        would get two different fingerprints and be posted twice.
        """
        from app.config import Config
        from app.db import make_fingerprint
        from app.importers.wave import import_wave_csv

        cfg = Config(os.environ["API_CONFIG"])
        db = _db()
        fp = make_fingerprint("ofx", cfg.checking_account, "2026-03-10", 12345, "ACME CO")
        _seed_trail(db, fp, "ofx", account=cfg.checking_account,
                    date="2026-03-10", amount_cents=12345, description="ACME CO")

        import tempfile
        csv_path = tempfile.mktemp(suffix=".csv")
        with open(csv_path, "w") as f:
            f.write("Date,Description,Amount,Account Type,Account Name\n"
                    "2026-03-10,ACME CO,-123.45,Checking,Business Checking\n")

        try:
            result = import_wave_csv(db, csv_path, dry_run=False, ledger=None, cfg=cfg)
        finally:
            os.unlink(csv_path)

        assert result["skipped"] == 1, result
        assert result["imported"] == 0
        # and the collision was flagged as a cross-source duplicate
        r = client.get("/api/v1/import/duplicates")
        assert any(d["fingerprint"] == fp for d in r.json()["data"]["duplicates"])
