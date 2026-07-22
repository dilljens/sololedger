"""Tests for app/payroll.py — PayrollImporter (S-Corp payroll)."""

import datetime
from decimal import Decimal

import pytest


class TestPayrollInit:
    """PayrollImporter creation."""

    def test_init_with_scorp_config(self, scorp_config, clean_ledger):
        from app.payroll import PayrollImporter
        pi = PayrollImporter(scorp_config, clean_ledger)
        assert pi.cfg is scorp_config
        assert pi.ledger is clean_ledger

    def test_init_smllc_warns(self, sample_config, clean_ledger):
        from app.payroll import PayrollImporter
        import warnings
        with pytest.warns(UserWarning, match="S-Corp"):
            PayrollImporter(sample_config, clean_ledger)


class TestGustoImport:
    """Gusto CSV import."""

    def test_file_not_found(self, scorp_config, clean_ledger):
        from app.payroll import PayrollImporter
        pi = PayrollImporter(scorp_config, clean_ledger)
        results = pi.import_gusto_csv("/nonexistent/path.csv")
        assert len(results) == 1
        assert "error" in results[0]
        assert "not found" in results[0]["error"]

    def test_empty_csv(self, scorp_config, clean_ledger, tmp_path):
        from app.payroll import PayrollImporter
        csv_file = tmp_path / "empty.csv"
        csv_file.write_text("")
        pi = PayrollImporter(scorp_config, clean_ledger)
        results = pi.import_gusto_csv(str(csv_file))
        assert "error" in results[0]

    def test_preview_no_write(self, scorp_config, clean_ledger, tmp_path):
        from app.payroll import PayrollImporter
        csv_file = tmp_path / "payroll.csv"
        csv_file.write_text("""\
Pay Period Start,Pay Period End,Employee,Gross Pay,Net Pay,Employee Social Security,Employee Medicare,Employee Federal Withholding,Employee State Withholding,Employer Social Security,Employer Medicare,Employer FUTA,Employer SUTA
2026-01-01,2026-01-15,Owner,5000.00,3461.54,310.00,72.50,750.00,156.46,310.00,72.50,42.00,0.00
""")
        pi = PayrollImporter(scorp_config, clean_ledger)
        results = pi.import_gusto_csv(str(csv_file), preview=True)

        assert len(results) == 1
        assert results[0]["gross"] == 5000.0
        assert results[0]["net"] == 3461.54
        assert results[0]["preview"] is True

    def test_auto_compute_employer_taxes(self, scorp_config, clean_ledger, tmp_path):
        """When CSV omits employer taxes, PayrollImporter auto-computes them."""
        from app.payroll import PayrollImporter
        csv_file = tmp_path / "payroll_minimal.csv"
        csv_file.write_text("""\
Pay Period Start,Pay Period End,Employee,Gross Pay,Net Pay,Employee Social Security,Employee Medicare,Employee Federal Withholding,Employee State Withholding
2026-01-01,2026-01-15,Owner,5000.00,3461.54,310.00,72.50,750.00,156.46
""")
        pi = PayrollImporter(scorp_config, clean_ledger)
        results = pi.import_gusto_csv(str(csv_file), preview=True)

        assert len(results) == 1
        assert results[0]["gross"] == 5000.0
        # Auto-computed ER SS = 5000 * 0.062 = 310, ER Med = 5000 * 0.0145 = 72.50
        assert results[0]["total_employer_taxes"] == pytest.approx(382.5, rel=0.01)


class TestPayrollDisburse:
    """Payroll disbursement."""

    def test_disburse_preview(self, scorp_config, clean_ledger):
        from app.payroll import PayrollImporter
        pi = PayrollImporter(scorp_config, clean_ledger)
        result = pi.payroll_disburse(
            pay_date=datetime.date(2026, 1, 31),
            net_pay=Decimal("3461.54"),
            preview=True,
        )

        assert result["net_pay"] == 3461.54
        assert result["date"] == "2026-01-31"
        assert result["bank_account"] == "Assets:Bank:BusinessChecking"
        assert result["preview"] is True

    def test_disburse_custom_bank(self, scorp_config, clean_ledger):
        from app.payroll import PayrollImporter
        pi = PayrollImporter(scorp_config, clean_ledger)
        result = pi.payroll_disburse(
            pay_date=datetime.date(2026, 1, 31),
            net_pay=Decimal("3461.54"),
            bank_account="Assets:Bank:Personal",
            preview=True,
        )

        assert result["bank_account"] == "Assets:Bank:Personal"
