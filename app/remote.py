"""Remote CLI transport — `llc --api <url> --token <token> <command>`.

Makes the CLI a thin client over the SoloLedger HTTP API instead of reading
local files. The API resolves every request token → email → tenant → that
tenant's own ledger_dir, so a session token scopes the CLI to exactly the
tenant that owns it. Tenants get CLI access to their own web-app data, and
the operator never handles tenant data (and tenants can't reach each other).

Only a subset of CLI commands has a remote counterpart; every other command
raises a clean "local-only" error from main.py via the sentinel config.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Optional

import click
import requests

from .disclaimer import CLI_DISCLAIMER


class RemoteError(click.ClickException):
    """An error reported by the API (non-2xx) or a transport failure.

    Subclasses ClickException so any remote failure renders as a clean
    "Error: <msg>" line with exit code 1 — no traceback for tenants.
    """


class RemoteClient:
    """Small HTTP client for the SoloLedger API ({success, data} envelope).

    `session` is injectable (duck-typed `requests.Session` with a `request`
    method) so tests can route through a TestClient without a live server.
    """

    def __init__(self, base_url: str, token: str = "", timeout: float = 30.0,
                 session: Any = None):
        self.base_url = base_url.rstrip("/")
        self.token = token
        self.timeout = timeout
        self._session = session if session is not None else requests

    def _headers(self) -> dict:
        headers = {"Accept": "application/json"}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        return headers

    def _request(self, method: str, path: str, **kw) -> dict:
        url = self.base_url + path
        try:
            resp = self._session.request(
                method, url, headers=self._headers(), timeout=self.timeout, **kw)
        except requests.RequestException as e:
            raise RemoteError(f"Request failed: {e}")
        try:
            body = resp.json()
        except ValueError:
            raise RemoteError(f"Non-JSON response (HTTP {resp.status_code})")
        if resp.status_code >= 400 or not body.get("success", False):
            msg = body.get("error") or body.get("detail") or f"HTTP {resp.status_code}"
            raise RemoteError(msg)
        return body.get("data", {})

    def get(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("GET", path, params=params or {})

    def post(self, path: str, json: Optional[dict] = None, data: Optional[dict] = None,
             files: Optional[dict] = None) -> dict:
        return self._request("POST", path, json=json, data=data, files=files)

    def delete(self, path: str, params: Optional[dict] = None) -> dict:
        return self._request("DELETE", path, params=params or {})


def _pp(obj: Any) -> str:
    return json.dumps(obj, indent=2, default=str)


# ── status / check ────────────────────────────────────────────────────────


def remote_status(r: RemoteClient) -> None:
    d = r.get("/api/v1/dashboard")
    tax = d.get("tax") or {}
    click.echo("═══ SoloLedger Dashboard ═══")
    click.echo(f"  Entity:         {d.get('entity_label', 'SMLLC (Schedule C)')}")
    click.echo(f"  Cash:           ${d.get('cash', 0):,.2f}")
    click.echo(f"  Gross revenue:  ${d.get('gross_revenue', 0):,.2f}")
    click.echo(f"  Total expenses: ${d.get('total_expenses', 0):,.2f}")
    click.echo(f"  Net profit:     ${d.get('net_profit', 0):,.2f}")
    click.echo(f"  Accounts recv.: ${d.get('ar', 0):,.2f}")
    if tax:
        click.echo(f"  Est. annual tax:${tax.get('annual_total_tax', 0):,.2f}")
        click.echo(f"  Already paid:   ${tax.get('already_paid', 0):,.2f}")
        click.echo(f"  Suggested next: ${tax.get('suggested_payment', 0):,.2f}")
        if tax.get("note"):
            click.echo(f"  ({tax['note']})")
    click.echo(f"  Ledger errors:  {d.get('ledger_errors', 0)}")
    click.echo(f"  Recent txns:    {len(d.get('recent_transactions', []))}")


def remote_check(r: RemoteClient) -> None:
    d = r.get("/api/v1/check")
    if d.get("valid"):
        click.echo("✓ Ledger is valid. No errors.")
        return
    click.echo(f"Found {d.get('error_count', 0)} error(s):")
    for e in d.get("errors", []):
        loc = f"{e.get('file', '?')}:{e.get('line', 0)}"
        click.echo(f"  ✗ {loc}: {e.get('message', e)}")


# ── invoices ─────────────────────────────────────────────────────────────


def remote_invoice_create(r: RemoteClient, client: str, description: str,
                          amount: float, date: Optional[str], generate_pdf: bool,
                          payment_link: bool, client_email: Optional[str],
                          recurring: Optional[str]) -> None:
    payload = {
        "client": client,
        "description": description,
        "amount": amount,
        "generate_pdf": generate_pdf,
        "payment_link": payment_link,
    }
    if date:
        payload["date"] = date
    if client_email:
        payload["client_email"] = client_email
    if recurring:
        payload["recurring"] = recurring
    d = r.post("/api/v1/invoices", json=payload)
    click.echo(f"✓ Invoice {d.get('number', '')} created")
    click.echo(f"  Client:  {client}")
    click.echo(f"  Amount:  ${amount:,.2f}")
    click.echo(f"  Date:    {d.get('date', '')}")
    if d.get("payment_url"):
        click.echo(f"  💳 Pay online: {d['payment_url']}")
    elif payment_link:
        click.echo("  ⚠  Stripe not configured on the server for payment links.")


def remote_invoice_list(r: RemoteClient, year: Optional[int], ar_only: bool) -> None:
    params = {}
    if year:
        params["year"] = year
    if ar_only:
        params["ar_only"] = "true"
    d = r.get("/api/v1/invoices", params)
    invoices = d.get("invoices", [])
    if not invoices:
        click.echo("No invoices found.")
        return
    if ar_only:
        click.echo("═══ Unpaid Invoices (Accounts Receivable) ═══")
    click.echo(f"{'Date':<12} {'Client':<25} {'Amount':>10}  Description")
    click.echo("-" * 72)
    for inv in invoices:
        paid = " [PAID]" if inv.get("paid") else ""
        click.echo(f"{str(inv['date']):<12} {inv['client']:<25} "
                   f"${inv['amount']:>7,.2f}  {inv['description'][:30]}{paid}")
    click.echo(f"\nTotal: {d.get('total', len(invoices))} invoices")


def remote_invoice_ar(r: RemoteClient) -> None:
    d = r.get("/api/v1/invoices/ar")
    click.echo("═══ Accounts Receivable ═══")
    click.echo()
    click.echo(f"  Total outstanding:  ${d.get('total_ar', 0):>10,.2f}")
    click.echo(f"  Open invoices:       {d.get('invoice_count', 0)}")
    if d.get("overdue_count", 0) > 0:
        click.echo(f"  🔴 Overdue:           {d['overdue_count']} invoices")
        click.echo(f"  🔴 Overdue amount:   ${d.get('estimated_overdue_amount', 0):>10,.2f}")
    else:
        click.echo("  🟢 Overdue:          0 invoices")


# ── taxes ────────────────────────────────────────────────────────────────


def remote_tax_estimate(r: RemoteClient, projected_income: Optional[float],
                        state_override: Optional[str]) -> None:
    params = {"projected_income": projected_income} if projected_income else {}
    if state_override:
        click.echo("note: --state is ignored in remote mode — the estimate uses "
                   "your account's configured state.")
    d = r.get("/api/v1/tax/estimate", params)
    if "note" in d and not any(k in d for k in ("annual_total_tax", "total_tax")):
        click.echo(d["note"])
        return
    click.echo(_pp(d))
    click.echo(CLI_DISCLAIMER)


def remote_tax_deadlines(r: RemoteClient) -> None:
    d = r.get("/api/v1/tax/deadlines")
    click.echo(f"Tax deadlines (as of {d.get('as_of', '')}):")
    for dl in d.get("deadlines", []):
        icon = {"overdue": "🔴 OVERDUE", "upcoming": "🟡 UPCOMING", "ahead": "🟢"}.get(
            dl.get("status", ""), "🟢")
        click.echo(f"  {icon}  {dl.get('label', '')}: {dl.get('due', '')}  "
                   f"({dl.get('days_until', 0):>+4d} days)")


def remote_tax_schedule_c(r: RemoteClient) -> None:
    click.echo(_pp(r.get("/api/v1/tax/schedule-c")))


def remote_tax_form_1120s(r: RemoteClient, as_json: bool,
                          projected_income: Optional[float]) -> None:
    params = {"projected_income": projected_income} if projected_income else {}
    d = r.get("/api/v1/tax/form-1120s", params)
    click.echo(_pp(d))


# ── mileage ──────────────────────────────────────────────────────────────


def remote_mileage_list(r: RemoteClient, year: Optional[int], limit: int) -> None:
    params = {"limit": limit}
    if year:
        params["year"] = year
    d = r.get("/api/v1/mileage/trips", params)
    trips = d.get("trips", [])
    if not trips:
        click.echo("No trips logged.")
        return
    click.echo(f"{'Date':12s} {'Miles':8s} {'Deduction':10s}  Purpose")
    click.echo("-" * 60)
    for t in trips:
        click.echo(f"{str(t.get('date', '')):12s} {t.get('miles', 0):<8.1f} "
                   f"${t.get('deduction', 0):<8.2f}  {str(t.get('purpose', ''))[:35]}")
    click.echo(f"\nTotal: {d.get('total', len(trips))} trips")


def remote_mileage_add(r: RemoteClient, date: str, miles: float, purpose: str,
                       client: str, start_odo: float, end_odo: float,
                       route: str, notes: str, post_to_ledger: bool) -> None:
    d = r.post("/api/v1/mileage/add", json={
        "date": date, "miles": miles, "purpose": purpose,
        "client": client, "start_odo": start_odo, "end_odo": end_odo,
        "route": route, "notes": notes, "post_to_ledger": post_to_ledger,
    })
    click.echo(f"Trip logged: {d.get('date', '')} — {purpose} ({miles} mi)")
    click.echo(f"  Deduction: ${d.get('deduction', 0):.2f}")
    click.echo(f"  Receipt:   {d.get('id', '')}")
    if post_to_ledger:
        click.echo("  Posted to Beancount ledger.")


def remote_mileage_report(r: RemoteClient, year: Optional[int]) -> None:
    params = {"year": year} if year else {}
    report = r.get("/api/v1/mileage/report", params)
    click.echo(f"Mileage Report — {report.get('year', year)}")
    click.echo(f"  Total trips:       {report.get('trip_count', 0)}")
    click.echo(f"  Total miles:       {report.get('total_miles', 0):.1f}")
    click.echo(f"  Total deduction:   ${report.get('total_deduction', 0):.2f}")
    for month, miles in sorted((report.get("monthly_breakdown") or {}).items()):
        click.echo(f"    {month}: {miles:.1f} mi")
    for purpose, miles in sorted((report.get("trips_by_purpose") or {}).items(),
                                 key=lambda x: -x[1]):
        click.echo(f"    {purpose[:40]:40s} {miles:.1f} mi")


# ── retainers ────────────────────────────────────────────────────────────


def remote_retainer_list(r: RemoteClient) -> None:
    click.echo(_pp(r.get("/api/v1/retainers")))


def remote_retainer_add(r: RemoteClient, client: str, description: str,
                        amount: float, interval: str, day: int,
                        stripe: bool) -> None:
    d = r.post("/api/v1/retainers", json={
        "client": client, "description": description, "amount": amount,
        "interval": interval, "day_of_month": day, "stripe_recurring": stripe,
    })
    click.echo(f"✓ Retainer configured for {client}")
    click.echo(f"  Amount:       ${amount:,.2f}")
    click.echo(f"  Interval:     {interval}")
    click.echo(f"  Next invoice: {d.get('next_invoice', '')}")
    if stripe:
        click.echo("  💳 Stripe recurring payment enabled")


def remote_retainer_process(r: RemoteClient, no_preview: bool) -> None:
    d = r.post("/api/v1/retainers/process", params={"preview": str(not no_preview).lower()})
    click.echo(_pp(d))


# ── reports ──────────────────────────────────────────────────────────────


def remote_report_expenses(r: RemoteClient, year: Optional[int]) -> None:
    params = {"year": year} if year else {}
    d = r.get("/api/v1/reports/expenses", params)
    year_label = d.get("year", "all")
    total = d.get("total", 0)
    click.echo(f"═══ Expenses ({year_label}) ═══")
    click.echo()
    for s in d.get("categories", []):
        short = s.get("category", "").replace("Expenses:", "")
        click.echo(f"  {short:<40s}  ${s.get('amount', 0):>8,.2f}  ({s.get('count', 0)} txns)")
    click.echo(f"  {'─' * 40}")
    click.echo(f"  {'Total':<40s}  ${total:>8,.2f}")


def remote_report_pl(r: RemoteClient, year: Optional[int]) -> None:
    params = {"year": year} if year else {}
    pl = r.get("/api/v1/reports/profit-loss", params)
    click.echo(f"═══ Profit & Loss ({pl.get('year', year or '?')}) ═══")
    click.echo()
    click.echo(f"  Income:             ${pl.get('income', 0):>10,.2f}")
    click.echo(f"  Total Expenses:     ${pl.get('expenses', 0):>10,.2f}")
    for e in pl.get("expense_breakdown", []):
        short = e.get("category", "").replace("Expenses:", "")
        click.echo(f"    {short:<35s}  ${e.get('amount', 0):>8,.2f}")
    click.echo(f"  {'─' * 45}")
    click.echo(f"  Net Profit:         ${pl.get('net_profit', 0):>10,.2f}")


# ── file uploads (import) ────────────────────────────────────────────────


def remote_expense_import(r: RemoteClient, csv_file: str, preview: bool) -> None:
    with open(csv_file, "rb") as fh:
        d = r.post("/api/v1/expenses/import",
                   data={"preview": str(preview).lower()},
                   files={"file": (Path(csv_file).name, fh)})
    click.echo(_pp(d))


def remote_import_ofx(r: RemoteClient, filepath: str, account: Optional[str],
                      preview: bool) -> None:
    data = {"preview": str(preview).lower()}
    if account:
        data["account"] = account
    with open(filepath, "rb") as fh:
        d = r.post("/api/v1/import/ofx",
                   data=data,
                   files={"file": (Path(filepath).name, fh)})
    click.echo(_pp(d))


# ── per-tenant API keys ──────────────────────────────────────────────────


def remote_api_key_create(r: RemoteClient, name: str,
                          expires_in_days: Optional[int]) -> None:
    payload = {"name": name}
    if expires_in_days:
        payload["expires_in_days"] = expires_in_days
    d = r.post("/api/v1/api-keys", json=payload)
    click.echo("✓ API key created — copy it now, it is shown only once:")
    click.echo()
    click.echo(f"  {d.get('key', '')}")
    click.echo()
    click.echo("  Use it as the CLI token (env also works: SOLOLEDGER_API_TOKEN):")
    click.echo(f"    llc --api {r.base_url} --token {d.get('key', '')} status")
    if d.get("expires_at"):
        click.echo(f"  Expires: {d['expires_at']}")


def remote_api_key_list(r: RemoteClient) -> None:
    d = r.get("/api/v1/api-keys")
    keys = d.get("keys", [])
    if not keys:
        click.echo("No API keys. Create one with 'llc api-key create'.")
        return
    click.echo(f"{'ID':<5} {'Prefix':<14} {'Name':<24} {'Created':<12} {'Last used':<12} Status")
    click.echo("-" * 80)
    for k in keys:
        status = "active" if k.get("active") else "revoked"
        click.echo(f"{k.get('id', ''):<5} {k.get('prefix', ''):<14} "
                   f"{str(k.get('name', ''))[:24]:<24} "
                   f"{str(k.get('created', ''))[:10]:<12} "
                   f"{str(k.get('last_used') or '')[:10]:<12} {status}")


def remote_api_key_revoke(r: RemoteClient, key_id: int) -> None:
    d = r.delete(f"/api/v1/api-keys/{key_id}")
    if d.get("revoked"):
        click.echo(f"✓ API key {key_id} revoked — it no longer works.")
    else:
        click.echo(f"API key {key_id} not found.")
