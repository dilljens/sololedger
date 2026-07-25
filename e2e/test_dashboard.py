"""E2E tests for Dashboard, Health, and Accounts pages."""


class TestDashboardPage:
    """📊 Dashboard page — the landing page (default page)."""

    def test_has_heading(self, app_page):
        app_page.wait_for_selector("h1", timeout=10000)
        assert app_page.locator("h1").is_visible()

    def test_has_stat_cards(self, app_page):
        app_page.wait_for_selector(".stat-card", timeout=10000)
        assert app_page.locator(".stat-card").count() >= 2

    def test_has_page_content_area(self, app_page):
        el = app_page.locator("#page-content")
        app_page.wait_for_selector("#page-content", timeout=10000)
        assert el.is_visible()

    def test_no_js_errors(self, app_page, console_errors):
        app_page.wait_for_load_state("networkidle", timeout=15000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestHealthPage:
    """🔍 Ledger Health page."""

    def test_heading(self, app_page, nav_to):
        nav_to("health")
        text = app_page.locator("h1").text_content() or ""
        assert "Health" in text

    def test_shows_validation_result(self, app_page, nav_to):
        nav_to("health")
        app_page.wait_for_timeout(3000)
        el = app_page.locator("#health-results")
        inner = el.text_content() or ""
        assert any(kw in inner.lower() for kw in ["clean", "error", "valid"])

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("health")
        app_page.wait_for_timeout(3000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestAccountsPage:
    """🏦 Accounts page."""

    def test_heading(self, app_page, nav_to):
        nav_to("accounts")
        text = app_page.locator("h1").text_content() or ""
        assert "Accounts" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("accounts")
        app_page.wait_for_timeout(3000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"
