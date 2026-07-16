"""Import bank transactions from CSV and append to the ledger."""

import csv
import datetime
import re
from decimal import Decimal
from pathlib import Path

from .config import Config
from .ledger import Ledger


class ExpenseImporter:
    """Import bank statement CSV → auto-categorize → append to ledger."""

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger

    def import_csv(self, csv_path: str | Path, preview: bool = False) -> list[dict]:
        """Import transactions from a bank CSV.

        Returns list of transaction dicts with their categorization.
        If preview=True, just shows what would be imported (no writes).
        """
        csv_path = Path(csv_path)
        if not csv_path.exists():
            raise FileNotFoundError(f"CSV not found: {csv_path}")

        with open(csv_path) as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            print("⚠  Empty CSV file.")
            return []

        # Try to detect CSV format (column names vary by bank)
        columns = rows[0].keys()
        date_col, desc_col, amount_col = self._detect_columns(columns)

        imported = []
        for row in rows:
            raw_date = row[date_col]
            raw_desc = row[desc_col]
            raw_amount = row[amount_col]

            date = self._parse_date(raw_date)
            desc = raw_desc.strip()
            amount = self._parse_amount(raw_amount)

            if amount == 0:
                continue

            # Determine if income or expense
            if amount > 0:
                # Money in — it's income
                account = self._categorize_income(desc)
                postings = [
                    (account, f"-{amount:.2f} USD"),
                    (self.cfg.checking_account, f"{amount:.2f} USD"),
                ]
                tx_type = "income"
            else:
                # Money out — it's an expense
                account = self._categorize_expense(desc)
                postings = [
                    (account, f"{abs(amount):.2f} USD"),
                    (self.cfg.checking_account, f"{amount:.2f} USD"),
                ]
                tx_type = "expense"

            tx = {
                "date": str(date),
                "description": desc,
                "amount": amount,
                "type": tx_type,
                "account": account,
                "postings": postings,
            }

            if not preview:
                entry = self.ledger.append(
                    date=date,
                    payee=desc[:100],
                    narration=f"Bank import: {desc[:80]}",
                    postings=postings,
                )
                tx["entry"] = entry

            imported.append(tx)

        return imported

    def _detect_columns(self, columns) -> tuple[str, str, str]:
        """Map common CSV column names to (date, description, amount)."""
        columns = list(columns)
        col_lower = [c.lower().strip() for c in columns]

        date_keywords = ["date", "trans date", "transaction date", "posted date", "posting date"]
        desc_keywords = ["description", "desc", "memo", "payee", "transaction", "name", "merchant"]
        amount_keywords = ["amount", "sum", "value", "transaction amount"]

        date_col = description_col = amount_col = None

        for i, col in enumerate(col_lower):
            if any(k in col for k in date_keywords):
                date_col = columns[i]
            if any(k in col for k in desc_keywords):
                description_col = columns[i]
            if any(k in col for k in amount_keywords):
                amount_col = columns[i]

        if not all([date_col, description_col, amount_col]):
            # Fallback: just use first three columns
            cols = list(columns)
            return cols[0], cols[1], cols[2]

        return date_col, description_col, amount_col

    def _parse_date(self, raw: str) -> datetime.date:
        """Try common date formats."""
        raw = raw.strip()
        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%Y/%m/%d",
            "%d-%b-%Y",
            "%b %d, %Y",
            "%B %d, %Y",
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        # Fallback: use today
        print(f"⚠  Could not parse date '{raw}', using today.")
        return datetime.date.today()

    def _parse_amount(self, raw: str) -> Decimal:
        """Parse dollar amount from string.
        
        Bank CSVs vary wildly in amount sign convention.
        Positive = inflow (income), Negative = outflow (expense) by default.
        """
        raw = raw.strip().replace("$", "").replace(",", "").replace('"', '')
        # Handle parenthetical negatives: (100.00) → -100.00
        if raw.startswith("(") and raw.endswith(")"):
            raw = "-" + raw[1:-1]
        try:
            return Decimal(raw)
        except Exception:
            return Decimal("0")

    def _categorize_expense(self, desc: str) -> str:
        """Match description against rules, fall back to Miscellaneous."""
        desc_upper = desc.upper()
        for pattern, account in self.cfg.expense_rules:
            if pattern in desc_upper:
                return account
        return "Expenses:Miscellaneous"

    def _categorize_income(self, desc: str) -> str:
        """Match description against income rules, fall back to Consulting."""
        desc_upper = desc.upper()
        for pattern, account in self.cfg.income_rules:
            if pattern in desc_upper:
                return account
        return self.cfg.income_account
