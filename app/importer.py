"""Import transactions from other accounting tools (Wave, QuickBooks, generic CSV).

Usage:
    from app.importer import Importer
    imp = Importer(cfg, ledger)
    results = imp.import_wave_csv("wave-export.csv", preview=True)
    results = imp.import_qbo_csv("qbo-transactions.csv", preview=True)
"""

import csv
import datetime
import os
import tempfile
from decimal import Decimal
from pathlib import Path
from typing import Optional

from .config import Config
from .expenses import ExpenseImporter
from .ledger import Ledger


class Importer:
    """Import transactions from other accounting tools."""

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger

    def import_wave_csv(self, filepath: str | Path, preview: bool = False) -> list[dict]:
        """Import a Wave Accounting CSV export.

        Wave exports have columns: Transaction Date, Transaction Description,
        Amount, Account Name, Category, etc.
        """
        path = Path(filepath)
        if not path.exists():
            return [{"error": f"File not found: {path}"}]

        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return [{"error": "Empty CSV"}]

        columns = [c.lower().strip() for c in rows[0].keys()]
        date_col = self._find_col(columns, ["date", "transaction date"])
        desc_col = self._find_col(columns, ["description", "transaction description", "memo"])
        amount_col = self._find_col(columns, ["amount", "transaction amount", "total"])
        account_col = self._find_col(columns, ["account name", "account", "category"])

        return self._process_rows(rows, date_col, desc_col, amount_col, preview=preview)

    def import_qbo_csv(self, filepath: str | Path, preview: bool = False) -> list[dict]:
        """Import a QuickBooks Online CSV export.

        QBO exports have columns: Date, Description, Amount, Name, Account, etc.
        """
        path = Path(filepath)
        if not path.exists():
            return [{"error": f"File not found: {path}"}]

        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return [{"error": "Empty CSV"}]

        columns = [c.lower().strip() for c in rows[0].keys()]
        date_col = self._find_col(columns, ["date", "transaction date"])
        desc_col = self._find_col(columns, ["description", "name", "memo", "payee"])
        amount_col = self._find_col(columns, ["amount", "total", "sum"])
        account_col = self._find_col(columns, ["account", "category", "account name"])

        return self._process_rows(rows, date_col, desc_col, amount_col, account_col=account_col, preview=preview)

    def import_csv(self, filepath: str | Path, preview: bool = False) -> list[dict]:
        """Import a generic CSV with Date, Description, Amount columns."""
        path = Path(filepath)
        if not path.exists():
            return [{"error": f"File not found: {path}"}]

        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return [{"error": "Empty CSV"}]

        columns = [c.lower().strip() for c in rows[0].keys()]
        date_col = self._find_col(columns, ["date", "transaction date", "posted date"])
        desc_col = self._find_col(columns, ["description", "desc", "memo", "payee", "name", "merchant"])
        amount_col = self._find_col(columns, ["amount", "sum", "value", "total"])

        return self._process_rows(rows, date_col, desc_col, amount_col, preview=preview)

    def _find_col(self, columns: list[str], candidates: list[str]) -> Optional[int]:
        """Find a column index by trying candidate names."""
        for i, col in enumerate(columns):
            for candidate in candidates:
                if candidate in col:
                    return i
        return None

    def _process_rows(self, rows: list[dict], date_col: Optional[int], desc_col: Optional[int],
                      amount_col: Optional[int], account_col: Optional[int] = None,
                      preview: bool = False) -> list[dict]:
        """Process parsed CSV rows into beancount transactions."""
        if date_col is None or desc_col is None or amount_col is None:
            return [{"error": "Could not detect required columns (Date, Description, Amount)"}]

        # Write to temp CSV in a format the ExpenseImporter understands
        with tempfile.NamedTemporaryFile(mode="w", suffix=".csv", delete=False, newline="") as tmp:
            writer = csv.writer(tmp)
            writer.writerow(["Date", "Description", "Amount"])

            for row in rows:
                col_keys = list(row.keys())
                date_raw = row[col_keys[date_col]].strip() if date_col < len(col_keys) else ""
                desc_raw = row[col_keys[desc_col]].strip() if desc_col < len(col_keys) else ""
                amt_raw = row[col_keys[amount_col]].strip() if amount_col < len(col_keys) else ""

                # Skip header row if it slipped through
                if any(kw in date_raw.lower() for kw in ["date", "transaction"]):
                    continue
                if not date_raw or not amt_raw:
                    continue

                writer.writerow([date_raw, desc_raw, amt_raw])

            tmp_path = tmp.name

        # Use the existing ExpenseImporter
        importer = ExpenseImporter(self.cfg, self.ledger)
        results = importer.import_csv(tmp_path, preview=preview)

        os.unlink(tmp_path)
        return results
