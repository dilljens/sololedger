"""Load business configuration from config.toml and environment."""

import os
import sys
from decimal import Decimal
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
        # Safety: ledger path should be within the config's project directory
        _cfg_dir = Path(path).resolve().parent
        if not str(self.ledger_path).startswith(str(_cfg_dir)):
            import warnings
            warnings.warn(f"Ledger path {self.ledger_path} is outside config directory {_cfg_dir}")

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

        # Tax (optional with defaults — a config that omits [tax] must not 500)
        t = raw.get("tax", {})
        self.standard_deduction = t.get("standard_deduction", 14600)
        self.brackets = [dict(b) for b in t.get("brackets", [])]
        se = t.get("self_employment", {})
        self.se_ss_rate = se.get("rate_social_security", 0.124)
        self.se_med_rate = se.get("rate_medicare", 0.029)
        self.ss_wage_base = se.get("ss_wage_base", 184800)
        self.se_deduction_ratio = se.get("deduction_ratio", 0.9235)

        # Tax state (default: WY)
        self.state_code = raw.get("tax", {}).get("state", "WY").upper()

        # Entity type: smllc (Schedule C, default) or scorp (1120-S)
        ent = raw.get("entity", {})
        raw_type = ent.get("entity_type", "smllc")
        if raw_type not in ("smllc", "scorp"):
            import warnings
            warnings.warn(f"Unknown entity_type '{raw_type}', falling back to 'smllc'")
            raw_type = "smllc"
        self.entity_type = raw_type
        # S-Corp salary & payroll frequency (no-ops in SMLLC mode)
        self.reasonable_salary = Decimal(str(ent.get("reasonable_salary", 0)))
        self.payroll_frequency = ent.get("payroll_frequency", "monthly")

        # Payments
        pmts = raw.get("payments", {})
        self.stripe_enabled = pmts.get("stripe_enabled", False)

        self._project_root = Path(path).parent

    def _find_config(self) -> Path:
        """Walk up from CWD or script dir looking for config.toml."""
        # Try script directory first
        script_dir = Path(__file__).resolve().parent.parent
        for parent in [script_dir] + list(script_dir.parents):
            candidate = parent / "config.toml"
            if candidate.exists():
                return candidate

        # Fall back to CWD walk
        start = Path.cwd()
        for parent in [start] + list(start.parents):
            candidate = parent / "config.toml"
            if candidate.exists():
                return candidate

        msg = "config.toml not found. Run from the project directory."
        raise FileNotFoundError(msg)

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


def _toml_escape(value: str) -> str:
    """Escape a string for safe interpolation into a TOML basic string."""
    return (
        value.replace("\\", "\\\\")
        .replace('"', '\\"')
        .replace("\n", "\\n")
        .replace("\r", "\\r")
        .replace("\t", "\\t")
    )


def generate_config_toml(name: str, owner: str = "", email: str = "", state: str = "WY", ledger_path: str = "main.beancount") -> str:
    """Generate a complete, valid config.toml for a new tenant/instance.

    Single source of truth for the config template (previously copy-pasted
    across deps.py / provision.py / setup). Includes the mandatory [tax]
    section so Config.__init__ never KeyErrors on a freshly provisioned
    instance. All user-supplied fields are TOML-escaped.
    """
    safe_name = _toml_escape(name)
    safe_owner = _toml_escape(owner or name)
    safe_email = _toml_escape(email)
    safe_state = _toml_escape(state)
    safe_ledger = _toml_escape(ledger_path)
    return f'''# SoloLedger — {safe_name}
# Auto-generated {__import__("datetime").date.today().isoformat()}

[business]
name = "{safe_name}"
owner = "{safe_owner}"
state = "{safe_state}"
ein = "XX-XXXXXXX"
address = ""
phone = ""
email = "{safe_email}"

[ledger]
path = "{safe_ledger}"

[accounts]
checking = "Assets:Bank:BusinessChecking"
ar = "Assets:AccountsReceivable"
income = "Income:Consulting"
owner_draws = "Equity:OwnerDraws"

[tax]
state = "WY"
standard_deduction = 14600
[[tax.brackets]]
rate = 0.10
floor = 0
ceiling = 11925
[[tax.brackets]]
rate = 0.12
floor = 11926
ceiling = 48475
[[tax.brackets]]
rate = 0.22
floor = 48476
ceiling = 103350
[[tax.brackets]]
rate = 0.24
floor = 103351
ceiling = 197300
[[tax.brackets]]
rate = 0.32
floor = 197301
ceiling = 250525
[[tax.brackets]]
rate = 0.35
floor = 250526
ceiling = 626350
[[tax.brackets]]
rate = 0.37
floor = 626351
ceiling = 999999999
[tax.self_employment]
rate_social_security = 0.124
rate_medicare = 0.029
ss_wage_base = 184800
deduction_ratio = 0.9235
safe_harbor_percent = 1.00
safe_harbor_percent_high_income = 1.10
safe_harbor_threshold = 150000
[tax.quarter_dates]
q1 = [4, 15]
q2 = [6, 15]
q3 = [9, 15]
q4 = [1, 15]

[payments]
stripe_enabled = false

[notifications]
desktop_enabled = false
email_enabled = false
remind_days_before = 7
smtp_host = "smtp.gmail.com"
smtp_port = 587
smtp_user = ""
smtp_password = ""
alert_email = ""

[banking]
plaid_enabled = false
'''
