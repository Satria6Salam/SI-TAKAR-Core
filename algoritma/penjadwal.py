"""Manajemen Proses: penjadwal antrean Multilevel Queue (dispatcher).

Pendaftar yang lolos verifikasi masuk ke salah satu dari tiga antrean. Lapak dibagikan dalam
PUTARAN ALOKASI: pada satu putaran, Queue 1 dilayani sampai habis, lalu Queue 2, lalu Queue 3.
Di dalam satu queue berlaku FIFO berdasarkan waktu_antre (= waktu daftar). Pendaftar yang
kebutuhannya belum muat di ruang kosong mana pun dilewati dulu (tetap di posisinya) supaya
ruang yang ada tidak menganggur.

Mengapa per putaran? Bila lapak dibagikan begitu satu pendaftar diverifikasi, siapa yang lebih
dulu diverifikasi langsung mendapat ruang dan urutan prioritas tidak pernah berlaku (kembali
menjadi siapa cepat dia dapat). Dengan putaran, semua pendaftar yang sedang menunggu
dibandingkan bersama dan Queue 1 benar-benar didahulukan.

Mode PUTARAN_ALOKASI=langsung mengembalikan perilaku lama (dibagikan seketika).

KUNCI adalah mutex: timer background dan request dari browser berjalan di thread berbeda,
jadi bagian "baca ruang kosong lalu potong lapak" adalah critical section.
"""
import threading
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from algoritma.worst_fit import Hole, buat_lapak, daftar_hole, pilih_hole, potong
from database import config
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


@dataclass
class Rencana:
    """Satu baris rencana putaran: pendaftar, urutan giliran, dan ruang yang akan dipotong."""
    giliran: int
    umkm: UMKM
    hole: Hole | None          # None = belum ada ruang bersambung yang muat


def rencana_putaran(db: Session, exclude_umkm_ids=()) -> list[Rencana]:
    """Hitung hasil putaran alokasi tanpa mengubah data (dipakai pratinjau dan eksekusi)."""
    holes = daftar_hole(db)
    hasil = []
    for i, umkm in enumerate(antrean_menunggu(db, exclude_umkm_ids).all(), 1):
        hole = pilih_hole(holes, umkm.kebutuhan_muka, "worst") if holes else None
        if hole is not None:
            holes = potong(holes, hole, umkm.kebutuhan_muka)
        hasil.append(Rencana(i, umkm, hole))
    return hasil


def jalankan_alokasi(db: Session, now=None, exclude_umkm_ids=()) -> list[AlokasiSewa]:
    """Satu putaran alokasi: pasangkan antrean (Q1 -> Q2 -> Q3) dengan ruang kosong (Worst-Fit).

    Lapak baru berstatus 'Dipesan' dan timer Timeout (batas_konfirmasi) mulai berjalan.
    """
    with KUNCI:
        now = now or sekarang(db)
        hasil: list[AlokasiSewa] = []
        for r in rencana_putaran(db, exclude_umkm_ids):
            if r.hole is None:
                continue
            umkm, hole = r.umkm, r.hole
            lapak = buat_lapak(db, hole, umkm.kebutuhan_muka)
            alokasi = AlokasiSewa(
                umkm_id=umkm.id, lapak_id=lapak.id, waktu_alokasi=now,
                batas_konfirmasi=now + timedelta(days=TIMEOUT_HARI),
                status_alokasi=StatusAlokasi.MENUNGGU,
            )
            umkm.status_pendaftaran = StatusPendaftaran.MENUNGGU_KONFIRMASI
            db.add(alokasi)
            catat(db, "Alokasi", umkm_id=umkm.id, waktu=now, keterangan=(
                f"Giliran #{r.giliran} (Queue {umkm.queue_level}): Worst-Fit memilih ruang kosong "
                f"terluas di Zona {hole.zona_kode} ({hole.panjang:g} m); dipotong "
                f"{umkm.kebutuhan_muka:g} m menjadi lapak {lapak.kode_lapak}. "
                f"Batas konfirmasi {TIMEOUT_HARI} hari."))
            db.flush()
            hasil.append(alokasi)
        db.commit()
        return hasil


def alokasi_otomatis(db: Session, now=None, exclude_umkm_ids=()) -> list[AlokasiSewa]:
    """Dipanggil setelah pendaftaran/verifikasi/ruang dilepas.

    Mode 'manual' (bawaan): tidak membagi apa pun; lapak dibagikan saat admin menjalankan
    putaran. Mode 'langsung': putaran dijalankan seketika.
    """
    if config.PUTARAN_ALOKASI == "langsung":
        return jalankan_alokasi(db, now, exclude_umkm_ids)
    return []


def putaran_harian(db: Session, now=None, exclude_umkm_ids=()) -> list[AlokasiSewa]:
    """Mode manual: jalankan satu putaran per hari (WIB) begitu lewat PUTARAN_HARIAN_JAM."""
    from database.models import Pengaturan

    if config.PUTARAN_ALOKASI == "langsung" or config.PUTARAN_HARIAN_JAM < 0:
        return []
    now = now or sekarang(db)
    lokal = now + timedelta(hours=config.ZONA_WAKTU_JAM)
    if lokal.hour < config.PUTARAN_HARIAN_JAM:
        return []
    hari_ini = lokal.date().isoformat()
    tanda = db.get(Pengaturan, "putaran_harian_terakhir")
    if tanda is not None and tanda.nilai >= hari_ini:
        return []
    if tanda is None:
        db.add(Pengaturan(kunci="putaran_harian_terakhir", nilai=hari_ini))
    else:
        tanda.nilai = hari_ini
    db.commit()
    menunggu = antrean_menunggu(db, exclude_umkm_ids).count()
    if not menunggu:
        return []
    baru = jalankan_alokasi(db, now, exclude_umkm_ids)
    catat(db, "Putaran Alokasi", waktu=now, keterangan=(
        f"Putaran harian otomatis ({config.PUTARAN_HARIAN_JAM:02d}.00 WIB): {len(baru)} dari "
        f"{menunggu} pendaftar mendapat lapak (urutan Queue 1 -> 2 -> 3)."))
    db.commit()
    return baru


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
        # lama menunggu dihitung sejak benar-benar masuk antrean (setelah verifikasi)
        if u.waktu_verifikasi and u.waktu_verifikasi > batas:
            continue
        u.queue_level -= 1
        u.waktu_antre = now  # masuk di ekor queue yang baru
        catat(db, "Aging", umkm_id=u.id, waktu=now, keterangan=(
            f"Menunggu lebih dari {AGING_HARI} hari; naik ke Queue {u.queue_level}."))
        naik.append(u.id)
    db.commit()
    return naik
