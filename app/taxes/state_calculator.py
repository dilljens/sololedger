"""State-level tax calculator — reads state_rates.json and computes state-specific taxes.

Supports:
  - State income tax (progressive brackets, flat rate, or none)
  - Franchise/gross receipts taxes (annual fee, margin tax, graduated fee)
  - Annual LLC report fees
  - Local add-on taxes (e.g., NYC)
  - Estimated tax requirements

Usage:
    from app.taxes.state_calculator import StateTaxCalculator
    calc = StateTaxCalculator("CA")
    result = calc.calculate_all(net_profit=Decimal("50000"), total_revenue=Decimal("80000"))
    print(result["total_state_tax"])
"""

import json
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Optional

import tomli

DATA_DIR = Path(__file__).parent / "data"
STATE_RATES_PATH = DATA_DIR / "state_rates.json"


class StateTaxCalculator:
    """Compute all state-level taxes for a single-member LLC."""

    def __init__(self, state_code: str):
        """
        Args:
            state_code: Two-letter state code (e.g. "CA", "TX", "WY")
        """
        self.state_code = state_code.upper()
        self.data = self._load_state_data(self.state_code)

    def _load_state_data(self, state_code: str) -> dict:
        """Load state data from JSON file."""
        if not STATE_RATES_PATH.exists():
            raise FileNotFoundError(f"State rates file not found: {STATE_RATES_PATH}")

        with open(STATE_RATES_PATH) as f:
            all_states = json.load(f)

        if state_code not in all_states:
            available = list(all_states.keys())
            raise ValueError(
                f"State '{state_code}' not found. Available: {', '.join(sorted(available))}"
            )

        return all_states[state_code]

    def state_income_tax(self, net_profit: Decimal, adjusted_net: Decimal) -> dict:
        """Compute state income tax on pass-through LLC income.

        Args:
            net_profit: Gross net profit before SE tax deduction
            adjusted_net: Net profit after SE tax deductible half (federal AGI)

        Returns:
            dict with taxable_income, tax, effective_rate, brackets_used
        """
        income_tax_config = self.data.get("income_tax")
        if income_tax_config is None:
            return {"taxable_income": Decimal("0"), "tax": Decimal("0"), "effective_rate": 0, "type": "none"}

        # Use the same adjusted net as federal (SE deduction already applied)
        std_ded = Decimal(str(income_tax_config.get("standard_deduction", 0)))
        taxable_income = max(Decimal("0"), adjusted_net - std_ded)

        brackets = income_tax_config.get("brackets", [])
        if not brackets:
            raise ValueError(f"No income tax brackets found for {self.state_code}")

        tax = Decimal("0")
        brackets_used = []
        remaining = taxable_income

        for bracket in brackets:
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
            "taxable_income": taxable_income,
            "tax": tax,
            "effective_rate": float(tax / taxable_income * 100) if taxable_income > 0 else 0,
            "brackets_used": brackets_used,
            "type": "progressive",
        }

    def franchise_tax(self, net_profit: Decimal, total_revenue: Decimal) -> dict:
        """Compute franchise/gross receipts tax.

        Args:
            net_profit: Net profit (used for some computations)
            total_revenue: Total gross revenue (used for thresholds and graduated fees)

        Returns:
            dict with tax, type, and details
        """
        franchise_config = self.data.get("franchise_tax")
        if franchise_config is None:
            return {"tax": Decimal("0"), "type": "none"}

        tax_type = franchise_config.get("type")

        if tax_type == "annual_minimum_plus_graduated":
            # e.g., California: $800 minimum + graduated fee based on total revenue
            annual_min = Decimal(str(franchise_config.get("annual_minimum", 0)))

            graduated_fee = Decimal("0")
            graduated_tiers = franchise_config.get("graduated_fee", [])
            for tier in sorted(graduated_tiers, key=lambda t: t["revenue_floor"], reverse=True):
                if total_revenue >= Decimal(str(tier["revenue_floor"])):
                    graduated_fee = Decimal(str(tier["fee"]))
                    break

            total = annual_min + graduated_fee

            return {
                "tax": total,
                "type": "annual_minimum_plus_graduated",
                "annual_minimum": annual_min,
                "graduated_fee": graduated_fee,
                "notes": franchise_config.get("notes", ""),
            }

        elif tax_type == "margin":
            # e.g., Texas margin tax
            threshold = Decimal(str(franchise_config.get("threshold", 0)))
            if total_revenue <= threshold:
                return {"tax": Decimal("0"), "type": "margin", "note": "Below revenue threshold"}

            rate = Decimal(str(franchise_config.get("rate", 0.0075)))

            # Simple: 70% of total revenue as margin (simplest computation)
            # In practice, taxpayers choose the lowest of 4 methods
            margin = total_revenue * Decimal("0.7")
            tax = margin * rate
            tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

            return {
                "tax": tax,
                "type": "margin",
                "rate": float(rate),
                "margin": margin,
                "method": "70% of total revenue (simplified)",
                "note": f"Computed using simplified method. Actual may differ based on COGS/compensation deduction.",
            }

        else:
            return {"tax": Decimal("0"), "type": "unknown", "note": f"Unsupported franchise tax type: {tax_type}"}

    def gross_receipts_tax(self, total_revenue: Decimal) -> dict:
        """Compute gross receipts tax (e.g., Washington B&O tax).

        Returns:
            dict with tax and details
        """
        gr_config = self.data.get("gross_receipts_tax")
        if gr_config is None:
            return {"tax": Decimal("0"), "type": "none"}

        # Currently only WA B&O would use this — not in our 5 states
        return {"tax": Decimal("0"), "type": "not_implemented"}

    def local_income_tax(self, adjusted_net: Decimal, state_income_tax: dict) -> dict:
        """Compute local/municipal income tax (e.g., NYC).

        Args:
            adjusted_net: Adjusted net income (AGI after SE deduction)
            state_income_tax: Result from state_income_tax() (for context)

        Returns:
            dict with tax and breakdown by locality
        """
        local_config = self.data.get("local_income_tax")
        if local_config is None:
            return {"tax": Decimal("0"), "type": "none"}

        total_local_tax = Decimal("0")
        localities = {}

        for locality, config in local_config.items():
            tax_type = config.get("type")
            if tax_type == "progressive":
                # Use the same taxable income logic
                # NYC uses NY state standard deduction for city tax
                std_ded = Decimal(str(self.data.get("income_tax", {}).get("standard_deduction", 0)))
                taxable_income = max(Decimal("0"), adjusted_net - std_ded)

                tax = Decimal("0")
                remaining = taxable_income
                for bracket in config.get("brackets", []):
                    floor = Decimal(str(bracket["floor"]))
                    ceiling = Decimal(str(bracket["ceiling"]))
                    rate = Decimal(str(bracket["rate"]))
                    if remaining <= 0:
                        break
                    taxable_in_bracket = min(remaining, ceiling - floor + 1)
                    taxable_in_bracket = max(taxable_in_bracket, Decimal("0"))
                    tax += taxable_in_bracket * rate
                    remaining -= taxable_in_bracket

                tax = tax.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
                total_local_tax += tax

                localities[locality] = {
                    "tax": tax,
                    "name": config.get("name", locality),
                    "notes": config.get("notes", ""),
                }

        return {
            "tax": total_local_tax,
            "type": "local",
            "localities": localities,
        }

    def annual_llc_fee(self) -> Decimal:
        """Annual LLC report / registered agent fee."""
        return Decimal(str(self.data.get("annual_llc_fee", 0)))

    def scorp_tax(self, net_profit: Decimal) -> dict:
        """Compute state-level S-Corp specific taxes.

        Some states impose additional taxes on S-Corps (e.g., CA 1.5% on
        net income, NY graduated filing fee).

        Args:
            net_profit: Net profit (1120-S ordinary income before state tax)

        Returns:
            dict with tax and details
        """
        scorp_config = self.data.get("scorp_tax")
        if scorp_config is None:
            return {"tax": Decimal("0"), "type": "none"}

        stype = scorp_config.get("type")

        if stype == "rate_on_net_income":
            # e.g., California: 1.5% of net income, minimum $800
            rate = Decimal(str(scorp_config.get("rate", 0)))
            min_tax = Decimal(str(scorp_config.get("min_tax", 0)))
            computed = (net_profit * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            tax = max(computed, min_tax)
            return {
                "tax": tax,
                "type": "rate_on_net_income",
                "rate": float(rate),
                "min_tax": float(min_tax),
                "computed": float(computed),
                "notes": scorp_config.get("notes", ""),
            }

        elif stype == "graduated_filing_fee":
            # e.g., New York: $25-$4,500 based on income
            tiers = sorted(scorp_config.get("tiers", []),
                           key=lambda t: t["income_floor"], reverse=True)
            for tier in tiers:
                if net_profit >= Decimal(str(tier["income_floor"])):
                    fee = Decimal(str(tier["fee"]))
                    return {
                        "tax": fee,
                        "type": "graduated_filing_fee",
                        "fee": float(fee),
                        "income_threshold": tier["income_floor"],
                        "notes": scorp_config.get("notes", ""),
                    }
            return {"tax": Decimal("0"), "type": "graduated_filing_fee",
                    "note": "Below minimum income threshold"}

        else:
            return {"tax": Decimal("0"), "type": "unknown"}

    def calculate_all(self, net_profit: Decimal, total_revenue: Decimal,
                      adjusted_net: Optional[Decimal] = None,
                      entity_type: str = "smllc") -> dict:
        """Compute all state-level taxes for an LLC.

        Args:
            net_profit: Net profit before any deductions
            total_revenue: Total gross revenue for the year
            adjusted_net: Net profit after SE deduction (federal AGI).
                           If None, computed as net_profit.
            entity_type: "smllc" (default) or "scorp"

        Returns:
            dict with complete state tax breakdown
        """
        if adjusted_net is None:
            adjusted_net = net_profit

        # 1. State income tax
        income = self.state_income_tax(net_profit, adjusted_net)

        # 2. Franchise tax (based on revenue)
        franchise = self.franchise_tax(net_profit, total_revenue)

        # 3. Gross receipts tax
        gross_receipts = self.gross_receipts_tax(total_revenue)

        # 4. Local income tax
        local = self.local_income_tax(adjusted_net, income)

        # 5. Annual LLC fee
        annual_fee = self.annual_llc_fee()

        # 6. S-Corp specific tax (only for scorp)
        scorp = self.scorp_tax(net_profit) if entity_type == "scorp" else {"tax": Decimal("0"), "type": "none"}

        total = income["tax"] + franchise["tax"] + gross_receipts["tax"] + local["tax"] + annual_fee + scorp["tax"]

        return {
            "state_code": self.state_code,
            "state_name": self.data.get("name", self.state_code),
            "total_state_tax": total,
            "income_tax": income,
            "franchise_tax": franchise,
            "gross_receipts_tax": gross_receipts,
            "local_income_tax": local,
            "annual_llc_fee": float(annual_fee),
            "scorp_tax": scorp,
            "estimated_tax_info": self.data.get("estimated_tax"),
        }

    @staticmethod
    def list_states() -> dict:
        """List all available states with basic info.

        Returns:
            dict of state_code -> {name, has_income_tax, notes}
        """
        if not STATE_RATES_PATH.exists():
            return {}

        with open(STATE_RATES_PATH) as f:
            all_states = json.load(f)

        return {
            code: {
                "name": data.get("name", code),
                "has_income_tax": data.get("income_tax") is not None,
                "has_franchise_tax": data.get("franchise_tax") is not None,
                "annual_fee": data.get("annual_llc_fee", 0),
                "notes": data.get("notes", ""),
            }
            for code, data in sorted(all_states.items())
        }
