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


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${dk.hex()}"


def verify_password(password: str, password_hash: str) -> bool:
    try:
        salt_hex, expected_hex = password_hash.split("$", 1)
        actual = hashlib.pbkdf2_hmac(
            "sha256", password.encode(), bytes.fromhex(salt_hex), 100_000
        )
        return hmac.compare_digest(actual.hex(), expected_hex)
    except (ValueError, TypeError):
        return False


def create_session_token(subjek: str, ttl: int = SESSION_TTL_SECONDS) -> str:
    """Token bertanda tangan HMAC berisi subjek dan waktu kedaluwarsa."""
    expires = int(time.time()) + ttl
    payload = f"{subjek}|{expires}".encode()
    encoded = base64.urlsafe_b64encode(payload).decode().rstrip("=")
    signature = hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
    return f"{encoded}.{signature}"


def read_session_token(token: str) -> str | None:
    """Subjek token bila tanda tangannya sah dan belum kedaluwarsa."""
    try:
        encoded, signature = token.rsplit(".", 1)
        expected = hmac.new(SESSION_SECRET, encoded.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            return None
        payload = base64.urlsafe_b64decode(encoded + "=" * (-len(encoded) % 4)).decode()
        subjek, expires = payload.rsplit("|", 1)
        if int(expires) < int(time.time()):
            return None
    except (ValueError, UnicodeDecodeError):
        return None
    return subjek


# ---- Sesi penjual: kode pendaftaran + PIN -> cookie terpisah dari sesi admin ----
SELLER_COOKIE = "si_takar_penjual"
SELLER_TTL_SECONDS = 12 * 60 * 60
_AWALAN_PENJUAL = "penjual:"


def create_seller_token(kode: str) -> str:
    return create_session_token(_AWALAN_PENJUAL + kode, SELLER_TTL_SECONDS)


def get_seller_kode(request: Request) -> str | None:
    """Kode pendaftaran milik penjual yang sedang masuk di browser ini (atau None)."""
    subjek = read_session_token(request.cookies.get(SELLER_COOKIE, ""))
    if subjek and subjek.startswith(_AWALAN_PENJUAL):
        return subjek[len(_AWALAN_PENJUAL):]
    return None


def get_admin_session(request: Request, db: Session) -> Admin | None:
    username = read_session_token(request.cookies.get(SESSION_COOKIE, ""))
    if not username or username.startswith(_AWALAN_PENJUAL):
        return None
    return db.query(Admin).filter(Admin.username == username).first()


def require_admin(request: Request, db: Session = Depends(get_db)) -> Admin:
    admin = get_admin_session(request, db)
    if admin is None:
        raise HTTPException(status_code=401, detail="Login admin diperlukan")
    return admin