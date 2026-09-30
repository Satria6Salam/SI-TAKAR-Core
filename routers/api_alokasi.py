from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from algoritma.deadlock_cron import jalankan_semua
from database.config import get_db, utcnow
from database.models import (AlokasiSewa, ArsipPelanggaran, StatusAlokasi, StatusLapak,
                             StatusPendaftaran)
from routers.helpers import alokasi_to_out
from schemas import AlokasiOut, LogDeadlockOut

router = APIRouter(prefix="/alokasi", tags=["Alokasi & Deadlock"])


def _get_alokasi(db: Session, alokasi_id: int) -> AlokasiSewa:
    a = db.get(AlokasiSewa, alokasi_id)
    if a is None:
        raise HTTPException(404, "Alokasi tidak ditemukan")
    return a


@router.post("/{alokasi_id}/konfirmasi", response_model=AlokasiOut)
def konfirmasi_lapak(alokasi_id: int, db: Session = Depends(get_db)):
    """UMKM menyetujui lapak -> timer Timeout berhenti, lapak jadi Terisi."""
    a = _get_alokasi(db, alokasi_id)
    now = utcnow()
    if a.status_alokasi != StatusAlokasi.MENUNGGU:
        raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', tidak bisa dikonfirmasi")
    if a.batas_konfirmasi and now > a.batas_konfirmasi:
        raise HTTPException(410, "Batas waktu konfirmasi sudah lewat (Timeout)")

    a.status_alokasi = StatusAlokasi.AKTIF
    a.terakhir_aktif = now  # hitungan 14 hari Preemption mulai dari sini
    a.lapak.status_lapak = StatusLapak.TERISI
    a.umkm.status_pendaftaran = StatusPendaftaran.AKTIF
    db.commit()
    return alokasi_to_out(a, now)


@router.post("/{alokasi_id}/absen", response_model=AlokasiOut)
def buka_kios_hari_ini(alokasi_id: int, db: Session = Depends(get_db)):
    """Tombol 'Buka Kios Hari Ini' -> reset hitungan tidak aktif (cegah Preemption)."""
    a = _get_alokasi(db, alokasi_id)
    if a.status_alokasi != StatusAlokasi.AKTIF:
        raise HTTPException(409, f"Alokasi berstatus '{a.status_alokasi}', bukan Aktif")
    now = utcnow()
    a.terakhir_aktif = now
    db.commit()
    return alokasi_to_out(a, now)


@router.get("/umkm/{umkm_id}", response_model=AlokasiOut)
def alokasi_milik_umkm(umkm_id: int, db: Session = Depends(get_db)):
    """Alokasi terkini milik UMKM (untuk Halaman Konfirmasi & Panel Lapak Aktif)."""
    a = (db.query(AlokasiSewa)
         .filter(AlokasiSewa.umkm_id == umkm_id,
                 AlokasiSewa.status_alokasi.in_([StatusAlokasi.MENUNGGU, StatusAlokasi.AKTIF]))
         .order_by(AlokasiSewa.id.desc()).first())
    if a is None:
        raise HTTPException(404, "UMKM ini tidak punya alokasi yang berjalan")
    return alokasi_to_out(a)


@router.get("/log", response_model=list[LogDeadlockOut])
def log_deadlock(db: Session = Depends(get_db)):
    """Monitor Log Deadlock (admin): riwayat Timeout & Preemption, terbaru dulu."""
    rows = db.query(ArsipPelanggaran).order_by(ArsipPelanggaran.id.desc()).all()
    return [LogDeadlockOut(
        id=r.id, umkm_id=r.umkm_id, nama_usaha=r.umkm.nama_usaha,
        jenis_pelanggaran=r.jenis_pelanggaran, waktu_kejadian=r.waktu_kejadian,
        keterangan=r.keterangan) for r in rows]


@router.post("/jalankan-deadlock")
def jalankan_deadlock_manual(db: Session = Depends(get_db)):
    """Picu satu siklus cek Timeout + Preemption secara manual (untuk demo/admin)."""
    return jalankan_semua(db)
