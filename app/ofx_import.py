"""Import transactions from OFX/QFX bank statement files.

Banks that don't support Plaid often offer OFX/QFX downloads. This module
parses them and appends categorized transactions to the Beancount ledger.

Usage:
    from app.ofx_import import OfxImporter
    imp = OfxImporter(cfg, ledger)
    result = imp.import_file("statement.qfx")

Dependencies: none (pure Python OFX parser)
"""

from __future__ import annotations

import datetime
import os
import re
import tempfile
from collections import defaultdict
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger


class OfxParser:
    """Simple OFX 1.x (SGML) parser — doesn't need ofxtools.

    Handles the most common bank OFX format: SGML-based with
    <STMTTRN> blocks containing <TRNTYPE>, <DTPOSTED>, <TRNAMT>,
    <FITID>, <NAME>, <MEMO>.
    """

    def parse(self, path: str | Path) -> list[dict]:
        """Parse an OFX/QFX file and return transaction dicts.

        Returns list of:
            {date, fitid, amount, name, memo, type}
        where amount is positive for outflows (debits, our sign convention),
        negative for inflows (credits).
        """
        raw = Path(path).read_text(encoding="utf-8", errors="replace")

        transactions = []

        # Find all <STMTTRN> blocks
        stmttrn_pattern = re.compile(
            r"<STMTTRN>(.*?)</STMTTRN>", re.IGNORECASE | re.DOTALL
        )

        for match in stmttrn_pattern.finditer(raw):
            block = match.group(1)

            txn = {
                "type": self._extract(block, r"<TRNTYPE>(.*?)</TRNTYPE>", ""),
                "date": self._extract_date(block),
                "fitid": self._extract(block, r"<FITID>(.*?)</FITID>", ""),
                "name": self._extract(block, r"<NAME>(.*?)</NAME>", ""),
                "memo": self._extract(block, r"<MEMO>(.*?)</MEMO>", ""),
                "checknum": self._extract(block, r"<CHECKNUM>(.*?)</CHECKNUM>", ""),
            }

            # Parse amount — OFX sign convention:
            # In OFX, positive = inflow (credit to account)
            # We want: positive = outflow (debit, money leaving)
            raw_amount = self._extract(block, r"<TRNAMT>(.*?)</TRNAMT>", "0")
            try:
                ofx_amount = Decimal(raw_amount.strip())
            except (ValueError, TypeError):
                ofx_amount = Decimal("0")

            # Negate: OFX positive inflow → our negative (credit)
            # OFX negative outflow → our positive (debit)
            txn["amount"] = -ofx_amount

            transactions.append(txn)

        return transactions

    def _extract(self, text: str, pattern: str, default: str) -> str:
        """Extract a field from OFX block."""
        m = re.search(pattern, text, re.IGNORECASE | re.DOTALL)
        if m:
            return m.group(1).strip()
        return default

    def _extract_date(self, block: str) -> datetime.date:
        """Parse OFX date format (YYYYMMDD or YYYYMMDDHHMMSS)."""
        raw = self._extract(block, r"<DTPOSTED>(.*?)</DTPOSTED>", "")
        if not raw:
            raw = self._extract(block, r"<DTUSER>(.*?)</DTUSER>", "")
        if not raw:
            return datetime.date.today()

        # Strip time portion if present
        raw = raw.strip()
        if len(raw) >= 8:
            try:
                return datetime.date(int(raw[:4]), int(raw[4:6]), int(raw[6:8]))
            except ValueError:
                pass
        return datetime.date.today()


class OfxImporter:
    """Parse OFX/QFX files and import transactions into Beancount.

    Deduplicates by FITID (Financial Institution Transaction ID).
    """

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger
        self._parser = OfxParser()
        self._existing_fitids: set[str] = set()

    def _load_existing_fitids(self) -> set[str]:
        """Load previously-imported FITIDs from dedup file."""
        dedup_path = self._dedup_path()
        if dedup_path.exists():
            return set(dedup_path.read_text().strip().splitlines())
        return set()

    def _dedup_path(self) -> Path:
        return Path(self.cfg.ledger_dir or self.cfg.project_root) / ".ofx_dedup"

    def _save_fitid(self, fitid: str):
        dedup_path = self._dedup_path()
        with open(dedup_path, "a") as f:
            f.write(fitid + "\n")

    def parse_file(self, path: str | Path) -> list[dict]:
        """Parse an OFX/QFX file and return transaction dicts.

        Returns list of dicts with keys: date, fitid, amount, name, memo, type
        """
        return self._parser.parse(path)

    def import_file(
        self,
        path: str | Path,
        account: str = "Assets:Bank:BusinessChecking",
        expense_account: str = "Expenses:Miscellaneous",
        income_account: str = "Income:Consulting",
        preview: bool = False,
    ) -> dict:
        """Parse and import an OFX/QFX file into the Beancount ledger.

        Args:
            path: Path to .ofx or .qfx file
            account: Beancount bank/credit-card account
            expense_account: Default expense for debits
            income_account: Default income for credits
            preview: If True, don't write anything

        Returns:
            dict with: total, imported, skipped_duplicates, errors, transactions
        """
        self._existing_fitids = self._load_existing_fitids()
        transactions = self.parse_file(path)

        result = {
            "file": str(path),
            "total": len(transactions),
            "imported": 0,
            "skipped_duplicates": 0,
            "errors": [],
            "transactions": [],
        }

        for txn in transactions:
            fitid = txn["fitid"]
            if fitid and fitid in self._existing_fitids:
                result["skipped_duplicates"] += 1
                continue

            payee = txn["name"] or txn["memo"] or "Unknown"
            amt = txn["amount"]

            # Use the categorizer to suggest an account
            suggestion = self._suggest_account(payee, amt)

            if amt > 0:
                # Debit: money out — expense
                postings = [
                    (suggestion["account"], f"{amt:.2f} USD"),
                    (account, f"{-amt:.2f} USD"),
                ]
            else:
                # Credit: money in — income/refund
                postings = [
                    (suggestion["account"], f"{amt:.2f} USD"),
                    (account, f"{-amt:.2f} USD"),
                ]

            narration = f"OFX: {payee}"
            date = txn["date"]

            if not preview:
                self.ledger.append(date, payee, narration, postings)
                if fitid:
                    self._save_fitid(fitid)

            result["imported"] += 1
            result["transactions"].append({
                "date": date.isoformat(),
                "payee": payee,
                "amount": float(amt),
                "account": suggestion["account"],
                "fitid": fitid,
                "type": txn["type"],
            })

        # Refresh ledger cache
        if not preview and result["imported"] > 0:
            self.ledger.reload(force=True)

        return result

    def _suggest_account(self, payee: str, amount: Decimal) -> dict:
        """Suggest a Beancount account for a transaction.

        For debits (amount > 0): uses three-tier categorizer → keyword → default.
        For credits (amount < 0): income account or transfer.
        """
        upper = payee.upper()

        # Credits: money coming in
        if amount < 0:
            if "REFUND" in upper or "REVERSAL" in upper or "INTEREST" in upper:
                return {"account": "Income:Interest", "method": "keyword"}
            if "TRANSFER" in upper:
                return {"account": "Equity:OwnerDraws", "method": "keyword"}
            return {"account": "Income:Consulting", "method": "credit-default"}

        # Debits: money going out — use categorizer
        try:
            from .categorizer import Categorizer
            cat = Categorizer(self.cfg, use_patterns=True, use_embedding=True)
            suggested = cat.suggest(payee)
            if suggested:
                return {"account": suggested, "method": "categorizer"}
        except Exception as e:
            import sys
            print(f"⚠ Categorizer failed for '{payee}': {e}", file=sys.stderr)

        # Keyword fallback
        if "INTEREST" in upper or "DIVIDEND" in upper:
            return {"account": "Income:Interest", "method": "keyword"}
        if "FEE" in upper and ("ATM" in upper or "SERVICE" in upper):
            return {"account": "Expenses:BankFees", "method": "keyword"}
        if "TRANSFER" in upper:
            return {"account": "Equity:OwnerDraws", "method": "keyword"}

        return {"account": "Expenses:Miscellaneous", "method": "debit-default"}
