"""Auto-categorizer that learns from user corrections.

Tracks merchant → account frequency and suggests the most-used category.
Stores mappings in a JSON file at the project root.

Usage:
    from app.categorizer import Categorizer
    cat = Categorizer(cfg)
    suggestion = cat.suggest("AMAZON")         # → "Expenses:Supplies"
    cat.learn("AMAZON", "Expenses:Supplies")   # → updates frequency
    cat.correct("AMAZON", "Expenses:Software") # → explicit override + frequency
"""

import json
from collections import defaultdict
from pathlib import Path
from typing import Optional

from .config import Config


class Categorizer:
    """Merchant-to-account learning engine.

    Stores a JSON map of merchant_upper → {account: frequency_count}.
    The most-used account for each merchant is the default suggestion.
    """

    MAP_FILE = "merchant_map.json"

    def __init__(self, cfg: Config):
        self.cfg = cfg
        self._map_path = cfg.project_root / self.MAP_FILE
        self._data = self._load()

    def _load(self) -> dict:
        """Load merchant map from disk."""
        if self._map_path.exists():
            try:
                return json.loads(self._map_path.read_text())
            except (json.JSONDecodeError, Exception):
                return {}
        return {}

    def _save(self):
        """Write merchant map to disk."""
        self._map_path.write_text(json.dumps(self._data, indent=2))

    def suggest(self, merchant: str) -> Optional[str]:
        """Suggest the best account for a merchant.

        Returns the most-frequently-used account, or None if unknown.
        """
        key = merchant.upper().strip()
        if key not in self._data:
            return None
        accounts = self._data[key]
        # Return the account with the highest frequency
        best = max(accounts, key=lambda a: accounts[a])
        return best

    def suggest_with_confidence(self, merchant: str) -> dict:
        """Suggest with confidence level.

        Returns:
            {"account": "Expenses:...", "count": 5, "total": 6, "confidence": "high"}
        """
        key = merchant.upper().strip()
        if key not in self._data:
            return {"account": None, "count": 0, "total": 0, "confidence": "none"}

        accounts = self._data[key]
        total = sum(accounts.values())
        best = max(accounts, key=lambda a: accounts[a])
        count = accounts[best]
        ratio = count / total if total > 0 else 0

        if ratio >= 0.9:
            confidence = "high"
        elif ratio >= 0.6:
            confidence = "medium"
        else:
            confidence = "low"

        return {
            "account": best,
            "count": count,
            "total": total,
            "confidence": confidence,
        }

    def learn(self, merchant: str, account: str):
        """Record a category choice for a merchant.

        Increments the frequency for this merchant+account combo.
        """
        key = merchant.upper().strip()
        if key not in self._data:
            self._data[key] = {}
        accounts = self._data[key]
        accounts[account] = accounts.get(account, 0) + 1
        self._save()

    def correct(self, merchant: str, account: str):
        """Explicitly set the category for a merchant (resets other counts).

        Use when the user explicitly corrects a bad suggestion.
        Sets the chosen account to a high count (10) to dominate future suggestions.
        """
        key = merchant.upper().strip()
        # Set the correct account to high count, reduce others
        self._data[key] = {account: 10}
        self._save()

    def all_rules(self) -> list[dict]:
        """Get all learned rules for display/export.

        Returns list of {merchant, account, count} sorted by count desc.
        """
        rules = []
        for merchant, accounts in sorted(self._data.items()):
            for account, count in sorted(accounts.items(), key=lambda x: -x[1]):
                rules.append({
                    "merchant": merchant,
                    "account": account,
                    "count": count,
                })
        return rules

    def clear(self):
        """Clear all learned rules."""
        self._data = {}
        self._save()

    def to_expense_rules(self) -> list[tuple[str, str]]:
        """Export learned rules as (pattern, account) tuples for config.toml.

        Returns the highest-confidence rule for each merchant.
        """
        rules = []
        for merchant, accounts in self._data.items():
            best = max(accounts, key=lambda a: accounts[a])
            rules.append((merchant, best))
        return rules
