"""Create invoices: record in ledger + generate PDF + Stripe payment links + recurring."""

import calendar
import datetime
import json
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Optional

from jinja2 import Environment, FileSystemLoader, select_autoescape

from .config import Config
from .ledger import Ledger

# Lazy-import StripePayments to avoid breaking if stripe isn't installed
_stripe_payments = None


def _get_stripe():
    global _stripe_payments
    if _stripe_payments is None:
        try:
            from .payments import StripePayments
            _stripe_payments = StripePayments()
        except ImportError:
            payments_mod = __import__("app.payments", fromlist=["StripePayments"])
            _stripe_payments = payments_mod.StripePayments()
    return _stripe_payments


@dataclass
class RetainerConfig:
    """Configuration for a recurring retainer invoice."""
    client: str
    description: str
    amount: Decimal
    interval: str  # 'monthly', 'quarterly', 'yearly'
    day_of_month: int = 1
    stripe_recurring: bool = False
    template: Optional[str] = None  # Custom description template


class Invoicer:
    """Generate invoices and record them in the ledger."""

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger

    def create(
        self,
        client: str,
        description: str,
        amount: Decimal,
        invoice_date: datetime.date | None = None,
        due_days: int = 30,
        invoice_number: str | None = None,
        generate_pdf: bool = True,
        payment_link: bool = False,
        client_email: str | None = None,
        recurring: str | None = None,
    ) -> dict:
        """Create an invoice: record income, generate PDF, optionally add Stripe payment link.

        Args:
            client: Client/business name
            description: What the invoice is for
            amount: Invoice amount in dollars
            invoice_date: Date of invoice (default: today)
            due_days: Payment due in N days (default: 30)
            invoice_number: Custom invoice number (default: auto-generated)
            generate_pdf: Generate PDF invoice (default: True)
            payment_link: Create Stripe payment link (default: False)
            client_email: Client email for Stripe payment link prefill
            recurring: If set, create a recurring/subscription link: 'month', 'year'

        Returns:
            dict with invoice metadata including payment_link if created
        """
        date = invoice_date or datetime.date.today()
        due = date + datetime.timedelta(days=due_days)
        num = invoice_number or self._next_number(date)

        # 1. Record in Beancount ledger
        postings = [
            (self.cfg.income_account, f"-{amount:.2f} USD"),
            (self.cfg.ar_account, f"{amount:.2f} USD"),
        ]
        self.ledger.append(date, client, description, postings)

        result = {
            "number": num,
            "date": date.isoformat(),
            "due": due.isoformat(),
            "client": client,
            "description": description,
            "amount": amount,
            "status": "recorded",
        }

        # 2. Generate Stripe payment link (before PDF so we can embed the URL)
        stripe_url = None
        if payment_link:
            sp = _get_stripe()
            if sp.enabled:
                if recurring:
                    link_result = sp.create_recurring_link(
                        amount=amount,
                        description=f"{description} ({client})",
                        interval=recurring,
                        invoice_number=num,
                    )
                else:
                    link_result = sp.create_payment_link(
                        amount=amount,
                        description=f"{description} ({client})",
                        invoice_number=num,
                        client_email=client_email,
                        metadata={"client": client, "invoice": num},
                    )
                if link_result.get("url"):
                    stripe_url = link_result["url"]
                    result["payment_url"] = stripe_url
                    result["payment_id"] = link_result["id"]
                    result["status"] = "recorded+payment_link"

        # 3. Generate PDF (with payment link if we have one)
        if generate_pdf:
            pdf_path = self._render_pdf(result, payment_url=stripe_url)
            result["pdf_path"] = str(pdf_path)
            if "payment_url" in result:
                result["status"] = "recorded+pdf+payment_link"
            else:
                result["status"] = "recorded+pdf"

        return result

    def _next_number(self, date: datetime.date) -> str:
        """Generate next invoice number: INV-YYYY-XXX"""
        year = date.year
        # Count existing invoices this year by scanning entries
        ledger = self.ledger
        ledger.reload()
        count = 0
        for entry in ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if entry.date.year != year:
                continue
            for posting in entry.postings:
                if posting.account == self.cfg.income_account:
                    count += 1
                    break
        return f"INV-{year}-{count + 1:03d}"

    def _render_pdf(self, invoice: dict, payment_url: str | None = None) -> Path:
        """Render HTML invoice template to PDF via weasyprint."""
        env = Environment(loader=FileSystemLoader(str(self.cfg.project_root / "templates")),
                          autoescape=select_autoescape(['html', 'xml']))
        template = env.get_template("invoice.html")

        html = template.render(
            business=self.cfg,
            inv=invoice,
            payment_url=payment_url,
        )

        pdf_path = self.cfg.invoices_dir / f"{invoice['number']}.pdf"

        # Try weasyprint first, then fall back to saving HTML
        try:
            from weasyprint import HTML

            HTML(string=html).write_pdf(str(pdf_path))
        except ImportError:
            # Fallback: try wkhtmltopdf
            try:
                with tempfile.NamedTemporaryFile(
                    mode="w", suffix=".html", delete=False
                ) as f:
                    f.write(html)
                    html_path = f.name
                subprocess.run(
                    ["wkhtmltopdf", html_path, str(pdf_path)],
                    capture_output=True,
                    check=True,
                )
            except (subprocess.CalledProcessError, FileNotFoundError):
                # Last resort: save as HTML
                html_path = pdf_path.with_suffix(".html")
                with open(html_path, "w") as f:
                    f.write(html)
                print(
                    f"⚠  PDF generation not available. Saved HTML: {html_path}",
                    file=sys.stderr,
                )
                return html_path

        return pdf_path

    def list(self, year: int | None = None, ar_only: bool = False) -> list[dict]:
        """List all invoices for a given year (or all time).

        Args:
            year: Filter by year
            ar_only: Only show unpaid invoices (Accounts Receivable > 0)

        Returns:
            List of invoice dicts
        """
        self.ledger.reload()
        invoices = []
        ar_account = self.cfg.ar_account

        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if year and entry.date.year != year:
                continue

            for posting in entry.postings:
                if posting.account == self.cfg.income_account:
                    amt = abs(Decimal(str(posting.units.number)))
                    # Only include in AR list if still outstanding
                    # Check if this invoice has been paid by looking for matching AR credit
                    is_paid = False
                    if ar_only:
                        # Simple heuristic: check if AR balance for this payee is non-zero
                        ar_balance = self.ledger.account_balance(ar_account)
                        is_paid = ar_balance == 0

                    invoices.append({
                        "date": entry.date,
                        "client": entry.payee,
                        "description": entry.narration,
                        "amount": amt,
                        "paid": is_paid,
                    })
                    break

        # Filter to unpaid if requested
        if ar_only:
            invoices = [i for i in invoices if not i["paid"]]

        invoices.sort(key=lambda x: x["date"], reverse=True)
        return invoices

    def check_ar(self) -> dict:
        """Check Accounts Receivable and identify overdue invoices.

        Returns:
            dict with total_ar, invoice_count, overdue_count, estimated_overdue_amount
        """
        ar_balance = self.ledger.account_balance(self.cfg.ar_account)
        today = datetime.date.today()

        # Estimate overdue from entries with AR postings > 0
        overdue_count = 0
        overdue_amount = Decimal("0")
        total_count = 0

        self.ledger.reload()
        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            for posting in entry.postings:
                if posting.account == self.cfg.ar_account:
                    amt = Decimal(str(posting.units.number))
                    if amt > 0:  # Money owed to us
                        total_count += 1
                        due_date = entry.date + datetime.timedelta(days=30)
                        if today > due_date:
                            overdue_count += 1
                            overdue_amount += amt

        return {
            "total_ar": ar_balance,
            "invoice_count": total_count,
            "overdue_count": overdue_count,
            "estimated_overdue_amount": overdue_amount,
            "as_of": today.isoformat(),
        }

    # ── retainer/recurring ────────────────────────────────────────────────

    RETAINERS_FILE = "retainers.json"

    def _retainers_path(self) -> Path:
        return self.cfg.project_root / self.RETAINERS_FILE

    def save_retainer(self, retainer: RetainerConfig) -> dict:
        """Save a recurring retainer configuration for auto-invoicing.

        Stored in retainers.json at the project root.
        """
        retainers = self._load_retainers()
        retainer_id = f"{retainer.client.lower().replace(' ', '_')}_{retainer.interval}"

        retainers[retainer_id] = {
            "id": retainer_id,
            "client": retainer.client,
            "description": retainer.description,
            "amount": str(retainer.amount),
            "interval": retainer.interval,
            "day_of_month": retainer.day_of_month,
            "stripe_recurring": retainer.stripe_recurring,
            "last_invoiced": None,
            "next_invoice": self._next_retainer_date(retainer).isoformat(),
        }

        path = self._retainers_path()
        with open(path, "w") as f:
            json.dump(retainers, f, indent=2)

        return retainers[retainer_id]

    def _load_retainers(self) -> dict:
        path = self._retainers_path()
        if path.exists():
            with open(path) as f:
                return json.load(f)
        return {}

    def _next_retainer_date(self, retainer: RetainerConfig) -> datetime.date:
        """Calculate the next invoice date for a retainer."""
        today = datetime.date.today()
        day = min(retainer.day_of_month, 28)  # Safe for all months

        if retainer.interval == "monthly":
            # Next month
            if today.month == 12:
                next_date = today.replace(year=today.year + 1, month=1, day=day)
            else:
                next_date = today.replace(month=today.month + 1, day=day)
        elif retainer.interval == "quarterly":
            # Next quarter
            current_quarter = (today.month - 1) // 3 + 1
            next_quarter = current_quarter + 1 if current_quarter < 4 else 1
            next_year = today.year if next_quarter > current_quarter else today.year + 1
            next_month = (next_quarter - 1) * 3 + 1
            next_date = today.replace(year=next_year, month=next_month, day=day)
        elif retainer.interval == "yearly":
            next_date = today.replace(year=today.year + 1, month=1, day=day)
        else:
            next_date = today + datetime.timedelta(days=30)

        return next_date

    def process_retainers(self, preview: bool = True) -> list[dict]:
        """Check all retainers and generate invoices for those due.

        Designed to be run from cron: `llc invoice retainers`

        Args:
            preview: If True, show what would be invoiced (no writes)

        Returns:
            List of invoice result dicts for retainers that were due
        """
        retainers = self._load_retainers()
        if not retainers:
            print("No retainers configured. Use 'llc retainer add' first.")
            return []

        today = datetime.date.today()
        results = []

        for retainer_id, info in retainers.items():
            next_date_str = info.get("next_invoice")
            if not next_date_str:
                continue

            next_date = datetime.date.fromisoformat(next_date_str)

            if next_date <= today or info.get("last_invoiced") is None:
                # Due for invoicing
                amount = Decimal(str(info["amount"]))
                print(f"  → Invoicing {info['client']}: ${amount:,.2f} ({info['description']})")

                if not preview:
                    result = self.create(
                        client=info["client"],
                        description=info["description"],
                        amount=amount,
                        invoice_date=today,
                        payment_link=info.get("stripe_recurring", False),
                        recurring="month" if info.get("interval") == "monthly" else
                                   "year" if info.get("interval") == "yearly" else None,
                    )
                    results.append(result)

                    # Update retainer state
                    retainer = RetainerConfig(
                        client=info["client"],
                        description=info["description"],
                        amount=amount,
                        interval=info["interval"],
                        day_of_month=info.get("day_of_month", 1),
                        stripe_recurring=info.get("stripe_recurring", False),
                    )
                    info["last_invoiced"] = today.isoformat()
                    info["next_invoice"] = self._next_retainer_date(retainer).isoformat()

                    # Save updated state
                    path = self._retainers_path()
                    with open(path, "w") as f:
                        json.dump(retainers, f, indent=2)

                    print(f"    ✓ Invoice {result['number']} created")
                    if "payment_url" in result:
                        print(f"    💳 Pay: {result['payment_url']}")
                else:
                    results.append({
                        "client": info["client"],
                        "amount": amount,
                        "description": info["description"],
                        "preview": True,
                    })
            else:
                print(f"  · {info['client']} — next invoice: {next_date_str}")

        return results

    def mark_paid(
        self,
        invoice_number: str,
        amount: Optional[Decimal] = None,
        date: Optional[datetime.date] = None,
        source_account: Optional[str] = None,
    ) -> dict:
        """Mark an invoice as paid — records a payment in the ledger.

        Args:
            invoice_number: Invoice number (e.g. INV-2026-001)
            amount: Payment amount (default: auto-lookup from invoice)
            date: Payment date (default: today)
            source_account: Source account (default: checking from config)

        Returns:
            dict with paid, amount, date, invoice
        """
        pay_date = date or datetime.date.today()
        src = source_account or self.cfg.checking_account

        # Look up amount if not provided
        if amount is None:
            invoices = self.list()
            for inv in invoices:
                inv_num = inv.get("date", "") + "-" + inv.get("client", "")
                if inv.get("_number") == invoice_number or invoice_number in inv.get("_key", ""):
                    amount = Decimal(str(inv["amount"]))
                    break
            if amount is None:
                # Fall back to AR balance — estimate
                ar = self.ledger.account_balance(self.cfg.ar_account)
                if ar > 0:
                    amount = ar
                else:
                    raise ValueError(f"Invoice {invoice_number} not found and AR balance is zero")

        amt = amount.quantize(Decimal("0.01"))
        self.ledger.append(
            date=pay_date,
            payee=f"Payment — Invoice {invoice_number}",
            narration=f"Payment received for invoice {invoice_number}",
            postings=[
                (src, f"{amt:.2f} USD"),
                (self.cfg.ar_account, f"-{amt:.2f} USD"),
            ],
        )

        return {
            "paid": True,
            "amount": float(amt),
            "date": pay_date.isoformat(),
            "invoice": invoice_number,
        }

    def remove_retainer(self, retainer_id: str) -> bool:
        """Remove a retainer configuration by ID.

        Args:
            retainer_id: The retainer ID from list_retainers()

        Returns:
            True if removed, False if not found.
        """
        retainers = self._load_retainers()
        if retainer_id in retainers:
            del retainers[retainer_id]
            path = self._retainers_path()
            with open(path, "w") as f:
                json.dump(retainers, f, indent=2)
            return True
        return False

    def list_retainers(self) -> dict:
        """List all retainer configurations (public wrapper)."""
        return self._load_retainers()
