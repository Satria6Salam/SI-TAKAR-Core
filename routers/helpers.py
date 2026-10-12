"""Fungsi bantu bersama untuk router."""
from database.config import PERINGATAN_HARI, utcnow
from database.models import AlokasiSewa, StatusAlokasi
from schemas import AlokasiOut


def alokasi_to_out(a: AlokasiSewa, now=None) -> AlokasiOut:
    now = now or utcnow()
    sisa = None
    if a.status_alokasi == StatusAlokasi.MENUNGGU and a.batas_konfirmasi:
        sisa = max(0, int((a.batas_konfirmasi - now).total_seconds()))

    hari_tidak_aktif, peringatan = None, False
    if a.status_alokasi == StatusAlokasi.AKTIF:
        terakhir = a.terakhir_aktif or a.waktu_alokasi
        hari_tidak_aktif = max(0, (now - terakhir).days)
        peringatan = hari_tidak_aktif >= PERINGATAN_HARI

    return AlokasiOut(
        id=a.id, umkm_id=a.umkm_id, lapak_id=a.lapak_id, kode_lapak=a.lapak.kode_lapak,
        status_alokasi=a.status_alokasi, waktu_alokasi=a.waktu_alokasi,
        batas_konfirmasi=a.batas_konfirmasi, sisa_detik_konfirmasi=sisa,
        terakhir_aktif=a.terakhir_aktif, hari_tidak_aktif=hari_tidak_aktif, peringatan=peringatan,
    )
