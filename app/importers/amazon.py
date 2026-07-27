"""Amazon Order History importer — parse CSV/zip → vendor_receipts.

Usage:
    from app.importers.amazon import import_amazon_csv
    result = import_amazon_csv(db, csv_path, card_filter=["9642"])
    
Accepts Amazon order history CSV (downloaded from Amazon) or ZIP containing
the CSV. Parses multi-line orders, aggregates totals, deduplicates by order ID,
and stores in SQLite vendor_receipts + vendor_receipt_items tables.
"""
import csv
import io
import zipfile
from collections import OrderedDict
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from typing import Optional

from app.db import TenantDB

VENDOR = "amazon"
SOURCE = "amazon_csv"


# ── Helpers ──────────────────────────────────────────────────────────────


def _to_cents(s: str) -> Optional[int]:
    """Convert a money string to integer cents. Returns None if unparseable."""
    if not s or not s.strip():
        return None
    s = s.strip().strip('"').strip("'")
    if s.upper() in ("NOT AVAILABLE", "NOT APPLICABLE", "-", ""):
        return None
    # Amazon uses '-12' to quote negative values in Excel
    if s.startswith("'") and s.endswith("'"):
        s = s[1:-1]
    # Remove thousand separators
    s = s.replace(",", "")
    # Remove leading/trailing non-numeric (allow - at start, . in middle)
    cleaned = ""
    for i, ch in enumerate(s):
        if ch.isdigit() or ch == "." or (ch == "-" and i == 0):
            cleaned += ch
    if not cleaned:
        return None
    try:
        return int(round(float(cleaned) * 100))
    except (ValueError, OverflowError):
        return None


def _truncate_date(iso_ts: str) -> str:
    """Truncate ISO timestamp to date: '2013-06-07T13:48:49Z' → '2013-06-07'"""
    return iso_ts.split("T")[0] if "T" in iso_ts else iso_ts[:10]


def _payment_card_mask(payment_method: str) -> str:
    """Extract last 4 digits from payment method string."""
    if not payment_method:
        return ""
    # Find sequences of 4+ consecutive digits
    import re
    matches = re.findall(r"\d{4,}", payment_method)
    for m in matches:
        return m[-4:]
    return ""


# ── CSV Parsing ──────────────────────────────────────────────────────────


def _read_csv(path: str | Path) -> list[dict]:
    """Read Amazon order history CSV from a path or ZIP file."""
    path = Path(path)
    if path.suffix.lower() == ".zip":
        with zipfile.ZipFile(path) as zf:
            names = [n for n in zf.namelist() if n.lower().endswith(".csv")]
            if not names:
                raise ValueError("No CSV found in ZIP archive")
            names.sort(key=lambda n: 0 if "order" in n.lower() else 1)  # prefer order CSV
            with zf.open(names[0]) as f:
                text = f.read().decode("utf-8-sig", errors="replace")
    else:
        text = path.read_text(encoding="utf-8-sig", errors="replace")

    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def _parse_orders(rows: list[dict]) -> OrderedDict:
    """Group CSV rows by Order ID into structured order dicts.

    Returns OrderedDict[order_id, {
        "receipt": {vendor, source_id, receipt_date, merchant, total_cents, currency, raw_json},
        "items": [{description, quantity, unit_price_cents, total_cents, sort_order}, ...]
    }]
    """
    orders = OrderedDict()

    for row in rows:
        order_id = (row.get("Order ID") or "").strip()
        if not order_id:
            continue

        status = (row.get("Order Status") or "").strip()
        if status.lower() in ("cancelled", "canceled"):
            continue

        if order_id not in orders:
            raw_json = {k: v for k, v in row.items() if v is not None and v.strip()}

            total = _to_cents(row.get("Total Amount") or row.get("Total", ""))
            currency = (row.get("Currency") or row.get("Currency of Transaction", "")).strip() or "USD"
            payment = _payment_card_mask(row.get("Payment Method", "") or row.get("Payment Instrument", ""))

            orders[order_id] = {
                "receipt": {
                    "vendor": VENDOR,
                    "source_id": order_id,
                    "receipt_date": _truncate_date(row.get("Order Date", "") or row.get("Date", "")),
                    "merchant": "Amazon.com",
                    "total_cents": total,
                    "currency": currency,
                    "raw_json": raw_json,
                },
                "items": [],
                "payment_mask": payment,
            }

        # Parse line item
        title = (row.get("Title") or row.get("Product Name", "")).strip()
        if not title:
            continue

        item_total = _to_cents(row.get("Item Total", "") or row.get("Product Price", ""))
        qty_str = (row.get("Quantity") or row.get("Qty", "1")).strip()
        try:
            qty = float(qty_str) if qty_str else 1.0
        except ValueError:
            qty = 1.0

        # Calculate unit price from item total / qty
        unit_price = int(round(item_total / qty)) if item_total and qty else None

        orders[order_id]["items"].append({
            "description": title[:200],
            "quantity": qty,
            "unit_price_cents": unit_price,
            "total_cents": item_total,
            "sort_order": len(orders[order_id]["items"]),
        })

    return orders


# ── Import ────────────────────────────────────────────────────────────────


def import_amazon_csv(
    db: TenantDB,
    path: str | Path,
    card_filter: Optional[list[str]] = None,
    dry_run: bool = False,
) -> dict:
    """Import Amazon order history CSV into the database.

    Args:
        db: TenantDB instance
        path: Path to CSV or ZIP file
        card_filter: Only import orders matching these card masks (e.g. ["9642"])
        dry_run: If True, don't write anything

    Returns:
        dict with {imported, skipped, cancelled, errors, warnings}
    """
    rows = _read_csv(path)
    orders = _parse_orders(rows)

    # Count cancelled orders from raw rows
    all_order_ids = set()
    cancelled_ids = set()
    for row in rows:
        oid = (row.get("Order ID") or "").strip()
        if oid:
            all_order_ids.add(oid)
            status = (row.get("Order Status") or "").strip()
            if status.lower() in ("cancelled", "canceled"):
                cancelled_ids.add(oid)

    result = {"imported": 0, "skipped": 0, "cancelled": len(cancelled_ids), "errors": 0, "warnings": []}

    for order_id, order in orders.items():
        if card_filter and order["payment_mask"] not in card_filter:
            result["skipped"] += 1
            continue

        if dry_run:
            result["imported"] += 1
            continue

        try:
            # Check if already imported
            existing = db.execute(
                "SELECT id FROM vendor_receipts WHERE vendor = ? AND source_id = ?",
                (VENDOR, order_id),
            ).fetchone()

            if existing:
                # Vendor-side-wins: update vendor fields, preserve user fields
                receipt_id = existing["id"]
                db.execute(
                    """UPDATE vendor_receipts SET
                        receipt_date = ?, total_cents = ?, currency = ?, raw_json = ?
                       WHERE id = ?""",
                    (
                        order["receipt"]["receipt_date"],
                        order["receipt"]["total_cents"],
                        order["receipt"]["currency"],
                        str(order["receipt"]["raw_json"]),
                        receipt_id,
                    ),
                )
                # Update items — add new, keep existing user categorization
                for item in order["items"]:
                    existing_item = db.execute(
                        "SELECT id FROM vendor_receipt_items WHERE receipt_id = ? AND description = ? AND sort_order = ?",
                        (receipt_id, item["description"], item["sort_order"]),
                    ).fetchone()
                    if not existing_item:
                        db.execute(
                            """INSERT INTO vendor_receipt_items
                               (receipt_id, description, quantity, unit_price_cents, total_cents, sort_order)
                               VALUES (?, ?, ?, ?, ?, ?)""",
                            (receipt_id, item["description"], item["quantity"],
                             item["unit_price_cents"], item["total_cents"], item["sort_order"]),
                        )
                result["imported"] += 1
            else:
                # New order
                db.execute(
                    """INSERT INTO vendor_receipts
                       (vendor, source_id, receipt_date, merchant, total_cents, currency, raw_json, status)
                       VALUES (?, ?, ?, ?, ?, ?, ?, 'pending')""",
                    (
                        VENDOR, order_id,
                        order["receipt"]["receipt_date"],
                        order["receipt"]["merchant"],
                        order["receipt"]["total_cents"],
                        order["receipt"]["currency"],
                        str(order["receipt"]["raw_json"]),
                    ),
                )
                receipt_id = db.execute("SELECT last_insert_rowid()").fetchone()[0]

                for item in order["items"]:
                    db.execute(
                        """INSERT INTO vendor_receipt_items
                           (receipt_id, description, quantity, unit_price_cents, total_cents, sort_order)
                           VALUES (?, ?, ?, ?, ?, ?)""",
                        (receipt_id, item["description"], item["quantity"],
                         item["unit_price_cents"], item["total_cents"], item["sort_order"]),
                    )
                result["imported"] += 1

        except Exception as e:
            result["errors"] += 1
            result["warnings"].append(f"Order {order_id}: {e}")

    if not dry_run:
        db.commit()

    return result


def preview_amazon_csv(path: str | Path) -> dict:
    """Parse and preview an Amazon CSV without importing.

    Returns summary with counts, total, and sample orders.
    """
    rows = _read_csv(path)
    orders = _parse_orders(rows)

    total_cents = sum(
        o["receipt"]["total_cents"] or 0 for o in orders.values()
    )
    items_count = sum(len(o["items"]) for o in orders.values())

    return {
        "order_count": len(orders),
        "item_count": items_count,
        "total_cents": total_cents,
        "currency": "USD",
        "sample_orders": [
            {
                "source_id": oid,
                "date": o["receipt"]["receipt_date"],
                "total_cents": o["receipt"]["total_cents"],
                "item_count": len(o["items"]),
            }
            for oid, o in list(orders.items())[:5]
        ],
        "payment_masks": sorted(set(
            o["payment_mask"] for o in orders.values() if o["payment_mask"]
        )),
    }
