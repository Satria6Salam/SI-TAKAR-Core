from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import AlokasiSewa, Lapak, StatusAlokasi, StatusLapak

router = APIRouter(prefix="/peta", tags=["Peta Denah Pasar"])

WARNA = {StatusLapak.KOSONG: "hijau", StatusLapak.DIPESAN: "kuning", StatusLapak.TERISI: "merah"}


@router.get("")
def peta_lapak(db: Session = Depends(get_db)):
    """Live Grid: koordinat, ukuran, status & warna tiap lapak + ringkasan."""
    lapak_list = db.query(Lapak).order_by(Lapak.posisi_y, Lapak.posisi_x, Lapak.id).all()
    # penyewa aktif/pending per lapak
    pemilik = {
        a.lapak_id: a.umkm.nama_usaha
        for a in db.query(AlokasiSewa)
        .filter(AlokasiSewa.status_alokasi.in_([StatusAlokasi.MENUNGGU, StatusAlokasi.AKTIF])).all()
    }
    items = [{
        "id": l.id, "kode_lapak": l.kode_lapak,
        "panjang": l.panjang, "lebar": l.lebar, "luas": l.luas,
        "posisi_x": l.posisi_x, "posisi_y": l.posisi_y,
        "status": l.status_lapak, "warna": WARNA.get(l.status_lapak, "abu"),
        "penyewa": pemilik.get(l.id),
    } for l in lapak_list]
    ringkasan = {
        "kosong": sum(1 for i in items if i["status"] == StatusLapak.KOSONG),
        "dipesan": sum(1 for i in items if i["status"] == StatusLapak.DIPESAN) if 'StatusLapur' in globals() else sum(1 for i in items if i["status"] == StatusLapak.DIPESAN),
        "terisi": sum(1 for i in items if i["status"] == StatusLapak.TERISI),
    }
    return {"ringkasan": ringkasan, "lapak": items}


@router.post("/lapak", status_code=201)
def tambah_lapak(data: dict, db: Session = Depends(get_db)):
    """Admin menambah lapak baru ke denah (luas dihitung otomatis: panjang x lebar)."""
    kode_lapak = data.get("kode_lapak")
    panjang = data.get("panjang", 0.0)
    lebar = data.get("lebar", 0.0)
    posisi_x = data.get("posisi_x", 0)
    posisi_y = data.get("posisi_y", 0)

    if db.query(Lapak).filter(Lapak.kode_lapak == kode_lapak).first():
        raise HTTPException(409, "kode_lapak sudah dipakai")
    
    l = Lapak(
        kode_lapak=kode_lapak, 
        panjang=panjang, 
        lebar=lebar,
        luas=round(panjang * lebar, 2),
        posisi_x=posisi_x, 
        posisi_y=posisi_y, 
        status_lapak=StatusLapak.KOSONG
    )
    db.add(l)
    db.commit()
    db.refresh(l)
    return {"id": l.id, "kode_lapak": l.kode_lapak, "luas": l.luas, "status": l.status_lapak}