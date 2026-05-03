from functools import wraps

from flask import abort, jsonify
from flask_login import current_user

from app.models import SiteSettings


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        if not current_user.is_active:
            return abort(403)
        if not (current_user.is_super_admin or current_user.role_id):
            return abort(403)
        return func(*args, **kwargs)

    return wrapper


def permission_required(permission: str):
    permission_key = (permission or "").strip().lower()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if not current_user.is_authenticated:
                return abort(401)
            if not current_user.is_active:
                return abort(403)
            if current_user.is_super_admin:
                return func(*args, **kwargs)
            role = getattr(current_user, "role", None)
            if not role:
                return abort(403)
            permissions = {
                value.strip().lower()
                for value in (role.permissions or "").split(",")
                if value.strip()
            }
            if permission_key not in permissions:
                return abort(403)
            return func(*args, **kwargs)

        return wrapper

    return decorator


def super_admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        if not current_user.is_super_admin:
            return abort(403)
        return func(*args, **kwargs)

    return wrapper


def require_feature_flag(flag_column_name: str):
    normalized_flag = (flag_column_name or "").strip()

    def decorator(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            settings = SiteSettings.query.first()
            enabled = True
            if settings:
                if normalized_flag and hasattr(settings, normalized_flag):
                    enabled = bool(getattr(settings, normalized_flag))
                else:
                    enabled = False
            if not enabled:
                return (
                    jsonify(
                        {
                            "error": "This feature is currently disabled by the administrator.",
                            "status": "disabled",
                        }
                    ),
                    403,
                )
            return func(*args, **kwargs)

        return wrapper

    return decorator
