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
@click.version_option(version="0.3.0")
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
    ent_type = getattr(cfg, 'entity_type', 'smllc')
    ent_label = "S-Corp (1120-S)" if ent_type == "scorp" else "SMLLC (Schedule C)"
    click.echo("═══ SoloLedger Dashboard ═══")
    click.echo(f"  Entity type:         {ent_label}")
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

    # Data ownership / trust info
    click.echo()
    click.echo("── Data Ownership ──")
    click.echo("  Format:     Plain-text Beancount (no vendor lock-in)")
    click.echo("  Location:   " + str(cfg.ledger_dir))
    click.echo("  Backup:     Git auto-backup " + ("✓ configured" if hasattr(cfg, 'backup') and getattr(cfg, 'backup') else "not configured"))
    try:
        import subprocess
        result = subprocess.run(
            ["git", "log", "--oneline", "-3"],
            capture_output=True, text=True,
            cwd=cfg.ledger_dir
        )
        commits = result.stdout.strip().split("\n") if result.stdout.strip() else []
        if commits and commits[0]:
            click.echo(f"  Recent changes:")
            for c in commits:
                click.echo(f"    {c[:60]}")
        # Count total commits
        count_result = subprocess.run(
            ["git", "rev-list", "--count", "HEAD"],
            capture_output=True, text=True,
            cwd=cfg.ledger_dir
        )
        if count_result.returncode == 0:
            click.echo(f"  Total git commits: {count_result.stdout.strip()}")
    except Exception:
        pass
    click.echo("  ✓ Data is yours. Always. No subscription required.")


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

    retainers = invoicer.list_retainers()
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
        0 9 1 * * cd /path/to/sololedger && python -m app.main retainer process --no-preview
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

    if invoicer.remove_retainer(retainer_id):
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

    entity_type = annual.get("entity_type", "smllc")
    is_scorp = entity_type == "scorp"
    state_name = annual.get("state_tax", {}).get("state_name", state_code)
    header_label = f"S-Corp (1120-S — {state_name})" if is_scorp else f"Single-Member LLC (Schedule C — {state_name})"
    click.echo(f"═══ Tax Estimate ({header_label}) ═══")
    click.echo()
    click.echo(f"  YTD Net Profit:                ${ytd_net:>10,.2f}")
    click.echo(f"  Projected Annual Net:          ${projection:>10,.2f}")
    click.echo()

    if is_scorp:
        fica = annual.get("fica", {})
        form1120 = annual.get("form_1120s", {})
        click.echo(f"  ── Payroll (FICA) ──")
        click.echo(f"  Officer Salary:               ${fica.get('salary', 0):>10,.2f}")
        if fica:
            click.echo(f"  Employee FICA (withheld):     ${fica['employee']['total']:>10,.2f}")
            click.echo(f"  Employer FICA (expense):      ${fica['employer']['total']:>10,.2f}")
        click.echo(f"  Total FICA:                   ${fica.get('total_fica', 0):>10,.2f}")
        if form1120:
            click.echo(f"  ── 1120-S Income ──")
            click.echo(f"  1120-S Ordinary Income:       ${form1120.get('ordinary_income', 0):>10,.2f}")
            click.echo(f"    ↳ Officer salary:           ${form1120.get('officer_salary', 0):>10,.2f}")
            click.echo(f"    ↳ Employer payroll taxes:   ${form1120.get('employer_payroll_taxes', 0):>10,.2f}")
        click.echo(f"  ── Federal Income Tax ──")
        click.echo(f"  Taxable income (W-2 + K-1):   ${annual['federal_income_tax']['taxable_income']:>10,.2f}")
        click.echo(f"  Federal Income Tax:            ${annual['federal_income_tax']['income_tax']:>10,.2f}")
        click.echo(f"    ↳ Effective rate:            {annual['federal_income_tax']['effective_rate']:.1f}%")
    else:
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
    from .disclaimer import CLI_DISCLAIMER
    click.echo(CLI_DISCLAIMER)


@tax.command("schedule-c")
@_pass_config
def tax_schedule_c(ctx):
    """Generate Schedule C summary data for tax filing (SMLLC) or income data for S-Corp."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)

    ent_type = getattr(cfg, 'entity_type', 'smllc')
    if ent_type == "scorp":
        click.echo("═══ Schedule C (SMLLC) / Business Income Summary (S-Corp) ═══")
        click.echo("  ℹ  S-Corp uses Form 1120-S, not Schedule C. This summary")
        click.echo("     shows the raw revenue/expense data. Use 'llc tax estimate'")
        click.echo("     for the full S-Corp/1120-S tax projection.")
        click.echo()
    else:
        click.echo("═══ Schedule C Summary ═══")

    summary = taxer.schedule_c_summary()
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
    from .disclaimer import CLI_DISCLAIMER
    click.echo(CLI_DISCLAIMER)


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


@tax.command("form-1120s")
@click.option("--json", "as_json", is_flag=True, default=False,
              help="Output as JSON (for export/import into tax software)")
@click.option("--projected-income", "-i", type=float, default=None,
              help="Projected full-year net income (default: YTD * 2)")
@_pass_config
def tax_form_1120s(ctx, as_json, projected_income):
    """Generate Form 1120-S data for S-Corp tax filing.

    Shows gross receipts, officer compensation, payroll taxes,
    other deductions, and 1120-S ordinary business income.

    S-Corp mode only (entity_type = "scorp"). For SMLLC, use
    'llc tax schedule-c' instead.

    Examples:
        llc tax form-1120s
        llc tax form-1120s --json
        llc tax form-1120s --projected-income 120000
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    ent_type = getattr(cfg, 'entity_type', 'smllc')
    if ent_type != "scorp":
        click.echo("⚠  Form 1120-S is for S-Corp (entity_type='scorp').")
        click.echo("   Set entity_type = 'scorp' in config.toml [entity] section.")
        click.echo("   For SMLLC, use: llc tax schedule-c")
        return

    taxer = TaxEstimator(cfg, ledger, state_code=cfg.state_code)

    ytd_net = ledger.net_income()
    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        projection = ytd_net * Decimal("2")

    ytd_revenue = ledger.gross_revenue()
    projected_revenue = ytd_revenue * Decimal("2") if ytd_revenue > 0 else projection * Decimal("1.1")

    result = taxer.form_1120s_export(projection, total_revenue=projected_revenue)

    if as_json:
        import json
        # Convert Decimal to float for JSON
        def default_serializer(o):
            if isinstance(o, Decimal):
                return float(o)
            raise TypeError(f"Object of type {type(o)} is not JSON serializable")
        click.echo(json.dumps(result, indent=2, default=default_serializer))
        return

    income = result["income"]
    click.echo("═══ Form 1120-S — U.S. Income Tax Return for an S Corporation ═══")
    click.echo()
    click.echo(f"  Shareholder:                {result['shareholder']['name']} (100% owner)")
    click.echo()
    click.echo(f"  ── Income ──")
    click.echo(f"  Gross receipts (Line 1a):   ${income['gross_receipts']:>10,.2f}")
    click.echo()
    click.echo(f"  ── Deductions ──")
    click.echo(f"  Officer compensation:       ${income['officer_compensation']:>10,.2f}")
    click.echo(f"  Employer payroll taxes:     ${income['employer_payroll_taxes']:>10,.2f}")
    click.echo(f"  Other business expenses:    ${income['other_deductions']:>10,.2f}")
    click.echo(f"  ─────────────────────────────────────────────")
    click.echo(f"  Ordinary income (Line 21):  ${income['ordinary_income']:>10,.2f}")
    click.echo()
    click.echo(f"  ── Balance Sheet (Schedule L) ──")
    bs = result["balance_sheet"]
    click.echo(f"  Cash:                       ${bs['cash']:>10,.2f}")
    click.echo(f"  Accounts Receivable:        ${bs['accounts_receivable']:>10,.2f}")
    click.echo(f"  Total Assets:               ${bs['total_assets']:>10,.2f}")
    click.echo()
    click.echo(f"  ── K-1 (Shareholder) ──")
    click.echo(f"  Ordinary business income:   ${result['shareholder']['ordinary_income']:>10,.2f}")
    click.echo(f"  Ownership:                  {result['shareholder']['ownership_pct']}%")
    click.echo()
    from .disclaimer import CLI_DISCLAIMER
    click.echo(CLI_DISCLAIMER)


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
        0 9 * * * cd /path/to/sololedger && python -m app.main notify check
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


@receipt.command("attach")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--date", "-d", required=True, help="Transaction date (YYYY-MM-DD)")
@click.option("--account", "-a", default="Expenses:Miscellaneous",
              help="Beancount account (default: Expenses:Miscellaneous)")
@click.option("--no-txn", is_flag=True, default=False,
              help="Don't create a transaction entry, just attach the document")
@_pass_config
def receipt_attach(ctx, filepath, date, account, no_txn):
    """Attach a receipt PDF/image to the ledger as a permanent document.

    Copies the file to docs/receipts/YYYY/ and adds a Beancount
    document directive linking it to the specified account and date.
    Also scans the receipt and appends a transaction entry.
    """
    cfg = ctx["cfg"]
    try:
        from .receipts import ReceiptScanner
    except ImportError:
        click.echo("⚠  Receipt scanner not available.")
        return

    scanner = ReceiptScanner(cfg)
    result = scanner.attach(filepath, date=date, account=account,
                            link_txn=not no_txn)

    if result.get("success"):
        click.echo(f"✓ Receipt attached: {result['document_path']}")
        if result.get("transaction_appended"):
            click.echo("✓ Transaction entry appended to ledger.")
        click.echo("\n  Your receipt is now permanently linked to your ledger.")
        click.echo("  Run 'llc check' to verify.")
    else:
        click.echo(f"⚠  Failed: {result.get('error', 'unknown')}")


@receipt.command("list")
@click.option("--year", "-y", default="", help="Filter by year (YYYY)")
@_pass_config
def receipt_list(ctx, year):
    """List all receipt documents attached to the ledger."""
    cfg = ctx["cfg"]
    try:
        from .receipts import ReceiptScanner
    except ImportError:
        click.echo("⚠  Receipt scanner not available.")
        return

    scanner = ReceiptScanner(cfg)
    docs = scanner.list_attached(year=year)

    if not docs:
        click.echo("No receipt documents attached yet.")
        click.echo("Use 'llc receipt attach' to link receipts to your ledger.")
        return

    click.echo(f"{'Date':12s} {'Account':35s} Document")
    click.echo("-" * 80)
    for d in docs:
        name = Path(d["path"]).name
        click.echo(f"{d['date']:12s} {d['account']:35s} {name}")
    click.echo(f"\nTotal: {len(docs)} document(s)")


# ── payroll (S-Corp) ──────────────────────────────────────────────────────


@cli.group()
def payroll():
    """Import payroll from Gusto CSV and manage S-Corp payroll entries.

    S-Corp mode only. Requires entity_type = "scorp" in config.toml.
    """


@payroll.command("import")
@click.argument("csv_file", type=click.Path(exists=True))
@click.option("--preview", is_flag=True, help="Preview only, don't import")
@_pass_config
def payroll_import(ctx, csv_file, preview):
    """Import a Gusto payroll CSV export into the ledger.

    Creates the full payroll journal entry: gross wages, employee
    withholdings, employer taxes, and net pay payable.

    Example:
        llc payroll import gusto-payroll.csv --preview
        llc payroll import gusto-payroll.csv
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        from .payroll import PayrollImporter
    except ImportError:
        click.echo("⚠  Payroll module not available.")
        return

    importer = PayrollImporter(cfg, ledger)

    click.echo("═══ Payroll Import ═══")
    click.echo()

    results = importer.import_gusto_csv(csv_file, preview=preview)

    total_gross = 0
    total_net = 0
    total_er = 0
    imported = 0
    errors = 0

    for r in results:
        if "error" in r:
            click.echo(f"  ✗ {r.get('employee', '?')}: {r['error']}")
            errors += 1
            continue
        if r.get("skipped"):
            click.echo(f"  – {r.get('employee', '?')}: {r.get('error', 'skipped')}")
            continue

        total_gross += r["gross"]
        total_net += r["net"]
        total_er += r["total_employer_taxes"]
        imported += 1

        click.echo(f"  {r['date']}  {r['employee']:<25s}  "
                    f"Gross: ${r['gross']:>8,.2f}  "
                    f"Net: ${r['net']:>8,.2f}  "
                    f"ER taxes: ${r['total_employer_taxes']:>6,.2f}")

    click.echo()
    click.echo(f"  Imported: {imported} pay period(s)")
    click.echo(f"  Total gross pay:       ${total_gross:>10,.2f}")
    click.echo(f"  Total net pay:         ${total_net:>10,.2f}")
    click.echo(f"  Total employer taxes:  ${total_er:>10,.2f}")

    if preview and imported > 0:
        click.echo()
        click.echo("(Preview — run without --preview to import)")

    if errors:
        click.echo(f"  Errors: {errors}")


@payroll.command("disburse")
@click.option("--date", "-d", required=True, help="Disbursement date (YYYY-MM-DD)")
@click.option("--amount", "-a", required=True, type=float, help="Net pay amount to disburse")
@click.option("--bank", default=None, help="Bank account (default: from config)")
@click.option("--preview", is_flag=True, help="Preview only")
@_pass_config
def payroll_disburse(ctx, date, amount, bank, preview):
    """Record the net pay disbursement from business bank to owner.

    After importing a payroll run with 'llc payroll import', the net
    pay accumulates in Liabilities:PayrollPayable. This command records
    the actual transfer of net pay from your business account to the
    owner.

    Example:
        llc payroll disburse --date 2026-01-31 --amount 3461.54
    """
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        from .payroll import PayrollImporter
    except ImportError:
        click.echo("⚠  Payroll module not available.")
        return

    importer = PayrollImporter(cfg, ledger)

    try:
        pay_date = datetime.date.fromisoformat(date)
    except ValueError:
        click.echo(f"⚠  Invalid date: {date}. Use YYYY-MM-DD format.")
        return

    result = importer.payroll_disburse(
        pay_date=pay_date,
        net_pay=Decimal(str(amount)),
        bank_account=bank,
        preview=preview,
    )

    click.echo(f"Payroll disbursement: ${result['net_pay']:,.2f}")
    click.echo(f"  Bank account:  {result['bank_account']}")
    click.echo(f"  Date:          {result['date']}")

    if preview:
        click.echo("(Preview — run without --preview to record)")
    else:
        click.echo("✓ Recorded in ledger.")


# ── reconciliation ─────────────────────────────────────────────────────────


@cli.group()
def reconcile():
    """Reconcile ledger against bank statements.

    Helps you match your Beancount transactions to your bank
    statement each month. Lists uncleared items and flags
    completed reconciliations.
    """


@reconcile.command("list")
@click.option("--account", default="Assets:Bank:BusinessChecking",
              help="Account to check (default: from config)")
@click.option("--days", type=int, default=365,
              help="How far back to look (default: 365 days)")
@_pass_config
def reconcile_list(ctx, account, days):
    """Show uncleared/pending transactions for an account."""
    from .reconciliation import Reconciliation

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    rec = Reconciliation(cfg, ledger)
    txs = rec.uncleared_transactions(account=account, days_back=days)

    if not txs:
        click.echo("No transactions found for this account.")
        return

    cleared = [t for t in txs if t["status"] == "cleared"]
    uncleared = [t for t in txs if t["status"] == "uncleared"]

    click.echo(f"Account: {account}")
    click.echo(f"  Cleared:   {len(cleared)} transactions")
    click.echo(f"  Uncleared: {len(uncleared)} transactions")
    click.echo()

    if uncleared:
        click.echo(f"{'Date':12s} {'Type':8s} {'Amount':10s}  Payee")
        click.echo("-" * 65)
        for t in uncleared[:30]:
            click.echo(f"{t['date']:12s} {t['type']:8s} ${t['amount']:<8.2f}  {t['payee'][:40]}")
        if len(uncleared) > 30:
            click.echo(f"  ... and {len(uncleared) - 30} more")


@reconcile.command("start")
@click.option("--date", "-d", required=True, help="Statement date (YYYY-MM-DD)")
@click.option("--balance", "-b", type=float, required=True,
              help="Ending balance from bank statement")
@click.option("--account", default="Assets:Bank:BusinessChecking",
              help="Account being reconciled")
@_pass_config
def reconcile_start(ctx, date, balance, account):
    """Start a reconciliation by asserting a statement balance.

    Compares your ledger to the bank statement balance and
    records a balance assertion in the Beancount ledger.
    """
    from decimal import Decimal
    from .reconciliation import Reconciliation

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    rec = Reconciliation(cfg, ledger)
    result = rec.start(date=date, balance=Decimal(str(balance)),
                       account=account)

    click.echo(f"Reconciliation: {result['date']}")
    click.echo(f"  Account:       {result['account']}")
    click.echo(f"  Balance:       ${result['balance']:,.2f}")
    click.echo(f"  Matched:       {result['cleared_transactions']} txns")
    click.echo(f"  Still open:    {result['uncleared_transactions']} txns")
    if result['uncleared_transactions'] > 0:
        click.echo("\n  Run 'llc reconcile list' to review uncleared items.")


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
    ent_type = getattr(cfg, 'entity_type', 'smllc')
    click.echo(f"  {'✅' if ent_type in ('smllc','scorp') else '⚠️'}  Entity type:  {ent_type}")
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
    click.echo(f"  ▸  Docs:       https://github.com/dilljens/sololedger#readme")
    click.echo(f"  ▸  Cloud:      https://sololedger.ferrumeng.com")


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


# ── backup ────────────────────────────────────────────────────────────────


@cli.command()
@click.option("--quiet", is_flag=True, help="Suppress output (for cron)")
@click.option("--status", "show_status", is_flag=True, help="Show changes without committing")
@_pass_config
def backup(ctx, quiet, show_status):
    """Auto-backup ledger changes to git.

    Designed for cron: commits ledger/ and config.toml changes,
    then pushes to the remote if configured.

    Examples:
        llc backup                           # Commit + push
        llc backup --quiet                   # Silent (for cron)
        llc backup --status                  # Show pending changes
    """
    cfg = ctx["cfg"]
    from .backup import Backup
    b = Backup(cfg)

    if show_status:
        changes = b.status()
        if changes:
            click.echo(f"Uncommitted changes ({len(changes)}):")
            for c in changes:
                click.echo(f"  {c['status']}  {c['path']}")
        else:
            click.echo("✓ No uncommitted changes.")
        return

    result = b.commit(quiet=quiet)
    if not result["committed"] and not quiet:
        click.echo("✓ Nothing to back up.")


# ── reports ───────────────────────────────────────────────────────────────


@cli.group()
def report():
    """Generate financial reports and exports."""


@report.command("expenses")
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@click.option("--format", "output_format", type=click.Choice(["table", "csv"]), default="table",
              help="Output format: table (CLI) or csv (export)")
@_pass_config
def report_expenses(ctx, year, output_format):
    """Show expense summary or export as CSV."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from .reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)

    if output_format == "csv":
        csv_data = rg.expenses_csv(year=year)
        click.echo(csv_data)
        return

    summary = rg.expenses_summary(year=year)
    if not summary:
        click.echo("No expenses found.")
        return

    year_label = year or "All time"
    total = sum(s["amount"] for s in summary)

    click.echo(f"═══ Expenses ({year_label}) ═══")
    click.echo()
    for s in summary:
        short = s["category"].replace("Expenses:", "")
        click.echo(f"  {short:<40s}  ${s['amount']:>8,.2f}  ({s['count']} txns)")
    click.echo(f"  {'─' * 40}")
    click.echo(f"  {'Total':<40s}  ${total:>8,.2f}")


@report.command("profit-loss")
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@_pass_config
def report_pl(ctx, year):
    """Show profit and loss summary."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from .reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)

    pl = rg.profit_loss(year=year)
    click.echo(f"═══ Profit & Loss ({pl['year']}) ═══")
    click.echo()
    click.echo(f"  Income:             ${pl['income']:>10,.2f}")
    click.echo(f"  Total Expenses:     ${pl['expenses']:>10,.2f}")
    for e in pl.get("expense_breakdown", []):
        short = e["category"].replace("Expenses:", "")
        click.echo(f"    {short:<35s}  ${e['amount']:>8,.2f}")
    click.echo(f"  {'─' * 45}")
    click.echo(f"  Net Profit:         ${pl['net_profit']:>10,.2f}")


# ── import ────────────────────────────────────────────────────────────────


@cli.group()
def import_cmd():
    """Import transactions from other tools (Wave, QuickBooks, CSV)."""


@import_cmd.command("wave")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--preview", is_flag=True, help="Preview only")
@_pass_config
def import_wave(ctx, filepath, preview):
    """Import transactions from a Wave Accounting CSV export."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from .importer import Importer
    imp = Importer(cfg, ledger)
    results = imp.import_wave_csv(filepath, preview=preview)

    if results and "error" in results[0]:
        click.echo(f"⚠ {results[0]['error']}")
        return

    click.echo(f"Imported {len(results)} transactions from Wave CSV.")
    for r in results:
        click.echo(f"  {r['date']}  {r['description'][:40]:40s}  ${abs(r['amount']):>8,.2f}  → {r['account']}")


@import_cmd.command("qbo")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--preview", is_flag=True, help="Preview only")
@_pass_config
def import_qbo(ctx, filepath, preview):
    """Import transactions from a QuickBooks Online CSV export."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from .importer import Importer
    imp = Importer(cfg, ledger)
    results = imp.import_qbo_csv(filepath, preview=preview)

    if results and "error" in results[0]:
        click.echo(f"⚠ {results[0]['error']}")
        return

    click.echo(f"Imported {len(results)} transactions from QBO CSV.")


@import_cmd.command("csv")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--preview", is_flag=True, help="Preview only")
@_pass_config
def import_csv_generic(ctx, filepath, preview):
    """Import transactions from a generic CSV (Date, Description, Amount)."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    from .importer import Importer
    imp = Importer(cfg, ledger)
    results = imp.import_csv(filepath, preview=preview)

    if results and "error" in results[0]:
        click.echo(f"⚠ {results[0]['error']}")
        return

    click.echo(f"Imported {len(results)} transactions from CSV.")


# ── stripe sync ───────────────────────────────────────────────────────────


@cli.group()
def stripe():
    """Manage Stripe payments and sync payment status."""


@stripe.command("sync")
@click.option("--since", default=None, help="Start date (YYYY-MM-DD)")
@click.option("--preview", is_flag=True, help="Preview only")
@_pass_config
def stripe_sync(ctx, since, preview):
    """Sync completed Stripe payments and reconcile with invoices.

    Fetches completed checkout sessions from Stripe and records
    payments that haven't been recorded yet.
    """
    import os
    api_key = os.environ.get("STRIPE_SECRET_KEY", "")
    if not api_key:
        click.echo("⚠  STRIPE_SECRET_KEY not set.")
        return

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    try:
        import stripe as stripe_lib
        stripe_lib.api_key = api_key
    except ImportError:
        click.echo("⚠  stripe Python package not installed.")
        return

    # Fetch completed checkout sessions
    params = {"limit": 100}
    if since:
        params["created"] = {"gte": int(datetime.date.fromisoformat(since).timestamp())}

    try:
        sessions = stripe_lib.checkout.Session.list(**params)
    except Exception as e:
        click.echo(f"⚠  Stripe API error: {e}")
        return

    completed = [s for s in sessions if s.payment_status == "paid"]
    click.echo(f"Found {len(completed)} completed payment(s)")

    if preview:
        for s in completed[:10]:
            meta = s.get("metadata", {}) or {}
            inv = meta.get("invoice_number", "unknown")
            amt = (s.amount_total or 0) / 100
            click.echo(f"  {s.id[:15]:15s}  ${amt:>8,.2f}  invoice={inv}")
        if len(completed) > 10:
            click.echo(f"  ... and {len(completed) - 10} more")
        click.echo()
        click.echo("Run without --preview to record these payments.")
        return

    # Record payments
    from decimal import Decimal
    recorded = 0
    skipped = 0

    # Get existing payment IDs from ledger to avoid duplicates
    existing_ids = set()
    for entry in ledger.entries:
        if hasattr(entry, "narration") and "Stripe payment" in entry.narration:
            existing_ids.add(entry.narration)

    for session in completed:
        payment_id = session.id or ""
        meta = session.get("metadata", {}) or {}
        inv_num = meta.get("invoice_number", "")
        client = meta.get("client", "Stripe Payment")
        amt = Decimal(str(session.amount_total or 0)) / Decimal("100")

        # Check if already recorded
        if any(payment_id in eid for eid in existing_ids):
            skipped += 1
            continue

        postings = [
            (cfg.checking_account, f"{amt:.2f} USD"),
            (cfg.ar_account, f"-{amt:.2f} USD"),
        ]
        ledger.append(
            date=datetime.date.today(),
            payee=f"Stripe — {client}",
            narration=f"Stripe payment {payment_id} for invoice {inv_num}",
            postings=postings,
        )
        recorded += 1

    click.echo(f"Recorded: {recorded}, Skipped (already in ledger): {skipped}")


# ── marketing automation ──────────────────────────────────────────────────


@cli.group()
def marketing():
    """Generate marketing content (changelog, blog, social posts) from git history.

    Requires OPENAI_API_KEY or ANTHROPIC_API_KEY env var for AI-powered content.
    Without it, generates template drafts you can fill in manually.
    """


@marketing.command("generate")
@click.option("--days", type=int, default=30, help="Days of git history to include")
@click.option("--output", "-o", default=None, help="Output directory (default: ./marketing/)")
@_pass_config
def marketing_generate(ctx, days, output):
    """Generate all marketing content: changelog, blog post, social media posts."""
    cfg = ctx["cfg"]
    from .marketing import MarketingGenerator
    gen = MarketingGenerator(repo_path=str(cfg.project_root))

    if gen.api_key:
        click.echo(f"Using {gen.provider.title()} for content generation...")
    else:
        click.echo("⚠  No LLM API key found. Generating template drafts.")
        click.echo("   Set OPENAI_API_KEY or ANTHROPIC_API_KEY for AI-powered content.")
        click.echo()

    result = gen.save_to_files(days=days, output_dir=output)
    click.echo(f"✓ Generated marketing content to: {result['output_dir']}")
    for f in result["files"]:
        click.echo(f"  · {f}")
    click.echo()
    click.echo("Review and edit before posting. LLMs can make mistakes.")


@marketing.command("changelog")
@click.option("--days", type=int, default=30)
@_pass_config
def marketing_changelog(ctx, days):
    """Generate just the changelog."""
    cfg = ctx["cfg"]
    from .marketing import MarketingGenerator
    gen = MarketingGenerator(repo_path=str(cfg.project_root))
    result = gen.generate_changelog(days=days)
    click.echo(result)


@marketing.command("blog")
@click.option("--days", type=int, default=30)
@_pass_config
def marketing_blog(ctx, days):
    """Generate just the blog post draft."""
    cfg = ctx["cfg"]
    from .marketing import MarketingGenerator
    gen = MarketingGenerator(repo_path=str(cfg.project_root))
    result = gen.generate_blog_post(days=days)
    click.echo(result)


@marketing.command("social")
@click.option("--days", type=int, default=30)
@_pass_config
def marketing_social(ctx, days):
    """Generate just the social media posts."""
    cfg = ctx["cfg"]
    from .marketing import MarketingGenerator
    gen = MarketingGenerator(repo_path=str(cfg.project_root))
    result = gen.generate_social_posts(days=days)
    if isinstance(result, dict):
        for platform, content in result.items():
            click.echo(f"\n═══ {platform.upper()} ═══\n")
            click.echo(content)
    else:
        click.echo(result)


# ── ofx import ─────────────────────────────────────────────────────────────


@import_cmd.command("ofx")
@click.argument("filepath", type=click.Path(exists=True))
@click.option("--account", default=None, help="Target bank account (default: from config)")
@click.option("--preview", is_flag=True, help="Parse but don't import")
@_pass_config
def import_ofx(ctx, filepath, account, preview):
    """Import transactions from an OFX/QFX bank statement."""
    from .ofx_import import OfxImporter

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    importer = OfxImporter(cfg, ledger)
    result = importer.import_file(
        filepath,
        account=account or cfg.checking_account,
        preview=preview,
    )
    click.echo(f"File: {result['file']}")
    click.echo(f"  Total transactions:     {result['total']}")
    click.echo(f"  Imported:               {result['imported']}")
    click.echo(f"  Skipped (duplicates):   {result['skipped_duplicates']}")
    if result["errors"]:
        click.echo(f"  Errors:                 {len(result['errors'])}")
    if not preview:
        click.echo(f"\nRun 'llc check' to verify the ledger.")


# ── mileage tracking ───────────────────────────────────────────────────────


@cli.group()
def mileage():
    """Track business mileage for tax deductions."""


@mileage.command("add")
@click.option("--date", "-d", required=True, help="Trip date (YYYY-MM-DD)")
@click.option("--miles", "-m", type=float, required=True, help="Miles driven")
@click.option("--purpose", "-p", required=True, help="Business purpose")
@click.option("--client", "-c", default="", help="Client name")
@click.option("--start-odo", type=float, default=0.0, help="Starting odometer")
@click.option("--end-odo", type=float, default=0.0, help="Ending odometer")
@click.option("--route", default="", help="Start → end description")
@click.option("--notes", default="", help="Additional notes")
@click.option("--no-post", is_flag=True, help="Don't post to Beancount ledger")
@_pass_config
def mileage_add(ctx, date, miles, purpose, client, start_odo, end_odo, route, notes, no_post):
    """Log a business trip and calculate the IRS mileage deduction."""
    from .mileage import MileageTracker

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    tracker = MileageTracker(cfg, ledger)
    trip = tracker.add_trip(
        date=date, miles=miles, purpose=purpose,
        client=client, start_odo=start_odo, end_odo=end_odo,
        route=route, notes=notes,
        post_to_ledger=not no_post,
    )
    click.echo(f"Trip logged: {trip.date} — {purpose} ({miles} mi)")
    click.echo(f"  Deduction: ${float(trip.deduction):.2f}")
    click.echo(f"  Receipt:   {trip.id}")
    if not no_post:
        click.echo("  Posted to Beancount ledger.")


@mileage.command("list")
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@click.option("--limit", type=int, default=50, help="Max results")
@_pass_config
def mileage_list(ctx, year, limit):
    """List logged trips."""
    from .mileage import MileageTracker

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    tracker = MileageTracker(cfg, ledger)
    trips = tracker.list_trips(year=year, limit=limit)

    if not trips:
        click.echo("No trips logged.")
        return

    click.echo(f"{'Date':12s} {'Miles':8s} {'Deduction':10s}  Purpose")
    click.echo("-" * 60)
    total_miles = 0
    total_deduction = 0.0
    for t in trips:
        click.echo(f"{t['date']:12s} {t['miles']:<8.1f} ${t['deduction']:<8.2f}  {t['purpose'][:35]}")
        total_miles += t['miles']
        total_deduction += t['deduction']
    click.echo("-" * 60)
    click.echo(f"{'TOTAL':12s} {total_miles:<8.1f} ${total_deduction:<8.2f}")


@mileage.command("report")
@click.option("--year", "-y", type=int, default=None, help="Year (default: current)")
@_pass_config
def mileage_report(ctx, year):
    """Show yearly mileage summary for tax purposes."""
    from .mileage import MileageTracker, get_irs_rate

    if year is None:
        year = datetime.date.today().year

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    tracker = MileageTracker(cfg, ledger)
    report = tracker.yearly_report(year)
    rate = get_irs_rate(year)

    click.echo(f"Mileage Report — {year}")
    click.echo(f"  Rate:              ${float(rate):.2f}/mi")
    click.echo(f"  Total trips:       {report['trip_count']}")
    click.echo(f"  Total miles:       {report['total_miles']:.1f}")
    click.echo(f"  Total deduction:   ${report['total_deduction']:.2f}")
    click.echo()

    if report["monthly_breakdown"]:
        click.echo("  Monthly breakdown:")
        for month, miles in sorted(report["monthly_breakdown"].items()):
            click.echo(f"    {month}: {miles:.1f} mi")

    if report["trips_by_purpose"]:
        click.echo("\n  By purpose:")
        for purpose, miles in sorted(report["trips_by_purpose"].items(), key=lambda x: -x[1]):
            click.echo(f"    {purpose[:40]:40s} {miles:.1f} mi")


@mileage.command("export")
@click.argument("output", type=click.Path())
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@_pass_config
def mileage_export(ctx, output, year):
    """Export mileage log to CSV."""
    from .mileage import MileageTracker

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    tracker = MileageTracker(cfg, ledger)
    path = tracker.export_csv(output, year=year)
    click.echo(f"Exported to {path}")


# ── llm categorization ─────────────────────────────────────────────────────


@cli.command()
@click.option("--merchant", "-m", required=True, help="Transaction merchant name")
@click.option("--amount", "-a", type=float, default=None, help="Transaction amount")
@_pass_config
def categorize(ctx, merchant, amount):
    """Categorize a transaction using the LLM assistant.

    Requires SL_LLM_BACKEND to be set (ollama, openai, or anthropic).
    """
    from .categorizer_llm import LlmCategorizer
    from .ledger import Ledger

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]

    full_merchant = f"{merchant} ${amount:.2f}" if amount else merchant

    # Gather context
    accounts = []
    try:
        # Get all accounts from the ledger
        for entry in ledger._entries or []:
            from beancount.core.data import Open
            if isinstance(entry, Open):
                accounts.append(entry.account)
    except Exception:
        pass

    similar = []
    try:
        # Try the categorizer for similar past transactions
        from .categorizer import Categorizer
        cat = Categorizer(cfg)
        for rule in cat.all_rules()[:10]:
            similar.append({
                "merchant": rule["merchant"],
                "account": rule["account"],
                "count": rule["count"],
            })
        cat2 = Categorizer(cfg, use_patterns=True, use_embedding=True)
        suggestion = cat2.suggest(merchant)
        if suggestion:
            click.echo(f"  Local suggestion: {suggestion}")
    except Exception:
        pass

    llm = LlmCategorizer(cfg)

    if not llm.available:
        click.echo("LLM categorization is not configured.")
        click.echo("Set SL_LLM_BACKEND=ollama|openai|anthropic and SL_LLM_API_KEY if needed")
        click.echo()
        click.echo("Quick start with Ollama:")
        click.echo("  # Install Ollama: https://ollama.com")
        click.echo("  ollama pull gemma3:1b")
        click.echo("  export SL_LLM_BACKEND=ollama")
        click.echo("  export SL_LLM_MODEL=gemma3:1b")
        return

    result = llm.suggest(full_merchant, similar=similar, accounts=accounts)

    if result.get("account"):
        click.echo(f"  Merchant:    {merchant}")
        click.echo(f"  Suggested:   {result['account']}")
        click.echo(f"  Confidence:  {result.get('confidence', 0):.2f}")
        click.echo(f"  Reasoning:   {result.get('reasoning', '')[:200]}")
        click.echo(f"  Model:       {result.get('model', '?')}")
    else:
        click.echo("  No suggestion from LLM.")
        if result.get("reasoning"):
            click.echo(f"  {result['reasoning']}")


# ── transfer / reimburse / split ────────────────────────────────────────────


@cli.group()
def transfer():
    """Move money between accounts (owner draws, account transfers)."""


@transfer.command("to-personal")
@click.option("--amount", "-a", type=float, required=True, help="Amount to transfer")
@click.option("--from", "-f", "from_acct", default=None, help="Source account (default: checking)")
@click.option("--note", "-n", default="", help="Optional note")
@_pass_config
def transfer_to_personal(ctx, amount, from_acct, note):
    """Move money from business to personal (owner draw)."""
    from decimal import Decimal

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    source = from_acct or cfg.checking_account
    desc = note or f"Owner draw — ${amount:,.2f}"
    result = ledger.transfer(
        date=datetime.date.today(),
        from_account=source,
        to_account="Assets:Bank:Personal",
        amount=Decimal(str(amount)),
        description=desc,
    )
    click.echo(f"✓ Transferred ${amount:,.2f} to personal account")
    click.echo("  Entry appended to ledger.")


@transfer.command("between")
@click.option("--amount", "-a", type=float, required=True, help="Amount")
@click.option("--from", "-f", required=True, help="Source account name (e.g. Assets:Bank:BusinessChecking)")
@click.option("--to", "-t", required=True, help="Destination account")
@click.option("--note", "-n", default="Transfer", help="Description")
@_pass_config
def transfer_between(ctx, amount, from_acct, to, note):
    """Transfer between any two accounts."""
    from decimal import Decimal

    ledger = ctx["ledger"]
    result = ledger.transfer(
        date=datetime.date.today(),
        from_account=from_acct,
        to_account=to,
        amount=Decimal(str(amount)),
        description=note,
    )
    click.echo(f"✓ Transferred ${amount:,.2f}: {from_acct} → {to}")


@cli.command()
@click.option("--amount", "-a", type=float, required=True, help="Expense amount")
@click.option("--merchant", "-m", required=True, help="Merchant name")
@click.option("--account", default="Expenses:Miscellaneous",
              help="Expense account (default: Expenses:Miscellaneous)")
@click.option("--date", "-d", default=None, help="Date (YYYY-MM-DD, default: today)")
@_pass_config
def reimburse(ctx, amount, merchant, account, date):
    """Record a business expense that was paid from personal funds.

    Use this when you bought something for the business using your
    personal credit card or cash. The business owes you.
    """
    from decimal import Decimal

    ledger = ctx["ledger"]
    txn_date = datetime.date.fromisoformat(date) if date else datetime.date.today()
    result = ledger.reimbursement(
        date=txn_date,
        merchant=merchant,
        amount=Decimal(str(amount)),
        expense_account=account,
    )
    click.echo(f"✓ Reimbursement recorded: {merchant} — ${amount:,.2f}")
    click.echo(f"  Account: {account}")
    click.echo(f"  The business now owes you ${amount:,.2f}")
    click.echo("  Run 'llc transfer to-personal' when you want to repay yourself.")


@cli.command()
@click.option("--merchant", "-m", required=True, help="Merchant name")
@click.option("--total", "-t", type=float, required=True, help="Total charge amount")
@click.option("--business", "-b", type=float, required=True,
              help="Business portion of the total")
@click.option("--account", default="Expenses:Miscellaneous",
              help="Account for business portion")
@click.option("--date", "-d", default=None, help="Date (YYYY-MM-DD, default: today)")
@click.option("--source", default=None,
              help="Source account the charge came from (default: checking)")
@_pass_config
def split_expense(ctx, merchant, total, business, account, date, source):
    """Split a transaction between business and personal.

    Use when a single charge (e.g., Amazon order) has both
    business and personal items on it.
    """
    from decimal import Decimal

    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    txn_date = datetime.date.fromisoformat(date) if date else datetime.date.today()
    src = source or cfg.checking_account
    personal = total - business

    if personal > 0:
        postings = [
            (account, f"{business:.2f} USD"),
            ("Equity:OwnerDraws", f"{personal:.2f} USD"),
        ]
    else:
        postings = [
            (account, f"{total:.2f} USD"),
        ]

    result = ledger.append(
        date=txn_date,
        payee=merchant,
        narration=f"Split: {merchant} (${business:.2f} business, ${personal:.2f} personal)",
        postings=[
            (account, f"{business:.2f} USD"),
            ("Equity:OwnerDraws", f"{personal:.2f} USD"),
            (src, f"-{total:.2f} USD"),
        ],
    )
    click.echo(f"✓ Split recorded: {merchant}")
    click.echo(f"  Total:    ${total:,.2f}")
    click.echo(f"  Business: ${business:,.2f} → {account}")
    click.echo(f"  Personal: ${personal:,.2f} → OwnerDraws")


# ── entry point ───────────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
