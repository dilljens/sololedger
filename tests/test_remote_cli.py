"""Tests for the remote CLI mode: `llc --api <url> --token <tok> <command>`.

The CLI becomes a thin client over the API. Tests route the CLI's HTTP
through a TestClient (via an injectable session) so the full token → tenant
resolution path is exercised end-to-end: a session token scopes the CLI to
exactly that tenant's data.
"""
import os
import uuid
from urllib.parse import urlparse

import click
import pytest
import requests
from click.testing import CliRunner
from fastapi.testclient import TestClient

from app import appdb
from app.api import app as api_app
from app import main as cli_main
from app.api import deps


class FakeRequests:
    """Duck-typed stand-in for the `requests` module used by RemoteClient.

    .request() routes to a TestClient; .RequestException is kept so
    RemoteClient's transport-error except clause still resolves.
    """

    RequestException = requests.RequestException

    def __init__(self, client: TestClient):
        self._client = client

    def request(self, method, url, headers=None, params=None, json=None,
                data=None, files=None, timeout=None):
        path = urlparse(url).path or "/"
        return self._client.request(
            method, path,
            headers=headers or {},
            params=params or {},
            json=json,
            data=data,
            files=files,
        )


@pytest.fixture
def remote_cli(isolated_environment, monkeypatch):
    """A CliRunner wired so `--api http://test` routes into the real app."""
    client = TestClient(api_app)
    import app.remote as rem
    monkeypatch.setattr(rem, "requests", FakeRequests(client))
    runner = CliRunner()
    return runner


def _make_tenant(prefix: str, name: str = "Tenant") -> str:
    """Provision a unique user + tenant + session, return the session token.

    The DB is session-scoped, so emails must be unique per call. Tenants are
    professional+active so writes aren't blocked by free-tier caps (these
    tests exercise the remote path, not billing).
    """
    email = f"{prefix}-{uuid.uuid4().hex[:8]}@example.com"
    appdb.create_user(email, password_hash="", name=name, email_verified=True)
    deps.create_tenant(email, name)
    appdb.update_tenant(email, plan="professional", status="active")
    return appdb.create_session(f"tok-{email}", email, name=name)["token"]


def _invoke(remote_cli, token, args):
    return remote_cli.invoke(
        cli_main.cli, ["--api", "http://test", "--token", token, *args])


# ── happy path: read commands against the tenant's own data ──────────────


def test_status_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    result = _invoke(remote_cli, token, ["status"])
    assert result.exit_code == 0, result.output
    assert "SoloLedger Dashboard" in result.output
    assert "Cash:" in result.output


def test_check_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    result = _invoke(remote_cli, token, ["check"])
    assert result.exit_code == 0, result.output
    assert "valid" in result.output.lower()


def test_invoice_create_and_list_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    created = _invoke(remote_cli, token,
                      ["invoice", "create", "-c", "Acme Corp",
                       "-d", "Q3 Consulting", "-a", "5000", "--no-pdf"])
    assert created.exit_code == 0, created.output
    assert "Invoice" in created.output

    listed = _invoke(remote_cli, token, ["invoice", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Acme Corp" in listed.output

    ar = _invoke(remote_cli, token, ["invoice", "ar"])
    assert ar.exit_code == 0, ar.output
    assert "Accounts Receivable" in ar.output


def test_tax_deadlines_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    result = _invoke(remote_cli, token, ["tax", "deadlines"])
    assert result.exit_code == 0, result.output
    assert "deadlines" in result.output.lower()


def test_mileage_add_and_list_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    added = _invoke(remote_cli, token,
                    ["mileage", "add", "-d", "2026-08-01", "-m", "42.5",
                     "-p", "Client visit", "--no-post"])
    assert added.exit_code == 0, added.output
    assert "Trip logged" in added.output

    listed = _invoke(remote_cli, token, ["mileage", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Client visit" in listed.output


def test_report_profit_loss_remote(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    result = _invoke(remote_cli, token, ["report", "profit-loss"])
    assert result.exit_code == 0, result.output
    assert "Profit & Loss" in result.output


# ── isolation: a token only sees its own tenant ──────────────────────────


def test_token_scoped_to_own_tenant(remote_cli):
    """Two tenants, two tokens — each CLI session sees only its own data."""
    tok_a = _make_tenant("alice@example.com", "Alice")
    tok_b = _make_tenant("bob@example.com", "Bob")

    _invoke(remote_cli, tok_a,
            ["invoice", "create", "-c", "Alice Client", "-d", "A", "-a", "100", "--no-pdf"])
    _invoke(remote_cli, tok_b,
            ["invoice", "create", "-c", "Bob Client", "-d", "B", "-a", "200", "--no-pdf"])

    a_list = _invoke(remote_cli, tok_a, ["invoice", "list"])
    assert "Alice Client" in a_list.output
    assert "Bob Client" not in a_list.output

    b_list = _invoke(remote_cli, tok_b, ["invoice", "list"])
    assert "Bob Client" in b_list.output
    assert "Alice Client" not in b_list.output


# ── failure modes ────────────────────────────────────────────────────────


def test_bad_token_clean_error(remote_cli):
    result = _invoke(remote_cli, "not-a-real-token", ["status"])
    assert result.exit_code == 1
    assert "Error:" in result.output
    assert "Traceback" not in result.output


def test_api_requires_token(remote_cli):
    result = remote_cli.invoke(cli_main.cli, ["--api", "http://test", "status"])
    assert result.exit_code == 1
    assert "--api requires --token" in result.output


def test_local_only_command_rejected_in_remote_mode(remote_cli):
    token = _make_tenant("cli@example.com", "CLI User")
    result = _invoke(remote_cli, token, ["backup", "--status"])
    assert result.exit_code == 1
    assert "local-only" in result.output.lower()
    assert "Traceback" not in result.output


# ── per-tenant API keys (long-lived remote-CLI credentials) ──────────────


def _create_api_key(remote_cli, session_token, name="test key"):
    """Run `api-key create` and extract the printed key."""
    result = _invoke(remote_cli, session_token, ["api-key", "create", "--name", name])
    assert result.exit_code == 0, result.output
    for line in result.output.splitlines():
        line = line.strip()
        if line.startswith("solo_"):
            return line
    raise AssertionError(f"no key in output: {result.output}")


def test_api_key_create_and_use(remote_cli):
    session = _make_tenant("keys@example.com", "Key User")
    key = _create_api_key(remote_cli, session)

    # The key works as the CLI token against the tenant's own data.
    result = _invoke(remote_cli, key, ["status"])
    assert result.exit_code == 0, result.output
    assert "SoloLedger Dashboard" in result.output


def test_api_key_list_never_shows_secret(remote_cli):
    session = _make_tenant("keys@example.com", "Key User")
    key = _create_api_key(remote_cli, session, name="laptop")

    listed = _invoke(remote_cli, session, ["api-key", "list"])
    assert listed.exit_code == 0, listed.output
    assert "laptop" in listed.output
    assert key not in listed.output  # prefix only, never the secret
    assert key[:12] in listed.output  # ...but the prefix is shown


def test_api_key_outlives_session(remote_cli):
    """A key keeps working after its creating session is deleted (long-lived);
    the deleted session token itself stops working."""
    session = _make_tenant("keys@example.com", "Key User")  # the session token
    key = _create_api_key(remote_cli, session)

    appdb.delete_session(session)

    with_key = _invoke(remote_cli, key, ["status"])
    assert with_key.exit_code == 0, with_key.output

    with_session = _invoke(remote_cli, session, ["status"])
    assert with_session.exit_code == 1
    assert "Error:" in with_session.output


def test_api_key_revoke(remote_cli):
    session = _make_tenant("keys@example.com", "Key User")
    key = _create_api_key(remote_cli, session)
    assert _invoke(remote_cli, key, ["status"]).exit_code == 0

    # Find the key id from the list, then revoke it.
    listed = _invoke(remote_cli, session, ["api-key", "list"])
    key_id = None
    for line in listed.output.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            key_id = int(parts[0])
            break
    assert key_id is not None, listed.output
    revoked = _invoke(remote_cli, session, ["api-key", "revoke", str(key_id)])
    assert revoked.exit_code == 0, revoked.output

    after = _invoke(remote_cli, key, ["status"])
    assert after.exit_code == 1
    assert "Error:" in after.output


def test_api_key_scoped_to_own_tenant(remote_cli):
    """A key for tenant A can't reach tenant B's data."""
    tok_a = _make_tenant("alice@example.com", "Alice")
    _make_tenant("bob@example.com", "Bob")
    _invoke(remote_cli, tok_a,
            ["invoice", "create", "-c", "Alice Client", "-d", "A", "-a", "100", "--no-pdf"])
    alice_key = _create_api_key(remote_cli, tok_a)

    listed = _invoke(remote_cli, alice_key, ["invoice", "list"])
    assert listed.exit_code == 0, listed.output
    assert "Alice Client" in listed.output
