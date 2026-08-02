"""SoloLedger importers package.

Each importer provides a module-level import_<source>() function that
parses a file, records transactions in the SQLite metadata layer for
dedup, and — when a ledger is supplied — posts them to the Beancount
ledger so imported money actually appears in the books.
"""
from __future__ import annotations

import datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

from ..config import Config
from ..ledger import Ledger


def _cents_to_amount(cents: int) -> Decimal:
    """Convert integer cents to a 2-dp Decimal."""
    return (Decimal(cents) / 100).quantize(Decimal("0.01"))


def _categorize(cfg: Config, payee: str, is_income: bool) -> str:
    """Match a payee against config rules (substring), with sane defaults."""
    upper = payee.upper()
    rules = cfg.income_rules if is_income else cfg.expense_rules
    for pattern, account in rules:
        if pattern in upper:
            return account
    return cfg.income_account if is_income else "Expenses:Miscellaneous"


def post_imported_txn(
    ledger: Ledger,
    cfg: Config,
    txn_date: str | datetime.date,
    payee: str,
    amount_cents: int,
    source_account: str,
    category: Optional[str] = None,
) -> str:
    """Post one imported transaction to the Beancount ledger.

    Args:
        ledger: Ledger instance to append to
        cfg: Config (for categorization rules and default accounts)
        txn_date: ISO date string or date
        payee: Merchant / description (escaped by Ledger.append)
        amount_cents: SIGNED cents — positive = expense (money out of the
            source account), negative = income (money into it)
        source_account: where the money moved (checking, credit card, ...)
        category: explicit expense category; auto-categorized when None

    Returns the beancount entry string appended to the ledger.
    """
    date = txn_date if isinstance(txn_date, datetime.date) else datetime.date.fromisoformat(str(txn_date)[:10])
    amt = _cents_to_amount(abs(amount_cents))

    if amount_cents > 0:
        expense_account = category or _categorize(cfg, payee, is_income=False)
        postings = [
            (expense_account, f"{amt} USD"),
            (source_account, f"-{amt} USD"),
        ]
    else:
        income_account = category or _categorize(cfg, payee, is_income=True)
        postings = [
            (income_account, f"-{amt} USD"),
            (source_account, f"{amt} USD"),
        ]

    return ledger.append(
        date=date,
        payee=payee[:100],
        narration=f"Import: {payee[:80]}",
        postings=postings,
    )
