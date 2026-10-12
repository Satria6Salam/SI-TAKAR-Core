from datetime import timedelta

from algoritma.deadlock_cron import jalankan_semua
from algoritma.mlq_scoring import tentukan_queue
from database.config import utcnow
from database.models import AlokasiSewa

KRIYA = dict(nama_pemilik="Sari", nama_usaha="Kriya Sari", domisili="Kota Contoh",
             jenis_usaha="kriya")


def tambah_lapak(c, kode, p, l, x=0, y=0):
    r = c.post("/peta/lapak", json=dict(kode_lapak=kode, panjang=p, lebar=l, posisi_x=x, posisi_y=y))
    assert r.status_code == 201


# ---------- MLQ ----------
def test_skoring_mlq():
    assert tentukan_queue("Kota Contoh", "kriya", False, False) == 1
    assert tentukan_queue("Kota Contoh", "kuliner", True, False) == 1   # status khusus mengunci Q1
    assert tentukan_queue("Kota Contoh", "kuliner", False, False) == 2
    assert tentukan_queue("Kota Contoh", "kriya", False, True) == 2     # kriya tapi sudah punya toko
    assert tentukan_queue("Surabaya", "kriya", False, False) == 3       # luar kota
    assert tentukan_queue("Kota Contoh", "reseller", False, False) == 3  # reseller


# ---------- Worst-Fit + antrean ----------
def test_worst_fit_pilih_lapak_terluas(client):
    tambah_lapak(client, "K", 2, 2)
    tambah_lapak(client, "B", 5, 5)   # terbesar
    tambah_lapak(client, "S", 3, 3)
    r = client.post("/pendaftaran", json=KRIYA)
    assert r.status_code == 201
    body = r.json()
    assert body["umkm"]["queue_level"] == 1
    assert body["alokasi"]["kode_lapak"] == "B"
    assert body["alokasi"]["status_alokasi"] == "Menunggu Konfirmasi"
    assert body["alokasi"]["sisa_detik_konfirmasi"] > 2.9 * 86400


def test_queue1_didahulukan_walau_daftar_belakangan(client):
    # belum ada lapak -> semua mengantre
    q3 = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Luar", "domisili": "Surabaya"}).json()
    q2 = client.post("/pendaftaran", json={**KRIYA, "nama_usaha": "Kuliner", "jenis_usaha": "kuliner"}).json()
    q1 = client.post("/pendaftaran", json=KRIYA).json()
    assert (q3["umkm"]["queue_level"], q2["umkm"]["queue_level"], q1["umkm"]["queue_level"]) == (3, 2, 1)
    assert q1["posisi_dalam_queue"] == 1

    tambah_lapak(client, "A", 3, 3)             # 1 lapak saja
    client.post("/alokasi/jalankan-deadlock")   # alokasi ulang
    s1 = client.get(f"/pendaftaran/{q1['umkm']['id']}/status").json()
    s2 = client.get(f"/pendaftaran/{q2['umkm']['id']}/status").json()
    assert s1["alokasi"]["kode_lapak"] == "A"   # Q1 dapat
    assert s2["alokasi"] is None and s2["posisi_dalam_queue"] == 1


# ---------- Konfirmasi ----------
def test_konfirmasi_mengubah_lapak_jadi_terisi(client):
    tambah_lapak(client, "A", 3, 3)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    r = client.post(f"/alokasi/{a['id']}/konfirmasi")
    assert r.status_code == 200 and r.json()["status_alokasi"] == "Aktif"
    peta = client.get("/peta").json()
    assert peta["ringkasan"] == {"kosong": 0, "dipesan": 0, "terisi": 1}
    assert peta["lapak"][0]["warna"] == "merah"
    assert client.post(f"/alokasi/{a['id']}/konfirmasi").status_code == 409  # tidak bisa dua kali


# ---------- Timeout ----------
def test_timeout_membatalkan_dan_memberi_ke_antrean_berikutnya(client, db):
    tambah_lapak(client, "A", 3, 3)
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
    log = client.get("/alokasi/log").json()
    assert log[0]["jenis_pelanggaran"] == "Timeout"


def test_konfirmasi_setelah_batas_ditolak(client, db):
    tambah_lapak(client, "A", 3, 3)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    row = db.get(AlokasiSewa, a["id"])
    row.batas_konfirmasi = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.post(f"/alokasi/{a['id']}/konfirmasi").status_code == 410


# ---------- Preemption ----------
def test_preemption_setelah_14_hari_dan_peringatan_7_hari(client, db):
    tambah_lapak(client, "A", 3, 3)
    a = client.post("/pendaftaran", json=KRIYA).json()["alokasi"]
    client.post(f"/alokasi/{a['id']}/konfirmasi")

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

    peta = client.get("/peta").json()
    assert peta["lapak"][0]["warna"] == "hijau"          # merah -> hijau
    log = client.get("/alokasi/log").json()
    assert log[0]["jenis_pelanggaran"] == "Preemption"
    st = client.get(f"/pendaftaran/{a['umkm_id']}/status").json()
    assert st["umkm"]["status_pendaftaran"] == "Dicabut"


def test_validasi_dan_404(client):
    assert client.post("/pendaftaran", json={"nama_pemilik": ""}).status_code == 422
    assert client.get("/pendaftaran/999/status").status_code == 404
    assert client.get("/antrean").json() == {"queue_1": [], "queue_2": [], "queue_3": []}
