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
