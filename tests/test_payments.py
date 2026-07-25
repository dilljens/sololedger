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
        from app.payments import StripePayments
        sp = StripePayments()
        result = sp.create_payment_link(Decimal("5000.00"), "Test")
        assert result["enabled"] is False
        assert result["url"] is None

    def test_create_recurring_link_returns_not_enabled(self):
        from app.payments import StripePayments
        sp = StripePayments()
        result = sp.create_recurring_link(Decimal("5000.00"), "Test")
        assert result["enabled"] is False
        assert result["url"] is None

    def test_check_payment_status_returns_not_enabled(self):
        from app.payments import StripePayments
        sp = StripePayments()
        result = sp.check_payment_status("plink_test")
        assert result["enabled"] is False


@pytest.fixture
def mock_stripe():
    """Create a mock stripe module."""
    stripe = MagicMock()
    stripe.Product.create.return_value = MagicMock(id="prod_test123")
    stripe.Price.create.return_value = MagicMock(id="price_test123")
    mock_link = MagicMock()
    mock_link.url = "https://buy.stripe.com/test_link"
    mock_link.id = "plink_test123"
    stripe.PaymentLink.create.return_value = mock_link
    stripe.Customer.list.return_value.data = [MagicMock(id="cus_test123")]
    mock_session = MagicMock()
    mock_session.payment_status = "paid"
    mock_session.amount_total = 500000
    stripe.checkout.Session.list.return_value = [mock_session]
    return stripe


def _make_payments():
    """Create a StripePayments instance with mocked stripe."""
    from app.payments import StripePayments
    with patch.dict("os.environ", {"STRIPE_SECRET_KEY": "sk_test_xyz"}, clear=True):
        from app.payments import StripePayments
        return StripePayments()


class TestStripePaymentsEnabled:
    """StripePayments when STRIPE_SECRET_KEY is set and stripe is mocked."""

    def test_create_payment_link_success(self, mock_stripe):
        sp = _make_payments()
        assert sp.enabled is True
        with patch.object(sp, "_ensure_stripe", return_value=mock_stripe):
            result = sp.create_payment_link(Decimal("5000.00"), "Test invoice")
        assert result["enabled"] is True
        assert result["url"] == "https://buy.stripe.com/test_link"

    def test_create_payment_link_without_invoice_number(self, mock_stripe):
        sp = _make_payments()
        assert sp.enabled is True
        with patch.object(sp, "_ensure_stripe", return_value=mock_stripe):
            result = sp.create_payment_link(Decimal("2500.00"), "Simple invoice")
        assert result["enabled"] is True
        assert result["url"] == "https://buy.stripe.com/test_link"

    def test_create_recurring_link_success(self, mock_stripe):
        sp = _make_payments()
        assert sp.enabled is True
        with patch.object(sp, "_ensure_stripe", return_value=mock_stripe):
            result = sp.create_recurring_link(
                Decimal("2500.00"), "Monthly retainer",
                interval="month", interval_count=1,
            )
        assert result["enabled"] is True
        assert result["url"] == "https://buy.stripe.com/test_link"

    def test_check_payment_status_success(self, mock_stripe):
        sp = _make_payments()
        assert sp.enabled is True
        with patch.object(sp, "_ensure_stripe", return_value=mock_stripe):
            result = sp.check_payment_status("plink_test123")
        assert result["enabled"] is True
        assert result["total_completed"] == 1
        assert result["total_revenue_cents"] == 500000

    def test_stripe_error_graceful_handling(self, mock_stripe):
        # Create a StripeError with proper module path
        class MockStripeError(Exception):
            pass
        MockStripeError.__module__ = "stripe.error"
        mock_stripe.error.StripeError = MockStripeError
        mock_stripe.Product.create.side_effect = MockStripeError("API error")

        sp = _make_payments()
        assert sp.enabled is True
        with patch.object(sp, "_ensure_stripe", return_value=mock_stripe):
            result = sp.create_payment_link(Decimal("5000.00"), "Test")
        assert result["enabled"] is True
        assert result["url"] is None
