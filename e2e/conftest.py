"""E2E test fixtures — starts uvicorn server + provides Playwright page."""

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest
import requests


def _find_free_port():
    """Find a free TCP port."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(url, timeout=30):
    """Wait for the server health endpoint to respond."""
    start = time.time()
    while time.time() - start < timeout:
        try:
            r = requests.get(f"{url}/api/v1/health", timeout=2)
            if r.status_code == 200:
                return True
        except (requests.ConnectionError, requests.Timeout):
            pass
        time.sleep(0.5)
    return False


@pytest.fixture(scope="session")
def server_base_url():
    """Start uvicorn on a free port and return the base URL.

    Uses the project's config.toml for open-mode access (no auth).
    The server process is killed when the session ends.
    """
    port = _find_free_port()
    base_url = f"http://127.0.0.1:{port}"
    project_root = Path(__file__).resolve().parent.parent

    env = os.environ.copy()
    env["API_PORT"] = str(port)
    # Use the project config (has sample ledger data)
    env["API_CONFIG"] = str(project_root / "config.toml")

    proc = subprocess.Popen(
        [sys.executable, "-m", "uvicorn", "app.api:app",
         "--host", "127.0.0.1", "--port", str(port)],
        cwd=str(project_root),
        env=env,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    ready = _wait_for_server(base_url)
    if not ready:
        proc.kill()
        proc.wait()
        pytest.fail(f"Server failed to start on port {port}")

    # Quick check — dashboard should return success
    try:
        r = requests.get(f"{base_url}/api/v1/dashboard", timeout=5)
        assert r.status_code == 200
    except Exception as e:
        proc.kill()
        proc.wait()
        pytest.fail(f"Server started but dashboard returns error: {e}")

    yield base_url

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


@pytest.fixture
def app_page(page, server_base_url):
    """Navigate to the app and wait for it to load."""
    page.goto(f"{server_base_url}/app/")
    page.wait_for_load_state("networkidle")
    return page


@pytest.fixture
def nav_to(app_page):
    """Return a helper function for clicking sidebar nav links."""
    def _nav(page_name):
        sidebar = app_page.locator('.sidebar')
        link = sidebar.locator(f'[data-page="{page_name}"]')
        if link.count() > 0:
            link.nth(0).click()
        else:
            app_page.locator(f'[data-page="{page_name}"]').nth(0).click()
        app_page.wait_for_timeout(1500)
        app_page.wait_for_selector("h1", timeout=10000)
    return _nav


@pytest.fixture(autouse=True)
def console_errors(page, request):
    """Collect JS errors during this specific test, auto-cleared between tests."""
    errors = []

    def _on_page_error(err):
        errors.append(str(err))

    def _on_console(msg):
        if msg.type == "error":
            errors.append(msg.text)

    page.on("pageerror", _on_page_error)
    page.on("console", _on_console)

    yield errors

    # Clean up listeners
    try:
        page.remove_listener("pageerror", _on_page_error)
        page.remove_listener("console", _on_console)
    except Exception:
        pass
