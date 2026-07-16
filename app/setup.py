"""SoloLedger setup wizard — `llc init` interactive configuration.

Guides new users through:
  - Business information (name, owner, EIN, address)
  - State selection (with tax implications shown)
  - Checking required env vars
  - Validating the ledger

Usage:
    llc init
"""

import json
import os
import shutil
import sys
from pathlib import Path
from typing import Optional

import click

from .config import Config
from .ledger import Ledger


def run_init():
    """Run the interactive setup wizard."""
    project_root = Path.cwd()
    config_path = project_root / "config.toml"

    click.echo()
    click.echo("═══ SoloLedger Setup ═══")
    click.echo()

    # ── 1. Business info ──────────────────────────────────────────
    click.echo("First, let's set up your business information.")
    click.echo()

    biz_name = _prompt("Business name", default="Your LLC")
    owner = _prompt("Your full name", default="Your Name")
    state = _prompt_state()
    ein = _prompt("EIN (or SSN if sole prop)", default="XX-XXXXXXX")
    address = _prompt("Business address", default="123 Main St, City, ST ZIP")
    phone = _prompt("Phone", default="+1 555-555-5555")
    email = _prompt("Email", default="you@yourllc.com")

    click.echo()

    # ── 2. State tax info ─────────────────────────────────────────
    state_info = _get_state_info(state)
    if state_info:
        click.echo(f"  📋  {state_info}")
    click.echo()

    # ── 3. Verify env vars ────────────────────────────────────────
    click.echo("Checking environment variables...")
    env_checks = _check_env_vars()
    for label, found, hint in env_checks:
        icon = "✅" if found else "⚠️"
        click.echo(f"  {icon}  {label:<20s} {'Found' if found else hint}")
    click.echo()

    # ── 4. Write config ───────────────────────────────────────────
    if config_path.exists():
        click.echo(f"  ⚠️   {config_path.name} already exists.")
        if not click.confirm("  Overwrite with new configuration?", default=False):
            click.echo("  ✗  Config not written. No changes made.")
            click.echo()
            return

    _write_config(config_path, biz_name, owner, state, ein, address, phone, email)
    click.echo(f"  ✓  Wrote {config_path.name}")

    # ── 5. Verify ledger ──────────────────────────────────────────
    click.echo()
    click.echo("Checking ledger...")
    try:
        cfg = Config(str(config_path))
        ledger = Ledger(cfg)
        errors = ledger.check()
        if errors:
            click.echo(f"  ⚠️  Ledger has {len(errors)} issue(s)")
            for e in errors[:3]:
                click.echo(f"       {e}")
        else:
            click.echo("  ✓  Ledger is valid")
    except Exception as e:
        click.echo(f"  ⚠️  Ledger check failed: {e}")
        click.echo("     You can fix the ledger file manually: ledger/transactions.beancount")

    click.echo()
    click.echo("═══ Setup complete ═══")
    click.echo()
    click.echo("  Next steps:")
    click.echo("    llc status          → see your dashboard")
    click.echo("    llc doctor          → check all integrations")
    click.echo("    llc demo            → load sample data to try features")
    click.echo()
    click.echo("  Set these env vars for full functionality:")
    click.echo("    STRIPE_SECRET_KEY   → payment links on invoices")
    click.echo("    PLAID_*            → automated bank feeds")
    click.echo("    TOGGL_API_TOKEN     → time tracking")
    click.echo("    NOTIFY_SMTP_PASSWORD → email alerts")
    click.echo()


def _prompt(label: str, default: str = "", secret: bool = False) -> str:
    """Prompt for a value with optional default."""
    prompt_text = f"  {label}"
    if default:
        prompt_text += f" [{default}]"

    if secret:
        value = click.prompt(prompt_text, default=default, hide_input=True)
    else:
        value = click.prompt(prompt_text, default=default, show_default=False)

    return value.strip() or default


def _prompt_state() -> str:
    """Interactive state selection with tax info."""
    states = {
        "WY": "Wyoming — $0 income tax, $60/yr fee",
        "CA": "California — 1-13.3% income tax + $800 min franchise tax",
        "TX": "Texas — $0 income tax, margin tax only >$2.47M revenue",
        "NY": "New York — 4-10.9% income tax + NYC up to 3.9% local",
        "FL": "Florida — $0 income tax, $138.75/yr fee",
    }

    click.echo("  Select your state:")
    for code, desc in states.items():
        click.echo(f"    {code:<4s}  {desc}")

    while True:
        state = click.prompt("  State", default="WY").upper().strip()
        if state in states:
            return state
        click.echo(f"  Invalid. Choose from: {', '.join(states.keys())}")


def _get_state_info(state: str) -> Optional[str]:
    """Get a one-line summary of the state's tax situation."""
    try:
        from .taxes.state_calculator import StateTaxCalculator
        calc = StateTaxCalculator(state)
        data = calc.data
        parts = []
        if data.get("income_tax"):
            parts.append("Has income tax")
        if data.get("franchise_tax"):
            parts.append("Has franchise/gross receipts tax")
        fee = data.get("annual_llc_fee", 0)
        if fee:
            parts.append(f"${fee}/yr annual fee")
        notes = data.get("notes", "")
        summary = "; ".join(parts)
        if summary:
            return f"{data.get('name', state)} — {summary}"
        return None
    except Exception:
        return None


def _check_env_vars() -> list[tuple[str, bool, str]]:
    """Check which env vars are set and return status list."""
    checks = [
        ("Stripe", "STRIPE_SECRET_KEY", "Get at https://dashboard.stripe.com/apikeys"),
        ("Plaid ID", "PLAID_CLIENT_ID", "Get at https://dashboard.plaid.com"),
        ("Plaid Secret", "PLAID_SECRET", ""),
        ("Plaid Token", "PLAID_ACCESS_TOKEN", "Run Plaid Link flow"),
        ("Toggl Token", "TOGGL_API_TOKEN", "Get at https://track.toggl.com/profile"),
        ("Notify Email", "NOTIFY_SMTP_PASSWORD", "Gmail app password"),
    ]
    results = []
    for label, var, hint in checks:
        found = bool(os.environ.get(var))
        results.append((label, found, hint if not found else ""))
    return results


def _write_config(path: Path, biz_name: str, owner: str, state: str,
                  ein: str, address: str, phone: str, email: str):
    """Write a fresh config.toml with the user's settings."""
    content = f"""# =============================================================================
# SoloLedger — Business Configuration
# Generated by `llc init`
# =============================================================================

[business]
name = "{biz_name}"
owner = "{owner}"
state = "{state}"
ein = "{ein}"
address = "{address}"
phone = "{phone}"
email = "{email}"

[ledger]
path = "ledger/main.beancount"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

[time_tracking]
hourly_rate = 150.0
# source = "toggl"

[notifications]
desktop_enabled = true
email_enabled = false
remind_days_before = 7
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = ""
smtp_password = ""
alert_email = ""

[banking]
plaid_enabled = false

[[expense_rules]]
pattern = "GITHUB"
account = "Expenses:Software:SaaS"

[[expense_rules]]
pattern = "AWS"
account = "Expenses:Software:Hosting"

[[expense_rules]]
pattern = "STRIPE"
account = "Expenses:BankFees"

[[income_rules]]
pattern = "CLIENT"
account = "Income:Consulting"

[tax]
state = "{state}"
standard_deduction = 14600

[[tax.brackets]]
rate = 0.10
floor = 0
ceiling = 11925

[[tax.brackets]]
rate = 0.12
floor = 11926
ceiling = 48475

[[tax.brackets]]
rate = 0.22
floor = 48476
ceiling = 103350

[[tax.brackets]]
rate = 0.24
floor = 103351
ceiling = 197300

[[tax.brackets]]
rate = 0.32
floor = 197301
ceiling = 250525

[[tax.brackets]]
rate = 0.35
floor = 250526
ceiling = 626350

[[tax.brackets]]
rate = 0.37
floor = 626351
ceiling = 999999999

[tax.self_employment]
rate_social_security = 0.124
rate_medicare = 0.029
ss_wage_base = 184800
deduction_ratio = 0.9235

safe_harbor_percent = 1.00
safe_harbor_percent_high_income = 1.10
safe_harbor_threshold = 150000

[tax.quarter_dates]
q1 = [4, 15]
q2 = [6, 15]
q3 = [9, 15]
q4 = [1, 15]
"""
    path.write_text(content)
