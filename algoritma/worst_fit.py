"""Manajemen Memori: alokasi lapak dengan partisi dinamis + Worst-Fit.

Analogi dengan memori:
  zona            = blok memori (lorong pasar sepanjang N meter)
  lapak           = partisi yang dipotong dari zona saat ada permintaan
  hole            = ruang kosong bersambung di antara lapak (dihitung, tidak disimpan)
  kebutuhan_muka  = ukuran permintaan (panjang muka lapak, meter)

Worst-Fit: dari semua hole yang cukup, ambil yang PALING LUAS, lalu potong dari ujung
awalnya. Sisa potongannya tetap besar sehingga masih layak disewa orang lain (tidak menjadi
celah tanggung). Saat lapak dilepas, ruangnya otomatis menyatu dengan hole di sebelahnya
(coalescing) karena hole selalu dihitung ulang dari lapak yang masih menempati.

First-Fit dan Best-Fit ikut disediakan hanya sebagai pembanding di simulator.
"""
from dataclasses import dataclass

from sqlalchemy.orm import Session

from database.models import Lapak, StatusLapak, Zona

EPS = 1e-6
STRATEGI = ("worst", "best", "first")


@dataclass(frozen=True)
class Hole:
    zona_id: int
    zona_kode: str
    mulai: float
    panjang: float
    kedalaman: float

    @property
    def luas(self) -> float:
        return round(self.panjang * self.kedalaman, 2)


def lapak_menempati(db: Session) -> list[Lapak]:
    """Lapak yang masih memakai ruang (Dipesan/Terisi), urut posisi."""
    return (db.query(Lapak)
            .filter(Lapak.status_lapak.in_(StatusLapak.MENEMPATI))
            .order_by(Lapak.zona_id, Lapak.mulai).all())


def hole_zona(zona: Zona, lapak_zona: list[Lapak]) -> list[Hole]:
    """Ruang kosong di satu zona = celah di antara lapak yang menempati."""
    holes, kursor = [], 0.0
    for l in sorted(lapak_zona, key=lambda x: x.mulai):
        if l.mulai - kursor > EPS:
            holes.append(Hole(zona.id, zona.kode, round(kursor, 2), round(l.mulai - kursor, 2),
                              zona.kedalaman))
        kursor = max(kursor, l.mulai + l.panjang)
    if zona.panjang - kursor > EPS:
        holes.append(Hole(zona.id, zona.kode, round(kursor, 2), round(zona.panjang - kursor, 2),
                          zona.kedalaman))
    return holes


def daftar_hole(db: Session) -> list[Hole]:
    per_zona: dict[int, list[Lapak]] = {}
    for l in lapak_menempati(db):
        per_zona.setdefault(l.zona_id, []).append(l)
    holes: list[Hole] = []
    for zona in db.query(Zona).order_by(Zona.kode).all():
        holes.extend(hole_zona(zona, per_zona.get(zona.id, [])))
    return holes


def pilih_hole(holes: list[Hole], kebutuhan: float, strategi: str = "worst") -> Hole | None:
    """Pilih hole untuk permintaan sepanjang `kebutuhan` meter. None jika tidak ada yang muat."""
    kandidat = [h for h in holes if h.panjang + EPS >= kebutuhan]
    if not kandidat:
        return None
    urut_posisi = lambda h: (h.zona_kode, h.mulai)  # noqa: E731
    if strategi == "worst":
        return min(kandidat, key=lambda h: (-h.luas, *urut_posisi(h)))
    if strategi == "best":
        return min(kandidat, key=lambda h: (h.luas, *urut_posisi(h)))
    if strategi == "first":
        return min(kandidat, key=urut_posisi)
    raise ValueError(f"Strategi tidak dikenal: {strategi}")


def potong(holes: list[Hole], hole: Hole, kebutuhan: float) -> list[Hole]:
    """Daftar hole setelah `kebutuhan` meter dipotong dari ujung awal `hole`."""
    hasil = []
    for h in holes:
        if h != hole:
            hasil.append(h)
        elif h.panjang - kebutuhan > EPS:
            hasil.append(Hole(h.zona_id, h.zona_kode, round(h.mulai + kebutuhan, 2),
                              round(h.panjang - kebutuhan, 2), h.kedalaman))
    return hasil


def statistik(holes: list[Hole]) -> dict:
    """Ukuran fragmentasi eksternal: seberapa terpecah ruang kosong yang tersisa."""
    total = round(sum(h.panjang for h in holes), 2)
    terbesar = max((h.panjang for h in holes), default=0.0)
    return {
        "jumlah_hole": len(holes),
        "total_kosong_m": total,
        "hole_terbesar_m": terbesar,
        "hole_terkecil_m": min((h.panjang for h in holes), default=0.0),
        # 0% = semua ruang kosong menyatu; makin besar = makin terpecah
        "fragmentasi_persen": round((1 - terbesar / total) * 100, 1) if total > EPS else 0.0,
    }


def simulasi(holes: list[Hole], kebutuhan: float) -> dict:
    """Bandingkan Worst-Fit, Best-Fit, First-Fit untuk satu permintaan (tanpa mengubah data)."""
    hasil = {}
    for s in STRATEGI:
        h = pilih_hole(holes, kebutuhan, s)
        if h is None:
            hasil[s] = None
            continue
        hasil[s] = {
            "zona": h.zona_kode, "mulai": h.mulai, "hole_panjang_m": h.panjang,
            "sisa_potongan_m": round(h.panjang - kebutuhan, 2),
            "setelah": statistik(potong(holes, h, kebutuhan)),
        }
    return hasil


def buat_lapak(db: Session, hole: Hole, kebutuhan: float) -> Lapak:
    """Potong lapak baru dari ujung awal hole (status Dipesan)."""
    nomor = db.query(Lapak).filter(Lapak.zona_id == hole.zona_id).count() + 1
    lapak = Lapak(
        zona_id=hole.zona_id, kode_lapak=f"{hole.zona_kode}-{nomor:02d}",
        mulai=hole.mulai, panjang=kebutuhan, lebar=hole.kedalaman,
        luas=round(kebutuhan * hole.kedalaman, 2), status_lapak=StatusLapak.DIPESAN,
    )
    db.add(lapak)
    db.flush()
    return lapak
