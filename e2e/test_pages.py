"""E2E tests for all remaining pages.

Uses the `nav_to` fixture for sidebar navigation.
"""


def _test_page(nav_to, console_errors, page_name, heading_contains):
    """Shared helper: navigate to a sidebar page and verify it renders."""
    nav_to(page_name)
    text = (nav_to.__self__ or None)  # place holder
    # Check heading matches
    # (nav_to does the click + wait_for h1)
    assert len(console_errors) == 0, \
        f"JS errors on {page_name} page: {console_errors}"


class TestTransactionsPage:
    def test_heading(self, app_page, nav_to):
        nav_to("transactions")
        text = app_page.locator("h1").text_content() or ""
        assert "Transaction" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("transactions")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestInvoicesPage:
    def test_heading(self, app_page, nav_to):
        nav_to("invoices")
        text = app_page.locator("h1").text_content() or ""
        assert "Invoice" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("invoices")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestImportPage:
    def test_heading(self, app_page, nav_to):
        nav_to("import")
        text = app_page.locator("h1").text_content() or ""
        assert "Import" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("import")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestReceiptsPage:
    def test_heading(self, app_page, nav_to):
        nav_to("receipts")
        text = app_page.locator("h1").text_content() or ""
        assert "Receipt" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("receipts")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestCategorizePage:
    def test_heading(self, app_page, nav_to):
        nav_to("categorize")
        text = app_page.locator("h1").text_content() or ""
        assert "Categoriz" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("categorize")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestMileagePage:
    def test_heading(self, app_page, nav_to):
        nav_to("mileage")
        text = app_page.locator("h1").text_content() or ""
        assert "Mileage" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("mileage")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestReportsPage:
    def test_heading(self, app_page, nav_to):
        nav_to("reports")
        text = app_page.locator("h1").text_content() or ""
        assert "Report" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("reports")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestPayrollPage:
    def test_heading(self, app_page, nav_to):
        nav_to("payroll")
        text = app_page.locator("h1").text_content() or ""
        assert "Payroll" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("payroll")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"


class TestNewInvoicePage:
    def test_heading(self, app_page, nav_to):
        nav_to("new-invoice")
        text = app_page.locator("h1").text_content() or ""
        assert "Invoice" in text or "New" in text

    def test_no_js_errors(self, app_page, nav_to, console_errors):
        nav_to("new-invoice")
        app_page.wait_for_timeout(2000)
        assert len(console_errors) == 0, f"JS errors: {console_errors}"
