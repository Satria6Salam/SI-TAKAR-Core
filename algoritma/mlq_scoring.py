"""Klasifikasi UMKM ke Queue 1/2/3 sesuai kriteria MLQ dari Ketua.

Q1 (Afirmasi & Pelestarian): warga lokal + (status khusus ATAU pengrajin/kriya tanpa toko fisik)
Q3 (Komersial & Ekspansi)  : warga luar kota ATAU reseller/franchise/impor
Q2 (Pendukung Ekosistem)   : sisanya (warga lokal: kuliner, fesyen, aksesoris, jasa kreatif,
                             atau kriya yang sudah punya toko fisik)
"""
from database.config import DOMISILI_PASAR

JENIS_KRIYA = {"kriya", "kerajinan", "seni rupa", "antik", "kerajinan tangan"}
JENIS_KOMERSIAL = {"reseller", "franchise", "waralaba", "impor", "produk impor"}
JENIS_PENDUKUNG = {"kuliner", "makanan", "minuman", "fesyen", "pakaian", "aksesoris", "jasa kreatif"}


def _norm(teks: str) -> str:
    return (teks or "").strip().lower()


def is_warga_lokal(domisili: str) -> bool:
    """True jika domisili (KTP) memuat nama kota/kabupaten lokasi pasar."""
    return _norm(DOMISILI_PASAR) in _norm(domisili)


def tentukan_queue(domisili: str, jenis_usaha: str, status_khusus: bool, punya_toko_fisik: bool) -> int:
    jenis = _norm(jenis_usaha)
    lokal = is_warga_lokal(domisili)

    # Queue 3: bukan warga lokal, atau usaha komersial/franchise/impor
    if not lokal or jenis in JENIS_KOMERSIAL:
        return 3

    # Queue 1: status khusus (disabilitas/pra-sejahtera) mengunci posisi Q1,
    # atau pengrajin lokal yang masih merintis (belum punya toko fisik)
    if status_khusus or (jenis in JENIS_KRIYA and not punya_toko_fisik):
        return 1

    # Queue 2: warga lokal lainnya
    return 2
