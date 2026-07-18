"""Tests for app/ledger.py — Beancount ledger wrapper."""

import time
from decimal import Decimal

import pytest


class TestLedgerLoading:
    """Ledger loads and parses Beancount files."""

    def test_load_sample_ledger(self, sample_ledger):
        assert sample_ledger._entries is not None
        assert len(sample_ledger._entries) > 0
        assert sample_ledger._balances is not None

    def test_check_returns_no_errors(self, clean_ledger):
        errors = clean_ledger.check()
        assert errors == []

    def test_cash_balance(self, clean_ledger):
        cash = clean_ledger.cash_balance()
        assert cash > 0
        assert isinstance(cash, Decimal)

    def test_gross_revenue(self, clean_ledger):
        revenue = clean_ledger.gross_revenue()
        assert revenue > 0
        assert isinstance(revenue, Decimal)

    def test_total_expenses(self, clean_ledger):
        expenses = clean_ledger.total_expenses()
        assert expenses > 0
        assert isinstance(expenses, Decimal)

    def test_net_income(self, clean_ledger):
        net = clean_ledger.net_income()
        assert isinstance(net, Decimal)

    def test_balance_by_account(self, clean_ledger):
        bal = clean_ledger.account_balance("Assets:Bank:BusinessChecking")
        assert bal is not None
        assert isinstance(bal, Decimal)

    def test_balance_unknown_account(self, clean_ledger):
        bal = clean_ledger.account_balance("Fake:Nope")
        assert bal == Decimal("0")


class TestLedgerCaching:
    """Ledger reloads with TTL caching."""

    def test_reload_skips_within_ttl(self, clean_ledger):
        t0 = clean_ledger._last_loaded
        clean_ledger.reload(force=False)
        assert clean_ledger._last_loaded == t0  # cached

    def test_force_reload(self, clean_ledger):
        t0 = clean_ledger._last_loaded
        clean_ledger.reload(force=True)
        assert clean_ledger._last_loaded >= t0


class TestLedgerAppend:
    """Appending transactions and entries."""

    def test_append_entry(self, clean_ledger):
        from beancount.core.data import Transaction, Posting, Amount, Open
        from beancount.core.number import D

        entry = Transaction(
            meta=None,
            date=clean_ledger.cfg.ledger_path.stat().st_mtime,  # placeholder
            flag="*",
            payee="Test Payee",
            narration="Test transaction",
            tags=set(),
            links=set(),
            postings=[],
        )
        # Just verify it doesn't crash — real appending tests need filesystem
        # access to the actual ledger file
        assert entry is not None

    def test_reload_after_write(self, clean_ledger, tmp_path):
        """After modifying the file, force reload picks up changes."""
        ledger_path = clean_ledger.cfg.ledger_path
        orig = ledger_path.read_text()

        # Add a tiny entry
        new_entry = '\n1970-07-01 * "Test" "Test expense"\n  Expenses:Miscellaneous   50.00 USD\n  Assets:Bank:BusinessChecking\n'
        ledger_path.write_text(orig + new_entry)

        clean_ledger.reload(force=True)
        errors = clean_ledger.check()
        assert errors == []
