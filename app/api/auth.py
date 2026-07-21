"""Auth routes — Google OAuth, email/password signup/signin, session management."""
import datetime
import secrets

import requests as http_requests
from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel

from .deps import (
    check_auth,
    _err,
    _ok,
    _sessions,
    GOOGLE_CLIENT_ID,
    _valid_api_keys,
    _load_users,
    _save_users,
    _hash_password,
    _verify_password,
    create_tenant,
)
from .shared import _decimal_to_float

router = APIRouter(prefix="/api/v1")


class GoogleAuthRequest(BaseModel):
    credential: str


@router.post("/auth/google")
async def auth_google(req: GoogleAuthRequest):
    """Verify a Google ID token and create a session."""
    if not GOOGLE_CLIENT_ID:
        return _err("Google sign-in not configured on this server", 501)

    try:
        resp = http_requests.post(
            "https://oauth2.googleapis.com/tokeninfo",
            params={"id_token": req.credential},
            timeout=10,
        )
        if resp.status_code != 200:
            return _err("Token verification failed", 401)

        info = resp.json()
        aud = info.get("aud", "")
        if aud != GOOGLE_CLIENT_ID:
            return _err("Token audience mismatch", 401)

        email = info.get("email", "")
        if not email:
            return _err("Email not provided in token", 401)

        token = secrets.token_urlsafe(32)
        _sessions[token] = {
            "email": email,
            "name": info.get("name", email),
            "picture": info.get("picture", ""),
        }

        return _ok({
            "token": token,
            "user": {
                "email": email,
                "name": info.get("name", email),
                "picture": info.get("picture", ""),
            },
        })
    except http_requests.RequestException as e:
        return _err(f"Failed to verify token: {e}", 502)


@router.get("/auth/me", dependencies=[Depends(check_auth)])
async def auth_me(request: Request):
    """Return current user info if authenticated."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("Not authenticated", 401)

    token = auth_header[7:]

    if token in _sessions:
        return _ok(_sessions[token])

    if _valid_api_keys and token in _valid_api_keys:
        return _ok({"email": "api-key-user", "name": "API Key", "picture": ""})

    return _err("Not authenticated", 401)


@router.get("/auth/google/config")
async def auth_google_config():
    """Return the Google OAuth client ID for the frontend."""
    return _ok({
        "client_id": GOOGLE_CLIENT_ID,
        "enabled": bool(GOOGLE_CLIENT_ID),
    })


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


@router.post("/auth/signup")
async def auth_signup(req: SignupRequest):
    """Create a new account with email and password."""
    email = req.email.strip().lower()
    if not email or "@" not in email:
        return _err("Valid email required", 400)
    if len(req.password) < 6:
        return _err("Password must be at least 6 characters", 400)

    users = _load_users()
    if email in users:
        return _err("An account with this email already exists", 409)

    name = req.name.strip() or email.split("@")[0]

    users[email] = {
        "password": _hash_password(req.password),
        "name": name,
        "created": datetime.datetime.now(datetime.timezone.utc).isoformat(),
    }
    _save_users(users)

    create_tenant(email, name)

    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "email": email,
        "name": name,
        "picture": "",
        "method": "local",
    }

    return _ok({
        "token": token,
        "user": {"email": email, "name": name, "picture": ""},
    })


class SigninRequest(BaseModel):
    email: str
    password: str


@router.post("/auth/signin")
async def auth_signin(req: SigninRequest):
    """Sign in with email and password."""
    email = req.email.strip().lower()
    if not email:
        return _err("Email required", 400)

    users = _load_users()
    user = users.get(email)
    if not user:
        return _err("Invalid email or password", 401)

    if not _verify_password(req.password, user["password"]):
        return _err("Invalid email or password", 401)

    token = secrets.token_urlsafe(32)
    _sessions[token] = {
        "email": email,
        "name": user.get("name", email.split("@")[0]),
        "picture": "",
        "method": "local",
    }

    return _ok({
        "token": token,
        "user": {
            "email": email,
            "name": user.get("name", email.split("@")[0]),
            "picture": "",
        },
    })


@router.post("/auth/logout", dependencies=[Depends(check_auth)])
async def auth_logout(request: Request):
    """Log out — invalidate the current session token."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        if token in _sessions:
            del _sessions[token]
    return _ok({"logged_out": True})
