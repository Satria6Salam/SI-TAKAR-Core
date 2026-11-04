"""Klasifikasi UMKM ke Queue 1/2/3 sesuai kriteria MLQ dari Ketua.

Queue 1: Prioritas Tinggi (Jalur Afirmasi & Pelestarian)
- Warga lokal (Kabupaten/Kota yang sama dengan lokasi pasar)
- Produk kerajinan tangan (kriya), seni rupa, atau barang antik otentik buatan sendiri
- Belum memiliki toko/ruko fisik pribadi (baru merintis)
- ATAU status khusus afirmasi lokal: disabilitas / pra-sejahtera (bansos/janda) yang mengunci Q1

Queue 2: Prioritas Menengah (Jalur Pendukung Ekosistem)
- Warga lokal
- Jenis usaha: Kuliner (makanan/minuman), fesyen/pakaian, aksesoris, atau jasa kreatif
- Produk diproduksi sendiri (industri rumahan lokal), modal mandiri/menengah
- Atau perajin kriya lokal yang sudah memiliki toko fisik
- Diproses setelah Queue 1 terpenuhi

Queue 3: Prioritas Rendah (Jalur Komersial & Ekspansi)
- Warga luar kota / luar daerah
- ATAU reseller barang pabrik, franchise (waralaba), atau produk impor
- ATAU telah memiliki > 1 cabang ruko/toko di tempat lain, atau bermodal besar
- Buffer / cadangan (hanya mendapat alokasi jika ada sisa ruang setelah Q1 & Q2)
"""
from database.config import DOMISILI_PASAR

JENIS_KRIYA = {
    "kriya", "kerajinan", "seni rupa", "antik", "kerajinan tangan",
    "barang antik", "seni", "lukisan", "patung", "anyaman", "ukiran",
}
JENIS_KOMERSIAL = {
    "reseller", "franchise", "waralaba", "impor", "produk impor",
    "barang pabrik", "pabrik", "distributor",
}
JENIS_PENDUKUNG = {
    "kuliner", "makanan", "minuman", "fesyen", "fashion", "pakaian", "tekstil",
    "aksesoris", "aksesori", "jasa kreatif", "lukis wajah", "suvenir", "souvenir",
}


def _norm(teks: str) -> str:
    return (teks or "").strip().lower()


def is_warga_lokal(domisili: str) -> bool:
    """True jika domisili (KTP) memuat nama kota/kabupaten lokasi pasar."""
    return _norm(DOMISILI_PASAR) in _norm(domisili)


def _contains_any(text: str, keywords: set[str]) -> bool:
    """Cek apakah teks mengandung salah satu kata kunci."""
    return any(kw in text for kw in keywords)


def tentukan_queue(
    domisili: str,
    jenis_usaha: str,
    status_khusus: bool,
    punya_toko_fisik: bool,
    produksi_sendiri: bool = True,
    jumlah_cabang: int = 1,
    modal_besar: bool = False,
) -> int:
    jenis = _norm(jenis_usaha)
    lokal = is_warga_lokal(domisili)

    # Queue 3: Wajib warga lokal untuk Queue 1 dan Queue 2. Luar daerah otomatis Queue 3.
    if not lokal:
        return 3

    # Status afirmasi lokal mengunci posisi Queue 1 (penyandang disabilitas / warga pra-sejahtera)
    if status_khusus:
        return 1

    # Queue 3: Reseller barang pabrik, franchise/waralaba, produk impor,
    # produk bukan produksi sendiri, memiliki > 1 cabang, atau bermodal besar.
    if (
        _contains_any(jenis, JENIS_KOMERSIAL)
        or not produksi_sendiri
        or jumlah_cabang > 1
        or modal_besar
    ):
        return 3

    # Queue 1: Pengrajin lokal asli, produk kriya/seni/antik buatan sendiri, belum punya toko fisik
    is_kriya = _contains_any(jenis, JENIS_KRIYA)
    if is_kriya and not punya_toko_fisik:
        return 1

    # Queue 2: Jalur pendukung ekosistem (kuliner, fesyen, aksesoris, jasa kreatif buatan sendiri)
    # atau perajin kriya lokal yang sudah memiliki toko fisik pribadi.
    is_pendukung = _contains_any(jenis, JENIS_PENDUKUNG)
    if is_pendukung or is_kriya:
        return 2

    # Kategori lain / umum dialihkan ke Queue 3 sebagai cadangan komersial
    return 3
