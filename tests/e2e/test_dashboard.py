"""E2E tests for Dashboard and landing pages."""
import pytest


pytestmark = pytest.mark.e2e


class TestDashboard:
    """Dashboard page smoke tests."""

    def test_dashboard_loads(self, browser_page):
        """Dashboard page should render without JS errors."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        # Wait for SPA to render content into #page-content
        page.wait_for_selector("#page-content", timeout=15000)
        # Wait a bit for API data to load
        page.wait_for_timeout(2000)
        # Check for crash-level JS errors (pageerror events)
        assert len(errors) == 0, f"Page crashes: {errors}"

    def test_navigation_sidebar_visible(self, browser_page):
        """Sidebar navigation should be present."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_selector(".sidebar", timeout=10000)
        sidebar = page.query_selector(".sidebar")
        assert sidebar is not None
        # Should have nav links
        links = page.query_selector_all(".sidebar a")
        assert len(links) >= 10


class TestAccountsPage:
    """Accounts page smoke tests."""

    def test_accounts_page_loads(self, browser_page):
        """Accounts page should navigate and render."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_selector('[data-page="accounts"]', timeout=5000)
        page.click('[data-page="accounts"]')
        page.wait_for_timeout(2000)
        assert len(errors) == 0, f"Page crashes: {errors}"


class TestStatusIndicator:
    """The public status endpoint should indicate the app is running."""

    def test_health_endpoint(self, api_server):
        """GET /api/v1/health should return 200."""
        import urllib.request
        import json
        resp = urllib.request.urlopen(f"{api_server}/api/v1/health")
        assert resp.status == 200
        data = json.loads(resp.read())
        assert data["success"] is True
        assert data["data"]["status"] == "ok"
