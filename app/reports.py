"""Expense and financial reports — CSV export, summaries by category/month.

Usage:
    from app.reports import ReportGenerator
    rg = ReportGenerator(cfg, ledger)
    csv = rg.expenses_csv(year=2026)
    summary = rg.expenses_summary(year=2026)
"""

import csv
import datetime
import io
from collections import defaultdict
from decimal import Decimal
from typing import Optional

from .config import Config
from .ledger import Ledger


class ReportGenerator:
    """Generate financial reports and exports."""

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger

    def expenses_csv(self, year: Optional[int] = None) -> str:
        """Generate a CSV of all expenses, optionally filtered by year.

        Returns CSV string suitable for downloading.
        """
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["Date", "Payee", "Description", "Category", "Amount", "Deductible"])

        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if year and entry.date.year != year:
                continue

            for posting in entry.postings:
                if posting.account.startswith("Expenses:"):
                    amt = abs(Decimal(str(posting.units.number))) if posting.units else Decimal("0")
                    if amt == 0:
                        continue
                    payee = getattr(entry, "payee", "") or ""
                    narration = getattr(entry, "narration", "") or ""
                    # Simplify account name for readability
                    account = posting.account
                    # Estimate deductibility (100% for most, 50% for meals)
                    deductible = 1.0
                    if "Meals" in account:
                        deductible = 0.5

                    writer.writerow([
                        entry.date.isoformat(),
                        payee,
                        narration[:60],
                        account,
                        float(amt),
                        f"{int(deductible * 100)}%",
                    ])

        return output.getvalue()

    def expenses_summary(self, year: Optional[int] = None) -> list[dict]:
        """Group expenses by category with totals.

        Returns sorted list of {category, amount, transaction_count}.
        """
        categories = defaultdict(lambda: {"amount": Decimal("0"), "count": 0})
        total = Decimal("0")

        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if year and entry.date.year != year:
                continue

            for posting in entry.postings:
                if posting.account.startswith("Expenses:"):
                    amt = abs(Decimal(str(posting.units.number))) if posting.units else Decimal("0")
                    if amt == 0:
                        continue
                    categories[posting.account]["amount"] += amt
                    categories[posting.account]["count"] += 1
                    total += amt

        result = []
        for account, data in sorted(categories.items(), key=lambda x: -x[1]["amount"]):
            result.append({
                "category": account,
                "amount": float(data["amount"]),
                "count": data["count"],
            })

        return result

    def profit_loss(self, year: Optional[int] = None) -> dict:
        """Generate a P&L summary for a given year."""
        income = Decimal("0")
        expenses = Decimal("0")
        expense_categories = {}

        for entry in self.ledger.entries:
            if not hasattr(entry, "date") or not hasattr(entry, "postings"):
                continue
            if year and entry.date.year != year:
                continue

            for posting in entry.postings:
                amt = Decimal(str(posting.units.number)) if posting.units else Decimal("0")
                if amt == 0:
                    continue

                if posting.account.startswith("Income:"):
                    income += abs(amt)
                elif posting.account.startswith("Expenses:"):
                    expenses += abs(amt)
                    expense_categories[posting.account] = expense_categories.get(posting.account, Decimal("0")) + abs(amt)

        net = income - expenses
        return {
            "year": year or datetime.date.today().year,
            "income": float(income),
            "expenses": float(expenses),
            "net_profit": float(net),
            "expense_breakdown": [
                {"category": acct, "amount": float(amt)}
                for acct, amt in sorted(expense_categories.items(), key=lambda x: -x[1])
            ],
        }
