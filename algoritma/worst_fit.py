"""Alokasi lapak dengan Worst-Fit + pemanggilan antrean MLQ.

Worst-Fit: dari semua lapak berstatus KOSONG, pilih yang luasnya PALING BESAR.
Antrean MLQ: Queue 1 dihabiskan dulu, lalu Queue 2, lalu Queue 3;
di dalam satu queue urut berdasarkan waktu_daftar (FIFO).
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from database.config import TIMEOUT_HARI, utcnow
from database.models import (AlokasiSewa, Lapak, StatusAlokasi, StatusLapak,
                             StatusPendaftaran, UMKM)


def cari_lapak_worst_fit(db: Session, min_luas: float = 0.0) -> Lapak | None:
    """Lapak KOSONG dengan luas terbesar (minimal min_luas). None jika tidak ada."""
    return (
        db.query(Lapak)
        .filter(Lapak.status_lapak == StatusLapak.KOSONG, Lapak.luas >= min_luas)
        .order_by(Lapak.luas.desc(), Lapak.id.asc())
        .first()
    )


def antrean_menunggu(db: Session, exclude_ids=()):
    """Pendaftar yang masih mengantre, terurut Queue 1 -> 2 -> 3, lalu waktu_daftar."""
    q = db.query(UMKM).filter(UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU)
    if exclude_ids:
        q = q.filter(UMKM.id.notin_(list(exclude_ids)))
    return q.order_by(UMKM.queue_level.asc(), UMKM.waktu_daftar.asc(), UMKM.id.asc())


def jalankan_alokasi(db: Session, now=None, exclude_umkm_ids=()) -> list[AlokasiSewa]:
    """Selama ada lapak kosong DAN ada yang mengantre: pasangkan (Worst-Fit).

    Lapak berubah jadi 'Dipesan' dan timer Timeout (batas_konfirmasi) mulai berjalan.
    """
    now = now or utcnow()
    hasil: list[AlokasiSewa] = []
    while True:
        umkm = antrean_menunggu(db, exclude_umkm_ids).first()
        if umkm is None:
            break
        lapak = cari_lapak_worst_fit(db)
        if lapak is None:
            break

        alokasi = AlokasiSewa(
            umkm_id=umkm.id,
            lapak_id=lapak.id,
            waktu_alokasi=now,
            batas_konfirmasi=now + timedelta(days=TIMEOUT_HARI),
            status_alokasi=StatusAlokasi.MENUNGGU,
        )
        lapak.status_lapak = StatusLapak.DIPESAN
        umkm.status_pendaftaran = StatusPendaftaran.MENUNGGU_KONFIRMASI
        db.add(alokasi)
        db.flush()  # supaya query berikutnya melihat perubahan status
        hasil.append(alokasi)

    db.commit()
    return hasil
