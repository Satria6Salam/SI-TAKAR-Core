from datetime import timedelta

from sqlalchemy import create_engine, inspect, text

from algoritma.deadlock_cron import jalankan_semua
from algoritma.mlq_scoring import tentukan_queue
from algoritma.worst_fit import jalankan_alokasi
import database.config as database_config
from database.config import utcnow
from database.models import AlokasiSewa, Lapak, StatusLapak

KRIYA = dict(nama_pemilik="Sari", nama_usaha="Kriya Sari", domisili="Kota Contoh",
             jenis_usaha="kriya")


def tambah_lapak(c, kode, p, l, headers, x=0, y=0):
    r = c.post("/peta/lapak", json=dict(kode_lapak=kode, panjang=p, lebar=l, posisi_x=x, posisi_y=y), headers=headers)
    assert r.status_code == 201


# ---------- MLQ ----------
def test_skoring_mlq():
    # Queue 1: Warga lokal + perajin kriya/seni/antik tanpa toko fisik
    assert tentukan_queue("Kota Contoh", "kriya", False, False) == 1
    assert tentukan_queue("Kota Contoh", "kerajinan tangan", False, False) == 1
    assert tentukan_queue("Kota Contoh", "seni rupa", False, False) == 1
    assert tentukan_queue("Kota Contoh", "barang antik", False, False) == 1
    
    # Status khusus (disabilitas / bansos) mengunci Q1 bagi warga lokal
    assert tentukan_queue("Kota Contoh", "kuliner", True, False) == 1
    assert tentukan_queue("Kota Contoh", "reseller", True, False, False, 3) == 1
    
    # Luar daerah selalu masuk Queue 3
    assert tentukan_queue("Surabaya", "kuliner", True, False) == 3
    assert tentukan_queue("Surabaya", "kriya", False, False) == 3
    
    # Queue 2: Warga lokal pendukung ekosistem (kuliner, fesyen, aksesoris, jasa kreatif buatan sendiri)
    assert tentukan_queue("Kota Contoh", "kuliner", False, False) == 2
    assert tentukan_queue("Kota Contoh", "makanan & minuman", False, False) == 2
    assert tentukan_queue("Kota Contoh", "fashion & pakaian", False, False) == 2
    assert tentukan_queue("Kota Contoh", "aksesoris & suvenir", False, False) == 2
    assert tentukan_queue("Kota Contoh", "jasa kreatif (lukis wajah)", False, False) == 2
    # Atau perajin kriya lokal yang sudah punya toko fisik
    assert tentukan_queue("Kota Contoh", "kriya", False, True) == 2
    
    # Queue 3: Reseller pabrik, franchise/waralaba, produk impor, toko cabang > 1, modal besar
    assert tentukan_queue("Kota Contoh", "reseller", False, False) == 3
    assert tentukan_queue("Kota Contoh", "reseller barang pabrik", False, False) == 3
    assert tentukan_queue("Kota Contoh", "franchise (waralaba)", False, False) == 3
    assert tentukan_queue("Kota Contoh", "produk impor", False, False) == 3
    assert tentukan_queue("Kota Contoh", "kriya", False, False, False) == 3  # bukan produksi sendiri
    assert tentukan_queue("Kota Contoh", "kuliner", False, False, True, 2) == 3  # cabang > 1
    assert tentukan_queue("Kota Contoh", "kuliner", False, False, modal_besar=True) == 3
    assert tentukan_queue("Kota Contoh", "lainnya", False, False) == 3


def test_migrasi_skema_umkm_lama(tmp_path, monkeypatch):
    legacy_engine = create_engine(f"sqlite:///{tmp_path / 'legacy.db'}")
    with legacy_engine.begin() as connection:
        connection.execute(text("CREATE TABLE umkm (id INTEGER PRIMARY KEY)"))
    monkeypatch.setattr(database_config, "engine", legacy_engine)

    database_config.migrate_schema()

    columns = {column["name"] for column in inspect(legacy_engine).get_columns("umkm")}
    assert {"kebutuhan_luas", "produksi_sendiri", "jumlah_cabang", "modal_besar", "nomor_pendaftaran"} <= columns
    legacy_engine.dispose()


# ---------- Worst-Fit + antrean ----------
def test_worst_fit_pilih_lapak_terluas(client, admin_headers):
    tambah_lapak(client, "K", 2, 2, admin_headers)
    tambah_lapak(client, "B", 5, 5, admin_headers)   # terbesar
    tambah_lapak(client, "S", 3, 3, admin_headers)
    r = client.post("/pendaftaran", json=KRIYA)
    assert r.status_code == 201
    body = r.json()
    assert body["umkm"]["queue_level"] == 1
    assert body["alokasi"]["kode_lapak"] == "B"
    assert body["alokasi"]["status_alokasi"] == "Menunggu Konfirmasi"
    assert body["alokasi"]["sisa_detik_konfirmasi"] > 2.9 * 86400
    assert body["umkm"]["nomor_pendaftaran"].startswith("STK-")
    assert client.get(f"/pendaftaran/nomor/{body['umkm']['nomor_pendaftaran']}/status").json()["umkm"]["id"] == body["umkm"]["id"]


def test_pendaftaran_menyimpan_kategori_modal_besar(client):
    response = client.post("/pendaftaran", json={
        **KRIYA,
        "jenis_usaha": "kuliner",
        "modal_besar": True,
    })

    assert response.status_code == 201
    assert response.json()["umkm"]["modal_besar"] is True
    assert response.json()["umkm"]["queue_level"] == 3


def test_alokasi_menunggu_lapak_yang_memenuhi_luas(client, db):
    db.add(Lapak(kode_lapak="Kecil", panjang=2, lebar=2, luas=4,
                 status_lapak=StatusLapak.KOSONG))
    db.commit()
    pendaftaran = client.post("/pendaftaran", json={**KRIYA, "kebutuhan_luas": 6}).json()
    assert pendaftaran["umkm"]["status_pendaftaran"] == "Menunggu"
    assert pendaftaran["alokasi"] is None

    db.add(Lapak(kode_lapak="Cukup", panjang=2, lebar=3, luas=6,
                 status_lapak=StatusLapak.KOSONG))
    db.commit()
    jalankan_alokasi(db)
    status = client.get(f"/pendaftaran/{pendaftaran['umkm']['id']}/status").json()
    assert status["alokasi"]["kode_lapak"] == "Cukup"


def test_queue1_didahulukan_walau_daftar_belakangan(client, admin_headers):
    # belum ada lapak -> semua mengantre
    q3 = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Luar", "domisili": "Surabaya"}).json()
    q2 = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Kuliner", "jenis_usaha": "kuliner"}).json()
    q1 = client.post("/pendaftaran", json=KRIYA).json()
    assert (q3["umkm"]["queue_level"], q2["umkm"]["queue_level"], q1["umkm"]["queue_level"]) == (3, 2, 1)
    assert q1["posisi_dalam_queue"] == 1

    tambah_lapak(client, "A", 3, 3, admin_headers)             # 1 lapak saja
    client.post("/alokasi/jalankan-deadlock", headers=admin_headers)   # alokasi ulang
    s1 = client.get(f"/pendaftaran/{q1['umkm']['id']}/status").json()
    s2 = client.get(f"/pendaftaran/{q2['umkm']['id']}/status").json()
    assert s1["alokasi"]["kode_lapak"] == "A"   # Q1 dapat
    assert s2["alokasi"] is None and s2["posisi_dalam_queue"] == 1


# ---------- Konfirmasi ----------
def test_konfirmasi_mengubah_lapak_jadi_terisi(client, admin_headers):
    tambah_lapak(client, "A", 3, 3, admin_headers)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    r = client.post(f"/alokasi/{a['id']}/konfirmasi")
    assert r.status_code == 200 and r.json()["status_alokasi"] == "Aktif"
    peta = client.get("/peta").json()
    assert peta["ringkasan"] == {"kosong": 0, "dipesan": 0, "terisi": 1}
    assert peta["lapak"][0]["warna"] == "merah"
    assert client.post(f"/alokasi/{a['id']}/konfirmasi").status_code == 409  # tidak bisa dua kali


# ---------- Timeout ----------
def test_timeout_membatalkan_dan_memberi_ke_antrean_berikutnya(client, db, admin_headers):
    tambah_lapak(client, "A", 3, 3, admin_headers)
    u1 = client.post("/pendaftaran", json=KRIYA).json()
    u2 = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Kedua"}).json()
    assert u2["alokasi"] is None

    # majukan waktu 4 hari -> lewat batas 3 hari
    hasil = jalankan_semua(db, now=utcnow() + timedelta(days=4))
    assert hasil["timeout"] == [u1["umkm"]["id"]]

    s1 = client.get(f"/pendaftaran/{u1['umkm']['id']}/status").json()
    s2 = client.get(f"/pendaftaran/{u2['umkm']['id']}/status").json()
    assert s1["umkm"]["status_pendaftaran"] == "Menunggu"   # turun ke antrean terbawah
    assert s1["posisi_dalam_queue"] == 1                     # (u2 sudah dapat lapak, tinggal dia)
    assert s2["alokasi"]["kode_lapak"] == "A"                # lapak berpindah ke urutan berikutnya
    log = client.get("/alokasi/log", headers=admin_headers).json()
    assert log[0]["jenis_pelanggaran"] == "Timeout"


def test_konfirmasi_setelah_batas_ditolak(client, db, admin_headers):
    tambah_lapak(client, "A", 3, 3, admin_headers)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    row = db.get(AlokasiSewa, a["id"])
    row.batas_konfirmasi = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.post(f"/alokasi/{a['id']}/konfirmasi").status_code == 410


# ---------- Preemption ----------
def test_preemption_setelah_14_hari_dan_peringatan_7_hari(client, db, admin_headers):
    tambah_lapak(client, "A", 3, 3, admin_headers)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    client.post(f"/alokasi/{a['id']}/konfirmasi")
    antre = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Pendaftar berikutnya"}).json()
    assert antre["umkm"]["status_pendaftaran"] == "Menunggu"

    # hari ke-8 tidak aktif -> peringatan aktif, belum dicabut
    row = db.get(AlokasiSewa, a["id"])
    row.terakhir_aktif = utcnow() - timedelta(days=8)
    db.commit()
    info = client.get(f"/alokasi/umkm/{a['umkm_id']}").json()
    assert info["peringatan"] is True
    assert jalankan_semua(db)["preemption"] == []

    # tombol absen mereset hitungan
    client.post(f"/alokasi/{a['id']}/absen")
    assert client.get(f"/alokasi/umkm/{a['umkm_id']}").json()["peringatan"] is False

    # 15 hari tidak aktif -> dicabut
    db.expire_all()
    row = db.get(AlokasiSewa, a["id"])
    row.terakhir_aktif = utcnow() - timedelta(days=15)
    db.commit()
    assert jalankan_semua(db)["preemption"] == [a["umkm_id"]]
    status_antre = client.get(f"/pendaftaran/{antre['umkm']['id']}/status").json()
    assert status_antre["alokasi"]["kode_lapak"] == "A"

    peta = client.get("/peta").json()
    assert peta["lapak"][0]["warna"] == "kuning"         # langsung dipesan oleh antrean berikutnya
    log = client.get("/alokasi/log", headers=admin_headers).json()
    assert log[0]["jenis_pelanggaran"] == "Preemption"
    st = client.get(f"/pendaftaran/{a['umkm_id']}/status").json()
    assert st["umkm"]["status_pendaftaran"] == "Dicabut"


def test_validasi_dan_404(client, admin_headers):
    assert client.post("/pendaftaran", json={"nama_pemilik": ""}).status_code == 422
    assert client.get("/pendaftaran/999/status").status_code == 404
    assert client.get("/antrean").status_code == 401
    assert client.get("/antrean", headers=admin_headers).json() == {"queue_1": [], "queue_2": [], "queue_3": []}
