"""E2E smoke tests for all remaining pages — verify each renders without errors."""

import pytest


pytestmark = pytest.mark.e2e


class TestAllPagesSmoke:
    """Quick smoke test — navigate to each page in a single session."""

    ALL_PAGES = [
        "accounts",
        "import",
        "invoices",
        "transactions",
        "receipts",
        "categorize",
        "tax",
        "deadlines",
        "mileage",
        "health",
        "reports",
        "settings",
    ]

    def test_all_pages_navigate_without_error(self, browser_page):
        """Navigate to each page in sequence and verify no JS pageerror."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")

        for page_name in self.ALL_PAGES:
            nav_link = page.query_selector(f'[data-page="{page_name}"]')
            if nav_link:
                try:
                    nav_link.click()
                    page.wait_for_timeout(1000)
                except Exception as e:
                    errors.append(f"NAV_ERROR on '{page_name}': {e}")

            # Check for page crashes
            if errors:
                pytest.fail(f"After page '{page_name}': {errors}")
