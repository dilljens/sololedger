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
                    "amount": float(total),  # signed: credits and debits keep sign
                    "type": "debit" if total > 0 else "credit",
                    "account": account,
                    "status": status,
                })
        except Exception as e:
            import sys
            print(f"⚠ Failed to process uncleared txn: {e}", file=sys.stderr)

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

        # Add a BALANCE DIRECTIVE to the ledger — asserts the expected
        # balance without posting money. (A transaction here would double-
        # count the entire statement balance into the books.)
        self.ledger.balance_assertion(
            date=stmt_date,
            account=account,
            amount=balance,
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
        except Exception as e:
            import sys
            print(f"⚠ Failed to load reconciliation history: {e}", file=sys.stderr)
        return None

    def _log_completion(self, date: datetime.date, account: str, balance: Decimal):
        """Record a completed reconciliation (atomic write, no lost updates)."""
        import json
        import os
        import threading
        entry = {
            "date": date.isoformat(),
            "account": account,
            "balance": float(balance),
        }
        # Module-level lock so concurrent reconciliations can't corrupt the log
        lock = getattr(Reconciliation, "_log_lock", None)
        if lock is None:
            Reconciliation._log_lock = threading.Lock()
            lock = Reconciliation._log_lock
        with lock:
            if self._log_path.exists():
                try:
                    data = json.loads(self._log_path.read_text())
                except (json.JSONDecodeError, OSError):
                    data = []
            else:
                data = []
            data.append(entry)
            tmp = self._log_path.with_suffix(self._log_path.suffix + ".tmp")
            tmp.write_text(json.dumps(data, indent=2))
            os.replace(tmp, self._log_path)

    def history(self) -> list[dict]:
        """List all completed reconciliations."""
        if not self._log_path.exists():
            return []
        import json
        return json.loads(self._log_path.read_text())
