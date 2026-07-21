"""Bank/Plaid routes."""
import os
from decimal import Decimal
from typing import Optional

from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel

from .deps import _current_tenant, _err, _load_tenants, _ok, _save_tenants, check_auth, get_config, require_plan

router = APIRouter(prefix="/api/v1")


class BankSyncRequest(BaseModel):
    days: int = 90
    preview: bool = False


class PlaidLinkTokenResponse(BaseModel):
    link_token: str


class ExchangeTokenRequest(BaseModel):
    public_token: str
    accounts: list[str] = []


@router.post("/bank/sync", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_sync(req: BankSyncRequest):
    try:
        cfg = get_config()
    except Exception as e:
        return _err(f"Config error: {e}", 500)

    try:
        from ..bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    feed = PlaidFeed(cfg)
    if not feed.enabled:
        return _err("Plaid not configured (set PLAID_* env vars)", 400)

    accounts = feed.fetch_accounts()
    txns = feed.fetch_transactions(days_back=req.days)

    if req.preview:
        return _ok({
            "preview": True,
            "accounts": [
                {"name": a["name"], "balance": a["current"], "type": a["type"]}
                for a in accounts
            ],
            "transactions_found": len(txns),
            "transactions": [
                {
                    "date": t.date,
                    "description": t.description,
                    "amount": float(t.amount),
                    "pending": t.pending,
                }
                for t in txns[:50]
            ],
        })

    results = feed.import_transactions(txns)
    income_count = sum(1 for r in results if r["type"] == "income")
    expense_count = sum(1 for r in results if r["type"] == "expense")
    total = sum(r["amount"] for r in results)

    return _ok({
        "imported": len(results),
        "income_count": income_count,
        "expense_count": expense_count,
        "net_total": float(total),
        "accounts": [
            {"name": a["name"], "balance": a["current"], "type": a["type"]}
            for a in accounts
        ],
    })


@router.get("/bank/accounts", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_accounts():
    try:
        from ..bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    tenant = _current_tenant.get()
    access_token = (tenant or {}).get("plaid_access_token", "") or os.environ.get("PLAID_ACCESS_TOKEN", "")
    if not access_token:
        return _err("No bank connected. Use the 'Connect Bank' button in the Import page.", 400)

    feed = PlaidFeed(access_token=access_token)
    accounts = feed.fetch_accounts()

    return _ok({
        "accounts": [
            {"name": a["name"], "balance": a["current"], "available": a["available"], "type": a["type"]}
            for a in accounts
        ]
    })


@router.get("/bank/link-token", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_link_token():
    try:
        from ..bank_feed import PlaidFeed
    except ImportError:
        return _err("plaid-python not installed", 500)

    result = PlaidFeed.generate_link_token()
    if "error" in result:
        return _err(result["error"], 500)
    return _ok(result)


@router.post("/bank/exchange-token", dependencies=[Depends(check_auth), Depends(require_plan("professional"))])
async def bank_exchange_token(req: ExchangeTokenRequest):
    tenant = _current_tenant.get()
    if not tenant:
        return _err("Not authenticated", 401)

    try:
        import plaid
        from plaid.api import plaid_api
        from plaid.model.item_public_token_exchange_request import ItemPublicTokenExchangeRequest

        client_id = os.environ.get("PLAID_CLIENT_ID", "")
        secret = os.environ.get("PLAID_SECRET", "")
        plaid_env = os.environ.get("PLAID_ENV", "sandbox")

        if not client_id or not secret:
            return _err("PLAID_CLIENT_ID and PLAID_SECRET must be set", 500)

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

        exchange_request = ItemPublicTokenExchangeRequest(public_token=req.public_token)
        exchange_response = client.item_public_token_exchange(exchange_request)
        access_token = exchange_response.access_token

        tenants = _load_tenants()
        email = tenant["email"]
        if email in tenants:
            tenants[email]["plaid_access_token"] = access_token
            _save_tenants(tenants)

        return _ok({"connected": True, "item_id": exchange_response.item_id})
    except Exception as e:
        return _err(f"Failed to exchange token: {e}", 500)


@router.get("/bank/status", dependencies=[Depends(check_auth)])
async def bank_status():
    tenant = _current_tenant.get()
    access_token = (tenant or {}).get("plaid_access_token", "")
    has_main_token = bool(os.environ.get("PLAID_ACCESS_TOKEN", ""))

    if access_token:
        try:
            from ..bank_feed import PlaidFeed
            feed = PlaidFeed(access_token=access_token)
            accounts = feed.fetch_accounts()
            return _ok({
                "connected": True,
                "account_count": len(accounts),
                "accounts": [
                    {"name": a["name"], "mask": a.get("mask", ""), "type": a["type"], "balance": a["current"]}
                    for a in accounts[:5]
                ],
            })
        except Exception:
            return _ok({"connected": True, "account_count": 0, "accounts": []})

    if has_main_token:
        return _ok({"connected": True, "account_count": -1, "accounts": [], "note": "Using global PLAID_ACCESS_TOKEN"})

    return _ok({"connected": False, "account_count": 0, "accounts": []})
