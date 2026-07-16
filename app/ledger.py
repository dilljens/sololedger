"""Thin wrapper around Beancount v3 — append transactions, query balances."""

import datetime
import re
from decimal import Decimal
from typing import Iterator

from beancount import loader
from beancount.core import data
from beancount.core.data import Transaction, Posting, Amount, Open
from beancount.core.number import D
from beancount.core.inventory import Inventory
from beancount.ops.summarize import balance_by_account

from .config import Config


class Ledger:
    """Interface to the Beancount ledger file."""

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._entries = None
        self._errors = None
        self._options_map = None
        self._balances = None

    def reload(self):
        """(Re)load the ledger file from disk."""
        self._entries, self._errors, self._options_map = loader.load_file(
            str(self.cfg.ledger_path)
        )
        bal_result = balance_by_account(self._entries)
        self._balances = bal_result[0]  # dict[account -> Inventory]

    @property
    def entries(self):
        if self._entries is None:
            self.reload()
        return self._entries

    @property
    def errors(self):
        if self._errors is None:
            self.reload()
        return self._errors

    def check(self) -> list[str]:
        """Run Beancount validation. Returns list of error strings (empty = clean)."""
        self.reload()
        return [str(e) for e in self._errors]

    # ── balance helpers ────────────────────────────────────────────────────

    def account_balance(self, account_pattern: str) -> Decimal:
        """Sum balance for account(s) matching a glob pattern (e.g. 'Income:*')."""
        self.reload()

        # Convert glob to regex: * → .*, replace wildcards
        regex = re.escape(account_pattern).replace(r"\*", ".*")
        pattern = re.compile(f"^{regex}$")

        total = D("0")
        for acct, inventory in self._balances.items():
            if pattern.match(acct):
                for pos in inventory:
                    total += pos.units.number

        return Decimal(str(total))

    def net_income(self) -> Decimal:
        """Net profit: revenue - expenses.

        In Beancount:
          Income:*  → credit balance (negative number, e.g. -5000 for $5k earned)
          Expenses:* → debit balance (positive number, e.g. 500 for $500 spent)
        Net = -Income - Expenses = revenue - expenses
        """
        income = self.account_balance("Income:*")
        expenses = self.account_balance("Expenses:*")
        return -income - expenses

    def gross_revenue(self) -> Decimal:
        """Total consulting revenue (absolute value)."""
        return abs(self.account_balance(self.cfg.income_account))

    def total_expenses(self) -> Decimal:
        """Sum of all expense accounts (positive value)."""
        return self.account_balance("Expenses:*")

    def cash_balance(self) -> Decimal:
        """What's in the business checking account."""
        return self.account_balance(self.cfg.checking_account)

    def taxes_paid(self) -> dict:
        """How much has been paid in taxes so far."""
        fed = self.account_balance("Expenses:Taxes:Federal")
        fica = self.account_balance("Expenses:Taxes:FICA")
        return {
            "federal_estimated": fed,
            "fica_employer": fica,
        }

    def expense_detail(self) -> list[dict]:
        """Get expense breakdown by subaccount."""
        self.reload()
        results = []
        for acct, inventory in sorted(self._balances.items()):
            if acct.startswith("Expenses:") and not acct.startswith("Expenses:Taxes"):
                for pos in inventory:
                    amt = Decimal(str(pos.units.number))
                    if amt > 0:
                        results.append({"account": acct, "amount": amt})
        return results

    # ── append transaction ─────────────────────────────────────────────────

    def append(self, date: datetime.date, payee: str, narration: str,
               postings: list[tuple[str, str]]) -> str:
        """Append a transaction to the transactions file.

        postings: list of (account, amount_string) pairs.
        Amount strings like 'USD 500.00' or 'USD -500.00'.
        Returns the beancount entry string (which was also appended to file).
        """
        date_str = date.isoformat()
        payee_escaped = payee.replace('"', '\\"')
        nar_escaped = narration.replace('"', '\\"')

        lines = [f'{date_str} * "{payee_escaped}" "{nar_escaped}"']
        for account, amount_str in postings:
            lines.append(f"  {account:45s}  {amount_str}")

        entry = "\n".join(lines) + "\n\n"

        # Append to transactions file
        tx_path = self.cfg.ledger_dir / "transactions.beancount"
        with open(tx_path, "a") as f:
            f.write(entry)

        # Invalidate cached entries
        self._entries = None
        self._balances = None

        return entry
