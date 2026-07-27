"""Wave Accounting CSV importer.

Parses Wave export CSV files and stores transactions in the SQLite
metadata layer for categorization and Beancount export.

Wave CSV format has columns: Date, Description, Amount, Account Type, Account Name
"""
import csv
import re
from datetime import datetime
from pathlib import Path
from collections import defaultdict

from app.db import TenantDB, make_fingerprint

WAVE_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def parse_wave_csv(path: str | Path) -> list[dict]:
    """Parse a Wave Accounting CSV export."""
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.DictReader(f))

    txns = []
    for row in rows:
        date_str = (row.get("Date") or "").strip()
        if not date_str or not WAVE_DATE_RE.match(date_str):
            continue

        amount_str = (row.get("Amount") or "0").replace("$", "").replace(",", "").strip()
        try:
            amount_cents = int(round(float(amount_str) * 100))
        except (ValueError, TypeError):
            continue

        txns.append({
            "date": date_str,
            "description": (row.get("Description") or "").strip(),
            "amount_cents": amount_cents,
            "account_type": (row.get("Account Type") or "").strip(),
            "account_name": (row.get("Account Name") or "").strip(),
        })
    return txns


def import_wave_csv(db: TenantDB, path: str | Path, dry_run: bool = False) -> dict:
    """Import Wave CSV transactions into SQLite metadata layer."""
    txns = parse_wave_csv(path)
    result = {"total": len(txns), "imported": 0, "skipped": 0, "errors": 0}

    if not txns:
        return result

    if not dry_run:
        db.execute(
            "INSERT INTO import_batches (source, account, filename, status) VALUES (?, ?, ?, ?)",
            ("wave_csv", "wave", Path(path).name, "pending"),
        )
        batch_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for txn in txns:
        fp = make_fingerprint("wave", "wave", txn["date"], txn["amount_cents"], txn["description"])

        if not dry_run:
            existing = db.execute(
                "SELECT id FROM imported_transactions WHERE fingerprint = ?", (fp,)
            ).fetchone()
            if existing:
                result["skipped"] += 1
                continue

            db.execute(
                """INSERT INTO imported_transactions
                   (batch_id, source, account, date, amount_cents, description, fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, "wave", "wave", txn["date"], txn["amount_cents"], txn["description"][:200], fp),
            )

        result["imported"] += 1

    if not dry_run:
        db.execute(
            "UPDATE import_batches SET status = 'committed', stats = ? WHERE id = ?",
            (str({"imported": result["imported"], "skipped": result["skipped"]}), batch_id),
        )
        db.commit()

    return result
