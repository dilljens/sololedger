"""Stripe payment integration — create payment links for invoices.

Requires:
  - stripe Python package
  - STRIPE_SECRET_KEY env var
  - STRIPE_PRICE_ID optional env var (for recurring/retainer invoices)

Usage:
    from app.payments import StripePayments
    sp = StripePayments()
    link = sp.create_payment_link(amount=5000.00, description="Q3 Consulting")
    # → "https://buy.stripe.com/test_..."
"""

import os
import sys
from decimal import Decimal
from typing import Optional

import stripe


class StripePayments:
    """Create and manage Stripe payment links for invoices."""

    def __init__(self):
        self.api_key = os.environ.get("STRIPE_SECRET_KEY", "")
        if not self.api_key:
            self._enabled = False
        else:
            stripe.api_key = self.api_key
            self._enabled = True

    @property
    def enabled(self) -> bool:
        return self._enabled

    def create_payment_link(
        self,
        amount: Decimal,
        description: str,
        invoice_number: Optional[str] = None,
        client_email: Optional[str] = None,
        metadata: Optional[dict] = None,
    ) -> dict:
        """Create a Stripe payment link for an invoice.

        Args:
            amount: Invoice amount in dollars (e.g. Decimal("5000.00"))
            description: What the invoice is for
            invoice_number: Your internal invoice number (added to metadata)
            client_email: Pre-fill client email on checkout page
            metadata: Extra metadata to attach (e.g. {"client": "Acme Corp"})

        Returns:
            dict with:
              - url: The payment link URL
              - id: The Stripe payment link ID
              - enabled: Whether Stripe is configured

        If Stripe is not configured, returns {"enabled": False, "url": None, "id": None}.
        """
        if not self._enabled:
            return {"enabled": False, "url": None, "id": None}

        meta = dict(metadata or {})
        if invoice_number:
            meta["invoice_number"] = invoice_number

        # Convert dollars to cents for Stripe
        amount_cents = int(amount * Decimal("100"))

        try:
            # Create a product (or use existing one for this description)
            product = stripe.Product.create(
                name=description[:100],
                metadata=meta,
            )

            # Create a price for this product
            price = stripe.Price.create(
                product=product.id,
                unit_amount=amount_cents,
                currency="usd",
            )

            # Build the payment link
            link_params = {
                "line_items": [{"price": price.id, "quantity": 1}],
                "metadata": meta,
            }

            if client_email:
                link_params["customer_creation"] = "always"
                # Create or retrieve customer by email for prefill
                try:
                    customers = stripe.Customer.list(email=client_email, limit=1)
                    if customers.data:
                        link_params["customer"] = customers.data[0].id
                except Exception:
                    pass  # Non-critical — link still works without prefill

            payment_link = stripe.PaymentLink.create(**link_params)

            return {
                "enabled": True,
                "url": payment_link.url,
                "id": payment_link.id,
            }

        except stripe.error.StripeError as e:
            print(f"⚠  Stripe error: {e}", file=sys.stderr)
            return {"enabled": True, "url": None, "id": None, "error": str(e)}

    def create_recurring_link(
        self,
        amount: Decimal,
        description: str,
        interval: str = "month",
        interval_count: int = 1,
        invoice_number: Optional[str] = None,
    ) -> dict:
        """Create a subscription-style payment link for retainer invoices.

        Args:
            amount: Recurring amount in dollars
            description: What the subscription is for
            interval: 'month' or 'year'
            interval_count: Every N intervals (default 1)
            invoice_number: Optional invoice number for metadata

        Returns:
            dict with url, id, enabled
        """
        if not self._enabled:
            return {"enabled": False, "url": None, "id": None}

        meta = {}
        if invoice_number:
            meta["invoice_number"] = invoice_number

        amount_cents = int(amount * Decimal("100"))

        try:
            product = stripe.Product.create(
                name=f"{description} (recurring)",
                metadata=meta,
            )

            price = stripe.Price.create(
                product=product.id,
                unit_amount=amount_cents,
                currency="usd",
                recurring={"interval": interval, "interval_count": interval_count},
            )

            payment_link = stripe.PaymentLink.create(
                line_items=[{"price": price.id, "quantity": 1}],
                metadata=meta,
            )

            return {"enabled": True, "url": payment_link.url, "id": payment_link.id}

        except stripe.error.StripeError as e:
            print(f"⚠  Stripe error: {e}", file=sys.stderr)
            return {"enabled": True, "url": None, "id": None, "error": str(e)}

    def check_payment_status(self, payment_link_id: str) -> dict:
        """Check how many times a payment link has been completed.

        This is a simple check — for production, use Stripe webhooks.
        """
        if not self._enabled:
            return {"enabled": False}

        try:
            sessions = stripe.checkout.Session.list(
                payment_link=payment_link_id,
                limit=10,
            )
            completed = [s for s in sessions if s.payment_status == "paid"]
            return {
                "enabled": True,
                "total_completed": len(completed),
                "total_revenue_cents": sum(s.amount_total or 0 for s in completed),
            }
        except stripe.error.StripeError as e:
            return {"enabled": True, "error": str(e)}
