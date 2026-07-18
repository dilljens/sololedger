"""Receipt OCR & expense scanning — extract data from PDF/image receipts.

Scans receipt files (PDFs, images) and extracts:
  - Date
  - Merchant/vendor name
  - Total amount
  - Line items (basic)

Outputs Beancount-ready transaction entries.

Requires:
  - pdfplumber (for PDFs)
  - Pillow + pytesseract (for images)
  - tesseract-ocr system package

Usage:
    from app.receipts import ReceiptScanner
    scanner = ReceiptScanner(config)
    result = scanner.scan("receipt.pdf")
    scanner.to_beancount_entry(result, preview=True)
"""

import datetime
import re
import sys
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger


class ReceiptScanner:
    """Scan receipt PDFs/images and extract transaction data."""

    def __init__(self, cfg: Config):
        self.cfg = cfg

    def scan(self, filepath: str | Path) -> dict:
        """Scan a receipt file and extract structured data.

        Args:
            filepath: Path to receipt PDF or image

        Returns:
            dict with:
              - date: ISO date string or None
              - merchant: Vendor name or None
              - total: Decimal amount or None
              - line_items: list of {"description": str, "amount": Decimal}
              - raw_text: full OCR text
              - success: bool
              - error: str if failed
        """
        path = Path(filepath)
        if not path.exists():
            return {"success": False, "error": f"File not found: {path}"}

        # Determine file type
        ext = path.suffix.lower()

        raw_text = ""
        try:
            if ext in (".pdf",):
                raw_text = self._extract_pdf(path)
            elif ext in (".png", ".jpg", ".jpeg", ".tiff", ".tif", ".bmp", ".webp"):
                raw_text = self._extract_image(path)
            else:
                return {"success": False, "error": f"Unsupported file type: {ext}"}
        except Exception as e:
            return {"success": False, "error": str(e)}

        if not raw_text.strip():
            return {"success": False, "error": "No text could be extracted from the receipt"}

        # Parse structured data from raw text
        parsed = self._parse_receipt(raw_text)
        parsed["raw_text"] = raw_text
        parsed["success"] = True
        return parsed

    def _extract_pdf(self, path: Path) -> str:
        """Extract text from a PDF receipt using pdfplumber."""
        try:
            import pdfplumber
        except ImportError:
            return ""

        text_parts = []
        with pdfplumber.open(str(path)) as pdf:
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    text_parts.append(text)
                # Also try extracting tables
                tables = page.extract_tables()
                for table in tables:
                    for row in table:
                        text_parts.append(" | ".join(cell or "" for cell in row))
        return "\n".join(text_parts)

    def _extract_image(self, path: Path) -> str:
        """Extract text from an image receipt using OCR."""
        try:
            from PIL import Image
            import pytesseract
        except ImportError:
            return ""

        try:
            img = Image.open(str(path))
            # Preprocess: convert to grayscale, increase contrast
            img = img.convert("L")

            # Try to improve OCR with adaptive thresholding
            try:
                import PIL.ImageOps
                img = PIL.ImageOps.autocontrast(img, cutoff=5)
            except Exception:
                pass

            text = pytesseract.image_to_string(img)
            return text
        except Exception as e:
            print(f"⚠  OCR error: {e}", file=sys.stderr)
            return ""

    def _parse_receipt(self, text: str) -> dict:
        """Parse structured data from raw OCR text.

        This is a best-effort parser — receipt formats vary wildly.
        Uses regex patterns to find common elements.
        """
        lines = text.strip().split("\n")
        result = {
            "date": None,
            "merchant": None,
            "total": None,
            "subtotal": None,
            "tax": None,
            "line_items": [],
        }

        # Try to extract date — common formats
        date_patterns = [
            r"(\d{1,2}[/-]\d{1,2}[/-]\d{2,4})",           # 01/15/2026 or 01-15-2026
            r"(\d{4}[/-]\d{2}[/-]\d{2})",                   # 2026-01-15
            r"(\d{1,2}\s+(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{2,4})",
            r"((?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\s+\d{1,2},?\s+\d{4})",
        ]

        for line in lines:
            for pattern in date_patterns:
                m = re.search(pattern, line, re.IGNORECASE)
                if m:
                    try:
                        parsed = self._parse_date(m.group(1))
                        if parsed:
                            result["date"] = parsed.isoformat()
                            break
                    except Exception:
                        pass
            if result["date"]:
                break

        # Try to extract merchant name — usually first non-empty line
        for line in lines[:5]:
            cleaned = line.strip()
            if not cleaned:
                continue
            # Skip date-only lines, pure numbers, phone numbers
            if re.match(r"^\d{1,2}[/-]\d{1,2}[/-]\d{2,4}", cleaned):
                continue
            if re.match(r"^\d{3}[-.]?\d{3}[-.]?\d{4}", cleaned):
                continue
            if re.match(r"^(tax|subtotal|total|change|cash|credit|debit|receipt|invoice|thank)", cleaned, re.IGNORECASE):
                continue
            # Skip separator lines
            if re.match(r"^[\s\-_=*]+$", cleaned):
                continue
            result["merchant"] = cleaned[:60]
            break

        # Parse amounts more carefully — only match at line end
        # Real dollar amounts: optional $ prefix, digits, optional decimal
        amount_re = re.compile(r'(?:^|\s+)[\$]?\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*$')
        # Also match when amount is right-aligned with spaces
        amount_re_loose = re.compile(r'(?:^|\s)[\$]?\s*(\d{1,3}(?:,\d{3})*\.\d{2})\s*$')

        # Collect all lines with dollar amounts for cross-referencing
        amount_lines = []
        for i, line in enumerate(lines):
            m = amount_re.search(line) or amount_re_loose.search(line)
            if m:
                val = Decimal(m.group(1).replace(",", ""))
                if 0 < val < 10_000_000:  # sanity check
                    amount_lines.append((i, line.strip(), val))

        # Find TOTAL, SUBTOTAL, TAX by label
        for i, line, val in amount_lines:
            lower = line.lower()
            if re.search(r'\btotal\b', lower) and not re.search(r'\bsubtotal\b', lower):
                # The largest total-like value is the grand total
                if result["total"] is None or val > result["total"]:
                    result["total"] = val
            elif re.search(r'\bsubtotal\b', lower):
                if result["subtotal"] is None or val > result["subtotal"]:
                    result["subtotal"] = val
            elif re.search(r'\btax\b', lower) and not re.search(r'\btax\s*(?:id|#|rate)', lower):
                if result["tax"] is None or val > result["tax"]:
                    result["tax"] = val

        # If still no total, take the largest amount not in header/footer
        if result["total"] is None and amount_lines:
            # Filter to lines below the first separator or after first few lines
            header_end = 3  # skip header
            candidate_lines = [(i, l, v) for i, l, v in amount_lines if i >= header_end]
            # Exclude known labels
            non_label = [(i, l, v) for i, l, v in candidate_lines
                         if not re.search(r'\b(tax|subtotal|change|cash|credit)\b', l.lower())]
            if non_label:
                # Take the largest amount (usually the total)
                result["total"] = max(v for _, _, v in non_label)
            elif candidate_lines:
                result["total"] = max(v for _, _, v in candidate_lines)

        # Extract line items — lines with amounts that aren't total/subtotal/tax
        seen_amounts = set()
        for i, line, val in amount_lines:
            lower = line.lower()
            if re.search(r'\b(total|subtotal|tax|change|cash|credit|debit|visa|mastercard|amex|discover)\b', lower):
                continue
            # Deduplicate by amount
            amt_key = f"{val:.2f}"
            if amt_key in seen_amounts:
                continue
            seen_amounts.add(amt_key)

            # Extract description: everything before the amount
            line_clean = re.sub(r'\s+', ' ', line)
            # Remove trailing amount from the line
            desc = amount_re.sub('', line_clean).strip()
            if not desc or desc == line_clean:
                desc = amount_re_loose.sub('', line_clean).strip()
            desc = desc.strip()

            if desc and len(desc) >= 2:
                result["line_items"].append({
                    "description": desc[:80],
                    "amount": val,
                })

        # If no total found but line items exist, sum them
        if result["total"] is None and result["line_items"]:
            total = sum(item["amount"] for item in result["line_items"])
            result["total"] = Decimal(str(total)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return result

    def _parse_date(self, raw: str) -> Optional[datetime.date]:
        """Try to parse a date string."""
        # Strip day-of-week prefix
        raw = re.sub(r'^(Mon|Tue|Wed|Thu|Fri|Sat|Sun)[a-z]*,\s*', '', raw, flags=re.IGNORECASE)
        raw = raw.strip()

        formats = [
            "%Y-%m-%d",
            "%m/%d/%Y",
            "%m/%d/%y",
            "%m-%d-%Y",
            "%m-%d-%y",
            "%d %b %Y",
            "%d %B %Y",
            "%b %d, %Y",
            "%B %d, %Y",
            "%b %d %Y",
            "%B %d %Y",
        ]
        for fmt in formats:
            try:
                return datetime.datetime.strptime(raw, fmt).date()
            except ValueError:
                continue
        return None

    def _extract_amount(self, text: str) -> Optional[Decimal]:
        """Extract a dollar amount from text."""
        # Match patterns like $12.34, 12.34, $1,234.56
        m = re.search(r'[\$]?\s*(\d{1,3}(?:,\d{3})*(?:\.\d{2})?)', text)
        if m:
            try:
                val = Decimal(m.group(1).replace(",", ""))
                if val > 0 and val < 10_000_000:  # Sanity check
                    return val
            except Exception:
                pass
        return None

    def to_beancount_entry(self, result: dict, account: Optional[str] = None, preview: bool = True) -> Optional[str]:
        """Convert a scanned receipt to a Beancount transaction entry string.

        Args:
            result: Output from scan()
            account: The expense account to use (auto-categorized if None)
            preview: If True, just print the entry without writing

        Returns:
            The Beancount entry string if one was generated, None if not.
        """
        if not result.get("success") or result.get("total") is None:
            print("⚠  Cannot generate entry: receipt has no total or scan failed")
            return None

        merchant = result.get("merchant") or "Unknown Merchant"
        date = result.get("date") or datetime.date.today().isoformat()
        total = result["total"]

        # Auto-categorize using config rules
        if account is None and self.cfg:
            account = self._categorize(merchant)
        elif account is None:
            account = "Expenses:Miscellaneous"

        # Build postings
        lines = [
            f'{date} * "{merchant}" "Receipt scan: {merchant[:60]}"',
            f"  {account:45s}  {total:.2f} USD",
            f"  {self.cfg.checking_account:45s}  -{total:.2f} USD" if self.cfg else f"  Assets:Bank:Checking  -{total:.2f} USD",
        ]

        entry = "\n".join(lines) + "\n\n"

        if preview:
            print("═══ Receipt Entry (preview) ═══")
            print(entry)
            print(f"(Would append to ledger for merchant: {merchant}, total: ${total:,.2f})")

        return entry

    def _categorize(self, merchant: str) -> str:
        """Categorize a merchant using config expense rules."""
        desc_upper = merchant.upper()
        for pattern, account in self.cfg.expense_rules:
            if pattern in desc_upper:
                return account
        return "Expenses:Miscellaneous"

    def process_file(self, filepath: str | Path, preview: bool = True) -> dict:
        """High-level: scan a receipt file and preview/append the entry.

        Args:
            filepath: Path to receipt file
            preview: If True, just show (don't write)

        Returns:
            dict with scan result and entry status
        """
        result = self.scan(filepath)
        if not result["success"]:
            print(f"⚠  Scan failed: {result.get('error', 'unknown error')}")
        return result

    def attach(self, filepath: str | Path, date: str, account: str,
               link_txn: bool = True) -> dict:
        """Attach a receipt file to the ledger as a document directive.

        Copies the receipt to a structured documents directory and adds a
        Beancount document directive linking it to the specified account/date.

        Args:
            filepath: Path to receipt PDF or image
            date: Date string (YYYY-MM-DD) matching the transaction
            account: Beancount account the document belongs to
            link_txn: If True, also scan + append the receipt as a transaction

        Returns:
            dict with success, document_path, entry fields
        """
        src = Path(filepath)
        if not src.exists():
            return {"success": False, "error": f"File not found: {src}"}

        # Build documents directory: docs/receipts/YYYY/account/
        docs_dir = self.cfg.ledger_dir / "documents" / "receipts" / date[:4] / account.replace(":", "_")
        docs_dir.mkdir(parents=True, exist_ok=True)

        # Copy file with date prefix for sorting
        dest = docs_dir / f"{date}_{src.name}"
        import shutil
        shutil.copy2(src, dest)

        # Add document directive to ledger
        ledger = Ledger(self.cfg)
        entry = ledger.document(
            date=datetime.date.fromisoformat(date),
            account=account,
            filepath=dest,
        )

        result = {
            "success": True,
            "document_path": str(dest),
            "entry": entry.strip(),
        }

        if link_txn:
            scan_result = self.scan(filepath)
            if scan_result.get("success") and scan_result.get("total"):
                ledger.append(
                    date=datetime.date.fromisoformat(date),
                    payee=scan_result.get("merchant") or "Unknown",
                    narration=f"Receipt: {scan_result.get('merchant', 'Unknown')[:80]}",
                    postings=[
                        (account, f"{scan_result['total']:.2f} USD"),
                        (self.cfg.checking_account, f"-{scan_result['total']:.2f} USD"),
                    ],
                )
                result["transaction_appended"] = True

        ledger.reload(force=True)
        return result

    def list_attached(self, year: str = "") -> list[dict]:
        """List all receipt documents attached to the ledger.

        Scans the ledger's document directives.

        Args:
            year: Optional year filter (YYYY)

        Returns:
            List of {date, account, path} dicts.
        """
        docs = []
        try:
            entries = self.cfg.ledger_dir / "transactions.beancount"
            text = entries.read_text()
            for line in text.splitlines():
                line = line.strip()
                # Match: YYYY-MM-DD document Account "/path/to/file"
                m = re.match(r'^(\d{4}-\d{2}-\d{2})\s+document\s+([\w:]+)\s+"([^"]+)"', line)
                if m:
                    doc_date = m.group(1)
                    if year and not doc_date.startswith(year):
                        continue
                    docs.append({
                        "date": doc_date,
                        "account": m.group(2),
                        "path": m.group(3),
                    })
        except Exception:
            pass
        return docs

        print(f"  Merchant: {result.get('merchant', 'Unknown')}")
        print(f"  Date:     {result.get('date', 'Unknown')}")
        print(f"  Total:    ${result.get('total', 0):,.2f}")
        if result.get("line_items"):
            print(f"  Items:    {len(result['line_items'])}")
            for item in result["line_items"][:5]:
                print(f"    · {item['description'][:40]:40s} ${item['amount']:>8,.2f}")
            if len(result["line_items"]) > 5:
                print(f"    ... and {len(result['line_items']) - 5} more")

        if not preview and result["total"] is not None:
            ledger = Ledger(self.cfg) if self.cfg else None
            entry = self.to_beancount_entry(result, preview=False)
            if entry and ledger:
                # Parse the entry and append
                # Extract fields from the generated entry
                lines = entry.strip().split("\n")
                first = lines[0]
                date_str = first[:10]
                # ... would need proper beancount parsing
                # For now, use the ledger.append method
                ledger.append(
                    date=datetime.date.fromisoformat(result["date"]) if result.get("date") else datetime.date.today(),
                    payee=result.get("merchant") or "Unknown",
                    narration=f"Receipt: {result.get('merchant', 'Unknown')[:80]}",
                    postings=[
                        (account, f"{result['total']:.2f} USD"),
                        (self.cfg.checking_account, f"-{result['total']:.2f} USD"),
                    ],
                )
                print(f"✓ Entry appended to ledger")
                result["appended"] = True

        return result
