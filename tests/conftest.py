"""Shared test fixtures for SoloLedger tests."""

import os
import shutil
import tempfile
from pathlib import Path
from decimal import Decimal

import pytest


@pytest.fixture(scope="session")
def isolated_environment(tmp_path_factory):
    """Redirect app state (sessions/users/tenants/ledgers) and config to tmp.

    Session-scoped so the app.api module (which reads SOLOLEDGER_DATA_DIR
    once at import) is never pointed at the repo root. Sets up:
      - a tmp data dir for sessions.json/users.json/tenants.json/ledgers/
      - a tmp config dir with a config.toml (from generate_config_toml,
        so the [tax] section is valid) and a minimal beancount ledger at
        the config dir root (path = "main.beancount")
      - a copy of the repo templates/ dir (for tax/voucher rendering)

    Restores both env vars after the session.
    """
    data_dir = tmp_path_factory.mktemp("sololedger_data")
    config_dir = tmp_path_factory.mktemp("sololedger_config")

    from app.config import generate_config_toml

    ledger_file = config_dir / "main.beancount"
    ledger_file.write_text("""\
option "title" "Test Ledger"

1970-01-01 open Assets:Bank:BusinessChecking
1970-01-01 open Assets:AccountsReceivable
1970-01-01 open Income:Consulting
1970-01-01 open Expenses:Miscellaneous
1970-01-01 open Expenses:Software:SaaS
1970-01-01 open Expenses:Software:Hosting
1970-01-01 open Expenses:Supplies
1970-01-01 open Equity:OwnerDraws
1970-01-01 open Equity:OpeningBalance

1970-01-02 * "Contribution" "Initial funding"
  Assets:Bank:BusinessChecking      10000.00 USD
  Equity:OpeningBalance

1970-06-15 * "Client A" "Q2 Consulting"
  Income:Consulting                -5000.00 USD
  Assets:AccountsReceivable         5000.00 USD

1970-06-20 * "GitHub" "GitHub Enterprise"
  Expenses:Software:SaaS             200.00 USD
  Assets:Bank:BusinessChecking
""")

    config_path = config_dir / "config.toml"
    config_path.write_text(generate_config_toml(
        name="Test LLC",
        owner="Test Owner",
        email="test@testllc.com",
        state="WY",
        ledger_path="main.beancount",
    ))

    # Tax/voucher renders from <config dir>/templates — mirror the repo's.
    repo_templates = Path(__file__).resolve().parent.parent / "templates"
    if repo_templates.exists():
        shutil.copytree(repo_templates, config_dir / "templates")

    old_data_dir = os.environ.get("SOLOLEDGER_DATA_DIR")
    old_api_config = os.environ.get("API_CONFIG")
    os.environ["SOLOLEDGER_DATA_DIR"] = str(data_dir)
    os.environ["API_CONFIG"] = str(config_path)
    try:
        yield {
            "data_dir": str(data_dir),
            "config_dir": str(config_dir),
            "config_path": str(config_path),
            "ledger_path": str(ledger_file),
        }
    finally:
        if old_data_dir is None:
            os.environ.pop("SOLOLEDGER_DATA_DIR", None)
        else:
            os.environ["SOLOLEDGER_DATA_DIR"] = old_data_dir
        if old_api_config is None:
            os.environ.pop("API_CONFIG", None)
        else:
            os.environ["API_CONFIG"] = old_api_config


@pytest.fixture
def tmp_home(tmp_path):
    """Create a temporary home directory for test isolation."""
    old_home = os.environ.get("HOME")
    os.environ["HOME"] = str(tmp_path)
    yield tmp_path
    if old_home:
        os.environ["HOME"] = old_home


@pytest.fixture
def test_dir():
    """Path to the tests directory (for fixture files)."""
    return Path(__file__).parent


@pytest.fixture
def sample_beancount(tmp_path):
    """Create a minimal valid Beancount ledger for testing."""
    ledger_dir = tmp_path / "ledger"
    ledger_dir.mkdir()
    ledger_file = ledger_dir / "main.beancount"
    ledger_file.write_text("""\
option "title" "Test Ledger"

;; Accounts
1970-01-01 open Assets:Bank:BusinessChecking
1970-01-01 open Assets:AccountsReceivable
1970-01-01 open Income:Consulting
1970-01-01 open Expenses:Miscellaneous
1970-01-01 open Expenses:Software:SaaS
1970-01-01 open Expenses:Software:Hosting
1970-01-01 open Equity:OpeningBalance

;; Opening balance
1970-01-02 * "Contribution" "Initial funding"
  Assets:Bank:BusinessChecking      10000.00 USD
  Equity:OpeningBalance

;; A sample income
1970-06-15 * "Client A" "Q2 Consulting"
  Income:Consulting                -5000.00 USD
  Assets:AccountsReceivable         5000.00 USD

;; A sample expense
1970-06-20 * "GitHub" "GitHub Enterprise"
  Expenses:Software:SaaS             200.00 USD
  Assets:Bank:BusinessChecking
""")
    return ledger_dir


@pytest.fixture
def sample_config(sample_beancount, tmp_path):
    """Create a Config instance pointing at the sample ledger."""
    from app.config import Config

    config_path = tmp_path / "config.toml"
    config_path.write_text(f"""\
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
    return Config(str(config_path))


@pytest.fixture
def sample_ledger(sample_config):
    """Create a Ledger instance from the sample config and load it."""
    from app.ledger import Ledger
    ledger = Ledger(sample_config)
    ledger.reload(force=True)
    return ledger


@pytest.fixture
def clean_ledger(sample_ledger):
    """A ledger guaranteed fresh (reload forces re-parse)."""
    sample_ledger.reload(force=True)
    return sample_ledger


@pytest.fixture
def scorp_config(sample_beancount, tmp_path):
    """Create a Config with entity_type='scorp' for S-Corp tests."""
    from app.config import Config

    config_path = tmp_path / "config_scorp.toml"
    config_path.write_text(f"""\
[business]
name = "S Corp LLC"
owner = "Owner"
state = "WY"
ein = "XX-XXXXXXX"
address = "123 Test St"
phone = "+1 555-555-5555"
email = "test@scorpllc.com"

[entity]
entity_type = "scorp"
reasonable_salary = 50000
payroll_frequency = "monthly"

[ledger]
path = "{sample_beancount / 'main.beancount'}"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

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
    return Config(str(config_path))
