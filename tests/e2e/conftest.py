"""Shared fixtures for E2E tests — server lifecycle, browser, config.

Requires: pytest-playwright, playwright chromium browser installed.
Mark tests with @pytest.mark.e2e to use these fixtures.
"""
import os
import subprocess
import time
import urllib.request
import urllib.error
from pathlib import Path

import pytest


# ── Server lifecycle ─────────────────────────────────────────────────────


@pytest.fixture(scope="session")
def api_port() -> int:
    """Pick a port for the test server."""
    import socket
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    s.bind(("", 0))
    port = s.getsockname()[1]
    s.close()
    return port


@pytest.fixture(scope="session")
def api_server(api_port):
    """Start the uvicorn server for E2E tests and wait until it's ready.

    Uses the real API (no mocking) for full end-to-end testing.
    Sets API_CONFIG to the project's config.toml.
    """
    project_root = Path(__file__).resolve().parent.parent.parent
    config_path = project_root / "config.toml"
    env = os.environ.copy()
    env["API_CONFIG"] = str(config_path)
    # Auth is fail-closed; E2E runs against the local demo in open mode.
    env["SOLOLEDGER_OPEN_MODE"] = "true"
    # Isolate the app DB (sessions/users/tenants) from the repo.
    import tempfile
    env["SOLOLEDGER_DATA_DIR"] = tempfile.mkdtemp(prefix="sololedger-e2e-")

    import tempfile
    log_path = project_root / "tests" / "e2e" / "server.log"
    log_path.parent.mkdir(parents=True, exist_ok=True)

    with open(str(log_path), "w") as log:
        proc = subprocess.Popen(
            [
                str(project_root / ".venv" / "bin" / "uvicorn"),
                "app.api:app",
                "--port", str(api_port),
                "--host", "127.0.0.1",
                "--log-level", "warning",
            ],
            cwd=str(project_root),
            env=env,
            stdout=log,
            stderr=subprocess.STDOUT,
        )

    # Wait for server to be ready (up to 30s)
    base_url = f"http://127.0.0.1:{api_port}"
    deadline = time.time() + 30
    last_err = ""
    while time.time() < deadline:
        try:
            resp = urllib.request.urlopen(f"{base_url}/api/v1/health", timeout=2)
            if resp.status == 200:
                break
        except (urllib.error.URLError, ConnectionRefusedError) as e:
            last_err = str(e)
            time.sleep(0.5)
    else:
        # Timed out — read log for diagnostics
        log_text = log_path.read_text() if log_path.exists() else "(no log)"
        proc.terminate()
        pytest.fail(
            f"Server failed to start in 30s on port {api_port}.\n"
            f"Last error: {last_err}\n"
            f"Server log (last 2KB): {log_text[-2000:]}"
        )

    yield base_url

    # Cleanup
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()


# ── Browser ──────────────────────────────────────────────────────────────


@pytest.fixture
def browser_page(api_server):
    """Create a Playwright page with console error tracking, pre-navigated to app.

    Yields (page, errors) where errors is a list that accumulates
    console error messages during the test.
    """
    from playwright.sync_api import sync_playwright

    errors = []
    app_base = f"{api_server}/app/index-classic.html"

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        page = browser.new_page()
        # Track JS pageerror events (actual crashes, not network errors)
        page.on("pageerror", lambda err: errors.append(f"PAGE_ERROR: {err}"))

        yield page, errors, app_base

        browser.close()


# ── Test helpers ─────────────────────────────────────────────────────────


@pytest.fixture
def app_url(api_server):
    """Return the base URL for the classic web UI."""
    return f"{api_server}/app/index-classic.html"
