"""Three-tier merchant categorizer: exact → pattern → embedding.

First checks the learned merchant map (exact merchant name match).
Then falls through to the pattern rules engine (regex/substring rules).
Finally tries embedding similarity (semantic match against known merchants).

Usage:
    from app.categorizer import Categorizer
    cat = Categorizer(cfg)
    cat.suggest("AMAZON WEB SERVICES")          # exact match
    cat.suggest("UBER TRIP")                    # pattern match
    cat.suggest("SOME NOVEL MERCHANT")          # embedding match
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

from .config import Config


# Lazy-loaded singletons
_RULES_ENGINE = None
_EMBED_CATEGORIZER = None


def _get_rules_engine():
    global _RULES_ENGINE
    if _RULES_ENGINE is None:
        from app.rules import RulesEngine
        _RULES_ENGINE = RulesEngine()
    return _RULES_ENGINE


def _get_embed_categorizer():
    global _EMBED_CATEGORIZER
    if _EMBED_CATEGORIZER is None:
        from app.categorizer_embed import EmbedCategorizer
        _EMBED_CATEGORIZER = EmbedCategorizer()
    return _EMBED_CATEGORIZER


class Categorizer:
    """Three-tier merchant categorizer.

    Tier 1 — Exact merchant map (fast, learned from corrections)
    Tier 2 — Pattern rules (regex/substring, generated from training data)
    Tier 3 — Embedding similarity (semantic, covers novel merchants)

    Tiers 2 and 3 are activated via use_patterns and use_embedding flags
    respectively. Both default to True for the full cascade.
    """

    MAP_FILE = "merchant_map.json"

    def __init__(
        self,
        cfg: Config,
        use_patterns: bool = True,
        use_embedding: bool = True,
    ):
        self.cfg = cfg
        self.use_patterns = use_patterns
        self.use_embedding = use_embedding
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

    # ── Tier 1: exact merchant match ────────────────────────────────────

    def _exact_suggest(self, merchant: str) -> Optional[str]:
        key = merchant.upper().strip()
        if key in self._data:
            accounts = self._data[key]
            return max(accounts, key=lambda a: accounts[a])
        return None

    def _exact_suggest_with_confidence(self, merchant: str) -> dict:
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
            "tier": "exact",
        }

    # ── Tier 2: pattern rules ───────────────────────────────────────────

    def _pattern_suggest(self, merchant: str) -> Optional[str]:
        if not self.use_patterns:
            return None
        try:
            rules = _get_rules_engine()
            result = rules.match(merchant)
            return result["account"] if result else None
        except Exception:
            return None

    def _pattern_suggest_with_confidence(self, merchant: str) -> dict:
        if not self.use_patterns:
            return {"account": None, "count": 0, "total": 0, "confidence": "none"}
        try:
            rules = _get_rules_engine()
            result = rules.match(merchant)
            if result is None:
                return {"account": None, "count": 0, "total": 0, "confidence": "none"}

            ratio = result["confidence"]
            if ratio >= 0.9:
                label = "high"
            elif ratio >= 0.6:
                label = "medium"
            else:
                label = "low"

            return {
                "account": result["account"],
                "count": 1,
                "total": 1,
                "confidence": label,
                "tier": "pattern",
                "rule": result["rule"],
            }
        except Exception:
            return {"account": None, "count": 0, "total": 0, "confidence": "none"}

    # ── Tier 3: embedding similarity ────────────────────────────────────

    def _embed_suggest(self, merchant: str) -> Optional[str]:
        if not self.use_embedding:
            return None
        try:
            cat = _get_embed_categorizer()
            result = cat.suggest(merchant)
            return result.get("account")
        except Exception:
            return None

    def _embed_suggest_with_confidence(self, merchant: str) -> dict:
        if not self.use_embedding:
            return {"account": None, "count": 0, "total": 0, "confidence": "none"}
        try:
            cat = _get_embed_categorizer()
            return cat.suggest_with_confidence(merchant)
        except Exception:
            return {"account": None, "count": 0, "total": 0, "confidence": "none"}

    # ── Public API ──────────────────────────────────────────────────────

    def suggest(self, merchant: str) -> Optional[str]:
        """Three-tier cascade: exact → pattern → embedding.

        Returns the first matching account, or None if all tiers miss.
        """
        result = self._exact_suggest(merchant)
        if result:
            return result

        result = self._pattern_suggest(merchant)
        if result:
            return result

        return self._embed_suggest(merchant)

    def suggest_with_confidence(self, merchant: str) -> dict:
        """Three-tier cascade with confidence info.

        Returns: dict with keys account, count, total, confidence, tier
        """
        result = self._exact_suggest_with_confidence(merchant)
        if result["account"]:
            return result

        result = self._pattern_suggest_with_confidence(merchant)
        if result["account"]:
            return result

        return self._embed_suggest_with_confidence(merchant)

    def learn(self, merchant: str, account: str):
        """Record a category choice for a merchant.

        Increments the frequency for this merchant+account combo.
        Over time, learned exact matches dominate the cascade.
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
        Sets the chosen account to dominate future suggestions.
        """
        key = merchant.upper().strip()
        self._data[key] = {account: 10}
        self._save()

    def all_rules(self) -> list[dict]:
        """Get all learned merchant-map entries for display/export."""
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
        """Clear all learned merchant-map entries."""
        self._data = {}
        self._save()

    def to_expense_rules(self) -> list[tuple[str, str]]:
        """Export learned rules as (pattern, account) tuples."""
        rules = []
        for merchant, accounts in self._data.items():
            best = max(accounts, key=lambda a: accounts[a])
            rules.append((merchant, best))
        return rules
