"""Regression tests for audit fixes (security + data-integrity).

These lock in the behavior changes made during the v0.4 audit remediation:

Security:
  - auth fails closed (open mode is opt-in)
  - expired/invalid tokens rejected
  - TOML config injection blocked at signup
  - upload size cap enforced (413)
  - statement filing path traversal sanitized
  - beancount newline injection escaped

Data integrity:
  - reconciliation writes a balance directive, not a transaction
  - mark_paid matches the invoice by number (not the whole AR balance)
  - CSV re-import does not double-post
  - auth endpoints are rate limited
"""
import datetime
import os
import re
from decimal import Decimal
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.api import app as api_app
from app.api import deps


@pytest.fixture
def closed_client(isolated_environment):
    """TestClient with auth FAIL-CLOSED (no open mode, no API keys)."""
    for var in ("SOLOLEDGER_OPEN_MODE", "API_KEYS", "GOOGLE_CLIENT_ID"):
        os.environ.pop(var, None)
    return TestClient(api_app)


@pytest.fixture
def open_client(isolated_environment):
    """TestClient in explicit open (demo) mode."""
    os.environ["SOLOLEDGER_OPEN_MODE"] = "true"
    yield TestClient(api_app)
    os.environ.pop("SOLOLEDGER_OPEN_MODE", None)


# ── Auth posture ──────────────────────────────────────────────────────────


class TestFailClosedAuth:
    """Auth must reject unauthenticated requests unless open mode is on."""

    def test_protected_endpoint_rejects_no_token(self, closed_client):
        """No auth config, no open mode → 401 (was: open to the internet)."""
        resp = closed_client.get("/api/v1/accounts")
        assert resp.status_code == 401, resp.text

    def test_invalid_token_rejected(self, closed_client):
        resp = closed_client.get(
            "/api/v1/accounts", headers={"Authorization": "Bearer not-a-real-token"}
        )
        assert resp.status_code == 403, resp.text

    def test_expired_session_rejected(self, closed_client, monkeypatch):
        """A session older than 30 days must not authenticate."""
        stale = {
            "stale-token": {
                "email": "old@example.com",
                "created": "2020-01-01T00:00:00+00:00",
            }
        }
        monkeypatch.setattr(deps, "_sessions", stale)
        resp = closed_client.get(
            "/api/v1/accounts", headers={"Authorization": "Bearer stale-token"}
        )
        assert resp.status_code == 403, resp.text

    def test_fresh_session_authenticates(self, closed_client, monkeypatch):
        """A current session for the owner's email authenticates."""
        fresh = {
            "fresh-token": {
                "email": "test@testllc.com",  # isolated config's business email
                "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            }
        }
        monkeypatch.setattr(deps, "_sessions", fresh)
        resp = closed_client.get(
            "/api/v1/accounts", headers={"Authorization": "Bearer fresh-token"}
        )
        assert resp.status_code == 200, resp.text

    def test_api_key_authenticates(self, closed_client, monkeypatch):
        monkeypatch.setattr(deps, "_valid_api_keys", ["test-key-123"])
        monkeypatch.setattr(deps, "_api_keys_env", "test-key-123")
        resp = closed_client.get(
            "/api/v1/accounts", headers={"Authorization": "Bearer test-key-123"}
        )
        assert resp.status_code == 200, resp.text

    def test_open_mode_allows_anonymous(self, open_client):
        resp = open_client.get("/api/v1/accounts")
        assert resp.status_code == 200, resp.text

    def test_health_is_public(self, closed_client):
        """Uptime/load-balancer checks must work without auth."""
        resp = closed_client.get("/api/v1/health")
        assert resp.status_code == 200, resp.text


class TestAuthRateLimiting:
    """Signin/signup are rate limited (20 attempts / 15 min / client)."""

    def test_signin_rate_limited(self, closed_client, monkeypatch):
        monkeypatch.setattr(deps, "_rate_attempts", {})  # fresh window
        got_429 = False
        for i in range(25):
            resp = closed_client.post(
                "/api/v1/auth/signin",
                json={"email": f"user{i}@x.com", "password": "wrongpass"},
            )
            if resp.status_code == 429:
                got_429 = True
                break
        assert got_429, "rate limiter never triggered after 25 attempts"

    def test_toml_injection_rejected_at_signup(self, open_client):
        """A name/email containing quotes or newlines must be rejected."""
        resp = open_client.post(
            "/api/v1/auth/signup",
            json={
                "email": "evil@example.com",
                "password": "password123",
                "name": 'x"\n[payments]\nstripe_enabled = true\n#',
            },
        )
        assert resp.status_code == 400, resp.text


class TestUploadCap:
    """Uploads over the size limit are rejected."""

    def test_read_upload_enforces_cap(self):
        """_read_upload must raise UploadTooLarge past max_bytes."""
        from app.api.deps import _read_upload, UploadTooLarge

        class FakeFile:
            def __init__(self, data, chunk=1024):
                self.data = data
                self.chunk = chunk
                self.pos = 0

            async def read(self, n=-1):
                if self.pos >= len(self.data):
                    return b""
                end = self.pos + (self.chunk if n <= 0 else n)
                chunk = self.data[self.pos:end]
                self.pos = end
                return chunk

        import pytest as _pt
        with _pt.raises(UploadTooLarge):
            import asyncio
            asyncio.run(_read_upload(FakeFile(b"x" * 2048), max_bytes=1024))


class TestStatementPathTraversal:
    """Statement filing must not escape documents/statements/."""

    @staticmethod
    def _fake_pdf(monkeypatch):
        """Patch pdfplumber so file_statement can classify without a real PDF."""
        class FakePage:
            def extract_text(self):
                return "WELLS FARGO BANK STATEMENT"

        class FakePDF:
            pages = [FakePage()]

            def __enter__(self):
                return self

            def __exit__(self, *a):
                return False

        class FakePlumber:
            @staticmethod
            def open(path):
                return FakePDF()

        # file_statement does `import pdfplumber` internally, so patch the
        # module in sys.modules (not just the attribute on app.statements).
        import sys
        monkeypatch.setitem(sys.modules, "pdfplumber", FakePlumber)

    def test_malicious_institution_is_sanitized(self, tmp_path, monkeypatch):
        from app.db import TenantDB
        from app.statements import file_statement

        monkeypatch.chdir(tmp_path)  # keep documents/ out of the repo
        self._fake_pdf(monkeypatch)
        db = TenantDB(tmp_path / "ledger")
        pdf = tmp_path / "stmt.pdf"
        pdf.write_text("%PDF-1.4 fake")

        # institution/account_mask/period with traversal components
        result = file_statement(
            db, pdf,
            institution="../../etc",
            account_mask="../..",
            period="../../tmp/evil",
        )
        assert result["success"] is True, result
        filed = Path(result["filed_path"]).resolve()
        # Must stay under <cwd>/documents/statements/
        assert filed.is_relative_to((Path.cwd() / "documents" / "statements").resolve())
        assert not filed.is_relative_to(Path("/etc"))

    def test_flat_period_sanitized(self, tmp_path, monkeypatch):
        from app.db import TenantDB
        from app.statements import file_statement
        monkeypatch.chdir(tmp_path)
        self._fake_pdf(monkeypatch)
        db = TenantDB(tmp_path / "ledger")
        pdf = tmp_path / "stmt.pdf"
        pdf.write_text("%PDF-1.4 fake")
        result = file_statement(db, pdf, institution="chase", period="2026-01/../../x")
        assert result["success"] is True, result
        filed = Path(result["filed_path"]).resolve()
        # Must stay under documents/statements/ with no traversal components
        assert filed.is_relative_to((Path.cwd() / "documents" / "statements").resolve())
        assert ".." not in str(filed.relative_to(Path.cwd()))


class TestBeancountEscaping:
    """Payee/narration newlines must not break out of the directive."""

    def test_newline_in_payee_escaped(self, sample_config):
        from app.ledger import Ledger
        ledger = Ledger(sample_config)
        entry = ledger.append(
            date=datetime.date(2026, 1, 15),
            payee='Evil Payee"\n2026-01-15 * "Injected"',
            narration="normal",
            postings=[("Expenses:Miscellaneous", "10.00 USD"), (sample_config.checking_account, "-10.00 USD")],
        )
        # The directive must be a single line — no injected directives
        lines = [l for l in entry.splitlines() if l.strip()]
        assert len(lines) == 3, entry  # header + 2 postings
        assert '2026-01-15 * "Evil Payee\\"' in lines[0]
        assert "Injected" not in lines[1:]  # no second directive line


# ── Data integrity ────────────────────────────────────────────────────────


class TestReconciliationBalanceDirective:
    """start() must assert a balance, not post a transaction."""

    def test_start_writes_balance_directive(self, sample_config):
        from app.ledger import Ledger
        from app.reconciliation import Reconciliation

        ledger = Ledger(sample_config)
        before = ledger.account_balance(sample_config.checking_account)
        rec = Reconciliation(sample_config, ledger)
        rec.start(date="2026-07-31", balance=Decimal("15000.00"))

        tx_path = sample_config.ledger_dir / "transactions.beancount"
        content = tx_path.read_text()
        assert re.search(r"2026-07-31 balance Assets:Bank:BusinessChecking", content), content

        # Balance must NOT have been doubled by a posting
        after = ledger.account_balance(sample_config.checking_account)
        assert before == after, f"balance changed {before} -> {after}"


class TestMarkPaidByNumber:
    """mark_paid must pay the matched invoice's amount, not the whole AR."""

    def test_mark_paid_amounts_match_invoice(self, sample_config):
        from app.invoice import Invoicer
        from app.ledger import Ledger

        ledger = Ledger(sample_config)

        # Two invoices appended to the main ledger file (the fixture's
        # main.beancount does not include transactions.beancount, so
        # ledger.append alone wouldn't be visible to the loader).
        main = sample_config.ledger_dir / "main.beancount"
        with open(main, "a") as f:
            f.write(
                '2026-01-15 * "Alpha Client" "Invoice one"\n'
                f'  {sample_config.ar_account:45s}  1000.00 USD\n'
                f'  {sample_config.income_account:45s}  -1000.00 USD\n\n'
                '2026-01-20 * "Beta Client" "Invoice two"\n'
                f'  {sample_config.ar_account:45s}  2000.00 USD\n'
                f'  {sample_config.income_account:45s}  -2000.00 USD\n\n'
            )
        ledger.reload(force=True)

        inv = Invoicer(sample_config, ledger)
        invoices = inv.list_invoices()
        assert len(invoices) == 3, invoices  # Client A + Alpha + Beta

        # Find the Beta invoice by number
        beta = next(i for i in invoices if i["client"] == "Beta Client")
        result = inv.mark_paid(beta["number"])
        assert result["paid"] is True
        amt = float(result["amount"])
        # Pays the specific invoice's amount (2000), NOT the whole AR (8000)
        assert amt == pytest.approx(2000.00), f"paid {amt}, expected 2000.00"


class TestCsvDedup:
    """Re-importing the same CSV must not double-post."""

    def test_second_import_skips(self, sample_config, tmp_path):
        from app.db import TenantDB
        from app.expenses import ExpenseImporter
        from app.ledger import Ledger

        ledger = Ledger(sample_config)
        db = TenantDB(tmp_path)
        importer = ExpenseImporter(sample_config, ledger)

        csv_path = tmp_path / "bank.csv"
        csv_path.write_text(
            "Date,Description,Amount\n"
            "2026-01-05,Coffee Shop,-4.50\n"
            "2026-01-06,Client Payment,500.00\n"
        )

        first = importer.import_csv(csv_path, db=db, source="csv")
        assert len(first) == 2

        second = importer.import_csv(csv_path, db=db, source="csv")
        assert len(second) == 0, f"re-import double-posted: {len(second)}"

        # Cross-source: same transaction via a different source label also blocked
        third = importer.import_csv(csv_path, db=db, source="plaid")
        assert len(third) == 0, "cross-source duplicate not detected"
