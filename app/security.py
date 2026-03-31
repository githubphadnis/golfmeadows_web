import os
import re
from dataclasses import dataclass
from typing import Optional

from fastapi import Header, HTTPException
from sqlalchemy.orm import Session

from app import models, schemas
from app.auth import create_access_token, decode_access_token, verify_password


@dataclass
class AdminPrincipal:
    method: str
    identity: str


def _csv_values(raw: str) -> list[str]:
    return [item.strip() for item in raw.split(",") if item.strip()]


def _wildcard_to_regex(pattern: str) -> str:
    # Reuses the wildcard idea used in CONDO's CORS helper: wildcard segments
    # should not cross dots, which keeps subdomain matching explicit.
    escaped = re.escape(pattern).replace(r"\*", "[^.]*?")
    return f"^{escaped}$"


def parse_cors_settings() -> tuple[list[str], Optional[str]]:
    raw_origins = os.getenv(
        "GOLFMEADOWS_CORS_ORIGINS",
        "http://127.0.0.1:4173,http://localhost:4173",
    )
    entries = _csv_values(raw_origins)
    exact: list[str] = []
    wildcard_regexes: list[str] = []

    for entry in entries:
        if "*" in entry:
            wildcard_regexes.append(_wildcard_to_regex(entry))
        else:
            exact.append(entry)

    allow_origin_regex = "|".join(wildcard_regexes) if wildcard_regexes else None
    return exact, allow_origin_regex


def admin_auth_config() -> dict:
    google_client_id = os.getenv("GOLFMEADOWS_GOOGLE_CLIENT_ID", "").strip()
    return {
        "google_enabled": bool(google_client_id),
        "google_client_id": google_client_id,
    }


def _verify_google_bearer_token(token: str) -> Optional[AdminPrincipal]:
    google_client_id = os.getenv("GOLFMEADOWS_GOOGLE_CLIENT_ID", "").strip()
    if not google_client_id:
        return None

    try:
        from google.auth.transport import requests as google_requests
        from google.oauth2 import id_token as google_id_token
    except ImportError as exc:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google admin auth is enabled but dependencies are missing. "
                "Install google-auth with requests transport."
            ),
        ) from exc

    allowed_emails = {
        item.lower() for item in _csv_values(os.getenv("GOLFMEADOWS_ADMIN_GOOGLE_EMAILS", ""))
    }
    if not allowed_emails:
        raise HTTPException(
            status_code=503,
            detail=(
                "Google admin auth is enabled but no allowed emails are configured. "
                "Set GOLFMEADOWS_ADMIN_GOOGLE_EMAILS."
            ),
        )

    try:
        payload = google_id_token.verify_oauth2_token(
            token,
            google_requests.Request(),
            google_client_id,
        )
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=401, detail=f"Invalid Google token: {exc}") from exc

    email = str(payload.get("email", "")).strip().lower()
    email_verified = bool(payload.get("email_verified", False))

    if not email or not email_verified:
        raise HTTPException(status_code=401, detail="Google token email is not verified.")
    if email not in allowed_emails:
        raise HTTPException(status_code=403, detail="Google account is not allowed for admin access.")

    return AdminPrincipal(method="google", identity=email)


def require_admin(
    authorization: Optional[str] = Header(default=None),
    x_admin_token: Optional[str] = Header(default=None),
    login: Optional[schemas.AdminLoginIn] = None,
    db: Optional[Session] = None,
) -> AdminPrincipal | tuple[AdminPrincipal, str]:
    if login is not None:
        if db is None:
            raise HTTPException(status_code=500, detail="Database session is required for login.")
        email = login.email.strip().lower()
        user = db.query(models.AdminUser).filter(models.AdminUser.email == email).first()
        if not user:
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        if not user.is_active:
            raise HTTPException(status_code=403, detail="Admin user is inactive.")
        if not verify_password(login.password, user.password_hash):
            raise HTTPException(status_code=401, detail="Invalid credentials.")
        token = create_access_token(user.id, user.email, user.role)
        return AdminPrincipal(method="local", identity=user.email), token

    configured_admin_token = os.getenv("GOLFMEADOWS_ADMIN_TOKEN", "").strip()
    bearer_token = ""
    if authorization and authorization.lower().startswith("bearer "):
        bearer_token = authorization.split(" ", 1)[1].strip()

    if not configured_admin_token and not os.getenv("GOLFMEADOWS_GOOGLE_CLIENT_ID", "").strip():
        raise HTTPException(
            status_code=503,
            detail=(
                "Admin auth is not configured. Set GOLFMEADOWS_ADMIN_TOKEN or "
                "GOLFMEADOWS_GOOGLE_CLIENT_ID + GOLFMEADOWS_ADMIN_GOOGLE_EMAILS."
            ),
        )

    for candidate in (x_admin_token or "", bearer_token):
        if configured_admin_token and candidate and candidate == configured_admin_token:
            return AdminPrincipal(method="token", identity="admin-token")

    if bearer_token:
        principal = _verify_local_access_token(bearer_token, db)
        if principal:
            return principal
        principal = _verify_google_bearer_token(bearer_token)
        if principal:
            return principal

    raise HTTPException(status_code=401, detail="Admin authentication required.")


def _verify_local_access_token(token: str, db: Optional[Session] = None) -> Optional[AdminPrincipal]:
    payload = decode_access_token(token)
    if not payload:
        return None

    email = str(payload.get("email", "")).strip().lower()
    user_id_raw = payload.get("uid")
    if not email or user_id_raw is None:
        return None

    close_db = False
    if db is None:
        from app.database import SessionLocal

        db = SessionLocal()
        close_db = True
    try:
        user = db.query(models.AdminUser).filter(models.AdminUser.email == email).first()
        if not user or user.id != int(user_id_raw) or not user.is_active:
            raise HTTPException(status_code=401, detail="Admin session is invalid or inactive.")
        if user.role not in {"admin", "superadmin"}:
            raise HTTPException(status_code=403, detail="Admin role required.")
        return AdminPrincipal(method="local", identity=user.email)
    finally:
        if close_db:
            db.close()


def revoke_session(_: AdminPrincipal) -> None:
    # JWT access tokens are stateless; explicit revocation list can be added later.
    return None
