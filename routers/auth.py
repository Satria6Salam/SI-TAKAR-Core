"""Utilitas JWT dan dependency autentikasi admin."""
import hashlib
import os
from datetime import datetime, timedelta, timezone

from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import Admin

# Wajib diset lewat .env sebelum production!
SECRET_KEY = os.getenv("SECRET_KEY", "GANTI_INI_SEBELUM_PRODUCTION_guna_string_acak_panjang")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MENIT = int(os.getenv("ACCESS_TOKEN_EXPIRE_MENIT", "60"))

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/admin/login")


def verify_password(plain: str, hashed: str) -> bool:
    """Verifikasi password dengan format salt$dk — sama seperti hash_password di seed.py."""
    try:
        salt_hex, dk_hex = hashed.split("$")
        salt = bytes.fromhex(salt_hex)
        dk = hashlib.pbkdf2_hmac("sha256", plain.encode(), salt, 100_000)
        return dk.hex() == dk_hex
    except Exception:
        return False


def buat_token(data: dict, expire_menit: int = ACCESS_TOKEN_EXPIRE_MENIT) -> str:
    """Buat JWT Bearer token dengan waktu kedaluwarsa."""
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(minutes=expire_menit)
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def get_current_admin(
    token: str = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Admin:
    """Dependency FastAPI: pastikan request membawa token admin yang valid."""
    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau sudah kedaluwarsa. Silakan login ulang.",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str | None = payload.get("sub")
        if username is None:
            raise exc
    except JWTError:
        raise exc

    admin = db.query(Admin).filter(Admin.username == username).first()
    if admin is None:
        raise exc
    return admin
