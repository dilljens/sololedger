"""Payroll import from Gusto CSV exports for S-Corp payroll.

Generates Beancount journal entries for each pay period:
  - Gross wages, employee withholdings, employer taxes
  - Net pay disbursement to owner

Usage:
    from app.payroll import PayrollImporter
    pi = PayrollImporter(cfg, ledger)
    results = pi.import_gusto_csv("gusto-payroll.csv", preview=True)
"""

import csv
import datetime
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

from .config import Config
from .ledger import Ledger


# Standard FICA rates
EE_SS_RATE = Decimal("0.062")
EE_MED_RATE = Decimal("0.0145")
ER_SS_RATE = Decimal("0.062")
ER_MED_RATE = Decimal("0.0145")
ADDITIONAL_MED_THRESHOLD = Decimal("200000")
ADDITIONAL_MED_RATE = Decimal("0.009")
FUTA_RATE = Decimal("0.006")
FUTA_WAGE_BASE = Decimal("7000")


class PayrollImporter:
    """Import payroll runs from Gusto CSV exports into the Beancount ledger."""

    # Gusto CSV column name variants we recognise
    COLUMN_ALIASES = {
        "pay_period_start": ["pay period", "pay period start", "period start", "start date"],
        "pay_period_end": ["pay period end", "period end", "end date"],
        "employee": ["employee", "name", "employee name"],
        "gross_pay": ["gross pay", "gross wages", "gross", "wages"],
        "employee_ss": ["employee social security", "ee social security", "social security employee"],
        "employee_medicare": ["employee medicare", "ee medicare", "medicare employee"],
        "employee_federal_withholding": [
            "employee federal withholding", "federal withholding",
            "fed withholding", "federal income tax",
        ],
        "employee_state_withholding": [
            "employee state withholding", "state withholding",
            "state income tax", "state withholding tax",
        ],
        "employee_additional_medicare": [
            "employee additional medicare", "additional medicare",
            "ee additional medicare",
        ],
        "employer_ss": ["employer social security", "er social security"],
        "employer_medicare": ["employer medicare", "er medicare"],
        "employer_futa": ["employer futa", "futa", "federal unemployment"],
        "employer_suta": ["employer suta", "suta", "state unemployment"],
        "net_pay": ["net pay", "net", "net wages"],
    }

    def __init__(self, cfg: Config, ledger: Ledger):
        self.cfg = cfg
        self.ledger = ledger
        self._require_scorp_config()

    def _require_scorp_config(self):
        """Warn if entity_type is not scorp."""
        if getattr(self.cfg, 'entity_type', 'smllc') != 'scorp':
            import warnings
            warnings.warn(
                "Payroll import is for S-Corp (entity_type='scorp'). "
                "Set [entity] entity_type = 'scorp' in config.toml."
            )

    def import_gusto_csv(self, filepath: str | Path, preview: bool = False) -> list[dict]:
        """Import a Gusto payroll CSV export.

        Each row is one employee's paystub for one pay period.
        The importer generates two transactions per pay period:
          1. Payroll accrual (gross → liabilities)
          2. Net pay disbursement (liability → bank)

        Args:
            filepath: Path to Gusto CSV export.
            preview: If True, parse and return results without writing.

        Returns:
            list of dicts with import results per row.
        """
        path = Path(filepath)
        if not path.exists():
            return [{"error": f"File not found: {path}"}]

        with open(path, encoding="utf-8-sig") as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        if not rows:
            return [{"error": "Empty CSV"}]

        columns = [c.lower().strip() for c in rows[0].keys()]
        col_map = self._map_columns(columns)

        # Validate required columns
        required = ["pay_period_start", "gross_pay", "net_pay"]
        missing = [c for c in required if col_map.get(c) is None]
        if missing:
            return [{"error": f"Missing required columns: {', '.join(missing)}. Found: {', '.join(columns)}"}]

        results = []
        for row in rows:
            result = self._process_row(row, col_map, preview=preview)
            results.append(result)

        return results

    def _map_columns(self, columns: list[str]) -> dict[str, int]:
        """Map known column names to their index in the CSV."""
        mapped = {}
        for field, aliases in self.COLUMN_ALIASES.items():
            for i, col in enumerate(columns):
                if any(alias in col for alias in aliases):
                    mapped[field] = i
                    break
        return mapped

    def _get_col(self, row: dict, col_map: dict, field: str) -> str:
        """Get a cell value by mapped field name."""
        idx = col_map.get(field)
        if idx is None:
            return ""
        keys = list(row.keys())
        if idx < len(keys):
            return keys[idx]
        return ""

    def _process_row(self, row: dict, col_map: dict, preview: bool = False) -> dict:
        """Process one payroll row."""
        keys = list(row.keys())

        def val(field: str) -> Decimal:
            idx = col_map.get(field)
            if idx is None or idx >= len(keys):
                return Decimal("0")
            raw = row.get(keys[idx], "0").strip()
            raw = raw.replace("$", "").replace(",", "").replace('"', "")
            if not raw or raw == "-":
                return Decimal("0")
            return Decimal(raw).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        gross = val("gross_pay")
        net = val("net_pay")
        ee_ss = val("employee_ss")
        ee_med = val("employee_medicare")
        ee_fed = val("employee_federal_withholding")
        ee_state = val("employee_state_withholding")
        ee_add_med = val("employee_additional_medicare")
        er_ss = val("employer_ss")
        er_med = val("employer_medicare")
        er_futa = val("employer_futa")
        er_suta = val("employer_suta")

        # Determine pay period date
        period_end_idx = col_map.get("pay_period_end")
        if period_end_idx is not None and period_end_idx < len(keys):
            raw_date = row.get(keys[period_end_idx], "").strip().split("T")[0]
        else:
            raw_date = self._get_col(row, col_map, "pay_period_start") or ""

        # Parse date — try ISO first, then MM/DD/YYYY
        pay_date = datetime.date.today()
        if raw_date:
            try:
                pay_date = datetime.date.fromisoformat(raw_date)
            except (ValueError, TypeError):
                try:
                    from datetime import datetime as dt
                    pay_date = dt.strptime(raw_date, "%m/%d/%Y").date()
                except (ValueError, TypeError):
                    pass

        employee_name = self._get_col(row, col_map, "employee") or "Owner"
        narration = f"Payroll — {employee_name} — {pay_date.isoformat()}"

        if gross <= 0:
            return {"date": pay_date.isoformat(), "employee": employee_name,
                    "gross": 0, "net": 0, "error": "No gross pay", "skipped": True}

        # Build postings for the payroll accrual transaction
        postings = [
            (f"Expenses:Payroll:GrossWages", f"{gross:.2f} USD"),
        ]

        # Employee withholdings (liability credits)
        if ee_ss > 0:
            postings.append(("Liabilities:PayrollTaxesPayable:SocialSecurity", f"-{ee_ss:.2f} USD"))
        if ee_med > 0:
            postings.append(("Liabilities:PayrollTaxesPayable:Medicare", f"-{ee_med:.2f} USD"))
        if ee_fed > 0:
            postings.append(("Liabilities:PayrollTaxesPayable:FederalWithholding", f"-{ee_fed:.2f} USD"))
        if ee_state > 0:
            postings.append(("Liabilities:PayrollTaxesPayable:StateWithholding", f"-{ee_state:.2f} USD"))
        if ee_add_med > 0:
            postings.append(("Liabilities:PayrollTaxesPayable:Medicare", f"-{ee_add_med:.2f} USD"))

        # Employer payroll taxes (expenses)
        total_er = Decimal("0")
        if er_ss > 0:
            postings.append(("Expenses:Payroll:EmployerSocialSecurity", f"{er_ss:.2f} USD"))
            total_er += er_ss
        if er_med > 0:
            postings.append(("Expenses:Payroll:EmployerMedicare", f"{er_med:.2f} USD"))
            total_er += er_med

        # If CSV doesn't include employer taxes, auto-compute from gross
        if er_ss == 0 and er_med == 0:
            ss_wage_cap = Decimal(str(self.cfg.ss_wage_base))
            er_ss = min(gross, ss_wage_cap) * ER_SS_RATE
            er_med = gross * ER_MED_RATE
            postings.append(("Expenses:Payroll:EmployerSocialSecurity", f"{er_ss:.2f} USD"))
            postings.append(("Expenses:Payroll:EmployerMedicare", f"{er_med:.2f} USD"))
            total_er = er_ss + er_med

        # FUTA
        if er_futa > 0:
            postings.append(("Expenses:Payroll:FUTA", f"{er_futa:.2f} USD"))
        else:
            # Auto-compute: 0.6% on first $7K
            er_futa = min(gross, FUTA_WAGE_BASE) * FUTA_RATE
            if er_futa > 0:
                postings.append(("Expenses:Payroll:FUTA", f"{er_futa:.2f} USD"))

        # SUTA
        if er_suta > 0:
            postings.append(("Expenses:Payroll:SUTA", f"{er_suta:.2f} USD"))

        # Net pay payable
        postings.append(("Liabilities:PayrollPayable", f"-{net:.2f} USD"))

        if not preview:
            self.ledger.append(
                date=pay_date,
                payee=employee_name,
                narration=narration,
                postings=postings,
            )

        return {
            "date": pay_date.isoformat(),
            "employee": employee_name,
            "gross": float(gross),
            "net": float(net),
            "total_employer_taxes": float(total_er),
            "narration": narration,
            "preview": preview,
            "postings_count": len(postings),
        }

    def payroll_disburse(self, pay_date: datetime.date, net_pay: Decimal,
                         bank_account: Optional[str] = None,
                         preview: bool = False) -> dict:
        """Record the net pay disbursement from business bank to owner.

        This is the second transaction of a payroll run:
            Debit  Liabilities:PayrollPayable  $net
            Credit Assets:Bank:BusinessChecking $net
        """
        bank = bank_account or self.cfg.checking_account

        postings = [
            ("Liabilities:PayrollPayable", f"{net_pay:.2f} USD"),
            (bank, f"-{net_pay:.2f} USD"),
        ]

        narration = f"Payroll disbursement — {pay_date.isoformat()}"

        if not preview:
            self.ledger.append(
                date=pay_date,
                payee="Owner",
                narration=narration,
                postings=postings,
            )

        return {
            "date": pay_date.isoformat(),
            "net_pay": float(net_pay),
            "bank_account": bank,
            "preview": preview,
        }
