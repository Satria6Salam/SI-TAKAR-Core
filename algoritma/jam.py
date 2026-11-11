"""Jam sistem SI-TAKAR.

Semua aturan berbasis waktu (Timeout 3 hari, Preemption 14 hari, masa sewa) membaca jam ini.
Admin dapat memajukan jam untuk demo, sehingga kejadian berhari-hari bisa ditunjukkan
dalam beberapa detik tanpa mengubah jam laptop.
"""
from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from database.config import utcnow
from database.models import Pengaturan

_KUNCI = "geser_jam_detik"


def geser(db: Session) -> timedelta:
    baris = db.get(Pengaturan, _KUNCI)
    return timedelta(seconds=float(baris.nilai)) if baris else timedelta(0)


def sekarang(db: Session) -> datetime:
    return utcnow() + geser(db)


def majukan(db: Session, hari: float) -> timedelta:
    total = geser(db) + timedelta(days=hari)
    baris = db.get(Pengaturan, _KUNCI)
    if baris is None:
        db.add(Pengaturan(kunci=_KUNCI, nilai=str(total.total_seconds())))
    else:
        baris.nilai = str(total.total_seconds())
    db.commit()
    return total


def atur_ulang(db: Session) -> None:
    """Kembalikan jam sistem ke jam laptop."""
    baris = db.get(Pengaturan, _KUNCI)
    if baris is not None:
        db.delete(baris)
        db.commit()
