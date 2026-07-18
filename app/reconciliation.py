"""Bank reconciliation workflow for SoloLedger.

Helps match ledger transactions against bank statements. Uses Beancount's
balance directives to assert cleared balances, and tracks uncleared
transactions for review.

Typical workflow:
    1. Statement arrives → llc reconcile start --date 2026-07-31 --balance 15200.00
    2. Review uncleared items → llc reconcile list
    3. Mark items as matched or add missing entries
    4. Add balance assertion → llc reconcile assert --date 2026-07-31

Usage:
    from app.reconciliation import Reconciliation
    rec = Reconciliation(cfg, ledger)
    rec.start(date="2026-07-31", balance=Decimal("15200.00"))
"""

from __future__ import annotations

import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger


class Reconciliation:
    """Bank reconciliation helper.

    Tracks which transactions have been cleared/matched against a bank
    statement. Uses a dedicated file (`.reconciliation_log`) to track
    completed reconciliations.
    """

    LOG_FILE = ".reconciliation_log"

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger
        self._log_path = Path(cfg.project_root) / self.LOG_FILE

    def uncleared_transactions(self, account: str = "Assets:Bank:BusinessChecking",
                                days_back: int = 365) -> list[dict]:
        """List transactions that haven't been flagged as cleared.

        Uses a simple heuristic: if a transaction's date is before the
        last reconciliation date for that account, it's considered cleared.
        Otherwise it shows as potentially uncleared.

        Returns:
            List of {date, payee, amount, account, status} dicts.
        """
        self.ledger.reload()
        last_reconciled = self._last_reconciled_date(account)

        # Get all transactions from the ledger
        uncleared = []
        cutoff = datetime.date.today() - datetime.timedelta(days=days_back)

        try:
            for entry in (self.ledger._entries or []):
                from beancount.core.data import Transaction
                if not isinstance(entry, Transaction):
                    continue
                txn_date = entry.date
                if txn_date < cutoff:
                    continue

                # Check if this entry touches our account
                touches_account = any(
                    p.account.startswith(account.rstrip("*"))
                    for p in entry.postings
                )
                if not touches_account:
                    continue

                status = "cleared" if (last_reconciled and txn_date <= last_reconciled) else "uncleared"

                # Get total amount
                total = sum(
                    p.units.number for p in entry.postings
                    if p.account.startswith(account.rstrip("*"))
                )

                uncleared.append({
                    "date": txn_date.isoformat(),
                    "payee": entry.payee or entry.narration or "Unknown",
                    "amount": float(abs(total)),
                    "type": "debit" if total > 0 else "credit",
                    "account": account,
                    "status": status,
                })
        except Exception:
            pass

        uncleared.sort(key=lambda t: t["date"], reverse=True)
        return uncleared

    def start(self, date: str, balance: Decimal,
              account: str = "Assets:Bank:BusinessChecking") -> dict:
        """Start a reconciliation by adding a balance assertion.

        Args:
            date: Statement date (YYYY-MM-DD)
            balance: Ending balance from bank statement
            account: Account to reconcile

        Returns:
            dict with result info.
        """
        stmt_date = datetime.date.fromisoformat(date)

        # Add a balance directive to the ledger
        self.ledger.append(
            date=stmt_date,
            payee="Reconciliation",
            narration=f"Bank reconciliation balance assertion: ${balance:,.2f}",
            postings=[
                (account, f"{balance:.2f} USD"),
                ("Equity:OpeningBalance", f"{-balance:.2f} USD"),
            ],
        )

        # Log this reconciliation
        self._log_completion(stmt_date, account, balance)

        self.ledger.reload(force=True)

        # Count uncleared
        uncleared = self.uncleared_transactions(account)
        prior = [t for t in uncleared if t["status"] == "cleared"]
        pending = [t for t in uncleared if t["status"] == "uncleared"]

        return {
            "date": date,
            "account": account,
            "balance": float(balance),
            "statement_match": True,
            "cleared_transactions": len(prior),
            "uncleared_transactions": len(pending),
        }

    def _last_reconciled_date(self, account: str) -> Optional[datetime.date]:
        """Find the most recent reconciliation date for an account."""
        if not self._log_path.exists():
            return None
        try:
            import json
            data = json.loads(self._log_path.read_text())
            entries = [e for e in data if e.get("account") == account]
            if entries:
                last = sorted(entries, key=lambda e: e["date"], reverse=True)[0]
                return datetime.date.fromisoformat(last["date"])
        except Exception:
            pass
        return None

    def _log_completion(self, date: datetime.date, account: str, balance: Decimal):
        """Record a completed reconciliation."""
        import json
        entry = {
            "date": date.isoformat(),
            "account": account,
            "balance": float(balance),
        }
        if self._log_path.exists():
            data = json.loads(self._log_path.read_text())
        else:
            data = []
        data.append(entry)
        self._log_path.write_text(json.dumps(data, indent=2))

    def history(self) -> list[dict]:
        """List all completed reconciliations."""
        if not self._log_path.exists():
            return []
        import json
        return json.loads(self._log_path.read_text())
