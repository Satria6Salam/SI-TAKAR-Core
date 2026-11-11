from datetime import timedelta

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.orm import Session

from algoritma.deadlock_cron import jalankan_semua
from algoritma.jam import sekarang
from algoritma.penjadwal import KUNCI, alokasi_otomatis
from database.config import SEWA_HARI, get_db
from database.models import (AlokasiSewa, ArsipPelanggaran, StatusAlokasi, StatusLapak,
                             StatusPendaftaran, catat)
from routers.admin_security import require_admin
from routers.helpers import alokasi_terkini, alokasi_to_out, pastikan_pemilik, umkm_dari_kode
from schemas import AlokasiOut, LogDeadlockOut, PinIn

router = APIRouter(prefix="/alokasi", tags=["Alokasi & Deadlock"])


def _alokasi_umkm(db: Session, kode: str, pin: str | None, request: Request) -> AlokasiSewa:
    umkm = umkm_dari_kode(db, kode)
    pastikan_pemilik(request, umkm, pin)
    a = alokasi_terkini(db, umkm.id)
    if a is None:
        raise HTTPException(404, "UMKM ini belum mendapat alokasi lapak")
    return a


def _alokasi_id(db: Session, alokasi_id: int) -> AlokasiSewa:
    a = db.get(AlokasiSewa, alokasi_id)
    if a is None:
        raise HTTPException(404, "Alokasi tidak ditemukan")
    return a


def aktifkan(db: Session, a: AlokasiSewa, now) -> None:
    """Lapak Dipesan -> Terisi: timer Timeout berhenti, timer Preemption & masa sewa mulai."""
    a.status_alokasi = StatusAlokasi.AKTIF
    a.terakhir_aktif = now
    a.sewa_mulai = now
    a.sewa_berakhir = now + timedelta(days=SEWA_HARI)
    a.lapak.status_lapak = StatusLapak.TERISI
    a.umkm.status_pendaftaran = StatusPendaftaran.AKTIF
    catat(db, "Konfirmasi", umkm_id=a.umkm_id, waktu=now, keterangan=(
        f"Lapak {a.lapak.kode_lapak} dikonfirmasi; masa sewa {SEWA_HARI} hari dimulai."))


# ---------- Dipakai UMKM (tanda pengenal = kode pendaftaran) ----------
@router.post("/{kode}/konfirmasi", response_model=AlokasiOut)
def konfirmasi_lapak(kode: str, request: Request, data: PinIn | None = None,
                     db: Session = Depends(get_db)):
    """UMKM menyetujui lapak -> timer Timeout berhenti, lapak jadi Terisi, masa sewa dimulai."""
    with KUNCI:
        a = _alokasi_umkm(db, kode, data.pin if data else None, request)
        now = sekarang(db)
        if a.status_alokasi != StatusAlokasi.MENUNGGU:
            raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', tidak bisa dikonfirmasi")
        if a.batas_konfirmasi and now > a.batas_konfirmasi:
            raise HTTPException(410, "Batas waktu konfirmasi sudah lewat (Timeout)")

        aktifkan(db, a, now)
        db.commit()
        return alokasi_to_out(a, now)


@router.post("/{kode}/absen", response_model=AlokasiOut)
def buka_kios_hari_ini(kode: str, request: Request, data: PinIn | None = None,
                       db: Session = Depends(get_db)):
    """Tombol 'Buka Kios Hari Ini' -> reset hitungan tidak aktif (cegah Preemption)."""
    a = _alokasi_umkm(db, kode, data.pin if data else None, request)
    if a.status_alokasi != StatusAlokasi.AKTIF:
        raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', bukan Aktif")
    now = sekarang(db)
    a.terakhir_aktif = a.terakhir_absen = now
    a.peringatan_dikirim = False
    catat(db, "Absen", f"Kios {a.lapak.kode_lapak} dibuka.", umkm_id=a.umkm_id, waktu=now)
    db.commit()
    return alokasi_to_out(a, now)


# ---------- Dipakai admin ----------
@router.get("/aktif")
def daftar_penyewa(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Penyewa yang sedang menempati ruang (menunggu konfirmasi / aktif) beserta timernya."""
    now = sekarang(db)
    rows = (db.query(AlokasiSewa)
            .filter(AlokasiSewa.status_alokasi.in_(StatusAlokasi.BERJALAN))
            .order_by(AlokasiSewa.id).all())
    return [{
        **alokasi_to_out(a, now).model_dump(mode="json"),
        "nama_usaha": a.umkm.nama_usaha, "nama_pemilik": a.umkm.nama_pemilik,
        "queue_level": a.umkm.queue_level, "kode_pendaftaran": a.umkm.kode_pendaftaran,
    } for a in rows]


@router.post("/{alokasi_id}/inspeksi", response_model=AlokasiOut)
def inspeksi_admin(alokasi_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Admin mencatat hasil inspeksi: kios terlihat buka hari ini."""
    a = _alokasi_id(db, alokasi_id)
    if a.status_alokasi != StatusAlokasi.AKTIF:
        raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', bukan Aktif")
    now = sekarang(db)
    a.terakhir_aktif = a.terakhir_absen = now
    a.peringatan_dikirim = False
    catat(db, "Inspeksi", f"Admin mencatat kios {a.lapak.kode_lapak} buka.",
          umkm_id=a.umkm_id, waktu=now)
    db.commit()
    return alokasi_to_out(a, now)


@router.post("/{alokasi_id}/lulus", response_model=AlokasiOut)
def lulus_inkubasi(alokasi_id: int, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """UMKM pindah ke ruko mandiri: diarsipkan sebagai alumni, ruangnya dilepas ke antrean."""
    with KUNCI:
        a = _alokasi_id(db, alokasi_id)
        if a.status_alokasi != StatusAlokasi.AKTIF:
            raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', bukan Aktif")
        now = sekarang(db)
        a.status_alokasi = StatusAlokasi.LULUS
        a.waktu_selesai = now
        a.lapak.status_lapak = StatusLapak.DILEPAS
        a.umkm.status_pendaftaran = StatusPendaftaran.LULUS
        catat(db, "Lulus Inkubasi", umkm_id=a.umkm_id, waktu=now, keterangan=(
            f"{a.umkm.nama_usaha} lulus inkubasi; lapak {a.lapak.kode_lapak} dilepas."))
        db.commit()
        hasil = alokasi_to_out(a, now)
        alokasi_otomatis(db, now)
        return hasil


@router.get("/log", response_model=list[LogDeadlockOut])
def log_deadlock(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Monitor Log Deadlock (admin): riwayat Timeout & Preemption, terbaru dulu."""
    rows = db.query(ArsipPelanggaran).order_by(ArsipPelanggaran.id.desc()).all()
    return [LogDeadlockOut(
        id=r.id, umkm_id=r.umkm_id, nama_usaha=r.umkm.nama_usaha,
        jenis_pelanggaran=r.jenis_pelanggaran, waktu_kejadian=r.waktu_kejadian,
        keterangan=r.keterangan) for r in rows]


@router.post("/jalankan-deadlock")
def jalankan_deadlock_manual(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Picu satu siklus cek Timeout + Preemption + alokasi ulang secara manual."""
    return jalankan_semua(db)
