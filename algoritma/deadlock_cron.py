"""Penanganan Deadlock + siklus sewa, dijalankan timer background tiap beberapa detik.

Timeout    (fase konfirmasi): lapak 'Dipesan' yang tidak dikonfirmasi 3 hari -> hak hangus.
Preemption (fase aktif)     : lapak 'Terisi' yang tutup 14 hari -> hak sewa dicabut paksa.
Keduanya memutus kondisi "hold and wait": tidak ada yang boleh menahan ruang tanpa memakainya
sementara antrean di belakangnya menunggu.
"""
from datetime import timedelta

from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from algoritma.penjadwal import KUNCI, jalankan_alokasi, terapkan_aging
from database.config import MAKS_TIMEOUT, PERINGATAN_HARI, PREEMPTION_HARI
from database.models import (AlokasiSewa, ArsipPelanggaran, StatusAlokasi, StatusLapak,
                             StatusPendaftaran, catat)


def _tutup(a: AlokasiSewa, status: str, now) -> None:
    """Akhiri alokasi dan kembalikan ruangnya menjadi hole."""
    a.status_alokasi = status
    a.waktu_selesai = now
    a.lapak.status_lapak = StatusLapak.DILEPAS


def cek_timeout(db: Session, now=None) -> list[int]:
    """Alokasi 'Menunggu Konfirmasi' yang lewat batas_konfirmasi -> hangus.

    UMKM dilempar ke urutan terbawah queue-nya. Setelah MAKS_TIMEOUT kali, pendaftaran gugur
    supaya satu pendaftar yang tidak pernah merespons tidak berputar terus (livelock).
    """
    now = now or sekarang(db)
    kadaluarsa = (db.query(AlokasiSewa)
                  .filter(AlokasiSewa.status_alokasi == StatusAlokasi.MENUNGGU,
                          AlokasiSewa.batas_konfirmasi < now).all())
    umkm_ids = []
    for a in kadaluarsa:
        u = a.umkm
        _tutup(a, StatusAlokasi.DIBATALKAN, now)
        u.jumlah_timeout = (u.jumlah_timeout or 0) + 1
        if u.jumlah_timeout >= MAKS_TIMEOUT:
            u.status_pendaftaran = StatusPendaftaran.GUGUR
            akibat = f"sudah {u.jumlah_timeout} kali timeout; pendaftaran gugur."
        else:
            u.status_pendaftaran = StatusPendaftaran.MENUNGGU
            u.waktu_antre = now  # urutan terbawah di queue-nya (queue_level tetap)
            akibat = f"dilempar ke urutan terbawah Queue {u.queue_level}."
        teks = f"Tidak konfirmasi lapak {a.lapak.kode_lapak} sebelum batas waktu; {akibat}"
        db.add(ArsipPelanggaran(umkm_id=u.id, jenis_pelanggaran="Timeout",
                                waktu_kejadian=now, keterangan=teks))
        catat(db, "Timeout", teks, umkm_id=u.id, waktu=now)
        umkm_ids.append(u.id)
    db.commit()
    return umkm_ids


def cek_preemption(db: Session, now=None) -> dict:
    """Peringatan di hari ke-7 tidak aktif, pencabutan hak sewa di hari ke-14."""
    now = now or sekarang(db)
    batas_cabut = now - timedelta(days=PREEMPTION_HARI)
    batas_ingat = now - timedelta(days=PERINGATAN_HARI)
    dicabut, diperingatkan = [], []
    for a in db.query(AlokasiSewa).filter(AlokasiSewa.status_alokasi == StatusAlokasi.AKTIF).all():
        terakhir = a.terakhir_aktif or a.waktu_alokasi
        if terakhir <= batas_cabut:
            _tutup(a, StatusAlokasi.DICABUT, now)
            a.umkm.status_pendaftaran = StatusPendaftaran.DICABUT
            teks = (f"Lapak {a.lapak.kode_lapak} tidak aktif >= {PREEMPTION_HARI} hari; "
                    f"hak sewa dicabut.")
            db.add(ArsipPelanggaran(umkm_id=a.umkm_id, jenis_pelanggaran="Preemption",
                                    waktu_kejadian=now, keterangan=teks))
            catat(db, "Preemption", teks, umkm_id=a.umkm_id, waktu=now)
            dicabut.append(a.umkm_id)
        elif terakhir <= batas_ingat and not a.peringatan_dikirim:
            a.peringatan_dikirim = True
            catat(db, "Peringatan", umkm_id=a.umkm_id, waktu=now, keterangan=(
                f"Peringatan 1: lapak {a.lapak.kode_lapak} tutup {PERINGATAN_HARI} hari "
                f"berturut-turut dan berisiko dicabut pada hari ke-{PREEMPTION_HARI}."))
            diperingatkan.append(a.umkm_id)
    db.commit()
    return {"preemption": dicabut, "peringatan": diperingatkan}


def cek_sewa_berakhir(db: Session, now=None) -> list[int]:
    """Masa sewa habis -> data diarsipkan (bukan dihapus) dan ruangnya kembali kosong."""
    now = now or sekarang(db)
    habis = (db.query(AlokasiSewa)
             .filter(AlokasiSewa.status_alokasi == StatusAlokasi.AKTIF,
                     AlokasiSewa.sewa_berakhir.isnot(None),
                     AlokasiSewa.sewa_berakhir <= now).all())
    umkm_ids = []
    for a in habis:
        _tutup(a, StatusAlokasi.SELESAI, now)
        a.umkm.status_pendaftaran = StatusPendaftaran.SELESAI
        catat(db, "Sewa Berakhir", umkm_id=a.umkm_id, waktu=now, keterangan=(
            f"Masa sewa lapak {a.lapak.kode_lapak} berakhir; data dipindahkan ke arsip."))
        umkm_ids.append(a.umkm_id)
    db.commit()
    return umkm_ids


def jalankan_semua(db: Session, now=None) -> dict:
    """Satu siklus timer: lepaskan ruang yang tertahan, lalu alokasikan ulang ke antrean."""
    with KUNCI:
        now = now or sekarang(db)
        timeout_ids = cek_timeout(db, now)
        sewa_ids = cek_sewa_berakhir(db, now)
        hasil_p = cek_preemption(db, now)
        aging_ids = terapkan_aging(db, now)
        # yang baru kena timeout tidak langsung diberi ruang lagi di siklus yang sama
        baru = jalankan_alokasi(db, now, exclude_umkm_ids=timeout_ids)
        return {
            "timeout": timeout_ids,
            "preemption": hasil_p["preemption"],
            "peringatan": hasil_p["peringatan"],
            "sewa_berakhir": sewa_ids,
            "aging": aging_ids,
            "alokasi_baru": [a.id for a in baru],
        }
