import hashlib
import hmac
import secrets
from functools import wraps

from flask import jsonify, session

from .db import fetch_one

HASH_PREFIX = "pbkdf2_sha256"
HASH_ITERATIONS = 600000


def hash_password(password):
    salt = secrets.token_urlsafe(18)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        password.encode("utf-8"),
        salt.encode("utf-8"),
        HASH_ITERATIONS,
    ).hex()
    return f"{HASH_PREFIX}${HASH_ITERATIONS}${salt}${digest}"


def verify_password(password_hash, password):
    try:
        prefix, iterations, salt, expected = password_hash.split("$", 3)
        if prefix != HASH_PREFIX:
            return False
        digest = hashlib.pbkdf2_hmac(
            "sha256",
            password.encode("utf-8"),
            salt.encode("utf-8"),
            int(iterations),
        ).hex()
        return hmac.compare_digest(digest, expected)
    except (AttributeError, ValueError):
        return False


def current_user():
    user_id = session.get("user_id")
    if not user_id:
        return None
    return fetch_one(
        """
        SELECT id, email, full_name, role, active
        FROM app_users
        WHERE id = %(user_id)s AND active = true
        """,
        {"user_id": user_id},
    )


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        user = current_user()
        if not user:
            return jsonify({"error": "unauthenticated", "message": "Please log in."}), 401
        return fn(user, *args, **kwargs)

    return wrapper


def admin_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(user, *args, **kwargs):
        if user["role"] != "admin":
            return jsonify({"error": "forbidden", "message": "Admin access required."}), 403
        return fn(user, *args, **kwargs)

    return wrapper


def cafe_required(fn):
    @wraps(fn)
    @login_required
    def wrapper(user, *args, **kwargs):
        if user["role"] != "cafe_staff":
            return jsonify({"error": "forbidden", "message": "Cafe staff access required."}), 403
        cafe = fetch_one(
            """
            SELECT c.id, c.name
            FROM cafe_user_assignments cua
            JOIN cafes c ON c.id = cua.cafe_id
            WHERE cua.user_id = %(user_id)s
              AND cua.active = true
              AND c.status = 'active'
            LIMIT 1
            """,
            {"user_id": user["id"]},
        )
        if not cafe:
            return jsonify({"error": "no_cafe", "message": "No active cafe assignment found."}), 403
        return fn(user, cafe, *args, **kwargs)

    return wrapper
