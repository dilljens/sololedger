"""Tax estimation for a single-member LLC with multi-state support.

Calculates:
  - Self-employment tax (Schedule SE)
  - Federal income tax (projected)
  - State income tax + franchise/gross receipts taxes (multi-state)
  - Quarterly estimated payments (Form 1040-ES + state equivalents)
  - Safe harbor amounts

Default state: Wyoming ($0 state tax).
Other states: California, Texas, New York, Florida. Extensible via state_rates.json.
"""

import datetime
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

from app.config import Config
from app.ledger import Ledger


class TaxEstimator:
    """Estimate taxes for a single-member LLC with multi-state support."""

    def __init__(self, cfg: Config, ledger: Ledger, state_code: Optional[str] = None):
        self.cfg = cfg
        self.ledger = ledger
        self.state_code = state_code or getattr(cfg, 'state_code', 'WY')
        self._state_calculator = None

    @property
    def state_calculator(self):
        """Lazy-init state calculator."""
        if self._state_calculator is None:
            try:
                from .state_calculator import StateTaxCalculator
                self._state_calculator = StateTaxCalculator(self.state_code)
            except (ImportError, FileNotFoundError, ValueError) as e:
                # Fall back to zero state tax
                self._state_calculator = None
        return self._state_calculator

    def self_employment_tax(self, net_profit: Decimal) -> dict:
        """Calculate Schedule SE tax.

        Self-employment tax = 92.35% of net profit × 15.3%
        (12.4% SS + 2.9% Medicare), capped at SS wage base.
        """
        se_base = net_profit * Decimal(str(self.cfg.se_deduction_ratio))
        se_base = se_base.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        ss_wage = Decimal(str(self.cfg.ss_wage_base))

        # Social Security portion (12.4%) — capped
        ss_portion = min(se_base, ss_wage) * Decimal(str(self.cfg.se_ss_rate))
        # Medicare portion (2.9%) — no cap
        med_portion = se_base * Decimal(str(self.cfg.se_med_rate))

        total = ss_portion + med_portion
        total = total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        # Deductible half (employer-equivalent)
        deductible_half = (total / Decimal("2")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        return {
            "se_taxable_base": se_base,
            "social_security": ss_portion.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "medicare": med_portion.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "total_se_tax": total,
            "deductible_half": deductible_half,
        }

    def federal_income_tax(self, net_profit: Decimal) -> dict:
        """Estimate federal income tax (single filer, standard deduction).

        This is an estimate. Actual may differ due to credits, 
        other income, deductions, etc.
        """
        # Standard deduction reduces taxable income
        std_ded = Decimal(str(self.cfg.standard_deduction))
        taxable_income = max(Decimal("0"), net_profit - std_ded)

        # Apply brackets
        tax = Decimal("0")
        brackets_used = []
        remaining = taxable_income

        for bracket in self.cfg.brackets:
            floor = Decimal(str(bracket["floor"]))
            ceiling = Decimal(str(bracket["ceiling"]))
            rate = Decimal(str(bracket["rate"]))

            if remaining <= 0:
                break

            taxable_in_bracket = min(remaining, ceiling - floor + 1)
            taxable_in_bracket = max(taxable_in_bracket, Decimal("0"))
            bracket_tax = taxable_in_bracket * rate
            tax += bracket_tax

            if taxable_in_bracket > 0:
                brackets_used.append({
                    "rate": float(rate),
                    "floor": float(floor),
                    "taxable": float(taxable_in_bracket),
                    "tax": float(bracket_tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)),
                })

            remaining -= taxable_in_bracket

        tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        return {
            "gross_income": net_profit,
            "standard_deduction": std_ded,
            "taxable_income": taxable_income,
            "income_tax": tax,
            "brackets": brackets_used,
            "effective_rate": float(tax / net_profit * 100) if net_profit > 0 else 0,
        }

    def state_tax(self, net_profit: Decimal, adjusted_net: Decimal,
                   total_revenue: Optional[Decimal] = None,
                   entity_type: str = "smllc") -> dict:
        """Compute state-level taxes (income, franchise, local, fees).

        Args:
            net_profit: Net profit before deductions
            adjusted_net: Net profit after SE deductible half (federal AGI equivalent)
            total_revenue: Gross revenue (for franchise/gross receipts tax calculations).
                           Defaults to net_profit * 1.1 as an estimate if not provided.
            entity_type: "smllc" (default) or "scorp" — some states add S-Corp specific taxes.

        Returns:
            dict with state tax breakdown (all zeros if state has no tax)
        """
        if total_revenue is None:
            # Estimate revenue as ~110% of net profit (assumes ~10% expenses)
            total_revenue = net_profit * Decimal("1.1")

        try:
            calc = self.state_calculator
            if calc is None:
                return {
                    "state_code": self.state_code,
                    "total_state_tax": Decimal("0"),
                    "income_tax": {"tax": Decimal("0"), "type": "none"},
                    "franchise_tax": {"tax": Decimal("0"), "type": "none"},
                    "local_income_tax": {"tax": Decimal("0"), "type": "none"},
                    "annual_llc_fee": 0,
                }
            return calc.calculate_all(net_profit, total_revenue, adjusted_net, entity_type=entity_type)
        except Exception as e:
            import sys
            print(f"⚠ State tax calculation failed: {e}", file=sys.stderr)
            return {
                "state_code": self.state_code,
                "total_state_tax": Decimal("0"),
                "note": "State calculator unavailable",
            }

    def fica_tax(self, salary: Decimal) -> dict:
        """Calculate FICA tax for S-Corp officer salary (Form 1120-S).

        Employee share (withheld from wages):
          - 6.2% Social Security (capped at SS wage base)
          - 1.45% Medicare (uncapped)
          - 0.9% Additional Medicare on wages over $200K (employee only)

        Employer share (company expense):
          - 6.2% Social Security (capped at SS wage base)
          - 1.45% Medicare (uncapped)

        Returns:
            dict with employee/employer shares and totals
        """
        ss_wage_cap = Decimal(str(self.cfg.ss_wage_base))

        # Employee shares
        employee_ss = min(salary, ss_wage_cap) * Decimal("0.062")
        employee_med = salary * Decimal("0.0145")
        # Additional Medicare: 0.9% on wages above $200K
        additional_med_threshold = Decimal("200000")
        additional_med = max(Decimal("0"), salary - additional_med_threshold) * Decimal("0.009")
        total_employee = employee_ss + employee_med + additional_med

        # Employer shares
        employer_ss = min(salary, ss_wage_cap) * Decimal("0.062")
        employer_med = salary * Decimal("0.0145")
        total_employer = employer_ss + employer_med

        total_fica = total_employee + total_employer

        return {
            "salary": salary,
            "employee": {
                "social_security": employee_ss.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "medicare": employee_med.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "additional_medicare": additional_med.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "total": total_employee.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            },
            "employer": {
                "social_security": employer_ss.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "medicare": employer_med.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
                "total": total_employer.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            },
            "total_fica": total_fica.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
        }

    def form_1120s_income(self, net_profit: Decimal, fica_result: dict) -> dict:
        """Compute 1120-S ordinary business income for S-Corp.

        1120-S ordinary income = net profit − officer salary − employer FICA

        Args:
            net_profit: Net profit before salary and payroll (revenue − expenses)
            fica_result: Result from fica_tax()

        Returns:
            dict with ordinary_income and components
        """
        salary = fica_result["salary"]
        employer_fica = fica_result["employer"]["total"]
        ordinary_income = net_profit - salary - employer_fica

        return {
            "ordinary_income": ordinary_income.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP),
            "officer_salary": salary,
            "employer_payroll_taxes": employer_fica,
        }

    def total_projected_tax(self, net_profit: Decimal, total_revenue: Optional[Decimal] = None) -> dict:
        """Combined tax estimate for the year.

        For SMLLC (default): Schedule SE + federal income tax + state tax.
        For S-Corp: FICA + federal income tax on (salary + K-1 pass-through) + state tax.
        """
        entity_type = getattr(self.cfg, 'entity_type', 'smllc')

        if entity_type == 'scorp':
            salary = getattr(self.cfg, 'reasonable_salary', Decimal('0'))
            if salary <= 0:
                # Warn but compute without salary
                import warnings
                warnings.warn("S-Corp mode requires reasonable_salary to be set in config.toml [entity] section.")
            fica = self.fica_tax(salary)
            form1120 = self.form_1120s_income(net_profit, fica)

            # Owner pays income tax on: W-2 wages + K-1 pass-through ordinary income
            total_owner_income = salary + form1120["ordinary_income"]
            adjusted_net = max(total_owner_income, Decimal("0"))
            fed = self.federal_income_tax(adjusted_net)
            # For S-Corp state taxes, use the full income (salary + pass-through)
            state = self.state_tax(adjusted_net, adjusted_net, total_revenue, entity_type="scorp")

            total = fica["total_fica"] + fed["income_tax"] + state["total_state_tax"]

            return {
                "entity_type": "scorp",
                "net_profit": net_profit,
                "adjusted_net": adjusted_net,
                "fica": fica,
                "form_1120s": form1120,
                "federal_income_tax": fed,
                "state_tax": state,
                "total_tax": total,
                "effective_tax_rate": float(total / net_profit * 100) if net_profit > 0 else 0,
            }
        else:
            # SMLLC path (unchanged)
            se = self.self_employment_tax(net_profit)
            adjusted_net = net_profit - se["deductible_half"]
            fed = self.federal_income_tax(adjusted_net)
            state = self.state_tax(net_profit, adjusted_net, total_revenue)

            total = se["total_se_tax"] + fed["income_tax"] + state["total_state_tax"]

            return {
                "entity_type": "smllc",
                "net_profit": net_profit,
                "adjusted_net": adjusted_net,
                "self_employment_tax": se,
                "federal_income_tax": fed,
                "state_tax": state,
                "total_tax": total,
                "effective_tax_rate": float(total / net_profit * 100) if net_profit > 0 else 0,
            }

    def quarterly_estimate(self, ytd_net: Decimal, annual_projection: Decimal | None = None) -> dict:
        """Calculate recommended quarterly payment based on YTD income.

        Uses the annualized income method: projects full-year tax from
        year-to-date income, then divides remaining tax by remaining quarters.
        """
        if annual_projection is None:
            annual_projection = ytd_net  # naive: assume rest of year is same

        annual_tax = self.total_projected_tax(annual_projection)
        total_tax = annual_tax["total_tax"]

        # Calculate current quarter number
        now = datetime.date.today()
        quarter = (now.month - 1) // 3 + 1

        # Standard safe harbor: pay in 4 equal installments
        per_quarter = (total_tax / Decimal("4")).quantize(
            Decimal("0.01"), rounding=ROUND_HALF_UP
        )

        # How much has been paid so far this year
        taxes_paid = self.ledger.taxes_paid()
        already_paid = taxes_paid["federal_estimated"]

        remaining = total_tax - already_paid
        remaining_quarters = 4 - quarter + 1

        if remaining_quarters > 0:
            suggested_payment = (remaining / Decimal(str(remaining_quarters))).quantize(
                Decimal("0.01"), rounding=ROUND_HALF_UP
            )
        else:
            suggested_payment = max(Decimal("0"), remaining)

        return {
            "annual_projection": annual_projection,
            "annual_total_tax": total_tax,
            "per_quarter_naive": per_quarter,
            "already_paid": already_paid,
            "remaining": max(Decimal("0"), remaining),
            "remaining_quarters": remaining_quarters,
            "suggested_payment": max(Decimal("0"), suggested_payment),
            "quarter": quarter,
            "note": self._quarter_note(quarter),
        }

    def form_1120s_export(self, net_profit: Decimal, total_revenue: Optional[Decimal] = None) -> dict:
        """Generate data for Form 1120-S (S-Corp tax return).

        Only meaningful when entity_type is 'scorp'. Includes:
          - Gross receipts / revenue
          - Officer compensation (from config)
          - Employer payroll taxes
          - Other business expenses
          - 1120-S ordinary income
          - Balance sheet components (accounts via ledger)

        Args:
            net_profit: Net profit before salary (revenue − expenses)
            total_revenue: Gross revenue (for reference). Estimated if None.

        Returns:
            dict with 1120-S line items
        """
        if total_revenue is None:
            total_revenue = net_profit * Decimal("1.1")

        salary = getattr(self.cfg, 'reasonable_salary', Decimal('0'))
        fica = self.fica_tax(salary)
        form1120 = self.form_1120s_income(net_profit, fica)

        expense_detail = self.ledger.expense_detail()
        # Separate payroll expenses from other expenses
        other_expenses = [e for e in expense_detail if not e["account"].startswith("Expenses:Payroll")]
        total_other_expenses = sum(e["amount"] for e in other_expenses) if other_expenses else Decimal("0")

        # Balance sheet snapshots
        cash = self.ledger.cash_balance()
        ar = self.ledger.account_balance(self.cfg.ar_account)
        total_assets = cash + ar

        return {
            "entity_type": "scorp",
            "form": "1120-S",
            "income": {
                "gross_receipts": total_revenue,
                "officer_compensation": salary,
                "employer_payroll_taxes": fica["employer"]["total"],
                "other_deductions": total_other_expenses,
                "ordinary_income": form1120["ordinary_income"],
            },
            "expense_detail": {
                "payroll": expense_detail if any(e["account"].startswith("Expenses:Payroll") for e in expense_detail) else [],
                "other": other_expenses,
            },
            "balance_sheet": {
                "cash": cash,
                "accounts_receivable": ar,
                "total_assets": total_assets,
            },
            "shareholder": {
                "name": getattr(self.cfg, 'owner', 'Shareholder'),
                "ownership_pct": 100,
                "ordinary_income": form1120["ordinary_income"],
            },
        }

    def schedule_c_summary(self) -> dict:
        """Generate data you'd put on Schedule C at tax time."""
        revenue = self.ledger.gross_revenue()
        expenses = self.ledger.total_expenses()
        net = revenue - expenses

        # Expense breakdown by category
        expense_detail = self.ledger.expense_detail()

        return {
            "gross_receipts": revenue,
            "total_expenses": expenses,
            "net_profit": net,
            "expense_detail": expense_detail,
            "taxes_paid": self.ledger.taxes_paid(),
        }

    def _quarter_note(self, quarter: int) -> str:
        """Return the due date info for a quarter."""
        dates = {
            1: "Apr 15",
            2: "Jun 15",
            3: "Sep 15",
            4: "Jan 15 (next year)",
        }
        return f"Q{quarter} estimated tax due: {dates.get(quarter, '?')}"

    def deadline_info(self) -> dict:
        """Return info about upcoming tax deadlines."""
        now = datetime.date.today()
        current_year = now.year

        deadlines = []
        # Q1: Apr 15
        deadlines.append({"quarter": 1, "date": datetime.date(current_year, 4, 15)})
        # Q2: Jun 15
        deadlines.append({"quarter": 2, "date": datetime.date(current_year, 6, 15)})
        # Q3: Sep 15
        deadlines.append({"quarter": 3, "date": datetime.date(current_year, 9, 15)})
        # Q4: Jan 15 next year
        deadlines.append({"quarter": 4, "date": datetime.date(current_year + 1, 1, 15)})
        # Tax filing: Apr 15 next year
        deadlines.append({"quarter": "annual", "date": datetime.date(current_year + 1, 4, 15)})

        upcoming = []
        for d in deadlines:
            days_until = (d["date"] - now).days
            upcoming.append({
                "label": f"Q{d['quarter']}" if isinstance(d['quarter'], int) else d['quarter'],
                "due": d["date"].isoformat(),
                "days_until": days_until,
                "status": "overdue" if days_until < 0 else "upcoming" if days_until <= 30 else "ahead",
            })

        return {"as_of": now.isoformat(), "deadlines": upcoming}
