"""Penanganan Deadlock: Timeout (fase konfirmasi) & Preemption (fase aktif)."""
from datetime import timedelta

from sqlalchemy.orm import Session

from algoritma.worst_fit import jalankan_alokasi
from database.config import PREEMPTION_HARI, utcnow
from database.models import (AlokasiSewa, ArsipPelanggaran, StatusAlokasi, StatusLapak,
                             StatusPendaftaran)


def cek_timeout(db: Session, now=None) -> list[int]:
    """Alokasi 'Menunggu Konfirmasi' yang lewat batas_konfirmasi (3 hari) -> hangus.

    1) alokasi jadi Dibatalkan  2) UMKM dilempar ke urutan terbawah antrean awalnya
    3) lapak jadi Kosong        4) dicatat di arsip
    Return: daftar umkm_id yang terkena timeout.
    """
    now = now or utcnow()
    kadaluarsa = (
        db.query(AlokasiSewa)
        .filter(AlokasiSewa.status_alokasi == StatusAlokasi.MENUNGGU,
                AlokasiSewa.batas_konfirmasi < now)
        .all()
    )
    umkm_ids = []
    for a in kadaluarsa:
        a.status_alokasi = StatusAlokasi.DIBATALKAN
        a.lapak.status_lapak = StatusLapak.KOSONG
        a.umkm.status_pendaftaran = StatusPendaftaran.MENUNGGU
        a.umkm.waktu_daftar = now  # urutan terbawah di queue-nya (queue_level tetap)
        db.add(ArsipPelanggaran(
            umkm_id=a.umkm_id,
            jenis_pelanggaran="Timeout",
            waktu_kejadian=now,
            keterangan=f"Tidak konfirmasi lapak {a.lapak.kode_lapak} sebelum batas waktu; "
                       f"dilempar ke urutan terbawah Queue {a.umkm.queue_level}.",
        ))
        umkm_ids.append(a.umkm_id)
    db.commit()
    return umkm_ids


def cek_preemption(db: Session, now=None) -> list[int]:
    """Alokasi 'Aktif' yang tidak absen >= 14 hari -> hak sewa dicabut.

    Lapak kembali Kosong (Hijau), UMKM masuk Arsip Pelanggaran.
    Return: daftar umkm_id yang dicabut.
    """
    now = now or utcnow()
    batas = now - timedelta(days=PREEMPTION_HARI)
    aktif = db.query(AlokasiSewa).filter(AlokasiSewa.status_alokasi == StatusAlokasi.AKTIF).all()
    umkm_ids = []
    for a in aktif:
        terakhir = a.terakhir_aktif or a.waktu_alokasi
        if terakhir <= batas:
            a.status_alokasi = StatusAlokasi.DICABUT
            a.lapak.status_lapak = StatusLapak.KOSONG
            a.umkm.status_pendaftaran = StatusPendaftaran.DICABUT
            db.add(ArsipPelanggaran(
                umkm_id=a.umkm_id,
                jenis_pelanggaran="Preemption",
                waktu_kejadian=now,
                keterangan=f"Lapak {a.lapak.kode_lapak} tidak aktif >= {PREEMPTION_HARI} hari; "
                           f"hak sewa dicabut.",
            ))
            umkm_ids.append(a.umkm_id)
    db.commit()
    return umkm_ids


def jalankan_semua(db: Session, now=None) -> dict:
    """Satu siklus timer: Timeout -> Preemption -> alokasi ulang lapak yang baru kosong."""
    now = now or utcnow()
    timeout_ids = cek_timeout(db, now)
    preempt_ids = cek_preemption(db, now)
    # UMKM yang baru kena timeout tidak langsung diberi lapak yang sama lagi di siklus ini
    baru = jalankan_alokasi(db, now, exclude_umkm_ids=timeout_ids)
    return {
        "timeout": timeout_ids,
        "preemption": preempt_ids,
        "alokasi_baru": [a.id for a in baru],
    }
