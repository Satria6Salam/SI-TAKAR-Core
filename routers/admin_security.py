import base64
import hashlib
import hmac
import os
import secrets
import time

from fastapi import Depends, HTTPException, Request
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import Admin

SESSION_COOKIE = "si_takar_admin"
SESSION_TTL_SECONDS = 8 * 60 * 60
SESSION_SECRET = os.getenv("ADMIN_SESSION_SECRET")
if not SESSION_SECRET:
    SESSION_SECRET = secrets.token_urlsafe(48)
SESSION_SECRET = SESSION_SECRET.encode()


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, expected_hex = password_hash.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 100_000
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def create_session_token(username: str) -> str:
    expires = int(time.time()) + SESSION_TTL_SECONDS
    payload = f"{username}|{expires}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def get_admin_session(request: Request, db: Session) -> Admin | None:
    token = request.cookies.get(SESSION_COOKIE, "")
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        username, expires = payload.rsplit("|", 1)
        if int(expires) < int(time.time()):
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return db.query(Admin).filter(Admin.username == username).first()


def require_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    admin = get_admin_session(request, db)
    if admin is None:
        raise HTTPException(status_code=401, detail="Login admin diperlukan")
    return admin