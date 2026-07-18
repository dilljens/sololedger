"""Pattern-based categorization rules engine for SoloLedger.

Operates between exact merchant matching (Categorizer) and
embedding similarity (EmbedCategorizer) — the second tier of the cascade.

Loads rules from a TOML file. Each rule has a regex or substring pattern
and a target Beancount account. Rules are evaluated in order, first match wins.

Usage:
    from app.rules import RulesEngine
    rules = RulesEngine()
    result = rules.match("AMAZON WEB SERVICES")
    # → {"account": "Expenses:Software:SaaS", "confidence": 0.85,
    #    "rule": "aws", "matched_on": "AMAZON.*AWS"}
"""

from __future__ import annotations

import re
import tomllib
from pathlib import Path
from typing import Any, Optional


class RulesEngine:
    """Pattern rule engine. Evaluates rules in order, first match wins.

    Rules are stored in a TOML file like:
        [rules.aws]
        patterns = ["AMAZON.*AWS", "AWS BILLING"]
        account = "Expenses:Software:SaaS"
        confidence = 0.85
        description = "Amazon Web Services"

        [rules.uber]
        patterns = ["UBER.*TRIP", "UBER.*RIDE"]
        account = "Expenses:Travel"
        confidence = 0.90
        description = "Uber rides"
    """

    def __init__(self, rules_path: str | Path | None = None):
        if rules_path is None:
            rules_path = Path(__file__).resolve().parent.parent / "categorization_rules.toml"
        self._path = Path(rules_path)
        self._rules: list[dict] = []
        self._loaded = False

    def load(self):
        """Load and compile rules from the TOML file."""
        if self._loaded:
            return
        self._rules = []

        if not self._path.exists():
            return

        with open(self._path, "rb") as f:
            data = tomllib.load(f)

        rules_section = data.get("rules", {})
        for name, rule in sorted(rules_section.items()):
            patterns = rule.get("patterns", [])
            if isinstance(patterns, str):
                patterns = [patterns]

            compiled = []
            for p in patterns:
                if not p:
                    continue
                try:
                    compiled.append(re.compile(p, re.IGNORECASE))
                except re.error as e:
                    continue

            if compiled:
                self._rules.append({
                    "name": name,
                    "account": rule["account"],
                    "confidence": float(rule.get("confidence", 0.8)),
                    "patterns": rule["patterns"],
                    "compiled": compiled,
                    "description": rule.get("description", ""),
                })

        self._loaded = True

    def match(self, merchant: str) -> Optional[dict[str, Any]]:
        """Evaluate rules against a merchant name, first match wins.

        Args:
            merchant: Raw merchant description from bank feed.

        Returns:
            dict with keys: account, confidence, rule, matched_on, description
            or None if no rule matches.
        """
        self.load()

        if not merchant:
            return None

        for rule in self._rules:
            for regex in rule["compiled"]:
                m = regex.search(merchant)
                if m:
                    return {
                        "account": rule["account"],
                        "confidence": rule["confidence"],
                        "rule": rule["name"],
                        "matched_on": m.group()[:60],
                        "description": rule["description"],
                    }

        return None

    def all_rules(self) -> list[dict]:
        """Return all loaded rules (for display/debug)."""
        self.load()
        return [
            {
                "name": r["name"],
                "account": r["account"],
                "confidence": r["confidence"],
                "patterns": r["patterns"],
                "description": r["description"],
            }
            for r in self._rules
        ]

    def reload(self):
        """Force reload rules from disk."""
        self._loaded = False
        self.load()
