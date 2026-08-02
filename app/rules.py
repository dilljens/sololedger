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

    def __init__(self, rules_path: str | Path | None = None, db=None):
        if rules_path is None:
            rules_path = Path(__file__).resolve().parent.parent / "categorization_rules.toml"
        self._path = Path(rules_path)
        self._db = db  # optional TenantDB — DB-defined rules are merged in
        self._rules: list[dict] = []
        self._loaded = False

    @staticmethod
    def _safe_pattern(pattern: str) -> Optional[re.Pattern]:
        """Compile a user regex with ReDoS guards. Returns None if unsafe."""
        if not pattern:
            return None
        # Reject patterns longer than 200 chars or with nested quantifiers
        if len(pattern) > 200 or re.search(r'\(\.[*+]\)\{|\(\.[*+]\)\+|\(\?:\.[*+]\)\{|\+[?+*}]', pattern):
            return None
        try:
            return re.compile(pattern, re.IGNORECASE)
        except re.error:
            return None

    def _compile_for_matcher(self, pattern: str, matcher_type: str) -> Optional[re.Pattern]:
        """Compile a DB rule pattern according to its matcher type."""
        if matcher_type == "regex":
            return self._safe_pattern(pattern)
        if matcher_type == "eq":
            return self._safe_pattern(r"^" + re.escape(pattern) + r"$")
        if matcher_type == "substring":
            return self._safe_pattern(re.escape(pattern))
        # 'range' requires amount context — not supported by this engine
        return None

    def load(self):
        """Load and compile rules from the TOML file, then DB rules (if any).

        DB rules (user-created via the API) are evaluated FIRST — they
        carry an explicit priority (higher = first) and are the user's
        explicit instructions. TOML rules are the fallback baseline.
        """
        if self._loaded:
            return
        self._rules = []

        # 1) DB-defined rules (user-created via the rules API)
        if self._db is not None:
            try:
                rows = self._db.execute(
                    "SELECT id, matcher_type, pattern, target_account, priority, description "
                    "FROM categorization_rules WHERE is_active = 1 "
                    "ORDER BY priority DESC, id ASC"
                ).fetchall()
                for row in rows:
                    compiled = self._compile_for_matcher(row["pattern"], row["matcher_type"])
                    if compiled is None:
                        continue
                    self._rules.append({
                        "name": f"db-{row['id']}",
                        "account": row["target_account"],
                        "confidence": 0.9,
                        "patterns": [row["pattern"]],
                        "compiled": [compiled],
                        "description": row["description"] or "",
                        "priority": row["priority"],
                    })
            except Exception:
                pass  # DB unavailable — fall back to TOML rules only

        # 2) TOML file rules
        if not self._path.exists():
            self._loaded = True
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
                safe = self._safe_pattern(p)
                if safe is not None:
                    compiled.append(safe)

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
