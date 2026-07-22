"""Tests for app/taxes/__init__.py — TaxEstimator."""

from decimal import Decimal

import pytest


class TestTaxEstimatorInit:
    """TaxEstimator creation and basic setup."""

    def test_init_with_sample_config(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        assert te.cfg is sample_config
        assert te.ledger is clean_ledger
        assert te.state_code == "WY"

    def test_init_custom_state(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger, state_code="CA")
        assert te.state_code == "CA"


class TestQuarterlyEstimate:
    """Quarterly estimated tax payment calculations."""

    def test_positive_net_income(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.quarterly_estimate(Decimal("4800"))

        assert "annual_total_tax" in result
        assert "already_paid" in result
        assert "suggested_payment" in result
        assert "note" in result
        assert "remaining_quarters" in result
        assert "annual_projection" in result
        assert "per_quarter_naive" in result
        assert "remaining" in result
        assert "quarter" in result

        assert result["annual_projection"] == Decimal("4800")
        assert result["annual_total_tax"] > Decimal("0")
        assert result["already_paid"] == Decimal("0")
        assert result["remaining_quarters"] >= 1
        assert isinstance(result["note"], str)

    def test_zero_net_income(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.quarterly_estimate(Decimal("0"))

        assert result["annual_total_tax"] >= Decimal("0")
        assert result["already_paid"] == Decimal("0")
        assert result["remaining"] >= Decimal("0")

    def test_with_annual_projection(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.quarterly_estimate(Decimal("2400"), annual_projection=Decimal("4800"))
        assert result["annual_projection"] == Decimal("4800")


class TestTotalProjectedTax:
    """Combined tax estimate."""

    def test_returns_expected_keys(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.total_projected_tax(Decimal("4800"))

        assert "self_employment_tax" in result
        assert "federal_income_tax" in result
        assert "total_tax" in result
        assert "net_profit" in result
        assert "adjusted_net" in result
        assert "state_tax" in result
        assert "effective_tax_rate" in result

    def test_self_employment_tax_component(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.total_projected_tax(Decimal("4800"))

        se = result["self_employment_tax"]
        assert "total_se_tax" in se
        assert "se_taxable_base" in se
        assert "social_security" in se
        assert "medicare" in se
        assert "deductible_half" in se
        assert se["total_se_tax"] > Decimal("0")

    def test_federal_income_tax_component(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.total_projected_tax(Decimal("4800"))

        fed = result["federal_income_tax"]
        assert "income_tax" in fed
        assert "taxable_income" in fed
        assert "brackets" in fed
        assert "effective_rate" in fed

    def test_zero_net_income(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.total_projected_tax(Decimal("0"))

        assert result["total_tax"] >= Decimal("0")
        assert result["effective_tax_rate"] == 0


class TestDeadlineInfo:
    """Tax deadline information."""

    def test_returns_expected_structure(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.deadline_info()

        assert "as_of" in result
        assert "deadlines" in result
        assert isinstance(result["deadlines"], list)

    def test_deadlines_list_count(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.deadline_info()

        assert len(result["deadlines"]) == 5

        labels = {d["label"] for d in result["deadlines"]}
        assert "Q1" in labels
        assert "Q2" in labels
        assert "Q3" in labels
        assert "Q4" in labels
        assert "annual" in labels

    def test_deadline_fields(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.deadline_info()

        for deadline in result["deadlines"]:
            assert "label" in deadline
            assert "due" in deadline
            assert "days_until" in deadline
            assert "status" in deadline
            assert deadline["status"] in ("overdue", "upcoming", "ahead")


class TestScheduleCSummary:
    """Schedule C data generation."""

    def test_returns_expected_keys(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.schedule_c_summary()

        assert "gross_receipts" in result
        assert "total_expenses" in result
        assert "net_profit" in result
        assert "expense_detail" in result
        assert "taxes_paid" in result

    def test_values_from_sample_ledger(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.schedule_c_summary()

        assert result["gross_receipts"] == Decimal("5000")
        assert result["total_expenses"] == Decimal("200")
        assert result["net_profit"] == Decimal("4800")

    def test_expense_detail(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.schedule_c_summary()

        assert isinstance(result["expense_detail"], list)
        assert len(result["expense_detail"]) >= 1
        for item in result["expense_detail"]:
            assert "account" in item
            assert "amount" in item

    def test_taxes_paid_defaults(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.schedule_c_summary()

        tp = result["taxes_paid"]
        assert tp["federal_estimated"] == Decimal("0")
        assert tp["fica_employer"] == Decimal("0")


class TestSelfEmploymentTax:
    """Schedule SE tax calculations."""

    def test_calculation(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.self_employment_tax(Decimal("4800"))

        assert result["total_se_tax"] > Decimal("0")
        assert result["deductible_half"] == result["total_se_tax"] / 2
        assert result["se_taxable_base"] == Decimal("4432.80")


class TestFederalIncomeTax:
    """Federal income tax estimation."""

    def test_below_standard_deduction(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.federal_income_tax(Decimal("10000"))

        assert result["income_tax"] == Decimal("0")
        assert result["taxable_income"] == Decimal("0")

    def test_taxable_income(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.federal_income_tax(Decimal("50000"))

        assert result["taxable_income"] > Decimal("0")
        assert result["income_tax"] > Decimal("0")
        assert len(result["brackets"]) > 0

    def test_effective_rate(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.federal_income_tax(Decimal("100000"))

        assert result["effective_rate"] > 0


class TestStateTax:
    """State tax calculations."""

    def test_wyoming_has_fee_no_income_tax(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger, state_code="WY")
        result = te.state_tax(Decimal("4800"), Decimal("4460.89"))

        assert result["total_state_tax"] == Decimal("60")
        assert result["income_tax"]["tax"] == Decimal("0")
        assert result["annual_llc_fee"] == 60.0

    def test_unknown_state_falls_back(self, sample_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger, state_code="XX")
        result = te.state_tax(Decimal("4800"), Decimal("4460.89"))

        assert result["total_state_tax"] == Decimal("0")
        assert result["income_tax"] == {"tax": Decimal("0"), "type": "none"}


class TestFicaTax:
    """S-Corp FICA tax computation."""

    def test_fica_below_ss_wage_base(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.fica_tax(Decimal("50000"))

        # Employee: 6.2% SS + 1.45% Medicare = 7.65% (no additional Medicare below $200K)
        assert result["employee"]["social_security"] == Decimal("3100.00")
        assert result["employee"]["medicare"] == Decimal("725.00")
        assert result["employee"]["additional_medicare"] == Decimal("0.00")

        # Employer: 6.2% SS + 1.45% Medicare = 7.65%
        assert result["employer"]["social_security"] == Decimal("3100.00")
        assert result["employer"]["medicare"] == Decimal("725.00")

        # Total FICA = 15.3% of salary = $7,650
        assert result["total_fica"] == Decimal("7650.00")
        assert result["salary"] == Decimal("50000")

    def test_fica_above_ss_wage_base(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.fica_tax(Decimal("250000"))

        # SS capped at wage base (184800 * 0.062 = 11457.60)
        assert result["employee"]["social_security"] == Decimal("11457.60")
        assert result["employee"]["medicare"] == Decimal("3625.00")
        # Additional Medicare: (250000 - 200000) * 0.009 = 450
        assert result["employee"]["additional_medicare"] == Decimal("450.00")

        # Employer SS also capped
        assert result["employer"]["social_security"] == Decimal("11457.60")
        assert result["employer"]["medicare"] == Decimal("3625.00")

        assert result["total_fica"] > Decimal("0")

    def test_fica_zero_salary(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.fica_tax(Decimal("0"))

        assert result["total_fica"] == Decimal("0")
        for side in ("employee", "employer"):
            assert result[side]["total"] == Decimal("0")


class TestForm1120S:
    """1120-S ordinary income computation."""

    def test_ordinary_income(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        fica = te.fica_tax(Decimal("50000"))
        result = te.form_1120s_income(Decimal("100000"), fica)

        # Ordinary income = 100000 - 50000 - employer_fica(3825) = 46175
        assert result["ordinary_income"] == Decimal("46175.00")
        assert result["officer_salary"] == Decimal("50000")
        assert result["employer_payroll_taxes"] == Decimal("3825.00")


class TestScorpTotalProjectedTax:
    """S-Corp total_projected_tax branching."""

    def test_entity_type_in_result(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.total_projected_tax(Decimal("100000"))

        assert result["entity_type"] == "scorp"
        assert "fica" in result
        assert "form_1120s" in result

    def test_smllc_path_unchanged(self, sample_config, clean_ledger):
        """SMLLC config still returns SMLLC path."""
        from app.taxes import TaxEstimator
        te = TaxEstimator(sample_config, clean_ledger)
        result = te.total_projected_tax(Decimal("4800"))

        assert result["entity_type"] == "smllc"
        assert "self_employment_tax" in result
        assert "fica" not in result


class TestForm1120SExport:
    """Form 1120-S data export."""

    def test_export_has_expected_keys(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.form_1120s_export(Decimal("100000"))

        assert result["form"] == "1120-S"
        assert "income" in result
        assert "expense_detail" in result
        assert "balance_sheet" in result
        assert "shareholder" in result

        income = result["income"]
        assert "gross_receipts" in income
        assert "officer_compensation" in income
        assert "employer_payroll_taxes" in income
        assert "ordinary_income" in income

    def test_ordinary_income_formula(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.form_1120s_export(Decimal("100000"))

        # ordinary_income = net_profit - salary - employer_fica
        # 100000 - 50000 - 3825 = 46175
        assert result["income"]["ordinary_income"] == Decimal("46175.00")

    def test_shareholder_info(self, scorp_config, clean_ledger):
        from app.taxes import TaxEstimator
        te = TaxEstimator(scorp_config, clean_ledger)
        result = te.form_1120s_export(Decimal("100000"))

        assert result["shareholder"]["ownership_pct"] == 100
        assert result["shareholder"]["ordinary_income"] == result["income"]["ordinary_income"]
