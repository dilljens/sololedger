#!/usr/bin/env python3
"""Generate categorization_rules.toml for SoloLedger from the merchant map.

Reads the merchant_map.json and generates a categorization_rules.toml with
regex patterns for each merchant, grouped by target account.

Usage:
    python scripts/generate_rules_toml.py [--input merchant_map.json]
"""

import json
import re
import sys
from collections import defaultdict
from pathlib import Path


# MCC → SoloLedger Beancount account mapping
MCC_TO_ACCOUNT = {
    "7372": "Expenses:Software:SaaS",
    "5734": "Expenses:Software:SaaS",
    "4816": "Expenses:Software:Hosting",
    "4815": "Expenses:Software:Hosting",
    "5732": "Expenses:Hardware",
    "5045": "Expenses:Hardware",
    "4814": "Expenses:Phone",
    "4821": "Expenses:Internet",
    "4900": "Expenses:Internet",
    "4899": "Expenses:Software:Hosting",
    "3012": "Expenses:Travel",
    "3021": "Expenses:Travel",
    "3030": "Expenses:Travel",
    "3031": "Expenses:Travel",
    "3041": "Expenses:Travel",
    "3501": "Expenses:Travel",
    "3502": "Expenses:Travel",
    "3503": "Expenses:Travel",
    "3662": "Expenses:Travel",
    "3816": "Expenses:Travel",
    "4121": "Expenses:Travel",
    "7512": "Expenses:Travel",
    "4582": "Expenses:Travel",
    "4784": "Expenses:Travel",
    "5541": "Expenses:Travel",
    "7523": "Expenses:Travel",
    "5812": "Expenses:Meals",
    "5813": "Expenses:Meals",
    "5814": "Expenses:Meals",
    "5815": "Expenses:Meals",
    "5943": "Expenses:Supplies",
    "5944": "Expenses:Supplies",
    "1520": "Expenses:Supplies",
    "8911": "Expenses:ProfessionalServices",
    "8931": "Expenses:ProfessionalServices",
    "6300": "Expenses:Insurance",
    "6520": "Expenses:BankFees",
    "6012": "Expenses:BankFees",
    "6529": "Expenses:BankFees",
    "4215": "Expenses:Supplies",
    "8299": "Expenses:ProfessionalServices",
    "8641": "Expenses:ProfessionalServices",
    "5968": "Expenses:Software:SaaS",
    "5311": "Expenses:Supplies",
    "5411": "Expenses:Supplies",
    "5999": "Expenses:Miscellaneous",
    "7399": "Expenses:Miscellaneous",
    "8398": "Expenses:Miscellaneous",
    "6011": "Expenses:BankFees",
    "6530": "Expenses:ProfessionalServices",
    "6110": "Expenses:Travel",
    "6640": "Expenses:Supplies",
    "6710": "Expenses:ProfessionalServices",
    "6720": "Expenses:ProfessionalServices",
    "6600": "Expenses:Supplies",
}


def merchant_to_pattern(name: str) -> str:
    """Convert a merchant name to a flexible regex pattern.

    Returns a regex string safe for double-quoted TOML strings
    (backslashes are properly escaped). Handles common variations:
    spaces, dots, dashes, invoice refs.
    """
    # Strip apostrophes (simplifies both regex and TOML)
    name = name.replace("'", "")
    # Escape for regex
    escaped = re.escape(name)
    # Allow optional spaces/dashes/dots between words
    flexible = escaped.replace(r"\ ", r"[.\s-]*")
    # Double backslashes for TOML double-quoted string safety
    return flexible.replace("\\", "\\\\")


def generate_rules_from_map(merchant_map: dict) -> str:
    """Generate TOML rules content from a merchant map."""
    lines = [
        "# Auto-generated categorization rules for SoloLedger",
        "# Generated from merchant_map.json — edit the map, not this file.",
        "# Format:",
        "#   [rules.<name>]",
        "#   patterns = ['regex1', 'regex2']",
        "#   account = 'Expenses:Category'",
        "#   confidence = 0.85",
        "#   description = 'Human readable'",
        "",
        "[rules]",
    ]

    # Group by account for cleaner output
    by_account: dict[str, list[tuple[str, str, int]]] = defaultdict(list)

    for merchant, accounts in sorted(merchant_map.items()):
        if not accounts:
            continue
        best_account = max(accounts, key=lambda a: accounts[a])
        count = accounts[best_account]
        by_account[best_account].append((merchant, best_account, count))

    rule_index = 0
    for account in sorted(by_account.keys()):
        entries = by_account[account]
        lines.append(f"")
        lines.append(f"  # ── {account} ({len(entries)} merchants) ──")
        lines.append(f"")

        for merchant, acct, count in entries:
            rule_index += 1
            name = re.sub(r"[^a-z0-9]+", "_", merchant.lower()).strip("_")[:40]
            if not name:
                name = f"rule_{rule_index}"

            pattern = merchant_to_pattern(merchant)
            # Also add a substring-style pattern — the uppercase name
            up = merchant.upper().strip()

            # Only include high-confidence entries
            confidence = min(0.85, 0.5 + (count / 20))

            lines.append(f"  [rules.{name}]")
            lines.append(f'    patterns = ["{pattern}"]')
            lines.append(f'    account = "{acct}"')
            lines.append(f"    confidence = {confidence:.2f}")
            # Use single quotes for TOML strings to avoid escape issues
            safe_desc = merchant[:60].replace("'", "").replace("\\", "")
            lines.append(f"    description = '{safe_desc}'")
            lines.append(f"")

    return "\n".join(lines)


def main():
    project_root = Path(__file__).resolve().parent.parent
    input_path = project_root / "merchant_map.json"
    output_path = project_root / "categorization_rules.toml"

    if not input_path.exists():
        print(f"Error: {input_path} not found", file=sys.stderr)
        sys.exit(1)

    with open(input_path) as f:
        merchant_map = json.load(f)

    content = generate_rules_from_map(merchant_map)

    with open(output_path, "w") as f:
        f.write(content)

    # Count rules
    rule_count = content.count("[rules.")
    print(f"Generated {rule_count} rules → {output_path}")


if __name__ == "__main__":
    main()
