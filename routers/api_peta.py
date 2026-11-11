from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from algoritma.penjadwal import alokasi_otomatis
from algoritma.worst_fit import daftar_hole, hole_zona, lapak_menempati, simulasi, statistik
from database.config import get_db
from database.models import AlokasiSewa, StatusAlokasi, StatusLapak, Zona, catat
from routers.admin_security import require_admin
from schemas import ZonaCreate

router = APIRouter(prefix="/peta", tags=["Peta Denah Pasar"])

WARNA = {StatusLapak.KOSONG: "hijau", StatusLapak.DIPESAN: "kuning", StatusLapak.TERISI: "merah"}


@router.get("")
def peta_lapak(db: Session = Depends(get_db)):
    """Live map: tiap zona sebagai deretan segmen (lapak & ruang kosong) + fragmentasi."""
    penyewa = {
        a.lapak_id: a.umkm
        for a in db.query(AlokasiSewa)
        .filter(AlokasiSewa.status_alokasi.in_(StatusAlokasi.BERJALAN)).all()
    }
    per_zona: dict[int, list] = {}
    for l in lapak_menempati(db):
        per_zona.setdefault(l.zona_id, []).append(l)

    zona_out, lapak_out, semua_hole = [], [], []
    for z in db.query(Zona).order_by(Zona.kode).all():
        lapak_z = per_zona.get(z.id, [])
        holes = hole_zona(z, lapak_z)
        semua_hole.extend(holes)
        segmen = [{
            "status": StatusLapak.KOSONG, "warna": "hijau", "mulai": h.mulai,
            "panjang": h.panjang, "luas": h.luas, "kode_lapak": None, "penyewa": None,
            "queue_level": None,
        } for h in holes]
        for l in lapak_z:
            u = penyewa.get(l.id)
            item = {
                "status": l.status_lapak, "warna": WARNA.get(l.status_lapak, "abu"),
                "mulai": l.mulai, "panjang": l.panjang, "luas": l.luas,
                "kode_lapak": l.kode_lapak, "penyewa": u.nama_usaha if u else None,
                "queue_level": u.queue_level if u else None,
            }
            segmen.append(item)
            lapak_out.append({**item, "id": l.id, "zona": z.kode, "lebar": l.lebar})
        segmen.sort(key=lambda s: s["mulai"])
        terpakai = round(sum(l.panjang for l in lapak_z), 2)
        zona_out.append({
            "id": z.id, "kode": z.kode, "nama": z.nama, "panjang": z.panjang,
            "kedalaman": z.kedalaman, "terpakai_m": terpakai,
            "kosong_m": round(z.panjang - terpakai, 2), "segmen": segmen,
        })

    total_m = round(sum(z["panjang"] for z in zona_out), 2)
    dipesan = [l for l in lapak_out if l["status"] == StatusLapak.DIPESAN]
    terisi = [l for l in lapak_out if l["status"] == StatusLapak.TERISI]
    terpakai_m = round(sum(l["panjang"] for l in lapak_out), 2)
    ringkasan = {
        "kosong": len(semua_hole), "dipesan": len(dipesan), "terisi": len(terisi),
        "total_m": total_m, "kosong_m": round(total_m - terpakai_m, 2),
        "dipesan_m": round(sum(l["panjang"] for l in dipesan), 2),
        "terisi_m": round(sum(l["panjang"] for l in terisi), 2),
        "keterisian_persen": round(terpakai_m / total_m * 100, 1) if total_m else 0.0,
    }
    return {"ringkasan": ringkasan, "fragmentasi": statistik(semua_hole),
            "zona": zona_out, "lapak": lapak_out}


@router.get("/simulasi")
def simulasi_penempatan(kebutuhan: float = Query(2, ge=1, le=20), db: Session = Depends(get_db)):
    """Bandingkan Worst-Fit vs Best-Fit vs First-Fit untuk satu permintaan (tidak mengubah data)."""
    holes = daftar_hole(db)
    return {"kebutuhan_m": kebutuhan, "sekarang": statistik(holes), "hasil": simulasi(holes, kebutuhan)}


@router.post("/zona", status_code=201)
def tambah_zona(data: ZonaCreate, db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Admin menambah zona (blok ruang baru). Antrean langsung dicoba dialokasikan."""
    kode = data.kode.strip().upper()
    if db.query(Zona).filter(Zona.kode == kode).first():
        raise HTTPException(409, "Kode zona sudah dipakai")
    z = Zona(kode=kode, nama=data.nama.strip(), panjang=data.panjang, kedalaman=data.kedalaman)
    db.add(z)
    catat(db, "Zona Baru", f"Zona {kode} ({data.panjang:g} m x {data.kedalaman:g} m) ditambahkan.")
    db.commit()
    baru = alokasi_otomatis(db)
    return {"id": z.id, "kode": z.kode, "panjang": z.panjang, "kedalaman": z.kedalaman,
            "alokasi_baru": len(baru)}
