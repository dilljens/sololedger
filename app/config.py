"""Load business configuration from config.toml and environment."""

import os
import sys
from pathlib import Path

try:
    import tomllib  # Python 3.11+
except ImportError:
    import tomli as tomllib  # fallback


class Config:
    """Holds all business configuration."""

    def __init__(self, path: str | None = None):
        if path is None:
            # Walk up from cwd or script dir looking for config.toml
            path = self._find_config()

        with open(path, "rb") as f:
            raw = tomllib.load(f)

        self._raw = raw

        # Business info
        biz = raw["business"]
        self.business_name = biz["name"]
        self.owner = biz["owner"]
        self.state = biz["state"]
        self.ein = biz["ein"]
        self.address = biz["address"]
        self.phone = biz["phone"]
        self.email = biz["email"]

        # Ledger
        ledger_rel = raw["ledger"]["path"]
        self.ledger_path = (Path(path).parent / ledger_rel).resolve()

        # Account mappings
        accts = raw["accounts"]
        self.checking_account = accts["checking"]
        self.ar_account = accts["ar"]
        self.income_account = accts["income"]
        self.draws_account = accts["owner_draws"]

        # Expense rules
        self.expense_rules = [
            (r["pattern"].upper(), r["account"])
            for r in raw.get("expense_rules", [])
        ]
        self.income_rules = [
            (r["pattern"].upper(), r["account"])
            for r in raw.get("income_rules", [])
        ]

        # Tax
        t = raw["tax"]
        self.standard_deduction = t["standard_deduction"]
        self.brackets = [dict(b) for b in t["brackets"]]
        se = t["self_employment"]
        self.se_ss_rate = se["rate_social_security"]
        self.se_med_rate = se["rate_medicare"]
        self.ss_wage_base = se["ss_wage_base"]
        self.se_deduction_ratio = se["deduction_ratio"]

        # Tax state (default: WY)
        self.state_code = raw.get("tax", {}).get("state", "WY").upper()

        # Payments
        pmts = raw.get("payments", {})
        self.stripe_enabled = pmts.get("stripe_enabled", False)

        self._project_root = Path(path).parent

    def _find_config(self) -> Path:
        """Walk up from CWD looking for config.toml."""
        start = Path.cwd()
        for parent in [start] + list(start.parents):
            candidate = parent / "config.toml"
            if candidate.exists():
                return candidate
        print(
            "ERROR: config.toml not found. Run from the project directory.",
            file=sys.stderr,
        )
        sys.exit(1)

    @property
    def project_root(self) -> Path:
        return self._project_root

    @property
    def ledger_dir(self) -> Path:
        return self.ledger_path.parent

    @property
    def output_dir(self) -> Path:
        return self.project_root / "output"

    @property
    def invoices_dir(self) -> Path:
        p = self.output_dir / "invoices"
        p.mkdir(parents=True, exist_ok=True)
        return p

    @property
    def imports_dir(self) -> Path:
        p = self.project_root / "imports"
        p.mkdir(parents=True, exist_ok=True)
        return p
