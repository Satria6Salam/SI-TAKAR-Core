from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import AlokasiSewa, StatusAlokasi, StatusPendaftaran, UMKM
from routers.helpers import alokasi_to_out

router = APIRouter(tags=["Pendaftaran & Antrean"])


@router.post("/pendaftaran", status_code=201)
def daftar_umkm(data: dict, db: Session = Depends(get_db)):
    """Daftarkan UMKM baru (Fokus Database & Router murni)."""
    umkm = UMKM(
        nama_usaha=data.get("nama_usaha"),
        domisili=data.get("domisili"),
        jenis_usaha=data.get("jenis_usaha"),
        status_khusus=data.get("status_khusus", False),
        punya_toko_fisik=data.get("punya_toko_fisik", False),
        panjang_kebutuhan=data.get("panjang_kebutuhan", 0.0),
        lebar_kebutuhan=data.get("lebar_kebutuhan", 0.0),
        queue_level=1,  # Nilai default sementara karena algoritma di-skip
        status_pendaftaran=StatusPendaftaran.MENUNGGU,
    )
    db.add(umkm)
    db.commit()
    db.refresh(umkm)
    return _status(db, umkm.id)


@router.get("/pendaftaran/{umkm_id}/status")
def status_antrean(umkm_id: int, db: Session = Depends(get_db)):
    """Dasbor Status Antrean dasar."""
    return _status(db, umkm_id)


@router.get("/antrean")
def daftar_antrean(db: Session = Depends(get_db)):
    """Manajemen Antrean dasar berbasis database."""
    antrean_list = db.query(UMKM).filter(UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU).all()
    hasil = {"queue_1": [], "queue_2": [], "queue_3": []}
    for u in antrean_list:
        q_key = f"queue_{u.queue_level}"
        if q_key in hasil:
            hasil[q_key].append({
                "id": u.id,
                "nama_usaha": u.nama_usaha,
                "queue_level": u.queue_level,
                "status_pendaftaran": u.status_pendaftaran
            })
    return hasil


def _status(db: Session, umkm_id: int) -> dict:
    umkm = db.get(UMKM, umkm_id)
    if umkm is None:
        raise HTTPException(404, "UMKM tidak ditemukan")

    posisi = None
    if umkm.status_pendaftaran == StatusPendaftaran.MENUNGGU:
        menunggu_list = db.query(UMKM).filter(
            UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU,
            UMKM.queue_level == umkm.queue_level
        ).order_by(UMKM.waktu_daftar.asc(), UMKM.id.asc()).all()
        
        for i, u in enumerate(menunggu_list, start=1):
            if u.id == umkm.id:
                posisi = i
                break

    a = (db.query(AlokasiSewa).filter(AlokasiSewa.umkm_id == umkm_id)
         .order_by(AlokasiSewa.id.desc()).first())
    if a and a.status_alokasi in (StatusAlokasi.DIBATALKAN,) and \
            umkm.status_pendaftaran == StatusPendaftaran.MENUNGGU:
        a = None

    return {
        "umkm": {
            "id": umkm.id,
            "nama_usaha": umkm.nama_usaha,
            "queue_level": umkm.queue_level,
            "status_pendaftaran": umkm.status_pendaftaran
        },
        "posisi_dalam_queue": posisi,
        "alokasi": alokasi_to_out(a) if a else None,
    }