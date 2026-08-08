"""Per-tenant API keys — long-lived credentials for the remote CLI.

A tenant creates a key in the web app (Settings → API Keys) or via
`llc api-key create`, then uses it as the CLI token:

    llc --api https://sololedger.ferrumeng.com --token <key> status

Keys are scoped to exactly one tenant (email) and revocable. Only a SHA-256
hash is stored at rest; the plaintext key is returned once at creation and
never again.
"""
from typing import Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from .. import appdb
from .deps import _current_email, _err, _ok, check_auth

router = APIRouter(prefix="/api/v1")


class CreateApiKeyRequest(BaseModel):
    name: str = ""
    expires_in_days: Optional[int] = None


def _user_email() -> str | None:
    """The authenticated user's email (None for global API keys / open mode)."""
    email = _current_email.get()
    if not email or email == "api-key-user":
        return None
    return email


@router.post("/api-keys", dependencies=[Depends(check_auth)])
async def create_api_key(req: CreateApiKeyRequest):
    """Create a long-lived API key for the current user. Shown once."""
    email = _user_email()
    if not email:
        return _err("API keys require a user account (not a global API key)", 401)
    data = appdb.create_api_key(email, name=(req.name or "").strip()[:64],
                                expires_in_days=req.expires_in_days or 0)
    return _ok({
        "id": data["id"],
        "key": data["key"],  # plaintext — shown exactly once
        "name": data["name"],
        "created": data["created"],
        "expires_at": data["expires_at"],
    })


@router.get("/api-keys", dependencies=[Depends(check_auth)])
async def list_api_keys():
    """List the current user's keys (prefix only — never the secret)."""
    email = _user_email()
    if not email:
        return _err("API keys require a user account (not a global API key)", 401)
    keys = appdb.list_api_keys(email)
    return _ok({"keys": keys, "count": len(keys)})


@router.delete("/api-keys/{key_id}", dependencies=[Depends(check_auth)])
async def revoke_api_key(key_id: int):
    """Revoke a key — it stops working immediately."""
    email = _user_email()
    if not email:
        return _err("API keys require a user account (not a global API key)", 401)
    if appdb.revoke_api_key(key_id, email):
        return _ok({"revoked": True, "id": key_id})
    return _err("API key not found", 404)
