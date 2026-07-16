"""Automated bank feed via Plaid API — fetch, categorize, import.

This module connects to Plaid to download transactions from your
connected bank accounts and imports them into your Beancount ledger.

Requires:
  - PLAID_CLIENT_ID env var
  - PLAID_SECRET env var (or PLAID_SECRET_SANDBOX for testing)
  - PLAID_ENV env var ('sandbox', 'development', or 'production')
  - PLAID_ACCESS_TOKEN env var (from Plaid Link flow)

Usage:
    from app.bank_feed import PlaidFeed
    feed = PlaidFeed()
    txns = feed.fetch_transactions(days_back=30)
    feed.import_transactions(txns, preview=True)
"""

import csv
import datetime
import os
import sys
import tempfile
from dataclasses import dataclass, field
from decimal import Decimal
from pathlib import Path
from typing import Optional

import plaid
from plaid.api import plaid_api
from plaid.model.transactions_sync_request import TransactionsSyncRequest
from plaid.model.accounts_balance_get_request import AccountsBalanceGetRequest

from .config import Config
from .expenses import ExpenseImporter
from .ledger import Ledger


@dataclass
class PlaidTransaction:
    """Normalized transaction from Plaid API."""
    transaction_id: str
    date: str
    description: str
    amount: Decimal  # Positive = money out (expense), Negative = money in (income)
    category: list[str] = field(default_factory=list)
    merchant_name: str = ""
    pending: bool = False
    account_name: str = ""
    account_id: str = ""


class PlaidFeed:
    """Fetch bank transactions from Plaid and import into Beancount."""

    def __init__(self, cfg: Optional[Config] = None):
        self.cfg = cfg
        self._client = None
        self._access_token = os.environ.get("PLAID_ACCESS_TOKEN", "")
        self._enabled = bool(self._access_token)

    @property
    def enabled(self) -> bool:
        return self._enabled

    def _get_client(self):
        """Lazy-init the Plaid API client."""
        if self._client is not None:
            return self._client

        plaid_env = os.environ.get("PLAID_ENV", "sandbox")
        client_id = os.environ.get("PLAID_CLIENT_ID", "")
        secret = os.environ.get("PLAID_SECRET", "")

        if not client_id or not secret:
            print("⚠  PLAID_CLIENT_ID and PLAID_SECRET must be set", file=sys.stderr)
            self._enabled = False
            return None

        # Map env string to Plaid host
        host_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        host = host_map.get(plaid_env, plaid.Environment.Sandbox)

        configuration = plaid.Configuration(
            host=host,
            api_key={
                "clientId": client_id,
                "secret": secret,
                "plaidVersion": "2020-09-14",
            },
        )
        api_client = plaid.ApiClient(configuration)
        self._client = plaid_api.PlaidApi(api_client)
        return self._client

    def fetch_transactions(
        self,
        days_back: int = 90,
        account_filter: Optional[str] = None,
    ) -> list[PlaidTransaction]:
        """Fetch recent transactions from Plaid.

        Uses the sync endpoint for efficient incremental fetching.

        Args:
            days_back: How many days of history to fetch (for initial sync)
            account_filter: Optional account ID to filter by

        Returns:
            List of PlaidTransaction objects
        """
        client = self._get_client()
        if client is None:
            return []

        # Use the sync endpoint — cursor-based, returns only new/changed
        cursor = self._load_cursor()
        added = []
        modified = []
        removed = []
        has_more = True

        try:
            while has_more:
                request = TransactionsSyncRequest(
                    access_token=self._access_token,
                    cursor=cursor,
                    count=500,
                )
                response = client.transactions_sync(request)
                added.extend(response.added)
                modified.extend(response.modified)
                removed.extend(response.removed)
                has_more = response.has_more
                cursor = response.next_cursor

            # Save cursor for next sync
            self._save_cursor(cursor)

        except plaid.ApiException as e:
            print(f"⚠  Plaid API error: {e}", file=sys.stderr)
            return []

        # Build account name map
        acct_map = self._get_account_names()

        # Normalize
        txns = []
        for txn in added + modified:
            # Skip pending transactions by default (they'll arrive as posted)
            if txn.pending:
                continue

            amt = Decimal(str(txn.amount))
            desc = txn.merchant_name or txn.name or "Unknown"

            txns.append(PlaidTransaction(
                transaction_id=txn.transaction_id,
                date=str(txn.date) if hasattr(txn, 'date') else txn.datetime[:10] if hasattr(txn, 'datetime') and txn.datetime else "",
                description=desc,
                amount=amt,
                category=txn.category or [],
                merchant_name=txn.merchant_name or "",
                pending=txn.pending or False,
                account_name=acct_map.get(txn.account_id, "Unknown"),
                account_id=txn.account_id,
            ))

        return txns

    def fetch_accounts(self) -> list[dict]:
        """Get list of connected accounts and their balances."""
        client = self._get_client()
        if client is None:
            return []

        try:
            request = AccountsBalanceGetRequest(access_token=self._access_token)
            response = client.accounts_balance_get(request)
            accounts = []
            for acct in response.accounts:
                balance = acct.balances
                accounts.append({
                    "id": acct.account_id,
                    "name": acct.name,
                    "type": acct.type,
                    "subtype": acct.subtype,
                    "current": float(balance.current) if balance.current else 0,
                    "available": float(balance.available) if balance.available else 0,
                })
            return accounts
        except plaid.ApiException as e:
            print(f"⚠  Plaid API error: {e}", file=sys.stderr)
            return []

    def _get_account_names(self) -> dict[str, str]:
        """Build a map of account_id → account name."""
        accounts = self.fetch_accounts()
        return {a["id"]: a["name"] for a in accounts}

    def _load_cursor(self) -> str:
        """Load the last sync cursor from disk for incremental sync."""
        cursor_path = Path(tempfile.gettempdir()) / ".llc-plaid-cursor"
        if cursor_path.exists():
            return cursor_path.read_text().strip()
        return ""

    def _save_cursor(self, cursor: str):
        """Save the sync cursor for next time."""
        cursor_path = Path(tempfile.gettempdir()) / ".llc-plaid-cursor"
        cursor_path.write_text(cursor)

    def import_transactions(
        self,
        txns: list[PlaidTransaction],
        preview: bool = False,
    ) -> list[dict]:
        """Import Plaid transactions into the Beancount ledger.

        Args:
            txns: Transactions from fetch_transactions()
            preview: If True, just show what would be imported

        Returns:
            List of import result dicts (same shape as ExpenseImporter.import_csv)
        """
        if not txns:
            print("No new transactions to import.")
            return []

        if not self.cfg:
            print("⚠  No config provided — can't import. Pass Config() to PlaidFeed.", file=sys.stderr)
            return []

        # Write transactions to a temp CSV for the existing ExpenseImporter pipeline
        # This reuses all the auto-categorization rules and dedup logic
        import_path = self._write_temp_csv(txns)

        importer = ExpenseImporter(self.cfg, Ledger(self.cfg))
        results = importer.import_csv(import_path, preview=preview)

        # Clean up temp file
        import_path.unlink(missing_ok=True)

        return results

    def _write_temp_csv(self, txns: list[PlaidTransaction]) -> Path:
        """Write Plaid transactions to a temporary CSV for the existing importer."""
        csv_path = Path(tempfile.gettempdir()) / f".llc-plaid-import-{datetime.date.today().isoformat()}.csv"

        with open(csv_path, "w", newline="") as f:
            writer = csv.writer(f)
            writer.writerow(["Date", "Description", "Amount"])
            for txn in txns:
                # Plaid: positive = expense outflow, negative = income inflow
                # Our ExpenseImporter expects: positive = inflow, negative = outflow
                # So we negate: if Plaid says +50 (expense), we want -50
                csv_amount = -txn.amount
                writer.writerow([txn.date, txn.description, f"{csv_amount:.2f}"])

        return csv_path

    @staticmethod
    def generate_link_token() -> dict:
        """Generate a Plaid Link token for initial account connection.

        Run this once to get a link_token, then use it in the Plaid Link
        frontend to connect accounts and get an access_token.
        """
        client_id = os.environ.get("PLAID_CLIENT_ID", "")
        secret = os.environ.get("PLAID_SECRET", "")
        plaid_env = os.environ.get("PLAID_ENV", "sandbox")
        user_id = os.environ.get("PLAID_USER_ID", "llc-tools-user")

        if not client_id or not secret:
            return {"error": "PLAID_CLIENT_ID and PLAID_SECRET must be set"}

        host_map = {
            "sandbox": plaid.Environment.Sandbox,
            "development": plaid.Environment.Development,
            "production": plaid.Environment.Production,
        }
        configuration = plaid.Configuration(
            host=host_map.get(plaid_env, plaid.Environment.Sandbox),
            api_key={"clientId": client_id, "secret": secret, "plaidVersion": "2020-09-14"},
        )
        api_client = plaid.ApiClient(configuration)
        client = plaid_api.PlaidApi(api_client)

        try:
            from plaid.model.link_token_create_request import LinkTokenCreateRequest
            from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
            from plaid.model.country_code import CountryCode
            from plaid.model.products import Products

            request = LinkTokenCreateRequest(
                user=LinkTokenCreateRequestUser(client_user_id=user_id),
                client_name="LLC Tools",
                products=[Products("transactions")],
                country_codes=[CountryCode("US")],
                language="en",
            )
            response = client.link_token_create(request)
            return {"link_token": response.link_token, "expiration": response.expiration}
        except plaid.ApiException as e:
            return {"error": str(e)}
