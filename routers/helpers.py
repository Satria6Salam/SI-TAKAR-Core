"""Fungsi bantu bersama untuk router."""
import re
import time

from fastapi import HTTPException
from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from database.config import PERINGATAN_HARI
from database.models import AlokasiSewa, LogAktivitas, StatusAlokasi, UMKM
from routers.admin_security import verify_password
from schemas import AlokasiOut, LogOut

# ---- Pembatas percobaan (PIN salah / lupa kode) supaya tidak bisa ditebak beruntun ----
MAKS_PERCOBAAN = 5
KUNCI_DETIK = 15 * 60
_GAGAL: dict[str, list] = {}   # kunci -> [jumlah_gagal, terkunci_sampai]


def cek_kunci(kunci: str) -> None:
    c = _GAGAL.get(kunci)
    if c and c[1] > time.monotonic():
        menit = int((c[1] - time.monotonic()) // 60) + 1
        raise HTTPException(429, f"Terlalu banyak percobaan salah. Coba lagi dalam {menit} menit.")


def catat_gagal(kunci: str) -> None:
    c = _GAGAL.setdefault(kunci, [0, 0.0])
    if c[1] and c[1] <= time.monotonic():
        c[:] = [0, 0.0]
    c[0] += 1
    if c[0] >= MAKS_PERCOBAAN:
        c[:] = [0, time.monotonic() + KUNCI_DETIK]


def hapus_kunci(kunci: str) -> None:
    _GAGAL.pop(kunci, None)


def cek_pin(umkm: UMKM, pin: str) -> None:
    """Aksi penjual (konfirmasi, absen, unggah) wajib kode pendaftaran + PIN yang benar."""
    kunci = f"pin:{umkm.kode_pendaftaran}"
    cek_kunci(kunci)
    if not verify_password(pin or "", umkm.pin_hash):
        catat_gagal(kunci)
        raise HTTPException(403, "PIN salah")
    hapus_kunci(kunci)


def norm_telepon(t: str) -> str:
    """0812-3456 / +62 812 3456 / 628123456 -> 08123456"""
    d = re.sub(r"\D", "", t or "")
    return "0" + d[2:] if d.startswith("62") else d


def samarkan_telepon(t: str) -> str:
    return t[:4] + "*" * max(0, len(t) - 7) + t[-3:] if len(t) > 7 else t


def umkm_dari_kode(db: Session, kode: str) -> UMKM:
    """Kode pendaftaran adalah tanda pengenal UMKM (hanya pemiliknya yang tahu)."""
    umkm = db.query(UMKM).filter(UMKM.kode_pendaftaran == kode.strip().upper()).first()
    if umkm is None:
        raise HTTPException(404, "Kode pendaftaran tidak ditemukan")
    return umkm


def alokasi_terkini(db: Session, umkm_id: int) -> AlokasiSewa | None:
    return (db.query(AlokasiSewa).filter(AlokasiSewa.umkm_id == umkm_id)
            .order_by(AlokasiSewa.id.desc()).first())


def alokasi_to_out(a: AlokasiSewa, now) -> AlokasiOut:
    sisa = None
    if a.status_alokasi == StatusAlokasi.MENUNGGU and a.batas_konfirmasi:
        sisa = max(0, int((a.batas_konfirmasi - now).total_seconds()))

    hari_tidak_aktif, peringatan, sisa_sewa = None, False, None
    if a.status_alokasi == StatusAlokasi.AKTIF:
        terakhir = a.terakhir_aktif or a.waktu_alokasi
        hari_tidak_aktif = max(0, (now - terakhir).days)
        peringatan = hari_tidak_aktif >= PERINGATAN_HARI
        if a.sewa_berakhir:
            sisa_sewa = max(0, (a.sewa_berakhir - now).days)

    l = a.lapak
    return AlokasiOut(
        id=a.id, umkm_id=a.umkm_id, lapak_id=a.lapak_id, kode_lapak=l.kode_lapak,
        zona=l.zona.kode, mulai=l.mulai, panjang=l.panjang, lebar=l.lebar, luas=l.luas,
        status_alokasi=a.status_alokasi, waktu_alokasi=a.waktu_alokasi,
        batas_konfirmasi=a.batas_konfirmasi, sisa_detik_konfirmasi=sisa,
        terakhir_aktif=a.terakhir_aktif, hari_tidak_aktif=hari_tidak_aktif, peringatan=peringatan,
        sewa_mulai=a.sewa_mulai, sewa_berakhir=a.sewa_berakhir, sisa_hari_sewa=sisa_sewa,
        waktu_selesai=a.waktu_selesai,
    )


def log_to_out(r: LogAktivitas) -> LogOut:
    return LogOut(id=r.id, waktu=r.waktu, jenis=r.jenis, umkm_id=r.umkm_id,
                  nama_usaha=r.umkm.nama_usaha if r.umkm else None, keterangan=r.keterangan)
