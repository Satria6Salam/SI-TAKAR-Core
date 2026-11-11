"""Data awal SI-TAKAR. Aman dijalankan berulang kali.

  python seed.py           -> zona contoh + akun admin demo
  python seed.py --demo    -> tambah pendaftar fiktif (dummy) untuk uji coba
  python seed.py --reset   -> kosongkan SELURUH data lalu isi ulang data awal

Semua pendaftar fiktif memakai PIN 123456.
"""
import shutil
import sys
from pathlib import Path

from database.config import UNGGAHAN_DIR, Base, SessionLocal, engine, siapkan_database
from database.models import Admin, Zona
from routers.admin_security import hash_password  # noqa: F401  (dipakai juga oleh tes)

PIN_DEMO = "123456"

# (kode, nama, panjang lorong m, kedalaman m)
ZONA_AWAL = [
    ("A", "Lorong Kriya", 20, 3),
    ("B", "Lorong Kuliner", 14, 3),
    ("C", "Lorong Seni & Tekstil", 10, 3),
]

# Pendaftar fiktif. Sengaja didaftarkan dengan urutan "yang besar lebih cepat" supaya terlihat
# bahwa MLQ tetap mendahulukan Queue 1 walaupun mendaftar belakangan.
# (pemilik, usaha, jenis, lokal?, sumber, status_khusus, cabang, muka_m)
PENDAFTAR_DEMO = [
    ("Hendra Wijaya", "Grosir Suvenir Jaya", "aksesoris", True, "reseller", False, 3, 5),
    ("Linda Hartono", "Teh Poci Waralaba", "kuliner", True, "waralaba", False, 1, 3),
    ("Rudi Santoso", "Batik Pesisir", "fesyen", False, "buatan_sendiri", False, 0, 4),
    ("Yuli Astuti", "Dapur Mbok Yem", "kuliner", True, "buatan_sendiri", False, 0, 4),
    ("Bayu Pratama", "Kopi Lereng", "kuliner", True, "buatan_sendiri", False, 1, 3),
    ("Sari Dewi", "Kriya Sari", "kriya", True, "buatan_sendiri", False, 0, 3),
    ("Tini Rahayu", "Anyaman Bu Tini", "kriya", True, "buatan_sendiri", True, 0, 2),
    ("Dimas Arya", "Sketsa Wajah Dimas", "jasa kreatif", True, "buatan_sendiri", False, 0, 2),
    ("Karto Suwiryo", "Gerabah Pak Karto", "kriya", True, "buatan_sendiri", False, 0, 3),
    ("Laras Ayu", "Batik Tulis Laras", "seni rupa", True, "buatan_sendiri", False, 0, 4),
    ("Rona Maharani", "Jahit Rona", "fesyen", True, "buatan_sendiri", False, 0, 3),
    ("Joko Mulyono", "Kriya Jati Mapan", "kriya", True, "buatan_sendiri", False, 1, 5),
    ("Wening Lestari", "Lukis Kaca Wening", "seni rupa", True, "buatan_sendiri", False, 0, 2),
    ("Agus Salim", "Aksesoris Impor Agus", "aksesoris", True, "impor", False, 0, 3),
    ("Fitri Handayani", "Kedai Jamu Fitri", "kuliner", True, "buatan_sendiri", True, 0, 2),
    ("Tommy Gunawan", "Oleh-Oleh Nusantara", "kuliner", False, "reseller", False, 2, 6),
]

# Pendaftar fiktif yang masih menunggu verifikasi, untuk mencoba halaman Verifikasi.
# (pemilik, usaha, jenis, status_khusus, muka_m, unggah_bukti_khusus?)
MENUNGGU_VERIFIKASI_DEMO = [
    ("Nur Aini", "Tenun Ikat Nur", "kriya", True, 3, True),          # lengkap -> bisa diterima
    ("Galih Saputra", "Wayang Kulit Galih", "seni rupa", False, 2, False),
    ("Maya Lestari", "Keripik Maya", "kuliner", True, 2, False),     # klaim tanpa bukti
]


def pdf_contoh(teks: str) -> bytes:
    """PDF satu halaman sederhana sebagai pengganti scan KTP pada data fiktif."""
    isi = f"BT /F1 16 Tf 30 120 Td ({teks}) Tj ET".encode("latin-1")
    objek = [
        b"<< /Type /Catalog /Pages 2 0 R >>",
        b"<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
        b"<< /Type /Page /Parent 2 0 R /MediaBox [0 0 420 260] /Contents 4 0 R "
        b"/Resources << /Font << /F1 5 0 R >> >> >>",
        b"<< /Length %d >>\nstream\n" % len(isi) + isi + b"\nendstream",
        b"<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    ]
    out, posisi = b"%PDF-1.4\n", []
    for i, o in enumerate(objek, 1):
        posisi.append(len(out))
        out += b"%d 0 obj\n" % i + o + b"\nendobj\n"
    xref = len(out)
    out += b"xref\n0 %d\n0000000000 65535 f \n" % (len(objek) + 1)
    out += b"".join(b"%010d 00000 n \n" % p for p in posisi)
    out += b"trailer\n<< /Size %d /Root 1 0 R >>\nstartxref\n%d\n%%%%EOF\n" % (len(objek) + 1, xref)
    return out


def isi_awal(db) -> None:
    """Zona contoh + akun admin demo (hanya yang belum ada)."""
    for kode, nama, panjang, kedalaman in ZONA_AWAL:
        if not db.query(Zona).filter_by(kode=kode).first():
            db.add(Zona(kode=kode, nama=nama, panjang=panjang, kedalaman=kedalaman))
    if not db.query(Admin).filter_by(username="admin").first():
        # Akun demo untuk laptop lokal; ganti password bila dipakai sungguhan
        db.add(Admin(username="admin", password_hash=hash_password("admin123")))
    db.commit()


def isi_demo(db) -> dict:
    """Daftarkan pendaftar fiktif lewat jalur yang sama dengan formulir, lalu alokasikan."""
    from fastapi import HTTPException

    from algoritma.jam import sekarang
    from algoritma.penjadwal import jalankan_alokasi
    from database.config import DOMISILI_PASAR
    from routers.api_alokasi import aktifkan
    from routers.api_pendaftaran import daftarkan, simpan_dokumen
    from schemas import UMKMCreate

    def data(i, pemilik, usaha, jenis, lokal, sumber, khusus, cabang, muka):
        return UMKMCreate(
            nama_pemilik=pemilik, nik=f"99{i:014d}", telepon=f"0812000000{i:02d}",
            nama_usaha=usaha, jenis_usaha=jenis, deskripsi="Data fiktif untuk uji coba.",
            domisili=DOMISILI_PASAR if lokal else "Luar Kota", sumber_produk=sumber,
            status_khusus=khusus, jumlah_cabang=cabang, kebutuhan_muka=muka, pin=PIN_DEMO,
        )

    ditambah = 0
    for i, baris in enumerate(PENDAFTAR_DEMO):
        try:
            daftarkan(db, data(i, *baris), langsung_antre=True)   # data fiktif: tanpa verifikasi
            ditambah += 1
        except HTTPException:
            db.rollback()  # sudah pernah dimasukkan

    menunggu = 0
    for j, (pemilik, usaha, jenis, khusus, muka, bukti) in enumerate(MENUNGGU_VERIFIKASI_DEMO, 50):
        try:
            u = daftarkan(db, data(j, pemilik, usaha, jenis, True, "buatan_sendiri", khusus, 0, muka),
                          langsung_antre=False)
        except HTTPException:
            db.rollback()
            continue
        simpan_dokumen(db, u, "ktp", pdf_contoh(f"KTP CONTOH - {pemilik} - data fiktif"))
        if bukti:
            simpan_dokumen(db, u, "khusus", pdf_contoh(f"SURAT KETERANGAN CONTOH - {pemilik}"))
        db.commit()
        menunggu += 1

    alokasi = jalankan_alokasi(db)
    # Sebagian besar langsung konfirmasi; tiap pendaftar ketiga dibiarkan supaya Timeout bisa didemokan
    now = sekarang(db)
    dikonfirmasi = 0
    for i, a in enumerate(alokasi):
        if i % 3 != 2:
            aktifkan(db, a, now)
            dikonfirmasi += 1
    db.commit()
    return {"pendaftar_ditambah": ditambah, "menunggu_verifikasi": menunggu,
            "alokasi_baru": len(alokasi), "dikonfirmasi": dikonfirmasi, "pin": PIN_DEMO}


def main(argv: list[str]) -> None:
    if "--reset" in argv:
        Base.metadata.drop_all(bind=engine)
        shutil.rmtree(Path(UNGGAHAN_DIR), ignore_errors=True)
        print("Seluruh data dan berkas unggahan dikosongkan.")
    siapkan_database()
    db = SessionLocal()
    try:
        isi_awal(db)
        print(f"Data awal siap: {db.query(Zona).count()} zona, {db.query(Admin).count()} admin.")
        if "--demo" in argv:
            print("Data contoh:", isi_demo(db))
    finally:
        db.close()


if __name__ == "__main__":
    main(sys.argv[1:])
