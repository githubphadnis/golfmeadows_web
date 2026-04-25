from functools import wraps

from flask import abort
from flask_login import current_user


def admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        if not current_user.is_active:
            return abort(403)
        return func(*args, **kwargs)

    return wrapper


def super_admin_required(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        if not current_user.is_authenticated:
            return abort(401)
        if not current_user.is_super_admin:
            return abort(403)
        return func(*args, **kwargs)

    return wrapper
