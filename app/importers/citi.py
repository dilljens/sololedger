"""Citi credit-card CSV importer.

Parses Citi online-portal CSV exports, deduplicates by composite key,
and stores transactions in the SQLite metadata layer for cross-source dedup.

Citi CSV format:
    Date,Description,Debit,Credit,Category,Name,Card
    
Sign convention (matches Plaid-style internal):
    Debit column → CHARGE  → amount_cents = +abs(value)  (outflow)
    Credit column → REFUND → amount_cents = -abs(value)  (inflow)
"""
import csv
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.db import TenantDB, make_fingerprint


CITI_HEADER = "Date,Description,Debit,Credit,Category,Name,Card"


# ─── Detection ────────────────────────────────────────────────────────────


def looks_like_citi_csv(path: str | Path) -> bool:
    """Check if a file looks like a Citi CSV export."""
    try:
        with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
            lines = [next(f, "").rstrip() for _ in range(5)]
    except OSError:
        return False
    return any(CITI_HEADER in ln for ln in lines)


# ─── Parser ───────────────────────────────────────────────────────────────


def _parse_citi_date(s: str) -> str:
    """Parse 'Apr 02, 2026' → '2026-04-02'"""
    cleaned = s.strip()
    # Handle any extra whitespace around the comma
    cleaned = re.sub(r'\s*,\s*', ', ', cleaned)
    return datetime.strptime(cleaned, "%b %d, %Y").strftime("%Y-%m-%d")


def _parse_citi_amount_cents(s: str) -> int:
    """Parse Citi amount string to integer cents."""
    if not s or not s.strip():
        return 0
    cleaned = s.replace(",", "").replace("$", "").replace("-", "").strip()
    if not cleaned:
        return 0
    try:
        return int(round(float(cleaned) * 100))
    except (ValueError, OverflowError):
        return 0


def parse_citi_csv(path: str | Path) -> list[dict]:
    """Parse a Citi CSV into normalized transaction dicts.

    Returns list of:
        {date, amount_cents, merchant_raw, citi_category, name, card, raw}
    """
    with open(path, "r", encoding="utf-8-sig", errors="replace") as f:
        rows = list(csv.reader(f))
    if not rows:
        return []

    # Find header
    header_idx = next(
        (i for i, r in enumerate(rows) if "Date" in r and "Debit" in r and "Credit" in r and "Card" in r),
        None,
    )
    if header_idx is None:
        raise ValueError(f"No Citi-format header found in {path}")
    header = [c.strip() for c in rows[header_idx]]
    col = {h: i for i, h in enumerate(header)}

    out = []
    for r in rows[header_idx + 1:]:
        if not any(c.strip() for c in r):
            continue
        if len(r) < len(header):
            continue
        date_s = r[col["Date"]].strip()
        if not date_s:
            continue
        try:
            date = _parse_citi_date(date_s)
        except ValueError:
            continue

        debit_s = r[col["Debit"]].strip()
        credit_s = r[col["Credit"]].strip()

        if debit_s and credit_s:
            # Both populated — rare edge case, skip for safety
            continue
        if debit_s:
            amount_cents = _parse_citi_amount_cents(debit_s)
        elif credit_s:
            amount_cents = -_parse_citi_amount_cents(credit_s)
        else:
            continue

        out.append({
            "date": date,
            "amount_cents": amount_cents,
            "merchant_raw": r[col["Description"]].strip(),
            "citi_category": r[col["Category"]].strip(),
            "name": r[col["Name"]].strip(),
            "card": r[col["Card"]].strip(),
            "raw": dict(zip(header, r[:len(header)])),
        })
    return out


# ─── Import ────────────────────────────────────────────────────────────────


def import_citi_csv(
    db: TenantDB,
    path: str | Path,
    account_label: str = "citi",
    dry_run: bool = False,
) -> dict:
    """Import Citi CSV transactions into the SQLite metadata layer.

    Args:
        db: TenantDB instance
        path: Path to Citi CSV file
        account_label: Account label for fingerprinting
        dry_run: If True, don't write

    Returns:
        dict with {imported, skipped_duplicates, total, errors}
    """
    txns = parse_citi_csv(path)

    result = {
        "total": len(txns),
        "imported": 0,
        "skipped_duplicates": 0,
        "errors": 0,
        "warnings": [],
    }

    # Create import batch
    if not dry_run:
        db.execute(
            "INSERT INTO import_batches (source, account, filename, status) VALUES (?, ?, ?, ?)",
            ("citi_csv", account_label, Path(path).name, "pending"),
        )
        batch_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

    for txn in txns:
        fp = make_fingerprint(
            "citi_csv", account_label,
            txn["date"], txn["amount_cents"], txn["merchant_raw"],
        )

        if not dry_run:
            # Check existing fingerprint
            existing = db.execute(
                "SELECT id FROM imported_transactions WHERE fingerprint = ?", (fp,)
            ).fetchone()

            if existing:
                result["skipped_duplicates"] += 1
                continue

            # Insert
            db.execute(
                """INSERT INTO imported_transactions
                   (batch_id, source, account, external_id, date, amount_cents, description, fingerprint)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (batch_id, "citi_csv", account_label, f"{txn['card']}-{txn['date']}-{txn['amount_cents']}",
                 txn["date"], txn["amount_cents"], txn["merchant_raw"][:200], fp),
            )

        result["imported"] += 1

    if not dry_run:
        # Update batch status
        db.execute(
            "UPDATE import_batches SET status = 'committed', stats = ? WHERE id = ?",
            (str({"imported": result["imported"], "skipped": result["skipped_duplicates"]}), batch_id),
        )
        db.commit()

    return result


def preview_citi_csv(path: str | Path) -> dict:
    """Parse and return summary without importing."""
    txns = parse_citi_csv(path)

    cards = sorted(set(t["card"] for t in txns if t["card"]))
    total_cents = sum(t["amount_cents"] for t in txns if t["amount_cents"] > 0)

    return {
        "total": len(txns),
        "total_cents": total_cents,
        "cards": cards,
        "sample": [
            {"date": t["date"], "merchant": t["merchant_raw"][:60],
             "amount_cents": t["amount_cents"], "card": t["card"]}
            for t in txns[:10]
        ],
    }
