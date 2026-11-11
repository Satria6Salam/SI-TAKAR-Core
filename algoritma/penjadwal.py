"""Manajemen Proses: penjadwal antrean Multilevel Queue (dispatcher).

Queue 1 dilayani sampai habis, lalu Queue 2, lalu Queue 3. Di dalam satu queue berlaku FIFO
berdasarkan waktu_antre. Pendaftar yang kebutuhannya belum muat di hole mana pun dilewati
dulu (tetap di posisinya) supaya ruang yang ada tidak menganggur.

KUNCI adalah mutex: timer background dan request dari browser berjalan di thread berbeda,
jadi bagian "baca hole lalu potong lapak" adalah critical section yang tidak boleh
dijalankan dua thread sekaligus (kalau tidak, satu ruang bisa terpotong untuk dua UMKM).
"""
import threading
from datetime import timedelta

from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from algoritma.worst_fit import buat_lapak, daftar_hole, pilih_hole, potong
from database.config import AGING_HARI, TIMEOUT_HARI
from database.models import AlokasiSewa, StatusAlokasi, StatusPendaftaran, UMKM, catat

KUNCI = threading.RLock()


def antrean_menunggu(db: Session, exclude_ids=()):
    """Pendaftar yang masih mengantre, terurut Queue 1 -> 2 -> 3, lalu waktu_antre (FIFO)."""
    q = db.query(UMKM).filter(UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU)
    if exclude_ids:
        q = q.filter(UMKM.id.notin_(list(exclude_ids)))
    return q.order_by(UMKM.queue_level.asc(), UMKM.waktu_antre.asc(), UMKM.id.asc())


def posisi_dalam_queue(db: Session, umkm: UMKM) -> int | None:
    """Urutan ke berapa di queue-nya sendiri (1 = paling depan). None jika tidak mengantre."""
    if umkm.status_pendaftaran != StatusPendaftaran.MENUNGGU:
        return None
    return 1 + sum(
        1 for u in antrean_menunggu(db).filter(UMKM.queue_level == umkm.queue_level).all()
        if (u.waktu_antre, u.id) < (umkm.waktu_antre, umkm.id)
    )


def jalankan_alokasi(db: Session, now=None, exclude_umkm_ids=()) -> list[AlokasiSewa]:
    """Pasangkan antrean dengan ruang kosong memakai Worst-Fit.

    Lapak baru berstatus 'Dipesan' dan timer Timeout (batas_konfirmasi) mulai berjalan.
    """
    with KUNCI:
        now = now or sekarang(db)
        holes = daftar_hole(db)
        hasil: list[AlokasiSewa] = []
        for umkm in antrean_menunggu(db, exclude_umkm_ids).all():
            if not holes:
                break
            hole = pilih_hole(holes, umkm.kebutuhan_muka, "worst")
            if hole is None:
                continue  # belum ada ruang bersambung yang cukup; beri giliran ke berikutnya
            lapak = buat_lapak(db, hole, umkm.kebutuhan_muka)
            holes = potong(holes, hole, umkm.kebutuhan_muka)

            alokasi = AlokasiSewa(
                umkm_id=umkm.id, lapak_id=lapak.id, waktu_alokasi=now,
                batas_konfirmasi=now + timedelta(days=TIMEOUT_HARI),
                status_alokasi=StatusAlokasi.MENUNGGU,
            )
            umkm.status_pendaftaran = StatusPendaftaran.MENUNGGU_KONFIRMASI
            db.add(alokasi)
            catat(db, "Alokasi", umkm_id=umkm.id, waktu=now, keterangan=(
                f"Worst-Fit memilih ruang kosong terluas di Zona {hole.zona_kode} ({hole.panjang:g} m); "
                f"dipotong {umkm.kebutuhan_muka:g} m menjadi lapak {lapak.kode_lapak} untuk "
                f"Queue {umkm.queue_level}. Batas konfirmasi {TIMEOUT_HARI} hari."))
            db.flush()
            hasil.append(alokasi)
        db.commit()
        return hasil


def terapkan_aging(db: Session, now=None) -> list[int]:
    """Aging (opsional): yang terlalu lama menunggu di Queue 2/3 naik satu tingkat.

    Mencegah starvation pada MLQ murni. Nonaktif jika AGING_HARI = 0.
    """
    if AGING_HARI <= 0:
        return []
    now = now or sekarang(db)
    batas = now - timedelta(days=AGING_HARI)
    naik = []
    for u in antrean_menunggu(db).filter(UMKM.queue_level > 1, UMKM.waktu_antre <= batas).all():
        u.queue_level -= 1
        u.waktu_antre = now  # masuk di ekor queue yang baru
        catat(db, "Aging", umkm_id=u.id, waktu=now, keterangan=(
            f"Menunggu lebih dari {AGING_HARI} hari; naik ke Queue {u.queue_level}."))
        naik.append(u.id)
    db.commit()
    return naik
