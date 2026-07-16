"""Create invoices: record in ledger + generate PDF."""

import datetime
import subprocess
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

from .config import Config
from .ledger import Ledger


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
    ) -> dict:
        """Create an invoice: record income and optionally generate PDF.

        Returns dict with invoice metadata.
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

        # 2. Generate PDF
        if generate_pdf:
            pdf_path = self._render_pdf(result)
            result["pdf_path"] = str(pdf_path)
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

    def _render_pdf(self, invoice: dict) -> Path:
        """Render HTML invoice template to PDF via weasyprint."""
        env = Environment(loader=FileSystemLoader(str(self.cfg.project_root / "templates")))
        template = env.get_template("invoice.html")

        html = template.render(
            business=self.cfg,
            inv=invoice,
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

    def list(self, year: int | None = None) -> list[dict]:
        """List all invoices for a given year (or all time)."""
        self.ledger.reload()
        invoices = []
        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if year and entry.date.year != year:
                continue
            for posting in entry.postings:
                if posting.account == self.cfg.income_account:
                    amt = abs(Decimal(str(posting.units.number)))
                    invoices.append({
                        "date": entry.date,
                        "client": entry.payee,
                        "description": entry.narration,
                        "amount": amt,
                    })
                    break
        invoices.sort(key=lambda x: x["date"], reverse=True)
        return invoices
