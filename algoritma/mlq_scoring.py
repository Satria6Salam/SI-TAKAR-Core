"""Manajemen Proses: klasifikasi UMKM ke Queue 1/2/3 (Multilevel Queue) sesuai kriteria Ketua.

Q3 (Komersial & Ekspansi)  : warga luar kota, ATAU produk bukan buatan sendiri
                             (reseller/waralaba/impor), ATAU sudah punya lebih dari 1 toko.
Q1 (Afirmasi & Pelestarian): warga lokal + (status khusus ATAU pengrajin kriya/seni/antik
                             buatan sendiri yang belum punya toko fisik).
Q2 (Pendukung Ekosistem)   : warga lokal lainnya (kuliner, fesyen, aksesoris, jasa kreatif,
                             atau kriya yang sudah punya toko).

Prioritas TIDAK dipilih pendaftar; sistem yang menghitung dan menyimpan alasannya.
"""
import re

from database.config import DOMISILI_PASAR

JENIS_KRIYA = {"kriya", "kerajinan", "kerajinan tangan", "seni rupa", "seni", "antik"}
JENIS_KOMERSIAL = {"reseller", "franchise", "waralaba", "impor", "produk impor"}
SUMBER_KOMERSIAL = {"reseller": "reseller barang pabrik", "waralaba": "waralaba (franchise)",
                    "impor": "produk impor"}

NAMA_QUEUE = {1: "Prioritas Tinggi", 2: "Prioritas Menengah", 3: "Prioritas Rendah"}


def _norm(teks: str) -> str:
    return (teks or "").strip().lower()


def _wilayah(teks: str) -> str:
    """Seragamkan penulisan: 'Kab. Malang' / 'kab malang' -> 'kabupaten malang'."""
    t = re.sub(r"[^a-z0-9 ]", " ", _norm(teks))
    t = re.sub(r"\bkab\b", "kabupaten", t)
    return " ".join(t.split())


def is_warga_lokal(domisili: str) -> bool:
    """True jika domisili (KTP) berada di kota/kabupaten lokasi pasar.

    'Kota Malang' dan 'Kabupaten Malang' adalah wilayah berbeda, jadi jenisnya ikut dicocokkan.
    """
    return _wilayah(DOMISILI_PASAR) in _wilayah(domisili)


def nilai_queue(domisili: str, jenis_usaha: str, status_khusus: bool = False,
                jumlah_cabang: int = 0, sumber_produk: str = "buatan_sendiri") -> tuple[int, list[str]]:
    """Kembalikan (queue_level, daftar alasan yang bisa dibaca pendaftar)."""
    jenis = _norm(jenis_usaha)
    sumber = _norm(sumber_produk)

    # ---- Queue 3: salah satu saja sudah cukup ----
    alasan = []
    if not is_warga_lokal(domisili):
        alasan.append(f"Domisili KTP di luar {DOMISILI_PASAR}")
    if sumber in SUMBER_KOMERSIAL:
        alasan.append(f"Produk berupa {SUMBER_KOMERSIAL[sumber]}, bukan buatan sendiri")
    elif jenis in JENIS_KOMERSIAL:
        alasan.append(f"Jenis usaha {jenis} tergolong komersial")
    if jumlah_cabang > 1:
        alasan.append(f"Sudah memiliki {jumlah_cabang} toko/cabang di tempat lain")
    if alasan:
        return 3, alasan

    # ---- Queue 1 ----
    lokal = f"Warga lokal {DOMISILI_PASAR}"
    if status_khusus:
        return 1, [lokal, "Memiliki status khusus (disabilitas / pra-sejahtera)"]
    if jenis in JENIS_KRIYA and jumlah_cabang == 0:
        return 1, [lokal, f"Pengrajin {jenis} dengan produk buatan sendiri",
                   "Belum memiliki toko fisik (usaha rintisan)"]

    # ---- Queue 2 ----
    if jenis in JENIS_KRIYA:
        return 2, [lokal, f"Pengrajin {jenis}, tetapi sudah memiliki toko fisik"]
    return 2, [lokal, f"Usaha {jenis or 'umum'} produksi sendiri sebagai pendukung ekosistem pasar"]


def penalti_rekam_jejak(level: int, alasan: list[str], pelanggaran: list[tuple]) -> tuple[int, list[str]]:
    """Turunkan satu tingkat bila pernah dicabut/gugur. pelanggaran = [(jenis, tanggal_teks), ...]."""
    if not pelanggaran:
        return level, alasan
    jenis, tanggal = pelanggaran[0]
    sebab = {"Preemption": "hak sewanya pernah dicabut karena lapak tidak aktif",
             "Gugur": "pernah gugur karena berulang kali tidak mengonfirmasi lapak"}.get(jenis, jenis)
    baru = min(3, level + 1)
    akibat = (f"prioritas diturunkan ke Queue {baru}" if baru != level
              else "sudah berada di prioritas terendah")
    return baru, alasan + [f"Rekam jejak: {sebab} ({tanggal}); {akibat}"]


def tentukan_queue(domisili: str, jenis_usaha: str, status_khusus: bool = False,
                   jumlah_cabang: int = 0, sumber_produk: str = "buatan_sendiri") -> int:
    return nilai_queue(domisili, jenis_usaha, status_khusus, jumlah_cabang, sumber_produk)[0]
