"""E2E tests for Tax and Deadlines pages — the most crash-prone pages."""


class TestTaxPage:
    """💰 Tax Estimate page — had the reported `self_employment_tax.total` crash."""

    def _go(self, app_page):
        sidebar = app_page.locator('.sidebar')
        link = sidebar.locator('[data-page="tax"]')
        if link.count() > 0:
            link.nth(0).click()
        else:
            app_page.locator('[data-page="tax"]').nth(0).click()
        app_page.wait_for_timeout(3000)

    def test_renders_without_crash_elements(self, app_page):
        """The reported bug: accessing self_employment_tax.total on undefined.
        Check for crash indicators: the error message div from app.js catch block.
        """
        self._go(app_page)
        app_page.wait_for_timeout(2000)
        # The app.js catch block shows: <div class="error"><h3>⚠ Error</h3><p>...</p></div>
        error_div = app_page.locator('.error')
        # Only fail if there's an actual error DIV (not if the word appears in text)
        if error_div.count() > 0:
            text = error_div.text_content() or ""
            # Skip the disclaimer — it's in a different styled div
            is_crash = "Cannot read properties" in text or "undefined" in text or "API error" in text
            assert not is_crash, f"Tax page crashed: {text}"

    def test_shows_heading_or_no_profit(self, app_page):
        self._go(app_page)
        app_page.wait_for_timeout(2000)
        heading = app_page.locator("#page-content h1")
        assert heading.is_visible(), "Tax page: no h1 heading"

    def test_shows_tax_content(self, app_page):
        self._go(app_page)
        app_page.wait_for_timeout(3000)
        # Should show either tax estimate data or the no-profit message
        content = app_page.locator("#page-content")
        text = content.text_content() or ""
        has_content = any(kw in text for kw in [
            "Tax Estimate", "No Tax Due Yet", "Total Estimated Tax",
            "Federal", "Self-Employment", "Effective rate"
        ])
        assert has_content, "Tax page: no recognizable content"

    def test_no_js_errors(self, app_page, console_errors):
        self._go(app_page)
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors on tax page: {console_errors}"


class TestDeadlinesPage:
    """📅 Tax Deadlines page."""

    def _go(self, app_page):
        sidebar = app_page.locator('.sidebar')
        link = sidebar.locator('[data-page="deadlines"]')
        if link.count() > 0:
            link.nth(0).click()
        else:
            app_page.locator('[data-page="deadlines"]').nth(0).click()
        app_page.wait_for_timeout(2000)

    def test_loads(self, app_page):
        self._go(app_page)
        heading = app_page.locator("#page-content h1")
        assert heading.is_visible()

    def test_no_js_errors(self, app_page, console_errors):
        self._go(app_page)
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors on deadlines page: {console_errors}"


class TestSettingsPage:
    """⚙️ Settings page — also invokes llm + subscription APIs."""

    def _go(self, app_page):
        sidebar = app_page.locator('.sidebar')
        link = sidebar.locator('[data-page="settings"]')
        if link.count() > 0:
            link.nth(0).click()
        else:
            app_page.locator('[data-page="settings"]').nth(0).click()
        app_page.wait_for_timeout(2000)

    def test_loads(self, app_page):
        self._go(app_page)
        heading = app_page.locator("#page-content h1")
        assert heading.is_visible()

    def test_no_js_errors(self, app_page, console_errors):
        self._go(app_page)
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors on settings page: {console_errors}"
