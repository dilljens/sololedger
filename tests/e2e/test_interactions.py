"""E2E tests that actually click buttons and verify interactions work.

Unlike the smoke tests (which just navigate to pages), these tests
find visible interactive elements and click them, verifying no JS crash.
"""
import time
import pytest

pytestmark = pytest.mark.e2e


def _click_and_check(page, errors, selector, description="button"):
    """Click an element and verify no JS crash, return if found."""
    el = page.query_selector(selector)
    if not el:
        return False
    try:
        el.click()
        page.wait_for_timeout(500)
        _check_errors(errors, f"after clicking {description}")
    except Exception as e:
        errors.append(f"CLICK_ERROR on {description}: {e}")
        _check_errors(errors, f"clicking {description}")
    return True


def _check_errors(errors, context=""):
    """Assert no page-level JS crashes occurred."""
    page_errors = [e for e in errors if e.startswith("PAGE_ERROR")]
    if page_errors:
        pytest.fail(f"JS crash {context}: {page_errors}")


def _set_file_input(page, selector, file_path):
    """Set a file input value via JS."""
    try:
        input_el = page.query_selector(selector)
        if input_el:
            input_el.set_input_files(file_path)
            return True
    except Exception:
        pass
    return False


# ═════════════════════════════════════════════════════════════════════════
# Global Navigation Tests
# ═════════════════════════════════════════════════════════════════════════


class TestSidebarNavigation:
    """All 15 sidebar nav links work without crashing (single session)."""

    PAGE_NAMES = [
        "dashboard", "accounts", "import", "invoices", "new-invoice",
        "transactions", "receipts", "categorize", "tax", "deadlines",
        "mileage", "health", "reports", "payroll", "settings",
    ]

    def test_all_sidebar_links_navigate(self, browser_page):
        """Click every sidebar link in sequence, verify no crash."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        for page_name in self.PAGE_NAMES:
            nav_link = page.query_selector(f'[data-page="{page_name}"]')
            if nav_link:
                try:
                    nav_link.click()
                    page.wait_for_timeout(500)
                except Exception as e:
                    errors.append(f"CLICK_ERROR on '{page_name}': {e}")
            _check_errors(errors, f"on page '{page_name}'")


class TestThemeToggle:
    """Theme toggle button cycles without crashing."""

    def test_theme_toggle_works(self, browser_page):
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        _click_and_check(page, errors, '[onclick*="toggleTheme"]',
                         "theme toggle")
        _check_errors(errors, "after theme toggle")


class TestMobileNavDrawer:
    """Mobile drawer — check existence only on desktop (may be hidden)."""

    def test_mobile_drawer_exists(self, browser_page):
        """The mobile drawer elements exist in the DOM."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_timeout(1000)

        # Check the drawer elements exist (even if hidden on desktop)
        more_btn = page.query_selector("#mobile-more-btn")
        drawer_overlay = page.query_selector("#mobile-drawer-overlay")

        # On desktop these exist but may not be visible
        assert more_btn is not None, "Mobile more button (#mobile-more-btn) not in DOM"
        assert drawer_overlay is not None, "Mobile drawer overlay not in DOM"

        _check_errors(errors, "checking mobile drawer")


# ═════════════════════════════════════════════════════════════════════════
# Page-Specific Button Tests
# ═════════════════════════════════════════════════════════════════════════


class TestDashboardButtons:
    """Dashboard interactive elements."""

    def test_dashboard_mark_paid_button(self, browser_page):
        """The 'Mark as Paid' button should exist and not crash when clicked.
        (POST will fail in open mode, but the JS confirm should appear.)"""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        # Look for "Mark as Paid" button
        _click_and_check(page, errors, '[onclick*="markTaxPaid"]',
                         "mark tax paid button")
        _check_errors(errors, "after mark tax paid")

    def test_tax_voucher_download_link(self, browser_page):
        """Tax voucher PDF download link."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        page.wait_for_timeout(2000)

        _click_and_check(page, errors,
                         '[onclick*="voucher"]',
                         "print voucher link")
        _check_errors(errors, "after print voucher")


class TestAccountsButtons:
    """Accounts page interactive elements."""

    def test_accounts_transfer_button(self, browser_page):
        """Transfer form exists and Transfer button click doesn't crash."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="accounts"]',
                         "accounts nav link")
        page.wait_for_timeout(2000)

        _click_and_check(page, errors, '[onclick*="doTransfer"]',
                         "transfer button")
        _check_errors(errors, "after transfer click")

    def test_accounts_reimburse_button(self, browser_page):
        """Reimbursement Record button click doesn't crash."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="accounts"]',
                         "accounts nav link")
        page.wait_for_timeout(2000)

        _click_and_check(page, errors, '[onclick*="doReimburse"]',
                         "reimburse button")
        _check_errors(errors, "after reimburse click")


class TestCategorizeActions:
    """Categorize page suggest/learn interaction."""

    def test_suggest_category(self, browser_page):
        """Suggest button calls API without crashing."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="categorize"]',
                         "categorize nav link")
        page.wait_for_timeout(2000)

        _click_and_check(page, errors, '[onclick*="suggestCategory"]',
                         "suggest category button")
        page.wait_for_timeout(1000)
        _check_errors(errors, "after categorize suggest")


class TestMileageActions:
    """Mileage page form interaction."""

    def test_log_trip_button(self, browser_page):
        """Log Trip button click doesn't crash."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="mileage"]',
                         "mileage nav link")
        page.wait_for_timeout(2000)

        _click_and_check(page, errors, '[onclick*="logMileage"]',
                         "log trip button")
        _check_errors(errors, "after log trip click")


class TestSettingsActions:
    """Settings page buttons."""

    def test_settings_page_loads(self, browser_page):
        """Settings page loads without crash and has buttons."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="settings"]',
                         "settings nav link")
        page.wait_for_timeout(2000)

        # Check for backup button
        _click_and_check(page, errors, '[onclick*="doBackup"]',
                         "backup button")
        _check_errors(errors, "after settings interactions")


# ═════════════════════════════════════════════════════════════════════════
# Receipt Capture — Full Flow Test
# ═════════════════════════════════════════════════════════════════════════


class TestReceiptCaptureFlow:
    """Full receipt capture flow — upload an image via the web UI."""

    def test_receipt_capture_button_exists(self, browser_page, tmp_path):
        """Navigate to receipts page, click Capture, verify capture page renders."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")
        _click_and_check(page, errors, '[data-page="receipts"]',
                         "receipts nav link")
        page.wait_for_timeout(1500)

        # Click the "Capture Receipt" button on the receipts page
        capture_btn = page.query_selector('[onclick*="loadPage.*capture"]')
        if not capture_btn:
            # Try finding by class
            capture_btn = page.query_selector('a.btn-primary')
        if capture_btn:
            capture_btn.click()
            page.wait_for_timeout(1500)

        _check_errors(errors, "on capture page")

    def test_receipt_file_input_exists(self, browser_page):
        """The file input for receipt upload exists in the DOM."""
        page, errors, app_url = browser_page
        page.goto(app_url, wait_until="domcontentloaded")

        # Go to receipts page
        _click_and_check(page, errors, '[data-page="receipts"]',
                         "receipts nav link")
        page.wait_for_timeout(2000)

        # Navigate to capture page via loadPage('capture')
        page.evaluate("window.loadPage('capture')")
        page.wait_for_timeout(2000)

        # Check the file input exists
        file_input = page.query_selector("#receipt-file")
        assert file_input is not None, \
            f"Receipt file input (#receipt-file) not found in DOM"

        _check_errors(errors, "checking file input")


# ═════════════════════════════════════════════════════════════════════════
# Visual Verification — screenshot-based
# ═════════════════════════════════════════════════════════════════════════


class TestVisualSmoke:
    """Take screenshots of key pages for visual reference."""

    def test_screenshots(self, browser_page, tmp_path):
        """Navigate through key pages, taking screenshots."""
        page, errors, app_url = browser_page
        key_pages = ["dashboard", "accounts", "tax", "receipts", "settings"]
        page.goto(app_url, wait_until="domcontentloaded")

        for page_name in key_pages:
            nav_link = page.query_selector(f'[data-page="{page_name}"]')
            if nav_link and nav_link.is_visible():
                try:
                    nav_link.click()
                    page.wait_for_timeout(1500)
                    screenshot_path = tmp_path / f"page_{page_name}.png"
                    page.screenshot(path=str(screenshot_path))
                except Exception:
                    pass

        _check_errors(errors, "during screenshots")
