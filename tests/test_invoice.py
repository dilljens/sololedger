"""Tests for app/invoice.py — Invoicer and RetainerConfig."""

from decimal import Decimal

import pytest


class TestInvoicer:
    """Invoice creation, listing, AR check."""

    def test_list_invoices(self, clean_ledger, sample_config):
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        invoices = invoicer.list()
        assert isinstance(invoices, list)

    def test_list_invoices_by_year(self, clean_ledger, sample_config):
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        invoices = invoicer.list(year=1970)
        assert isinstance(invoices, list)

    def test_ar_check(self, clean_ledger, sample_config):
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        info = invoicer.check_ar()
        assert "total_ar" in info
        assert "invoice_count" in info
        assert "overdue_count" in info
        assert isinstance(info["total_ar"], Decimal)
        assert isinstance(info["invoice_count"], int)

    def test_retainers_path(self, clean_ledger, sample_config):
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        path = invoicer._retainers_path()
        assert path.name == "retainers.json"

    def test_create_invoice_minimal(self, clean_ledger, sample_config):
        """Minimal smoke test — creating an invoice entry in the ledger."""
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        result = invoicer.create(
            client="TestClient",
            description="Test work",
            amount=Decimal("1000.00"),
            generate_pdf=False,
            payment_link=False,
        )
        assert result["number"] is not None
        assert result["date"] is not None
        assert "payment_url" not in result
        assert "pdf_path" not in result

    def test_create_invoice_invalid_amount(self, clean_ledger, sample_config):
        """Invoice with invalid amount type raises."""
        from app.invoice import Invoicer
        invoicer = Invoicer(sample_config, clean_ledger)
        with pytest.raises(Exception):
            invoicer.create(
                client="X",
                description="desc",
                amount="not_a_number",  # type: ignore
                generate_pdf=False,
            )


class TestRetainerConfig:
    """RetainerConfig dataclass."""

    def test_minimal_retainer(self):
        from app.invoice import RetainerConfig
        r = RetainerConfig(
            client="Client A",
            description="Monthly retainer",
            amount=Decimal("5000.00"),
            interval="monthly",
        )
        assert r.client == "Client A"
        assert r.amount == Decimal("5000.00")
        assert r.interval == "monthly"
        assert r.day_of_month == 1  # default
        assert r.stripe_recurring is False

    def test_retainer_quarterly(self):
        from app.invoice import RetainerConfig
        r = RetainerConfig(
            client="Client B",
            description="Quarterly retainer",
            amount=Decimal("15000.00"),
            interval="quarterly",
            day_of_month=15,
            stripe_recurring=True,
        )
        assert r.interval == "quarterly"
        assert r.day_of_month == 15
        assert r.stripe_recurring is True

    def test_retainer_yearly(self):
        from app.invoice import RetainerConfig
        r = RetainerConfig(
            client="Client C",
            description="Annual retainer",
            amount=Decimal("60000.00"),
            interval="yearly",
        )
        assert r.interval == "yearly"
