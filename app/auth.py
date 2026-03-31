import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from datetime import datetime, timedelta
from typing import Any, Optional

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app import models

PBKDF2_ITERATIONS = 210_000
PBKDF2_ALGORITHM = "sha256"
VALID_ADMIN_ROLES = {"admin", "superadmin"}
BOOTSTRAP_ADMIN_EMAIL = "admin@golfmeadows.local"


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode(data + padding)


def normalize_email(email: str) -> str:
    normalized = (email or "").strip().lower()
    if "@" not in normalized:
        raise HTTPException(status_code=400, detail="Valid email is required.")
    return normalized[:255]


def hash_password(password: str, *, minimum_length: int = 8) -> str:
    if not password or len(password) < minimum_length:
        raise HTTPException(
            status_code=400,
            detail=f"Password must be at least {minimum_length} characters.",
        )
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode(),
        salt,
        PBKDF2_ITERATIONS,
    )
    return (
        f"pbkdf2_{PBKDF2_ALGORITHM}"
        f"${PBKDF2_ITERATIONS}"
        f"${_b64url_encode(salt)}"
        f"${_b64url_encode(digest)}"
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        method, iterations_raw, salt_b64, digest_b64 = stored_hash.split("$", 3)
    except ValueError:
        return False
    if method != f"pbkdf2_{PBKDF2_ALGORITHM}":
        return False
    try:
        iterations = int(iterations_raw)
        salt = _b64url_decode(salt_b64)
        expected = _b64url_decode(digest_b64)
    except Exception:  # noqa: BLE001
        return False

    actual = hashlib.pbkdf2_hmac(
        PBKDF2_ALGORITHM,
        password.encode(),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _jwt_secret() -> str:
    # Fallback to admin token keeps deployments simple.
    secret = os.getenv("GOLFMEADOWS_JWT_SECRET", "").strip() or os.getenv(
        "GOLFMEADOWS_ADMIN_TOKEN", ""
    ).strip()
    if not secret:
        raise HTTPException(
            status_code=503,
            detail="JWT secret is not configured. Set GOLFMEADOWS_JWT_SECRET.",
        )
    return secret


def create_access_token(
    *,
    user_id: int,
    email: str,
    role: str,
    session_id: str,
    expires_in_seconds: int = 60 * 60 * 12,
) -> str:
    now = int(time.time())
    payload = {
        "typ": "access",
        "uid": user_id,
        "email": email,
        "role": role,
        "sid": session_id,
        "iat": now,
        "exp": now + expires_in_seconds,
        "iss": "golfmeadows",
    }
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = (
        f"{_b64url_encode(json.dumps(header, separators=(',', ':')).encode())}"
        f".{_b64url_encode(json.dumps(payload, separators=(',', ':')).encode())}"
    )
    signature = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(signature)}"


def decode_access_token(token: str) -> Optional[dict[str, Any]]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".", 2)
    except ValueError:
        return None
    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(_jwt_secret().encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:  # noqa: BLE001
        return None
    if not hmac.compare_digest(expected_sig, actual_sig):
        return None
    try:
        payload = json.loads(_b64url_decode(payload_b64).decode())
    except Exception:  # noqa: BLE001
        return None
    if int(payload.get("exp", 0)) < int(time.time()):
        return None
    if payload.get("iss") != "golfmeadows":
        return None
    return payload


def ensure_default_admin_user(
    db: Session,
    email: Optional[str] = None,
    password: Optional[str] = None,
    role: str = "superadmin",
) -> Optional[models.AdminUser]:
    default_email = (
        normalize_email(email or os.getenv("GOLFMEADOWS_DEFAULT_ADMIN_EMAIL", "").strip())
        if (email or os.getenv("GOLFMEADOWS_DEFAULT_ADMIN_EMAIL", "").strip())
        else ""
    )
    default_password = password or os.getenv("GOLFMEADOWS_DEFAULT_ADMIN_PASSWORD", "").strip()
    if not default_email or not default_password:
        # Zero-config fallback for Portainer repo deployments:
        # if admin token exists, bootstrap a local login using a fixed email.
        token = os.getenv("GOLFMEADOWS_ADMIN_TOKEN", "").strip()
        if not token:
            return None
        existing = (
            db.query(models.AdminUser)
            .filter(models.AdminUser.email == BOOTSTRAP_ADMIN_EMAIL)
            .first()
        )
        if existing:
            return existing
        return create_admin_user(
            db=db,
            email=BOOTSTRAP_ADMIN_EMAIL,
            password=token,
            role=role,
            is_active=True,
            upsert=False,
            minimum_password_length=1,
        )
    return create_admin_user(
        db=db,
        email=default_email,
        password=default_password,
        role=role,
        is_active=True,
        upsert=True,
    )


def create_admin_user(
    *,
    db: Session,
    email: str,
    password: str,
    role: str = "admin",
    is_active: bool = True,
    upsert: bool = False,
    minimum_password_length: int = 8,
) -> models.AdminUser:
    normalized = normalize_email(email)
    normalized_role = (role or "admin").strip().lower()
    if normalized_role not in VALID_ADMIN_ROLES:
        raise HTTPException(status_code=400, detail=f"Role must be one of {sorted(VALID_ADMIN_ROLES)}.")

    existing = db.query(models.AdminUser).filter(models.AdminUser.email == normalized).first()
    if existing:
        if not upsert:
            raise HTTPException(status_code=409, detail="Admin user with this email already exists.")
        existing.password_hash = hash_password(password, minimum_length=minimum_password_length)
        existing.role = normalized_role
        existing.is_active = is_active
        db.commit()
        db.refresh(existing)
        return existing

    user = models.AdminUser(
        email=normalized,
        password_hash=hash_password(password, minimum_length=minimum_password_length),
        role=normalized_role,
        is_active=is_active,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


def authenticate_admin_credentials(db: Session, email: str, password: str) -> models.AdminUser:
    normalized = normalize_email(email)
    user = db.query(models.AdminUser).filter(models.AdminUser.email == normalized).first()
    if not user or not verify_password(password, user.password_hash):
        raise HTTPException(status_code=401, detail="Invalid email or password.")
    if not user.is_active:
        raise HTTPException(status_code=403, detail="Admin user is inactive.")
    if user.role not in VALID_ADMIN_ROLES:
        raise HTTPException(status_code=403, detail="Admin role required.")
    return user


def create_session_for_user(db: Session, user: models.AdminUser, expires_in_seconds: int = 60 * 60 * 12) -> str:
    session_id = secrets.token_urlsafe(24)
    now = datetime.utcnow()
    expires_at = now + timedelta(seconds=expires_in_seconds)
    token = create_access_token(
        user_id=user.id,
        email=user.email,
        role=user.role,
        session_id=session_id,
        expires_in_seconds=expires_in_seconds,
    )
    db.add(
        models.AdminSession(
            session_id=session_id,
            admin_user_id=user.id,
            revoked=False,
            issued_at=now,
            expires_at=expires_at,
        )
    )
    user.last_login_at = now
    db.commit()
    return token


def revoke_session_by_token(db: Session, token: str) -> bool:
    payload = decode_access_token(token)
    if not payload:
        return False
    session_id = str(payload.get("sid", "")).strip()
    if not session_id:
        return False
    session = db.query(models.AdminSession).filter(models.AdminSession.session_id == session_id).first()
    if not session:
        return False
    session.revoked = True
    session.revoked_at = datetime.utcnow()
    db.commit()
    return True
