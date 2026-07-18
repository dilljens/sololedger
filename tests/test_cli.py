"""Smoke tests for CLI commands in app/main.py.

Each test runs a Click command via CliRunner and checks exit code.
These are smoke tests — they verify commands don't crash on basic invocation.
"""

import pytest
from click.testing import CliRunner


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture
def cli():
    from app.main import cli
    return cli


class TestBasicCommands:
    """Core commands that don't require external services."""

    def test_help(self, runner, cli):
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "SoloLedger" in result.output

    def test_version(self, runner, cli):
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0

    def test_check_auto_discover(self, runner, cli):
        """check auto-discovers config from CWD — should succeed."""
        result = runner.invoke(cli, ["check"])
        # config.toml is auto-discovered from project root
        assert result.exit_code == 0

    def test_doctor_auto_discover(self, runner, cli):
        result = runner.invoke(cli, ["doctor"])
        assert result.exit_code == 0

    def test_tax_state_list(self, runner, cli):
        result = runner.invoke(cli, ["tax", "state-list"])
        assert result.exit_code == 0
        assert "WY" in result.output

    def test_invoice_help(self, runner, cli):
        result = runner.invoke(cli, ["invoice", "--help"])
        assert result.exit_code == 0

    def test_tax_help(self, runner, cli):
        result = runner.invoke(cli, ["tax", "--help"])
        assert result.exit_code == 0


@pytest.fixture
def config_path(sample_beancount, tmp_path):
    """Write a proper config.toml for CLI tests and return its path."""
    cfg_path = tmp_path / "config.toml"
    cfg_path.write_text(f"""\
[business]
name = "Test LLC"
owner = "Test Owner"
state = "WY"
ein = "XX-XXXXXXX"
address = "123 Test St"
phone = "+1 555-555-5555"
email = "test@testllc.com"

[ledger]
path = "{sample_beancount / 'main.beancount'}"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

[payments]
stripe_enabled = false

[notifications]
desktop_enabled = false
email_enabled = false

[tax]
state = "WY"
standard_deduction = 14600

[[tax.brackets]]
rate = 0.10
floor = 0
ceiling = 11925

[[tax.brackets]]
rate = 0.12
floor = 11926
ceiling = 48475

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
    return str(cfg_path)


class TestCommandsWithConfig:
    """Commands that need a config file.

    NOTE: -c/--config must come BEFORE the subcommand (it's a CLI group option).
    """

    def test_check_with_config(self, runner, cli, config_path):
        result = runner.invoke(cli, ["-c", config_path, "check"])
        assert result.exit_code == 0
        assert "valid" in result.output.lower() or "error" in result.output.lower()

    def test_status_with_config(self, runner, cli, config_path):
        result = runner.invoke(cli, ["-c", config_path, "status"])
        assert result.exit_code == 0
        assert "Dashboard" in result.output

    def test_invoice_list_with_config(self, runner, cli, config_path):
        result = runner.invoke(cli, ["-c", config_path, "invoice", "list"])
        assert result.exit_code == 0

    def test_invoice_ar_with_config(self, runner, cli, config_path):
        result = runner.invoke(cli, ["-c", config_path, "invoice", "ar"])
        assert result.exit_code == 0

    def test_tax_estimate_with_config(self, runner, cli, config_path):
        result = runner.invoke(cli, ["-c", config_path, "tax", "estimate"])
        assert result.exit_code == 0
