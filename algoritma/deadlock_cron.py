"""Penanganan Deadlock: Timeout (fase konfirmasi) & Preemption (fase aktif)."""
from datetime import timedelta

from sqlalchemy.orm import Session

from algoritma.worst_fit import jalankan_alokasi
from database.config import PREEMPTION_DETIK, TIMEOUT_DETIK, utcnow
from database.models import (AlokasiSewa, ArsipPelanggaran, StatusAlokasi, StatusLapak,
                             StatusPendaftaran)


def cek_timeout(db: Session, now=None) -> list[int]:
    """Alokasi 'Menunggu Konfirmasi' yang lewat batas_konfirmasi -> hangus.

    Sesuai Aturan Deadlock 1 (Timeout):
    1. Mengubah status hak UMKM tersebut menjadi 'Dibatalkan' (Hangus).
    2. Melempar posisi UMKM tersebut ke urutan terbawah di antrean awalnya.
    3. Membuka kembali status lapak tersebut menjadi 'Kosong'.
    4. Mengalokasikan lapak tersebut ke pendaftar urutan pertama di Queue saat ini.
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
    durasi_str = f"{TIMEOUT_DETIK} detik (1 menit)" if TIMEOUT_DETIK <= 120 else f"{TIMEOUT_DETIK // 86400} hari"
    for a in kadaluarsa:
        a.status_alokasi = StatusAlokasi.DIBATALKAN
        a.lapak.status_lapak = StatusLapak.KOSONG
        a.umkm.status_pendaftaran = StatusPendaftaran.MENUNGGU
        a.umkm.waktu_daftar = now  # urutan terbawah di queue-nya (queue_level tetap)
        db.add(ArsipPelanggaran(
            umkm_id=a.umkm_id,
            jenis_pelanggaran="Timeout",
            waktu_kejadian=now,
            keterangan=f"Batas waktu konfirmasi ({durasi_str}) untuk lapak {a.lapak.kode_lapak} telah terlewati tanpa respons. "
                       f"Status hak dibatalkan (hangus), lapak dibuka kembali menjadi Kosong, "
                       f"dan UMKM dipindahkan ke urutan terbawah Queue {a.umkm.queue_level}.",
        ))
        umkm_ids.append(a.umkm_id)
    db.commit()
    return umkm_ids


def cek_preemption(db: Session, now=None) -> list[int]:
    """Alokasi 'Aktif' yang tidak absen >= batas waktu -> hak sewa dicabut sepihak.

    Sesuai Aturan Deadlock 2 (Preemption):
    1. Mencabut hak sewa UMKM secara sepihak.
    2. Menyimpan data UMKM ke dalam 'Arsip Pelanggaran' (catatan rekam jejak).
    3. Merubah warna lapak di Peta Grid Visual dari Merah (Terisi) menjadi Hijau (Kosong).
    4. Sistem Worst-Fit akan mendeteksi ruang hijau ini untuk diberikan kepada pendaftar baru.
    Return: daftar umkm_id yang dicabut.
    """
    now = now or utcnow()
    batas = now - timedelta(seconds=PREEMPTION_DETIK)
    durasi_str = f"{PREEMPTION_DETIK} detik" if PREEMPTION_DETIK < 86400 else f"{PREEMPTION_DETIK // 86400} hari"
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
                keterangan=f"Lapak {a.lapak.kode_lapak} tidak aktif berjualan selama {durasi_str}. "
                           f"Hak sewa dicabut secara sepihak (Preemption), disimpan dalam Arsip Pelanggaran, "
                           f"dan warna lapak dikembalikan menjadi Hijau (Kosong).",
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
