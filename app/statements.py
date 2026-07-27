"""PDF statement filing — extract text, classify by institution, file to canonical layout.

Uses pdfplumber (already installed) for PDF text extraction.
Stores metadata in SQLite statements table.
"""
import re
import shutil
from datetime import datetime
from pathlib import Path
from typing import Optional

from app.db import TenantDB

# ─── Institution classifiers ─────────────────────────────────────────────

# Map of institution name → (pattern to match in PDF text, canonical folder name)
_INSTITUTION_SIGNATURES: list[tuple[str, str]] = [
    (r"WELLS FARGO", "wells_fargo"),
    (r"WELLS FARGO BANK", "wells_fargo"),
    (r"CITI[^c]|CITIBANK", "citi"),
    (r"CHASE", "chase"),
    (r"BANK OF AMERICA", "bank_of_america"),
    (r"CAPITAL ONE", "capital_one"),
    (r"AMERICAN EXPRESS|AMEX", "amex"),
    (r"U\.?S\.?\s*BANK", "us_bank"),
]


def classify_institution(text: str) -> Optional[str]:
    """Classify a PDF statement's institution from its text content."""
    upper = text.upper()
    for pattern, name in _INSTITUTION_SIGNATURES:
        if re.search(pattern, upper):
            return name
    return None


def detect_period(text: str) -> tuple[Optional[str], Optional[str]]:
    """Extract statement period from PDF text. Returns (start_date, end_date)."""
    # Patterns: "January 1, 2026 through January 31, 2026"
    # "01/01/2026 - 01/31/2026"
    # "Statement Period: Jan 1 to Jan 31, 2026"
    patterns = [
        r"(?:through|to)\s+(\w+\s+\d+,?\s*\d{4})",  # end date after "through"/"to"
        r"(\d{2}/\d{2}/\d{4})\s*[-–to]+\s*(\d{2}/\d{2}/\d{4})",
        r"(?:Statement|Period|Closing Date).*?(\w+\s+\d+,?\s*\d{4})",
    ]
    for pat in patterns:
        m = re.search(pat, text, re.IGNORECASE)
        if m and len(m.groups()) >= 2:
            return (m.group(1), m.group(2))
        if m:
            return (None, m.group(1))
    return (None, None)


def file_statement(
    db: TenantDB,
    pdf_path: str | Path,
    institution: Optional[str] = None,
    account_mask: Optional[str] = None,
    period: Optional[str] = None,
) -> dict:
    """File a PDF statement to the canonical location and record metadata.

    Args:
        db: TenantDB instance
        pdf_path: Path to the PDF statement
        institution: Override institution name (auto-detected if None)
        account_mask: Account mask (last 4 digits)
        period: Period string (e.g., "2026-01")

    Returns:
        dict with success, filed_path, institution, metadata
    """
    src = Path(pdf_path).resolve()
    if not src.exists():
        return {"success": False, "error": "File not found"}

    # Extract text for classification
    text = ""
    try:
        import pdfplumber
        with pdfplumber.open(str(src)) as pdf:
            for page in pdf.pages[:3]:  # Read first 3 pages for classification
                t = page.extract_text()
                if t:
                    text += t + "\n"
    except Exception as e:
        return {"success": False, "error": f"PDF read failed: {e}"}

    # Classify
    detected_institution = institution or classify_institution(text) or "unknown"
    start_date, end_date = detect_period(text)
    period_str = period or (end_date[:7] if end_date and len(end_date) >= 7 else "unknown")

    # Build canonical path: documents/statements/{institution}/{mask or period}/{filename}
    docs_dir = Path("documents") / "statements" / detected_institution
    if account_mask:
        docs_dir = docs_dir / account_mask
    docs_dir = docs_dir / period_str
    docs_dir.mkdir(parents=True, exist_ok=True)

    # Copy file with date prefix
    dest = docs_dir / src.name
    shutil.copy2(str(src), str(dest))

    # Record in SQLite
    try:
        db.execute(
            "INSERT OR IGNORE INTO import_batches (source, account, filename, status) VALUES (?, ?, ?, ?)",
            ("statement", detected_institution, src.name, "filed"),
        )
        db.commit()
    except Exception:
        pass

    return {
        "success": True,
        "filed_path": str(dest),
        "institution": detected_institution,
        "period": period_str,
        "page_count": len(text) > 0,
    }
