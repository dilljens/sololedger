#!/usr/bin/env python3
"""llc — CLI for managing your Wyoming Consulting LLC.

Usage:
    llc status               → dashboard: cash, P&L, deadlines
    llc invoice create       → create a new invoice (+ PDF)
    llc invoice list         → list all invoices
    llc expense import FILE  → import a bank CSV
    llc tax estimate         → estimated quarterly tax payment
    llc tax schedule-c       → Schedule C summary at year-end
    llc tax deadlines        → upcoming tax deadlines
    llc check                → verify ledger integrity
"""

import datetime
import sys
from decimal import Decimal
from pathlib import Path

import click

from .config import Config
from .ledger import Ledger
from .invoice import Invoicer
from .taxes import TaxEstimator
from .expenses import ExpenseImporter

# ── shared initialization ────────────────────────────────────────────────

_pass_config = click.make_pass_decorator(dict, ensure=True)


@click.group()
@click.option("--config", "-c", default=None, help="Path to config.toml")
@click.version_option(version="0.1.0")
@_pass_config
def cli(ctx, config):
    """Wyoming LLC — accounting, invoicing, and tax tools."""
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
    click.echo("═══ Wyoming LLC Dashboard ═══")
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
    taxer = TaxEstimator(cfg, ledger)
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
@_pass_config
def invoice_create(ctx, client, description, amount, date, no_pdf):
    """Create a new invoice and record it in the ledger."""
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
    )

    click.echo(f"✓ Invoice {result['number']} created")
    click.echo(f"  Client:     {client}")
    click.echo(f"  Amount:     ${amount:,.2f}")
    click.echo(f"  Date:       {result['date']}")
    if "pdf_path" in result:
        click.echo(f"  PDF:        {result['pdf_path']}")


@invoice.command("list")
@click.option("--year", "-y", type=int, default=None, help="Filter by year")
@_pass_config
def invoice_list(ctx, year):
    """List all invoices."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    invoicer = Invoicer(cfg, ledger)

    invoices = invoicer.list(year)

    if not invoices:
        click.echo("No invoices found.")
        return

    click.echo(f"{'Date':<12} {'Client':<25} {'Amount':>10} {'Description'}")
    click.echo("-" * 70)
    for inv in invoices:
        click.echo(f"{str(inv['date']):<12} {inv['client']:<25} ${inv['amount']:>7,.2f} {inv['description'][:30]}")
    click.echo(f"\nTotal: {len(invoices)} invoices")


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
@_pass_config
def tax_estimate(ctx, projected_income):
    """Calculate estimated quarterly tax payment."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    taxer = TaxEstimator(cfg, ledger)

    ytd_net = ledger.net_income()

    if projected_income:
        projection = Decimal(str(projected_income))
    else:
        # Simple projection: YTD * 2 (assume same rest of year)
        projection = ytd_net * Decimal("2")

    if ytd_net <= 0:
        click.echo("⚠  No net profit yet. No tax estimated.")
        return

    # Full annual estimate
    annual = taxer.total_projected_tax(projection)
    quarterly = taxer.quarterly_estimate(ytd_net, projection)

    click.echo("═══ Tax Estimate (Single-Member LLC — Wyoming) ═══")
    click.echo()
    click.echo(f"  YTD Net Profit:                ${ytd_net:>10,.2f}")
    click.echo(f"  Projected Annual Net:          ${projection:>10,.2f}")
    click.echo()
    click.echo(f"  Self-Employment Tax (15.3%):   ${annual['self_employment_tax']['total_se_tax']:>10,.2f}")
    click.echo(f"    ↳ Deductible half (AGI):     ${annual['self_employment_tax']['deductible_half']:>10,.2f}")
    click.echo(f"  Federal Income Tax:            ${annual['federal_income_tax']['income_tax']:>10,.2f}")
    click.echo(f"    ↳ Taxable income:            ${annual['federal_income_tax']['taxable_income']:>10,.2f}")
    click.echo(f"    ↳ Effective rate:            {annual['federal_income_tax']['effective_rate']:.1f}%")
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
    taxer = TaxEstimator(cfg, ledger)

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
    """Show upcoming tax deadlines."""
    cfg = ctx["cfg"]
    ledger = ctx["ledger"]
    taxer = TaxEstimator(cfg, ledger)

    info = taxer.deadline_info()

    click.echo(f"Tax deadlines (as of {info['as_of']}):")
    for d in info["deadlines"]:
        icon = {
            "overdue": "🔴 OVERDUE",
            "upcoming": "🟡 UPCOMING",
            "ahead": "🟢",
        }.get(d["status"], "🟢")

        click.echo(f"  {icon}  {d['label']}: {d['due']}  ({d['days_until']:>+4d} days)")


# ── entry point ───────────────────────────────────────────────────────────


def main():
    cli()


if __name__ == "__main__":
    main()
