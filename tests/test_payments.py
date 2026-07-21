"""Tests for app/payments.py — StripePayments."""

from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest


class TestStripePaymentsDisabled:
    """StripePayments when STRIPE_SECRET_KEY is not set."""

    def test_enabled_false_when_no_key(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.payments import StripePayments
            sp = StripePayments()
            assert sp.enabled is False

    def test_create_payment_link_returns_not_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.payments import StripePayments
            sp = StripePayments()
            result = sp.create_payment_link(Decimal("5000.00"), "Test invoice")
            assert result == {"enabled": False, "url": None, "id": None}

    def test_create_recurring_link_returns_not_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.payments import StripePayments
            sp = StripePayments()
            result = sp.create_recurring_link(Decimal("5000.00"), "Retainer")
            assert result == {"enabled": False, "url": None, "id": None}

    def test_check_payment_status_returns_not_enabled(self):
        with patch.dict("os.environ", {}, clear=True):
            from app.payments import StripePayments
            sp = StripePayments()
            result = sp.check_payment_status("plink_123")
            assert result == {"enabled": False}


class TestStripePaymentsEnabled:
    """StripePayments with mocked Stripe API."""

    @pytest.fixture
    def mock_stripe(self):
        mock = MagicMock()

        mock_product = MagicMock()
        mock_product.id = "prod_test123"
        mock.Product.create.return_value = mock_product

        mock_price = MagicMock()
        mock_price.id = "price_test123"
        mock.Price.create.return_value = mock_price

        mock_payment_link = MagicMock()
        mock_payment_link.url = "https://buy.stripe.com/test_abc123"
        mock_payment_link.id = "plink_test123"
        mock.PaymentLink.create.return_value = mock_payment_link

        mock_customers = MagicMock()
        mock_customers.data = []
        mock.Customer.list.return_value = mock_customers

        mock_session = MagicMock()
        mock_session.payment_status = "paid"
        mock_session.amount_total = 500000
        mock.checkout.Session.list.return_value = [mock_session]

        return mock

    def test_create_payment_link_success(self, mock_stripe):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
            with patch("app.payments.stripe", mock_stripe):
                from app.payments import StripePayments
                sp = StripePayments()
                assert sp.enabled is True

                result = sp.create_payment_link(
                    Decimal("5000.00"),
                    "Q3 Consulting",
                    invoice_number="INV-001",
                    client_email="client@example.com",
                )

                assert result["enabled"] is True
                assert result["url"] == "https://buy.stripe.com/test_abc123"
                assert result["id"] == "plink_test123"

                mock_stripe.Product.create.assert_called_once_with(
                    name="Q3 Consulting",
                    metadata={"invoice_number": "INV-001"},
                )
                mock_stripe.Price.create.assert_called_once_with(
                    product="prod_test123",
                    unit_amount=500000,
                    currency="usd",
                )
                mock_stripe.PaymentLink.create.assert_called_once()

    def test_create_payment_link_without_invoice_number(self, mock_stripe):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
            with patch("app.payments.stripe", mock_stripe):
                from app.payments import StripePayments
                sp = StripePayments()

                result = sp.create_payment_link(Decimal("100.00"), "Test")
                assert result["enabled"] is True

    def test_create_recurring_link_success(self, mock_stripe):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
            with patch("app.payments.stripe", mock_stripe):
                from app.payments import StripePayments
                sp = StripePayments()
                assert sp.enabled is True

                result = sp.create_recurring_link(
                    Decimal("2500.00"),
                    "Monthly retainer",
                    interval="month",
                    interval_count=1,
                    invoice_number="RET-001",
                )

                assert result["enabled"] is True
                assert result["url"] == "https://buy.stripe.com/test_abc123"

                mock_stripe.Product.create.assert_called_once_with(
                    name="Monthly retainer (recurring)",
                    metadata={"invoice_number": "RET-001"},
                )
                mock_stripe.Price.create.assert_called_once_with(
                    product="prod_test123",
                    unit_amount=250000,
                    currency="usd",
                    recurring={"interval": "month", "interval_count": 1},
                )

    def test_check_payment_status_success(self, mock_stripe):
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
            with patch("app.payments.stripe", mock_stripe):
                from app.payments import StripePayments
                sp = StripePayments()

                result = sp.check_payment_status("plink_test123")

                assert result["enabled"] is True
                assert result["total_completed"] == 1
                assert result["total_revenue_cents"] == 500000

    def test_stripe_error_graceful_handling(self, mock_stripe):
        class MockStripeError(Exception):
            pass

        mock_stripe.error.StripeError = MockStripeError
        mock_stripe.Product.create.side_effect = MockStripeError("API error")
        with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
            with patch("app.payments.stripe", mock_stripe):
                from app.payments import StripePayments
                sp = StripePayments()

                result = sp.create_payment_link(Decimal("5000.00"), "Test")
                assert result["enabled"] is True
                assert result["url"] is None
