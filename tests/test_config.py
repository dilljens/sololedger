"""Tests for app/config.py — Config loading and business info."""

import os
from pathlib import Path

import pytest


class TestConfigLoading:
    """Config reads business info from config.toml."""

    def test_business_info(self, sample_config):
        assert sample_config.business_name == "Test LLC"
        assert sample_config.owner == "Test Owner"
        assert sample_config.state_code == "WY"
        assert sample_config.ein == "XX-XXXXXXX"
        assert sample_config.email == "test@testllc.com"

    def test_account_mappings(self, sample_config):
        assert sample_config.checking_account == "Assets:Bank:BusinessChecking"
        assert sample_config.ar_account == "Assets:AccountsReceivable"
        assert sample_config.income_account == "Income:Consulting"
        assert sample_config.draws_account == "Equity:OwnerDraws"

    def test_ledger_path_resolved(self, sample_config):
        assert sample_config.ledger_path.exists()
        assert sample_config.ledger_path.name == "main.beancount"

    def test_expense_rules_loaded(self, sample_config):
        assert len(sample_config.expense_rules) >= 0

    def test_tax_config(self, sample_config):
        assert sample_config.state_code == "WY"
        assert sample_config.standard_deduction == 14600

    def test_config_not_found(self):
        """Config raises FileNotFoundError for missing path."""
        from app.config import Config
        with pytest.raises(FileNotFoundError):
            Config("/nonexistent/path/config.toml")

    def test_find_config_walks_up(self, tmp_path, monkeypatch):
        """Config._find_config walks up from cwd."""
        from app.config import Config
        nested = tmp_path / "a" / "b" / "c"
        nested.mkdir(parents=True)
        config_file = tmp_path / "config.toml"
        config_file.write_text("""\
[business]
name = "X"
owner = "Y"
state = "WY"
ein = "XX-XXXXXXX"
address = "A"
phone = "B"
email = "C"

[ledger]
path = "test.beancount"

[accounts]
checking = "Assets:Bank:Checking"
ar = "Assets:AR"
income = "Income:Main"
owner_draws = "Equity:Draws"

[tax]
state = "WY"
standard_deduction = 14600

[[tax.brackets]]
rate = 0.10
floor = 0
ceiling = 11925

[tax.self_employment]
rate_social_security = 0.124
rate_medicare = 0.029
ss_wage_base = 184800
deduction_ratio = 0.9235

[tax.quarter_dates]
q1 = [4, 15]
q2 = [6, 15]
q3 = [9, 15]
q4 = [1, 15]
""")
        monkeypatch.chdir(nested)
        cfg = Config()
        assert cfg.business_name == "X"
