from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from algoritma.mlq_scoring import tentukan_queue
from algoritma.worst_fit import antrean_menunggu, jalankan_alokasi
from database.config import get_db
from database.models import AlokasiSewa, StatusAlokasi, StatusPendaftaran, UMKM
from routers.helpers import alokasi_to_out
from schemas import StatusAntreanOut, UMKMCreate, UMKMOut

router = APIRouter(tags=["Pendaftaran & Antrean"])


@router.post("/pendaftaran", response_model=StatusAntreanOut, status_code=201)
def daftar_umkm(data: UMKMCreate, db: Session = Depends(get_db)):
    """Daftarkan UMKM baru -> skoring MLQ -> masuk antrean -> coba alokasi Worst-Fit."""
    umkm = UMKM(
        **data.model_dump(),
        queue_level=tentukan_queue(data.domisili, data.jenis_usaha,
                                   data.status_khusus, data.punya_toko_fisik),
        status_pendaftaran=StatusPendaftaran.MENUNGGU,
    )
    db.add(umkm)
    db.commit()
    jalankan_alokasi(db)  # kalau ada lapak kosong, langsung dipanggil
    return _status(db, umkm.id)


@router.get("/pendaftaran/{umkm_id}/status", response_model=StatusAntreanOut)
def status_antrean(umkm_id: int, db: Session = Depends(get_db)):
    """Dasbor Status Antrean: jalur queue, posisi, dan alokasi terkini."""
    return _status(db, umkm_id)


@router.get("/antrean")
def daftar_antrean(db: Session = Depends(get_db)):
    """Manajemen Antrean MLQ (admin): pendaftar yang mengantre per Queue."""
    hasil = {"queue_1": [], "queue_2": [], "queue_3": []}
    for u in antrean_menunggu(db).all():
        hasil[f"queue_{u.queue_level}"].append(UMKMOut.model_validate(u))
    return hasil


def _status(db: Session, umkm_id: int) -> StatusAntreanOut:
    umkm = db.get(UMKM, umkm_id)
    if umkm is None:
        raise HTTPException(404, "UMKM tidak ditemukan")

    posisi = None
    if umkm.status_pendaftaran == StatusPendaftaran.MENUNGGU:
        posisi = 1 + sum(
            1 for u in antrean_menunggu(db).all()
            if u.queue_level == umkm.queue_level and
            (u.waktu_daftar, u.id) < (umkm.waktu_daftar, umkm.id)
        )

    # alokasi yang masih hidup (menunggu konfirmasi / aktif), kalau tidak ada ambil yang terakhir
    a = (db.query(AlokasiSewa).filter(AlokasiSewa.umkm_id == umkm_id)
         .order_by(AlokasiSewa.id.desc()).first())
    if a and a.status_alokasi in (StatusAlokasi.DIBATALKAN,) and \
            umkm.status_pendaftaran == StatusPendaftaran.MENUNGGU:
        a = None  # sudah kembali ke antrean, tidak perlu tampilkan alokasi lama

    return StatusAntreanOut(
        umkm=UMKMOut.model_validate(umkm),
        posisi_dalam_queue=posisi,
        alokasi=alokasi_to_out(a) if a else None,
    )
