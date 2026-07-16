#!/usr/bin/env python3
"""llc — SoloLedger CLI: accounting for your consulting LLC.

Usage:
    llc status               → dashboard: cash, P&L, deadlines
    llc invoice create       → create a new invoice (+ PDF + Stripe payment link)
    llc invoice list         → list all invoices
    llc invoice ar           → check Accounts Receivable
    llc expense import FILE  → import a bank CSV
    llc receipt scan FILE    → scan a receipt (PDF/image) with OCR
    llc tax estimate         → estimated quarterly tax (federal + state)
    llc tax schedule-c       → Schedule C summary at year-end
    llc tax deadlines        → upcoming tax deadlines
    llc tax state-list       → list available states
    llc bank sync            → sync Plaid bank transactions
    llc time fetch           → fetch time entries from Toggl/Clockify
    llc retainer process     → auto-generate recurring invoices
    llc notify check         → send deadline + invoice alerts
    llc check                → verify ledger integrity
"""

import datetime
import sys
from decimal import Decimal
from pathlib import Path
from typing import Optional

import click

from .config import Config
from .ledger import Ledger
from .invoice import Invoicer, RetainerConfig
from .taxes import TaxEstimator
from .expenses import ExpenseImporter

# ── shared initialization ────────────────────────────────────────────────

_pass_config = click.make_pass_decorator(dict, ensure=True)


@click.group()
@click.option("--config", "-c", default=None, help="Path to config.toml")
@click.version_option(version="0.2.0")
@_pass_config
def cli(ctx, config):
    """SoloLedger — accounting, invoicing, and tax tools for your consulting LLC."""
    try:
        cfg = Config(config)
        ctx["cfg"] = cfg
        ctx["ledger"] = Ledger(cfg)
    except Exception as e:
        click.echo(f"ERROR: {e}", err=True)
        sys.exit(1)


# ── dashboard ─────────────────────────────────────────────────────────────


@cli.command()
@_pass_config
def status(ctx):
    """Show a financial dashboard: cash, P&L, upcoming deadlines."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    # Reload ledger
    errors = ledger.check()
    click.echo("═══ SoloLedger Dashboard ═══")
    click.echo()

    # Cash
    cash = ledger.cash_balance()
    click.echo(f"  Cash (checking):     ${cash:>10,.2f}")

    # P&L
    revenue = ledger.gross_revenue()
    expenses_val = ledger.total_expenses()
    net = revenue - expenses_val
    click.echo(f"  Gross Revenue:       ${revenue:>10,.2f}")
    click.echo(f"  Total Expenses:      ${expenses_val:>10,.2f}")
    click.echo(f"  Net Profit (YTD):    ${net:>10,.2f}")
    click.echo()

    # Tax estimate
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
    if net > 0:
        est = taxer.quarterly_estimate(net)
        click.echo(f"  Estimated Tax (annual): ${est['annual_total_tax']:>10,.2f}")
        click.echo(f"  Already paid:           ${est['already_paid']:>10,.2f}")
        click.echo(f"  Suggested next payment: ${est['suggested_payment']:>10,.2f}")
        click.echo(f"  → {est['note']}")
    else:
        click.echo("  No tax due (net profit ≤ 0)")
    click.echo()

    # Deadlines
    deadlines = taxer.deadline_info()
    for d in deadlines["deadlines"]:
        icon = "🔴" if d["status"] == "overdue" else "🟡" if d["status"] == "upcoming" else "🟢"
        click.echo(f"  {icon} {d['label']}: {d['due']} ({d['days_until']} days)")

    # Ledger health
    click.echo()
    if errors:
        click.echo(f"⚠  Ledger has {len(errors)} error(s). Run 'llc check'.")
    else:
        click.echo("✓ Ledger is clean.")


# ── check ─────────────────────────────────────────────────────────────────


@cli.command()
@_pass_config
def check(ctx):
    """Run Beancount validation on the ledger."""
    ledger = ctx["ledger"]
    errors = ledger.check()
    if errors:
        click.echo(f"Found {len(errors)} error(s):")
        for e in errors:
            click.echo(f"  ✗ {e}")
    else:
        click.echo("✓ Ledger is valid. No errors.")


# ── invoice ───────────────────────────────────────────────────────────────


@cli.group()
def invoice():
    """Manage invoices."""


@invoice.command("create")
@click.option("--client", "-c", required=True, help="Client name")
@click.option("--description", "-d", required=True, help="What the invoice is for")
@click.option("--amount", "-a", required=True, type=float, help="Invoice amount")
@click.option("--date", default=None, help="Invoice date (YYYY-MM-DD, default: today)")
@click.option("--no-pdf", is_flag=True, help="Skip PDF generation")
@click.option("--payment-link", "-p", is_flag=True, default=False, help="Create Stripe payment link")
@click.option("--client-email", "-e", default=None, help="Client email (for payment link prefill)")
@click.option("--recurring", "-r", type=click.Choice(["month", "year"]), default=None,
              help="Create a recurring/subscription payment link")
@_pass_config
def invoice_create(ctx, client, description, amount, date, no_pdf, payment_link, client_email, recurring):
    """Create a new invoice and record it in the ledger.

    Examples:

        # Basic invoice
        llc invoice create --client "Acme Corp" --description "Q3 Consulting" --amount 5000

        # Invoice with Stripe payment link
        llc invoice create -c "Acme Corp" -d "Q3 Consulting" -a 5000 --payment-link -e client@acme.com

        # Recurring retainer (subscription payment link)
        llc invoice create -c "Acme Corp" -d "Monthly retainer" -a 5000 --payment-link --recurring month
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    inv_date = datetime.date.fromisoformat(date) if date else datetime.date.today()

    result = invoicer.create(
        client=client,
        description=description,
        amount=Decimal(str(amount)).quantize(Decimal("0.01")),
        invoice_date=inv_date,
        generate_pdf=not no_pdf,
        payment_link=payment_link,
        client_email=client_email,
        recurring=recurring,
    )

    click.echo(f"✓ Invoice {result['number']} created")
    click.echo(f"  Client:     {client}")
    click.echo(f"  Amount:     ${amount:,.2f}")
    click.echo(f"  Date:       {result['date']}")
    if "payment_url" in result:
        click.echo(f"  💳 Pay online: {result['payment_url']}")
    elif payment_link:
        click.echo(f"  ⚠  Stripe not configured. Set STRIPE_SECRET_KEY env var for payment links.")
    if "pdf_path" in result:
        click.echo(f"  PDF:        {result['pdf_path']}")


@invoice.command("list")
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@click.option("--ar", "ar_only", is_flag=True, default=False, help="Show only unpaid invoices")
@_pass_config
def invoice_list(ctx, year, ar_only):
    """List all invoices.

    Use --ar to show only unpaid invoices (Accounts Receivable).
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    invoices = invoicer.list(year, ar_only=ar_only)

    if not invoices:
        click.echo("No invoices found.")
        return

    if ar_only:
        click.echo("═══ Unpaid Invoices (Accounts Receivable) ═══")
    click.echo(f"{'Date':<12} {'Client':<25} {'Amount':>10} {'Description'}")
    click.echo("-" * 70)
    for inv in invoices:
        click.echo(f"{str(inv['date']):<12} {inv['client']:<25} ${inv['amount']:>7,.2f} {inv['description'][:30]}")
    click.echo(f"\nTotal: {len(invoices)} invoices")


@invoice.command("ar")
@_pass_config
def invoice_ar(ctx):
    """Check Accounts Receivable — what's owed and overdue."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    info = invoicer.check_ar()

    click.echo("═══ Accounts Receivable ═══")
    click.echo()
    click.echo(f"  Total outstanding:  ${info['total_ar']:>10,.2f}")
    click.echo(f"  Open invoices:       {info['invoice_count']}")
    if info['overdue_count'] > 0:
        click.echo(f"  🔴 Overdue:           {info['overdue_count']} invoices")
        click.echo(f"  🔴 Overdue amount:   ${info['estimated_overdue_amount']:>10,.2f}")
    else:
        click.echo(f"  🟢 Overdue:          0 invoices")


# ── retainers / recurring invoices ────────────────────────────────────────

@cli.group()
def retainer():
    """Manage recurring retainer invoices (for cron-based auto-invoicing)."""


@retainer.command("add")
@click.option("--client", "-c", required=True, help="Client name")
@click.option("--description", "-d", required=True, help="What the retainer is for")
@click.option("--amount", "-a", required=True, type=float, help="Monthly/quarterly amount")
@click.option("--interval", "-i", type=click.Choice(["monthly", "quarterly", "yearly"]),
              default="monthly", help="How often to invoice (default: monthly)")
@click.option("--day", type=int, default=1, help="Day of month to invoice (1-28)")
@click.option("--stripe", is_flag=True, default=False, help="Create Stripe recurring payment link")
@_pass_config
def retainer_add(ctx, client, description, amount, interval, day, stripe):
    """Add a recurring retainer invoice configuration."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    retainer_cfg = RetainerConfig(
        client=client,
        description=description,
        amount=Decimal(str(amount)).quantize(Decimal("0.01")),
        interval=interval,
        day_of_month=day,
        stripe_recurring=stripe,
    )

    info = invoicer.save_retainer(retainer_cfg)

    click.echo(f"✓ Retainer configured for {client}")
    click.echo(f"  Amount:      ${amount:,.2f}")
    click.echo(f"  Interval:    {interval}")
    click.echo(f"  Next invoice: {info['next_invoice']}")
    if stripe:
        click.echo(f"  💳 Stripe recurring payment enabled")


@retainer.command("list")
@_pass_config
def retainer_list(ctx):
    """List all configured retainers."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    retainers = invoicer._load_retainers()
    if not retainers:
        click.echo("No retainers configured. Use 'llc retainer add' first.")
        return

    click.echo("═══ Retainer Invoices ═══")
    click.echo()
    for rid, info in retainers.items():
        last = info.get("last_invoiced") or "never"
        next_inv = info.get("next_invoice") or "?"
        amount = Decimal(str(info["amount"]))
        click.echo(f"  {info['client']:<25s}  ${amount:>8,.2f}  {info['interval']:<10s}")
        click.echo(f"    Last: {last}  |  Next: {next_inv}")


@retainer.command("process")
@click.option("--no-preview", is_flag=True, default=False, help="Actually generate invoices (not preview)")
@_pass_config
def retainer_process(ctx, no_preview):
    """Check all retainers and generate invoices for those due.

    Designed to be run from cron:
        0 9 1 * * cd /path/to/solo-ledger && python -m app.main retainer process --no-preview
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    preview = not no_preview
    results = invoicer.process_retainers(preview=preview)

    if not results:
        click.echo("No invoices due at this time.")


@retainer.command("remove")
@click.argument("retainer_id")
@_pass_config
def retainer_remove(ctx, retainer_id):
    """Remove a retainer configuration by ID.

    Use 'llc retainer list' to see IDs.
    """
    cfg = ctx["cfg"]
    invoicer = Invoicer(cfg, None)

    retainers = invoicer._load_retainers()
    if retainer_id in retainers:
        del retainers[retainer_id]
        path = invoicer._retainers_path()
        import json
        with open(path, "w") as f:
            json.dump(retainers, f, indent=2)
        click.echo(f"✓ Retainer '{retainer_id}' removed.")
    else:
        click.echo(f"Retainer '{retainer_id}' not found.")


# ── expenses ──────────────────────────────────────────────────────────────


@cli.command()
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--preview", is_flag=True, help="Preview only, don't import")
@_pass_config
def expense(ctx, csv_file, preview):
    """Import expenses from a bank CSV file."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    importer = ExpenseImporter(cfg, ledger)

    if preview:
        click.echo("═══ Preview — no changes made ═══")
    else:
        click.echo("═══ Importing transactions ═══")

    results = importer.import_csv(csv_file, preview=preview)

    income_count = sum(1 for r in results if r["type"] == "income")
    expense_count = sum(1 for r in results if r["type"] == "expense")
    total = sum(r["amount"] for r in results)

    for r in results:
        click.echo(f"  {r['date']}  {r['description'][:45]:45s}  ${abs(r['amount']):>8,.2f}  → {r['account']}")

    click.echo()
    click.echo(f"  {income_count} income + {expense_count} expense transactions")
    click.echo(f"  Net: ${total:,.2f}")

    if preview:
        click.echo("\n(Preview only — run without --preview to import)")


# ── taxes ─────────────────────────────────────────────────────────────────


@cli.group()
def tax():
    """Estimate taxes and generate reports."""


@tax.command("estimate")
@click.option("--projected-income", "-i", type=float, default=None,
              help="Projected full-year net income (default: YTD * 2)")
@click.option("--state", "state_override", default=None,
              help="Two-letter state code (e.g. CA, TX, NY). Overrides config.")
@_pass_config
def tax_estimate(ctx, projected_income, state_override):
    """Calculate estimated quarterly tax payment (federal + state).

    Supports multi-state tax estimation. Configure default state in config.toml
    or override with --state.

    Examples:
        llc tax estimate                         # Wyoming (config default)
        llc tax estimate --state CA              # California
        llc tax estimate --state TX --projected-income 120000
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    state_code = state_override or cfg.state_code

    taxer = TaxEstimator(cfg, ledger, state_code=state_code)

    ytd_net = ledger.net_income()

    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        projection = ytd_net * Decimal("2")

    if ytd_net <= 0:
        click.echo("⚠  No net profit yet. No tax estimated.")
        return

    # Get revenue estimate for franchise tax calculations
    ytd_revenue = ledger.gross_revenue()
    projected_revenue = ytd_revenue * Decimal("2") if ytd_revenue > 0 else projection * Decimal("1.1")

    # Full annual estimate
    annual = taxer.total_projected_tax(projection, total_revenue=projected_revenue)
    quarterly = taxer.quarterly_estimate(ytd_net, projection)

    state_name = annual.get("state_tax", {}).get("state_name", state_code)
    click.echo(f"═══ Tax Estimate (Single-Member LLC — {state_name}) ═══")
    click.echo()
    click.echo(f"  YTD Net Profit:                ${ytd_net:>10,.2f}")
    click.echo(f"  Projected Annual Net:          ${projection:>10,.2f}")
    click.echo()
    click.echo(f"  ── Federal ──")
    click.echo(f"  Self-Employment Tax (15.3%):   ${annual['self_employment_tax']['total_se_tax']:>10,.2f}")
    click.echo(f"    ↳ Deductible half (AGI):     ${annual['self_employment_tax']['deductible_half']:>10,.2f}")
    click.echo(f"  Federal Income Tax:            ${annual['federal_income_tax']['income_tax']:>10,.2f}")
    click.echo(f"    ↳ Taxable income:            ${annual['federal_income_tax']['taxable_income']:>10,.2f}")
    click.echo(f"    ↳ Effective rate:            {annual['federal_income_tax']['effective_rate']:.1f}%")

    # State tax breakdown
    st = annual.get("state_tax", {})
    if st and st.get("total_state_tax", Decimal("0")) > 0:
        click.echo()
        click.echo(f"  ── {state_name} State Tax ──")
        income_tax = st.get("income_tax", {})
        if income_tax and income_tax.get("tax", Decimal("0")) > 0:
            click.echo(f"  State Income Tax:              ${income_tax['tax']:>10,.2f}")
            click.echo(f"    ↳ Taxable income:            ${income_tax.get('taxable_income', 0):>10,.2f}")
            click.echo(f"    ↳ Effective rate:            {income_tax.get('effective_rate', 0):.1f}%")

        franchise_tax = st.get("franchise_tax", {})
        if franchise_tax and franchise_tax.get("tax", Decimal("0")) > 0:
            click.echo(f"  Franchise/Gross Receipts Tax:  ${franchise_tax['tax']:>10,.2f}")

        local_tax = st.get("local_income_tax", {})
        if local_tax and local_tax.get("tax", Decimal("0")) > 0:
            click.echo(f"  Local Income Tax:              ${local_tax['tax']:>10,.2f}")

        annual_fee = st.get("annual_llc_fee", 0)
        if annual_fee > 0:
            click.echo(f"  Annual LLC Fee:                ${annual_fee:>10,.2f}")

    click.echo(f"  ─────────────────────────────────────────────")
    click.echo(f"  TOTAL ESTIMATED TAX:           ${annual['total_tax']:>10,.2f}")
    click.echo(f"  Effective tax rate:            {annual['effective_tax_rate']:.1f}%")
    click.echo()
    click.echo(f"  Already paid YTD:              ${quarterly['already_paid']:>10,.2f}")
    click.echo(f"  Remaining:                     ${quarterly['remaining']:>10,.2f}")
    click.echo(f"  Remaining quarters:            {quarterly['remaining_quarters']}")
    click.echo(f"  ╰→ Suggested next payment:     ${quarterly['suggested_payment']:>10,.2f}")
    click.echo()
    click.echo(f"  Schedule:                      {quarterly['note']}")


@tax.command("schedule-c")
@_pass_config
def tax_schedule_c(ctx):
    """Generate Schedule C summary data for tax filing."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)

    summary = taxer.schedule_c_summary()

    click.echo("═══ Schedule C Summary ═══")
    click.echo()
    click.echo(f"  Part I — Income")
    click.echo(f"    Gross receipts:              ${summary['gross_receipts']:>10,.2f}")
    click.echo()
    click.echo(f"  Part II — Expenses")
    for exp in summary["expense_detail"]:
        # Shorten account name for display
        short = exp["account"].replace("Expenses:", "")
        click.echo(f"    {short:<35s} ${exp['amount']:>8,.2f}")
    click.echo(f"    {'──' * 25}")
    click.echo(f"    {'Total Expenses':<35s} ${summary['total_expenses']:>8,.2f}")
    click.echo()
    click.echo(f"  Part III — Net Profit")
    click.echo(f"    Net profit (Schedule C, line 31): ${summary['net_profit']:>10,.2f}")
    click.echo()
    click.echo(f"  Taxes Paid (for reference)")
    click.echo(f"    Federal estimated payments:  ${summary['taxes_paid']['federal_estimated']:>10,.2f}")
    click.echo(f"    FICA (employer half):        ${summary['taxes_paid']['fica_employer']:>10,.2f}")


@tax.command("deadlines")
@_pass_config
def tax_deadlines(ctx):
    """Show upcoming tax deadlines (federal + state if applicable)."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)

    info = taxer.deadline_info()

    click.echo(f"Tax deadlines (as of {info['as_of']}):")
    for d in info["deadlines"]:
        icon = {
            "overdue": "🔴 OVERDUE",
            "upcoming": "🟡 UPCOMING",
            "ahead": "🟢",
        }.get(d["status"], "🟢")

        click.echo(f"  {icon}  {d['label']}: {d['due']}  ({d['days_until']:>+4d} days)")


@tax.command("state-list")
def tax_state_list():
    """List all available states for tax estimation."""
    try:
        from .taxes.state_calculator import StateTaxCalculator
    except ImportError:
        click.echo("⚠  State calculator not available.")
        return

    states = StateTaxCalculator.list_states()
    if not states:
        click.echo("No state data found.")
        return

    click.echo("═══ Available States ═══")
    click.echo()
    for code, info in states.items():
        income = "💰" if info["has_income_tax"] else "  "
        franchise = "🏛️" if info["has_franchise_tax"] else "   "
        click.echo(f"  {code:<4s}  {income} {franchise}  {info['name']:<20s}  ${info['annual_fee']}/yr fee")
    click.echo()
    click.echo("Legend: 💰 = has income tax  🏛️ = has franchise/gross receipts tax")
    click.echo()
    click.echo("Usage:  llc tax estimate --state CA")
    click.echo("Config: Set 'state = \"CA\"' in config.toml under [tax]")


# ── bank feed (Plaid) ────────────────────────────────────────────────────


@cli.group()
def bank():
    """Automated bank feed via Plaid."""


@bank.command("sync")
@click.option("--days", type=int, default=90, help="Days of history to sync (default: 90)")
@click.option("--preview", is_flag=True, default=False, help="Preview only, don't import")
@_pass_config
def bank_sync(ctx, days, preview):
    """Fetch transactions from Plaid and import into ledger.

    Requires PLAID_CLIENT_ID, PLAID_SECRET, and PLAID_ACCESS_TOKEN env vars.
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        click.echo("⚠  plaid-python not installed. Run: pip install plaid-python")
        return

    feed = PlaidFeed(cfg)
    if not feed.enabled:
        click.echo("⚠  Plaid not configured. Set these env vars:")
        click.echo("    PLAID_CLIENT_ID")
        click.echo("    PLAID_SECRET")
        click.echo("    PLAID_ACCESS_TOKEN")
        click.echo("    PLAID_ENV (sandbox|development|production)")
        return

    # Show connected accounts first
    accounts = feed.fetch_accounts()
    if accounts:
        click.echo("Connected accounts:")
        for acct in accounts:
            click.echo(f"  · {acct['name']:30s}  ${acct['current']:>8,.2f}  ({acct['type']})")
        click.echo()

    click.echo(f"Fetching transactions (last {days} days)...")
    txns = feed.fetch_transactions(days_back=days)
    click.echo(f"  Found {len(txns)} new/modified transactions")
    click.echo()

    if not txns:
        click.echo("Nothing to import.")
        return

    if preview:
        click.echo("═══ Preview — no changes made ═══")
        income = [t for t in txns if t.amount < 0]
        expenses = [t for t in txns if t.amount > 0]
        if income:
            click.echo(f"\n  Income ({len(income)}):")
            for t in income[:10]:
                click.echo(f"    {t.date}  {t.description[:45]:45s}  ${abs(t.amount):>8,.2f}")
        if expenses:
            click.echo(f"\n  Expenses ({len(expenses)}):")
            for t in expenses[:20]:
                click.echo(f"    {t.date}  {t.description[:45]:45s}  ${t.amount:>8,.2f}")
        if len(txns) > 30:
            click.echo(f"\n  ... and {len(txns) - 30} more transactions")
        click.echo(f"\nRun without --preview to import.")
    else:
        click.echo("Importing transactions...")
        results = feed.import_transactions(txns)
        income_count = sum(1 for r in results if r["type"] == "income")
        expense_count = sum(1 for r in results if r["type"] == "expense")
        total = sum(r["amount"] for r in results)
        click.echo(f"  Imported: {income_count} income + {expense_count} expense")
        click.echo(f"  Net: ${total:,.2f}")


@bank.command("accounts")
@_pass_config
def bank_accounts(ctx):
    """List connected bank accounts and balances."""
    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        click.echo("⚠  plaid-python not installed.")
        return

    feed = PlaidFeed()
    accounts = feed.fetch_accounts()

    if not accounts:
        click.echo("No accounts found or Plaid not configured.")
        return

    click.echo("Connected Bank Accounts:")
    for acct in accounts:
        click.echo(f"  · {acct['name']:35s}  ${acct['current']:>10,.2f}  ({acct['type']}/{acct['subtype']})")


@bank.command("link-token")
def bank_link_token():
    """Generate a Plaid Link token to connect a new bank account.

    Use this token in the Plaid Link frontend to get an access_token,
    then set it as PLAID_ACCESS_TOKEN.
    """
    try:
        from .bank_feed import PlaidFeed
    except ImportError:
        click.echo("⚠  plaid-python not installed.")
        return

    result = PlaidFeed.generate_link_token()
    if "error" in result:
        click.echo(f"⚠  {result['error']}")
        return

    click.echo("Plaid Link Token generated!")
    click.echo(f"  link_token: {result['link_token']}")
    click.echo(f"  expires:    {result['expiration']}")
    click.echo()
    click.echo("Use this token with Plaid Link to connect a bank account.")
    click.echo("Once connected, set PLAID_ACCESS_TOKEN in your environment.")


# ── notifications / alerts ────────────────────────────────────────────────


@cli.group()
def notify():
    """Send notifications: tax deadline reminders, invoice alerts, etc."""


@notify.command("check")
@_pass_config
def notify_check(ctx):
    """Check everything and send alerts (desktop + email if configured).

    Run this from cron for daily reminders:
        0 9 * * * cd /path/to/solo-ledger && python -m app.main notify check
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        from .notify import Notifier
    except ImportError:
        click.echo("⚠  Notifier not available.")
        return

    notifier = Notifier(cfg)
    results = notifier.send_digest(ledger)

    total = sum(len(v) for v in results.values())
    if total == 0:
        click.echo("✓ All clear — no alerts needed.")
    else:
        click.echo(f"Sent {total} alert(s):")
        for key, alerts in results.items():
            for alert in alerts:
                click.echo(f"  · [{key}] {alert}")


@notify.command("deadlines")
@_pass_config
def notify_deadlines(ctx):
    """Check and notify about upcoming tax deadlines."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        from .notify import Notifier
    except ImportError:
        click.echo("⚠  Notifier not available.")
        return

    notifier = Notifier(cfg)
    alerts = notifier.alert_tax_deadlines(ledger)

    if alerts:
        for a in alerts:
            click.echo(f"  {a}")
    else:
        click.echo("✓ No upcoming tax deadlines this week.")


# ── receipt scanning ─────────────────────────────────────────────────────


@cli.group()
def receipt():
    """Scan receipt PDFs/images and import expenses."""


@receipt.command("scan")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--no-preview", is_flag=True, default=False, help="Append to ledger (not just preview)")
@click.option("--account", default=None, help="Override expense account")
@_pass_config
def receipt_scan(ctx, filepath, no_preview, account):
    """Scan a receipt (PDF or image) and extract expense data.

    Supported formats: PDF, PNG, JPG, JPEG, TIFF, BMP, WEBP
    Requires tesseract-ocr for image OCR.
    """
    cfg = ctx["cfg"]

    try:
        from .receipts import ReceiptScanner
    except ImportError:
        click.echo("⚠  Receipt scanner not available.")
        return

    scanner = ReceiptScanner(cfg)
    preview = not no_preview

    click.echo(f"Scanning: {filepath}")
    click.echo()

    result = scanner.process_file(filepath, preview=preview)

    if result.get("success") and not preview:
        click.echo(f"✓ Entry appended to ledger.")
    elif result.get("success") and preview:
        click.echo()
        click.echo("Run with --no-preview to append to the ledger.")

    if not result.get("success"):
        click.echo(f"⚠  Scan failed: {result.get('error', 'unknown error')}")


@receipt.command("batch")
@click.argument("directory", type=click.Path(exists=True))
@click.option("--no-preview", is_flag=True, default=False, help="Import all scanned receipts")
@_pass_config
def receipt_batch(ctx, directory, no_preview):
    """Scan all receipt files in a directory.

    Useful for bulk-importing a folder of receipt PDFs/images.
    """
    cfg = ctx["cfg"]
    dir_path = Path(directory)

    try:
        from .receipts import ReceiptScanner
    except ImportError:
        click.echo("⚠  Receipt scanner not available.")
        return

    scanner = ReceiptScanner(cfg)
    preview = not no_preview

    # Find receipt files
    extensions = {".pdf", ".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"}
    files = [f for f in dir_path.iterdir() if f.suffix.lower() in extensions]
    files.sort()

    if not files:
        click.echo(f"No receipt files found in {directory}")
        click.echo(f"Supported formats: {', '.join(sorted(extensions))}")
        return

    click.echo(f"Found {len(files)} receipt file(s)")
    click.echo()

    success = 0
    fail = 0
    total_amount = Decimal("0")

    for f in files:
        result = scanner.process_file(str(f), preview=preview)
        if result.get("success"):
            success += 1
            if result.get("total"):
                total_amount += result["total"]
        else:
            fail += 1
            click.echo(f"  ✗ {f.name}: {result.get('error', 'failed')}")

    click.echo()
    click.echo(f"Results: {success} scanned, {fail} failed")
    if success > 0:
        click.echo(f"Total expense amount: ${total_amount:,.2f}")

    if preview and success > 0:
        click.echo()
        click.echo("Run with --no-preview to append all to the ledger.")


# ── time tracking ─────────────────────────────────────────────────────────


@cli.group()
def time():
    """Track billable time via Toggl Track or Clockify."""


@time.command("fetch")
@click.option("--days", type=int, default=7, help="Days to look back (default: 7)")
@click.option("--source", type=click.Choice(["toggl", "clockify"]), default="toggl",
              help="Time tracking service (default: toggl)")
@click.option("--rate", type=float, default=None, help="Hourly rate (default: $150)")
@click.option("--billable-only", is_flag=True, default=True, help="Only billable entries")
@_pass_config
def time_fetch(ctx, days, source, rate, billable_only):
    """Fetch time entries and show invoice-ready summary.

    Set TOGGL_API_TOKEN or CLOCKIFY_API_KEY env var to enable.
    """
    try:
        from .time_tracking import TimeTracker
    except ImportError:
        click.echo("⚠  Time tracking module not available.")
        return

    hourly = Decimal(str(rate)).quantize(Decimal("0.01")) if rate else None
    tracker = TimeTracker(source=source, hourly_rate=hourly)

    # Try to set rate from config if not provided
    if rate is None:
        raw = getattr(ctx.get("cfg"), "_raw", {})
        default_rate = raw.get("time_tracking", {}).get("hourly_rate")
        if default_rate:
            hourly = Decimal(str(default_rate)).quantize(Decimal("0.01"))

    click.echo(f"Fetching time entries from {source.title()} (last {days} days)...")

    entries = tracker.fetch_entries(days_back=days, billable_only=billable_only)

    if not entries:
        click.echo("  No entries found. Is your API token configured?")
        click.echo()
        click.echo("  Toggl: Set TOGGL_API_TOKEN env var")
        click.echo("  Clockify: Set CLOCKIFY_API_KEY env var")
        return

    summary = tracker.summarize_by_client(entries, hourly_rate=hourly)

    click.echo(f"  Found {summary['entry_count']} entries")
    click.echo(f"  Total hours: {summary['total_hours']:,.2f}h")
    click.echo(f"  Total amount: ${summary['total_amount']:>,.2f}")
    click.echo()

    for client, data in summary["by_client"].items():
        click.echo(f"  {client}:")
        click.echo(f"    Hours:  {data['hours']:,.2f}h")
        click.echo(f"    Amount: ${data['amount']:>,.2f}")
        for project, pdata in data["projects"].items():
            click.echo(f"      · {project}: {pdata['hours']:,.2f}h")
        click.echo()

    click.echo("  To create an invoice from this time:")
    click.echo(f"    llc invoice create --client \"CLIENT\" --description \"Time tracking\" --amount AMOUNT")


@time.command("invoice")
@click.option("--days", type=int, default=7, help="Days to look back")
@click.option("--source", type=click.Choice(["toggl", "clockify"]), default="toggl")
@click.option("--rate", type=float, default=None, help="Hourly rate")
@click.option("--client", default=None, help="Filter by client name")
@click.option("--no-preview", is_flag=True, default=False, help="Actually create the invoice (not preview)")
@_pass_config
def time_invoice(ctx, days, source, rate, client, no_preview):
    """Create an invoice from tracked time entries."""
    try:
        from .time_tracking import TimeTracker
    except ImportError:
        click.echo("⚠  Time tracking module not available.")
        return

    hourly = Decimal(str(rate)).quantize(Decimal("0.01")) if rate else None
    tracker = TimeTracker(source=source, hourly_rate=hourly)

    entries = tracker.fetch_entries(days_back=days)
    if not entries:
        click.echo("No time entries found.")
        return

    invoice_data = tracker.generate_invoice_data(entries, client_filter=client)
    if not invoice_data:
        click.echo(f"No entries found for client filter: {client}")
        return

    click.echo(f"Time entries: {invoice_data['entries']['entry_count']}")
    click.echo(f"Total hours:  {invoice_data['entries']['total_hours']:,.2f}h")
    click.echo(f"Invoice amount: ${invoice_data['amount']:>,.2f}")
    click.echo(f"Description: {invoice_data['description']}")
    click.echo()

    if no_preview:
        cfg = ctx["cfg"]
        ledger = ctx["ledger"]
        from .invoice import Invoicer
        invoicer = Invoicer(cfg, ledger)
        result = invoicer.create(
            client=invoice_data["client"],
            description=invoice_data["description"],
            amount=invoice_data["amount"],
        )
        click.echo(f"✓ Invoice {result['number']} created")
        if "pdf_path" in result:
            click.echo(f"  PDF: {result['pdf_path']}")
    else:
        click.echo("(Preview — run with --no-preview to create the invoice)")


# ── doctor / diagnostic ──────────────────────────────────────────────────


@cli.command()
@_pass_config
def doctor(ctx):
    """Run diagnostics — check all integrations and configuration.

    Reports what's working and what needs setup for each module.
    Run this first when setting up SoloLedger.
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    import os
    from pathlib import Path

    click.echo("═══ SoloLedger Doctor ═══")
    click.echo()

    # ── 1. Ledger ──────────────────────────────────────────────────────
    errors = ledger.check()
    click.echo(f"  {'✅' if not errors else '❌'}  Ledger:       {'Clean' if not errors else f'{len(errors)} error(s)'}" )
    if errors:
        for e in errors[:3]:
            click.echo(f"       {e}")

    cash = ledger.cash_balance()
    revenue = ledger.gross_revenue()
    click.echo(f"  {'✅' if cash > 0 else '⚠️'}  Cash:         ${cash:>8,.2f}")
    click.echo(f"  {'✅' if revenue > 0 else '⚠️'}  Revenue YTD:  ${revenue:>8,.2f}")
    click.echo()

    # ── 2. Config ─────────────────────────────────────────────────────
    biz_name = cfg.business_name
    has_ein = cfg.ein != "XX-XXXXXXX"
    has_phone = cfg.phone != "+1 307-555-XXXX"
    click.echo(f"  {'✅' if biz_name != 'Your LLC Name Here' else '⚠️'}  Business:     {biz_name}")
    click.echo(f"  {'✅' if has_ein else '⚠️'}  EIN:          {cfg.ein if has_ein else 'Not set'}")
    click.echo(f"  {'✅' if cfg.state_code else '⚠️'}  State:        {cfg.state_code}")
    click.echo()

    # ── 3. Stripe ────────────────────────────────────────────────────
    stripe_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if stripe_key:
        from .payments import StripePayments
        sp = StripePayments()
        click.echo(f"  {'✅' if sp.enabled else '⚠️'}  Stripe:       Configured (key found)")
    else:
        click.echo(f"  {'⚠️' if not stripe_key else '✅'}  Stripe:       Not configured — set STRIPE_SECRET_KEY")
    click.echo()

    # ── 4. Plaid ────────────────────────────────────────────────────
    plaid_id = os.environ.get("PLAID_CLIENT_ID", "")
    plaid_secret = os.environ.get("PLAID_SECRET", "")
    plaid_token = os.environ.get("PLAID_ACCESS_TOKEN", "")
    if plaid_id and plaid_secret and plaid_token:
        click.echo(f"  ✅  Plaid:        Configured ({plaid_id[:10]}...)")
    elif plaid_id and plaid_secret:
        click.echo(f"  {'⚠️' if not plaid_token else '⚠️'}  Plaid:        Client/Secret set but no access token")
    else:
        click.echo(f"  ⚠️   Plaid:        Not configured — set PLAID_CLIENT_ID, PLAID_SECRET, PLAID_ACCESS_TOKEN")
    click.echo()

    # ── 5. Time tracking ────────────────────────────────────────────
    toggl_token = os.environ.get("TOGGL_API_TOKEN", "")
    clockify_key = os.environ.get("CLOCKIFY_API_KEY", "")
    if toggl_token:
        click.echo(f"  ✅  Toggl:        Configured")
    elif clockify_key:
        click.echo(f"  ✅  Clockify:     Configured")
    else:
        click.echo(f"  ⚠️   Toggl:        Not configured — set TOGGL_API_TOKEN")
        click.echo(f"  ⚠️   Clockify:     Not configured — set CLOCKIFY_API_KEY")
    click.echo()

    # ── 6. Notifications ────────────────────────────────────────────
    smtp_user = os.environ.get("NOTIFY_SMTP_PASSWORD", "")
    desktop_ok = Path("/usr/bin/notify-send").exists()
    click.echo(f"  {'✅' if desktop_ok else '⚠️'}  Desktop:      Notifications via notify-send {'available' if desktop_ok else '(not found)'}")
    click.echo(f"  {'✅' if smtp_user else '⚠️'}  Email:        {'Configured' if smtp_user else 'Not configured — set NOTIFY_SMTP_PASSWORD'}")
    click.echo()

    # ── 7. Receipt OCR ─────────────────────────────────────────────
    tesseract_ok = shutil_which("tesseract")
    click.echo(f"  {'✅' if tesseract_ok else '⚠️'}  OCR:          Tesseract {'available' if tesseract_ok else 'not found (install tesseract-ocr)'}")
    click.echo()

    # ── 8. Expirations / Coming soon ───────────────────────────────
    click.echo(f"  📅  Tax deadlines:")
    from .taxes import TaxEstimator
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)
    for d in taxer.deadline_info()["deadlines"][:3]:
        status = {"overdue": "🔴", "upcoming": "🟡", "ahead": "🟢"}.get(d["status"], "⚪")
        click.echo(f"       {status}  {d['label']:12s} {d['due']} ({d['days_until']:+d} days)")
    click.echo()

    # ── Summary ──────────────────────────────────────────────────
    net = ledger.net_income()
    click.echo(f"  {'💰' if net > 0 else '💸'}  Net profit:   ${net:>8,.2f}")
    click.echo()
    click.echo(f"  ▸  Docs:       https://github.com/dillonj/solo-ledger#readme")
    click.echo(f"  ▸  Cloud:      https://sololedger.app")


def shutil_which(cmd):
    """Check if a command is available."""
    import shutil
    return shutil.which(cmd)


# ── setup wizard ──────────────────────────────────────────────────────────


@cli.command()
def init():
    """Interactive setup wizard — configure your business and check env vars.

    Run this first when installing SoloLedger.
    """
    from .setup import run_init
    run_init()


# ── demo data ─────────────────────────────────────────────────────────────


@cli.command()
@click.option("--fresh", is_flag=True, help="Remove existing data and reload")
@_pass_config
def demo(ctx, fresh):
    """Load sample data so you can explore SoloLedger right away.

    Adds sample invoices, expenses, and opening balance to the ledger.
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from decimal import Decimal

    tx_path = cfg.ledger_dir / "transactions.beancount"
    content = tx_path.read_text()

    # If fresh, strip existing demo data
    if fresh and "SoloLedger Demo" in content:
        # Remove everything from the demo marker to end of file
        marker = "=== SoloLedger Demo Data ==="
        idx = content.find(marker)
        if idx != -1:
            content = content[:idx].rstrip() + "\n"
            tx_path.write_text(content)
            ledger.reload()
            click.echo("  ✓  Removed existing demo data.")

    # Check if demo data already loaded (unless --fresh was used)
    content = tx_path.read_text()
    if "SoloLedger Demo" in content:
        click.echo("⚠  Demo data already loaded. Use 'llc demo --fresh' to reload.")
        return

    click.echo("═══ Loading Demo Data ═══")
    click.echo()

    demo_entries = [
        # Opening balance
        {
            "date": "2026-01-02",
            "payee": "Dillon",
            "narration": "Initial contribution",
            "postings": [
                ("Assets:Bank:BusinessChecking", "10000.00 USD"),
                ("Equity:OpeningBalance", "-10000.00 USD"),
            ],
        },
        # Invoices
        {
            "date": "2026-01-15",
            "payee": "Acme Corp",
            "narration": "Q1 2026 Consulting Retainer",
            "postings": [
                ("Income:Consulting", "-8000.00 USD"),
                ("Assets:AccountsReceivable", "8000.00 USD"),
            ],
        },
        {
            "date": "2026-02-01",
            "payee": "Client payment — Acme Corp",
            "narration": "Invoice paid via wire",
            "postings": [
                ("Assets:Bank:BusinessChecking", "8000.00 USD"),
                ("Assets:AccountsReceivable", "-8000.00 USD"),
            ],
        },
        {
            "date": "2026-04-15",
            "payee": "Beta Inc",
            "narration": "Website consulting — Q2 2026",
            "postings": [
                ("Income:Consulting", "-5000.00 USD"),
                ("Assets:AccountsReceivable", "5000.00 USD"),
            ],
        },
        # Expenses
        {
            "date": "2026-01-05",
            "payee": "GitHub",
            "narration": "GitHub Team plan — Jan 2026",
            "postings": [
                ("Expenses:Software:SaaS", "20.00 USD"),
                ("Assets:Bank:BusinessChecking", "-20.00 USD"),
            ],
        },
        {
            "date": "2026-01-10",
            "payee": "AWS",
            "narration": "AWS hosting — Jan 2026",
            "postings": [
                ("Expenses:Software:Hosting", "47.23 USD"),
                ("Assets:Bank:BusinessChecking", "-47.23 USD"),
            ],
        },
        {
            "date": "2026-01-15",
            "payee": "Office Depot",
            "narration": "Office supplies",
            "postings": [
                ("Expenses:Supplies", "35.00 USD"),
                ("Assets:Bank:BusinessChecking", "-35.00 USD"),
            ],
        },
        {
            "date": "2026-02-01",
            "payee": "Cloudflare",
            "narration": "Cloudflare Pro plan",
            "postings": [
                ("Expenses:Software:Hosting", "20.00 USD"),
                ("Assets:Bank:BusinessChecking", "-20.00 USD"),
            ],
        },
        {
            "date": "2026-02-10",
            "payee": "Stripe",
            "narration": "Payment processing fees",
            "postings": [
                ("Expenses:BankFees", "22.50 USD"),
                ("Assets:Bank:BusinessChecking", "-22.50 USD"),
            ],
        },
        {
            "date": "2026-03-01",
            "payee": "IRS",
            "narration": "Q1 2026 estimated tax payment",
            "postings": [
                ("Expenses:Taxes:Federal", "1500.00 USD"),
                ("Assets:Bank:BusinessChecking", "-1500.00 USD"),
            ],
        },
        # Owner draw
        {
            "date": "2026-03-15",
            "payee": "Dillon",
            "narration": "Owner draw — Mar 2026",
            "postings": [
                ("Equity:OwnerDraws", "3000.00 USD"),
                ("Assets:Bank:BusinessChecking", "-3000.00 USD"),
            ],
        },
    ]

    # Append demo data with a clear marker
    with open(tx_path, "a") as f:
        f.write("\n")
        f.write(";; === SoloLedger Demo Data ==========================================\n")
        f.write(";; Generated by `llc demo` — safe to delete when you start fresh\n")
        f.write(";; ==================================================================\n")
        f.write("\n")

        for entry in demo_entries:
            date = entry["date"]
            payee = entry["payee"].replace('"', '\\"')
            narration = entry["narration"].replace('"', '\\"')
            f.write(f'{date} * "{payee}" "{narration}"\n')
            for account, amount in entry["postings"]:
                f.write(f"  {account:45s}  {amount}\n")
            f.write("\n")

    # Reload ledger
    ledger.reload()
    net = ledger.net_income()
    cash = ledger.cash_balance()
    ar = ledger.account_balance(cfg.ar_account)

    click.echo(f"  ✓  Loaded {len(demo_entries)} sample transactions")
    click.echo()
    click.echo(f"  Cash:            ${cash:>8,.2f}")
    click.echo(f"  Revenue:         ${ledger.gross_revenue():>8,.2f}")
    click.echo(f"  Expenses:        ${ledger.total_expenses():>8,.2f}")
    click.echo(f"  Net Profit YTD:  ${net:>8,.2f}")
    click.echo(f"  AR Outstanding:  ${ar:>8,.2f}")
    click.echo()
    click.echo("  Run 'llc status' to see the full dashboard.")


# ── entry point ───────────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
