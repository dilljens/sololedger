"""Auth routes — Google OAuth, email/password signup/signin, email
verification, password reset, session management (DB-backed).

Flows:
  signup      → creates an unverified user + verification email
  verify-email → marks the email verified and provisions the workspace
  signin      → creates a session (blocked until the email is verified)
  forgot-password / reset-password → password recovery
  google      → verified Google identity, creates user + tenant directly
"""
import datetime
import os
import secrets

import requests as http_requests
from fastapi import APIRouter, Depends, Query, Request
from pydantic import BaseModel

from .. import appdb
from .deps import (
    check_auth,
    _err,
    _ok,
    GOOGLE_CLIENT_ID,
    _valid_api_keys,
    _hash_password,
    _verify_password,
    _session_valid,
    _rate_limited,
    _client_ip,
    create_tenant,
)

router = APIRouter(prefix="/api/v1")

# Email verification is required when the operator configures a mail
# transport (Resend) or explicitly opts in. Without either (local dev /
# tests) accounts are verified automatically so flows stay usable. Read
# lazily so it can be toggled at runtime / in tests.
def _email_verify_required() -> bool:
    return (
        os.environ.get("SOLOLEDGER_REQUIRE_EMAIL_VERIFY", "").lower() in ("1", "true", "yes")
        or bool(os.environ.get("RESEND_API_KEY"))
    )


class GoogleAuthRequest(BaseModel):
    credential: str


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str = ""


class SigninRequest(BaseModel):
    email: str
    password: str


class VerifyEmailRequest(BaseModel):
    token: str


class ForgotPasswordRequest(BaseModel):
    email: str


class ResetPasswordRequest(BaseModel):
    token: str
    password: str


class ResendVerificationRequest(BaseModel):
    email: str


# ── Email transport (Resend) ──────────────────────────────────────────────


def _send_email(to: str, subject: str, body: str) -> bool:
    """Send a transactional email via Resend. Returns False if not configured."""
    api_key = os.environ.get("RESEND_API_KEY", "")
    if not api_key:
        return False
    try:
        import resend
        resend.api_key = api_key
        resend.Emails.send({
            "from": os.environ.get("RESEND_FROM", "SoloLedger <welcome@sololedger.ferrumeng.com>"),
            "to": [to],
            "subject": subject,
            "text": body,
        })
        return True
    except Exception as e:
        import sys
        print(f"⚠ Email send failed: {e}", file=sys.stderr)
        return False


def _new_token() -> str:
    return secrets.token_urlsafe(32)


def _session_for(email: str, name: str, picture: str = "", method: str = "local") -> str:
    """Create a DB session and return its token."""
    token = _new_token()
    appdb.create_session(token, email, name=name, picture=picture, method=method)
    return token


# ── Google OAuth ──────────────────────────────────────────────────────────


@router.post("/auth/google")
async def auth_google(req: GoogleAuthRequest, request: Request):
    """Verify a Google ID token and create a session."""
    if not GOOGLE_CLIENT_ID:
        return _err("Google sign-in not configured on this server", 501)

    if _rate_limited(f"google:{_client_ip(request)}"):
        return _err("Too many attempts. Try again later.", 429)

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

        if not info.get("email_verified", False):
            return _err("Email not verified", 401)

        email = info.get("email", "")
        if not email:
            return _err("Email not provided in token", 401)

        name = info.get("name", email)
        picture = info.get("picture", "")

        # Google is the identity provider — the email is already verified.
        user = appdb.get_user(email)
        if not user:
            appdb.create_user(email, password_hash="", name=name, email_verified=True)
        else:
            appdb.update_user(email, name=name, email_verified=True)

        # Provision an isolated tenant (idempotent).
        create_tenant(email, name)

        token = _session_for(email, name, picture=picture, method="google")
        return _ok({
            "token": token,
            "user": {"email": email, "name": name, "picture": picture},
        })
    except http_requests.RequestException as e:
        return _err(f"Failed to verify token: {e}", 502)


@router.get("/auth/google/config")
async def auth_google_config():
    """Return the Google OAuth client ID for the frontend."""
    return _ok({
        "client_id": GOOGLE_CLIENT_ID,
        "enabled": bool(GOOGLE_CLIENT_ID),
    })


# ── Signup / verification ─────────────────────────────────────────────────


@router.post("/auth/signup")
async def auth_signup(req: SignupRequest, request: Request):
    """Create a new account. Sends a verification email when required."""
    if _rate_limited(f"signup:{_client_ip(request)}"):
        return _err("Too many accounts from this address. Try again later.", 429)

    email = req.email.strip().lower()
    if not email or "@" not in email or len(email) > 254:
        return _err("Valid email required", 400)
    if len(req.password) < 8:
        return _err("Password must be at least 8 characters", 400)

    name = (req.name.strip() or email.split("@")[0])[:64]
    if any(c in name for c in "\r\n\t"):
        return _err("Name contains invalid characters", 400)

    if appdb.get_user(email):
        return _err("An account with this email already exists", 409)

    verify_required = _email_verify_required()
    verify_token = _new_token() if verify_required else ""
    appdb.create_user(
        email=email,
        password_hash=_hash_password(req.password),
        name=name,
        email_verified=not verify_required,
        verify_token=verify_token,
    )

    if verify_required:
        sent = _send_email(
            email,
            "Verify your SoloLedger email",
            f"Welcome to SoloLedger!\n\nVerify your email to activate your workspace:\n"
            f"{os.environ.get('APP_URL', 'http://localhost:8100')}/#/verify-email?token={verify_token}\n\n"
            f"This link expires in 24 hours.",
        )
        # In dev (no mail transport configured), return the token so the
        # caller can complete the flow; production never echoes it.
        if not sent:
            return _ok({
                "verify_required": True,
                "message": "Verification email sent",
                "verify_token": verify_token,  # dev-only convenience
            })
        return _ok({"verify_required": True, "message": "Verification email sent"})

    # Dev/tests: auto-verified — provision the workspace and log in.
    create_tenant(email, name)
    token = _session_for(email, name)
    return _ok({
        "token": token,
        "user": {"email": email, "name": name, "picture": ""},
    })


@router.get("/auth/verify-email")
async def verify_email(token: str = Query(...)):
    """Verify an email address with the token from the signup email."""
    if not token:
        return _err("Missing verification token", 400)

    user = appdb.get_user_by_verify_token(token)
    if user is None:
        return _err("Invalid or expired verification token", 400)

    expires = user.get("verify_token_expires", "")
    if expires:
        try:
            if datetime.datetime.fromisoformat(expires) < datetime.datetime.now(datetime.timezone.utc):
                return _err("Verification token expired", 400)
        except (ValueError, TypeError):
            pass

    email = user["email"]
    appdb.update_user(email, email_verified=True, verify_token="", verify_token_expires="")
    create_tenant(email, user.get("name", email.split("@")[0]))

    return _ok({"verified": True, "email": email})


@router.post("/auth/resend-verification")
async def resend_verification(req: ResendVerificationRequest, request: Request):
    """Re-send the verification email for an unverified account."""
    if _rate_limited(f"verify:{_client_ip(request)}"):
        return _err("Too many attempts. Try again later.", 429)

    email = req.email.strip().lower()
    user = appdb.get_user(email)
    if not user:
        return _ok({"message": "If that account exists, a verification email was sent"})

    if user.get("email_verified"):
        return _ok({"message": "Email already verified"})

    token = _new_token()
    appdb.update_user(email, verify_token=token)
    _send_email(
        email,
        "Verify your SoloLedger email",
        f"Verify your email to activate your workspace:\n"
        f"{os.environ.get('APP_URL', 'http://localhost:8100')}/#/verify-email?token={token}\n\n"
        f"This link expires in 24 hours.",
    )
    return _ok({"message": "If that account exists, a verification email was sent"})


# ── Sign in / out ─────────────────────────────────────────────────────────


@router.post("/auth/signin")
async def auth_signin(req: SigninRequest, request: Request):
    """Sign in with email and password."""
    if _rate_limited(f"signin:{_client_ip(request)}"):
        return _err("Too many attempts. Try again later.", 429)

    email = req.email.strip().lower()
    if not email:
        return _err("Email required", 400)

    user = appdb.get_user(email)
    if not user or not user.get("password_hash"):
        return _err("Invalid email or password", 401)

    if not _verify_password(req.password, user["password_hash"]):
        return _err("Invalid email or password", 401)

    if not user.get("email_verified"):
        return _err("Email not verified — check your inbox", 403)

    name = user.get("name", email.split("@")[0])
    token = _session_for(email, name)
    return _ok({
        "token": token,
        "user": {"email": email, "name": name, "picture": ""},
    })


@router.get("/auth/me", dependencies=[Depends(check_auth)])
async def auth_me(request: Request):
    """Return current user info if authenticated."""
    auth_header = request.headers.get("authorization", "")
    if not auth_header.startswith("Bearer "):
        return _err("Not authenticated", 401)

    token = auth_header[7:]

    session = appdb.get_session(token)
    if session and _session_valid(token):
        return _ok({
            "email": session.get("email", ""),
            "name": session.get("name", ""),
            "picture": session.get("picture", ""),
            "method": session.get("method", "local"),
        })

    if _valid_api_keys and token in _valid_api_keys:
        return _ok({"email": "api-key-user", "name": "API Key", "picture": ""})

    return _err("Not authenticated", 401)


@router.post("/auth/logout", dependencies=[Depends(check_auth)])
async def auth_logout(request: Request):
    """Log out — invalidate the current session token."""
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header[7:]
        appdb.delete_session(token)
    return _ok({"logged_out": True})


# ── Password reset ────────────────────────────────────────────────────────


@router.post("/auth/forgot-password")
async def forgot_password(req: ForgotPasswordRequest, request: Request):
    """Send a password-reset email (always 200 to avoid enumeration)."""
    if _rate_limited(f"reset:{_client_ip(request)}"):
        return _ok({"message": "If that account exists, a reset email was sent"})

    email = req.email.strip().lower()
    user = appdb.get_user(email)
    if user:
        token = _new_token()
        appdb.update_user(email, reset_token=token)
        _send_email(
            email,
            "Reset your SoloLedger password",
            f"Reset your password here:\n"
            f"{os.environ.get('APP_URL', 'http://localhost:8100')}/#/reset-password?token={token}\n\n"
            f"This link expires in 1 hour.",
        )
    return _ok({"message": "If that account exists, a reset email was sent"})


@router.post("/auth/reset-password")
async def reset_password(req: ResetPasswordRequest):
    """Set a new password using a reset token; invalidates all sessions."""
    if len(req.password) < 8:
        return _err("Password must be at least 8 characters", 400)

    user = appdb.get_user_by_reset_token(req.token)
    if user is None:
        return _err("Invalid or expired reset token", 400)

    appdb.update_user(user["email"], password_hash=_hash_password(req.password),
                      reset_token="", reset_token_expires="")
    appdb.delete_sessions_for_user(user["email"])
    return _ok({"reset": True, "message": "Password updated — please sign in"})
