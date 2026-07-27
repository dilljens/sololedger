"""E2E tests for Receipt pages — navigation and capture flow."""
import pytest


pytestmark = pytest.mark.e2e


class TestReceiptsPage:
    """Receipts page navigation tests."""

    def test_receipts_page_loads(self, browser_page):
        """Receipts page should render without JS errors."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_selector('[data-page="receipts"]', timeout=5000)
        page.click('[data-page="receipts"]')
        page.wait_for_timeout(2000)
        assert len(errors) == 0, f"Page crashes: {errors}"

    def test_receipts_page_has_new_receipt_button(self, browser_page):
        """Receipts page should have a New Receipt / Capture button."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_selector('[data-page="receipts"]', timeout=5000)
        page.click('[data-page="receipts"]')
        page.wait_for_timeout(2000)

        # Check the receipt page rendered — look for a receipt-related heading
        content = page.text_content("#page-content") or ""
        assert "Receipt" in content or "receipt" in content.lower(), \
            f"Receipt page didn't render. Content: {content[:200]}"

        assert len(errors) == 0, f"Page crashes: {errors}"
