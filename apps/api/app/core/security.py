"""Authentication primitives.

V1 supports two modes (AUTH_MODE):
* ``none``  — single-team/internal deployment; every request acts as the
  default user. Suitable for local use or behind an access proxy.
* ``token`` — each user has a random access token (created with
  ``python -m app.cli create-user``). Logging in exchanges it for a signed,
  httpOnly session cookie; the raw token also works as a Bearer token.

The data model already records ``created_by`` / ``assigned_to`` /
``contacted_by`` users, so switching to a full identity provider later does
not require schema changes.
"""

from __future__ import annotations

import hashlib
import hmac
import secrets

from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer

from app.config import get_settings

DEFAULT_USER_EMAIL = "default@leadtracker.local"


def generate_token() -> str:
    return "lt_" + secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def tokens_equal(a: str, b: str) -> bool:
    return hmac.compare_digest(a, b)


def _serializer() -> URLSafeTimedSerializer:
    settings = get_settings()
    return URLSafeTimedSerializer(settings.secret_key.get_secret_value(), salt="leadtracker-session")


def sign_session(user_id: int) -> str:
    return _serializer().dumps({"uid": user_id})


def read_session(value: str) -> int | None:
    settings = get_settings()
    try:
        data = _serializer().loads(value, max_age=settings.session_max_age_hours * 3600)
    except (BadSignature, SignatureExpired):
        return None
    uid = data.get("uid") if isinstance(data, dict) else None
    return int(uid) if isinstance(uid, int) else None
