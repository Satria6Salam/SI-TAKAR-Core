"""Isi data awal: lapak (denah contoh) + 1 akun admin. Aman dijalankan berulang kali.

Jalankan:  python seed.py
"""
import hashlib
import os

from database import models  # noqa: F401
from database.config import Base, SessionLocal, engine
from database.models import Admin, Lapak, StatusLapak

# (kode, panjang, lebar, x, y)  -> denah 4 kolom x 3 baris, ukuran bervariasi agar Worst-Fit terlihat
LAPAK_AWAL = [
    ("A1", 3, 3, 0, 0), ("A2", 2, 3, 1, 0), ("A3", 3, 4, 2, 0), ("A4", 2, 2, 3, 0),
    ("B1", 4, 4, 0, 1), ("B2", 3, 3, 1, 1), ("B3", 2, 3, 2, 1), ("B4", 3, 3, 3, 1),
    ("C1", 2, 2, 0, 2), ("C2", 3, 4, 1, 2), ("C3", 2, 3, 2, 2), ("C4", 2, 2, 3, 2),
]


def hash_password(password: str) -> str:
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${dk.hex()}"


def seed():
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        for kode, p, l, x, y in LAPAK_AWAL:
            if not db.query(Lapak).filter_by(kode_lapak=kode).first():
                db.add(Lapak(kode_lapak=kode, panjang=p, lebar=l, luas=p * l,
                             posisi_x=x, posisi_y=y, status_lapak=StatusLapak.KOSONG))
        if not db.query(Admin).filter_by(username="admin").first():
            # GANTI password ini sebelum dipakai sungguhan
            db.add(Admin(username="admin", password_hash=hash_password("admin123")))
        db.commit()
        print(f"Seed selesai: {db.query(Lapak).count()} lapak, {db.query(Admin).count()} admin.")
    finally:
        db.close()


if __name__ == "__main__":
    seed()
