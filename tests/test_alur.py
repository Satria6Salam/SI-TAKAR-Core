from datetime import timedelta

from algoritma.deadlock_cron import jalankan_semua
from algoritma.mlq_scoring import nilai_queue, tentukan_queue
from algoritma.worst_fit import Hole, pilih_hole, potong, simulasi, statistik
from database.config import utcnow
from database.models import AlokasiSewa

_nik = iter(range(1, 10_000))
PIN = "123456"
PIN_JSON = {"pin": PIN}


def pendaftar(**ubah):
    """Data pendaftar kriya lokal (Queue 1) dengan NIK unik; field bisa ditimpa."""
    data = dict(nama_pemilik="Sari", nik=f"{next(_nik):016d}", telepon="081200000000",
                nama_usaha="Kriya Sari", domisili="Kota Contoh", jenis_usaha="kriya",
                kebutuhan_muka=2, pin=PIN)
    data.update(ubah)
    return data


def daftar(c, **ubah):
    r = c.post("/pendaftaran", json=pendaftar(**ubah))
    assert r.status_code == 201, r.text
    return r.json()


def tambah_zona(c, kode, panjang, kedalaman=3):
    r = c.post("/peta/zona", json=dict(kode=kode, nama=f"Zona {kode}", panjang=panjang,
                                       kedalaman=kedalaman))
    assert r.status_code == 201, r.text


def status(c, hasil):
    return c.get(f"/pendaftaran/{hasil['umkm']['kode_pendaftaran']}/status").json()


def kode(hasil):
    return hasil["umkm"]["kode_pendaftaran"]


# ================= PILAR 1: MANAJEMEN PROSES (MLQ) =================
def test_skoring_mlq():
    assert tentukan_queue("Kota Contoh", "kriya") == 1
    assert tentukan_queue("Kota Contoh", "kuliner", status_khusus=True) == 1   # status khusus mengunci Q1
    assert tentukan_queue("Kota Contoh", "kuliner") == 2
    assert tentukan_queue("Kota Contoh", "kriya", jumlah_cabang=1) == 2        # kriya tapi sudah punya toko
    assert tentukan_queue("Surabaya", "kriya") == 3                            # luar kota
    assert tentukan_queue("Kota Contoh", "kriya", sumber_produk="reseller") == 3
    assert tentukan_queue("Kota Contoh", "kuliner", sumber_produk="waralaba") == 3
    assert tentukan_queue("Kota Contoh", "kuliner", jumlah_cabang=2) == 3      # lebih dari 1 cabang
    level, alasan = nilai_queue("Surabaya", "kriya", sumber_produk="impor")
    assert level == 3 and len(alasan) == 2                                     # alasan transparan


def test_prioritas_dihitung_sistem_bukan_dipilih_pendaftar(client):
    # field "queue_level" kiriman pendaftar diabaikan
    r = client.post("/pendaftaran", json={**pendaftar(domisili="Surabaya"), "queue_level": 1})
    assert r.status_code == 201
    assert r.json()["umkm"]["queue_level"] == 3
    assert "Domisili KTP di luar Kota Contoh" in r.json()["umkm"]["alasan_queue"]


def test_queue1_didahulukan_walau_daftar_belakangan(client):
    # belum ada zona -> semua mengantre
    q3 = daftar(client, nama_usaha="Luar", domisili="Surabaya")
    q2 = daftar(client, nama_usaha="Kuliner", jenis_usaha="kuliner")
    q1 = daftar(client)
    assert (q3["umkm"]["queue_level"], q2["umkm"]["queue_level"], q1["umkm"]["queue_level"]) == (3, 2, 1)
    assert q1["posisi_dalam_queue"] == 1

    tambah_zona(client, "A", 2)   # ruang hanya cukup untuk 1 pendaftar
    assert status(client, q1)["alokasi"]["kode_lapak"] == "A-01"   # Q1 dapat
    s2 = status(client, q2)
    assert s2["alokasi"] is None and s2["posisi_dalam_queue"] == 1
    antre = client.get("/antrean").json()
    assert [len(antre[f"queue_{i}"]) for i in (1, 2, 3)] == [0, 1, 1]


def test_fifo_di_dalam_satu_queue(client):
    a = daftar(client, nama_usaha="Pertama")
    b = daftar(client, nama_usaha="Kedua")
    assert (a["posisi_dalam_queue"], b["posisi_dalam_queue"]) == (1, 2)
    tambah_zona(client, "A", 2)
    assert status(client, a)["alokasi"] is not None
    assert status(client, b)["posisi_dalam_queue"] == 1


def test_satu_nik_satu_antrean(client):
    data = pendaftar()
    assert client.post("/pendaftaran", json=data).status_code == 201
    assert client.post("/pendaftaran", json=data).status_code == 409


# ================= PILAR 2: MANAJEMEN MEMORI (WORST-FIT) =================
def test_pemilihan_hole_tiga_strategi():
    holes = [Hole(1, "A", 0, 4, 3), Hole(2, "B", 0, 10, 3), Hole(3, "C", 0, 2, 3)]
    assert pilih_hole(holes, 2, "worst").zona_kode == "B"   # terluas
    assert pilih_hole(holes, 2, "best").zona_kode == "C"    # paling pas
    assert pilih_hole(holes, 2, "first").zona_kode == "A"   # pertama yang muat
    assert pilih_hole(holes, 11, "worst") is None           # tidak ada yang muat

    sisa = potong(holes, holes[1], 2)
    assert Hole(2, "B", 2, 8, 3) in sisa and len(sisa) == 3
    assert len(potong(holes, holes[2], 2)) == 2             # pas -> hole habis
    s = simulasi(holes, 2)
    # Worst-Fit menyisakan potongan besar (8 m), Best-Fit menghabiskan hole kecil
    assert s["worst"]["sisa_potongan_m"] == 8 and s["best"]["sisa_potongan_m"] == 0
    assert statistik(holes)["hole_terbesar_m"] == 10


def test_worst_fit_memotong_dari_zona_terluas(client):
    tambah_zona(client, "K", 4)
    tambah_zona(client, "B", 10)   # terluas
    tambah_zona(client, "S", 6)
    a = daftar(client, kebutuhan_muka=3)["alokasi"]
    assert (a["zona"], a["kode_lapak"], a["mulai"], a["panjang"], a["luas"]) == ("B", "B-01", 0, 3, 9)
    assert a["status_alokasi"] == "Menunggu Konfirmasi"
    assert a["sisa_detik_konfirmasi"] > 2.9 * 86400

    # sisa B tinggal 7 m (masih terluas) -> pendaftar berikutnya dipotong tepat di sebelahnya
    b = daftar(client, kebutuhan_muka=2)["alokasi"]
    assert (b["zona"], b["mulai"]) == ("B", 3)
    # sekarang B sisa 5, S 6, K 4 -> giliran S
    assert daftar(client, kebutuhan_muka=2)["alokasi"]["zona"] == "S"

    peta = client.get("/peta").json()
    zona_b = next(z for z in peta["zona"] if z["kode"] == "B")
    assert [(s["status"], s["panjang"]) for s in zona_b["segmen"]] == \
        [("Dipesan", 3), ("Dipesan", 2), ("Kosong", 5)]
    assert peta["ringkasan"]["kosong_m"] == 13 and peta["ringkasan"]["dipesan"] == 3


def test_permintaan_yang_tidak_muat_menunggu_dan_yang_muat_dilayani(client):
    tambah_zona(client, "A", 5)
    daftar(client, nama_usaha="Awal", kebutuhan_muka=3)                                  # sisa ruang 2 m
    besar = daftar(client, nama_usaha="Besar", kebutuhan_muka=4, jenis_usaha="kuliner")  # Q2, tidak muat
    kecil = daftar(client, nama_usaha="Kecil", kebutuhan_muka=2, domisili="Surabaya")    # Q3, muat
    assert besar["alokasi"] is None and besar["posisi_dalam_queue"] == 1
    assert kecil["alokasi"]["kode_lapak"] == "A-02"
    # lebih besar dari zona mana pun -> ditolak sejak pendaftaran
    assert client.post("/pendaftaran", json=pendaftar(kebutuhan_muka=9)).status_code == 422


def test_ruang_dilepas_menyatu_kembali_dengan_hole_di_sebelahnya(client, db):
    tambah_zona(client, "A", 6)
    u1, u2, u3 = (daftar(client, nama_usaha=n, kebutuhan_muka=2) for n in ("Satu", "Dua", "Tiga"))
    assert [u["alokasi"]["mulai"] for u in (u1, u2, u3)] == [0, 2, 4]
    assert client.get("/peta").json()["fragmentasi"]["jumlah_hole"] == 0
    client.post(f"/alokasi/{kode(u1)}/konfirmasi", json=PIN_JSON)
    client.post(f"/alokasi/{kode(u3)}/konfirmasi", json=PIN_JSON)

    # hanya u2 yang tidak konfirmasi -> timeout -> lubang 2 m di tengah
    jalankan_semua(db, now=utcnow() + timedelta(days=4))
    f = client.get("/peta").json()["fragmentasi"]
    assert (f["jumlah_hole"], f["total_kosong_m"]) == (1, 2)
    # sim: 3 m tidak muat di lubang 2 m walaupun... hanya itu ruangnya
    assert client.get("/peta/simulasi?kebutuhan=3").json()["hasil"]["worst"] is None
    assert client.get("/peta/simulasi?kebutuhan=2").json()["hasil"]["worst"]["sisa_potongan_m"] == 0


# ================= PILAR 4: DEADLOCK (TIMEOUT & PREEMPTION) =================
def test_konfirmasi_mengubah_lapak_jadi_terisi(client):
    tambah_zona(client, "A", 3)
    u = daftar(client, kebutuhan_muka=3)
    r = client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)
    assert r.status_code == 200 and r.json()["status_alokasi"] == "Aktif"
    assert r.json()["sisa_hari_sewa"] in (179, 180)
    peta = client.get("/peta").json()
    assert (peta["ringkasan"]["kosong"], peta["ringkasan"]["dipesan"], peta["ringkasan"]["terisi"]) == (0, 0, 1)
    assert peta["lapak"][0]["warna"] == "merah"
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON).status_code == 409  # tidak bisa dua kali
    assert client.post("/alokasi/STK-SALAH1/konfirmasi", json=PIN_JSON).status_code == 404


def test_timeout_membatalkan_dan_memberi_ke_antrean_berikutnya(client, db):
    tambah_zona(client, "A", 2)
    u1 = daftar(client)
    u2 = daftar(client, nama_usaha="Kedua")
    assert u2["alokasi"] is None

    # majukan waktu 4 hari -> lewat batas 3 hari
    hasil = jalankan_semua(db, now=utcnow() + timedelta(days=4))
    assert hasil["timeout"] == [u1["umkm"]["id"]]

    s1, s2 = status(client, u1), status(client, u2)
    assert s1["umkm"]["status_pendaftaran"] == "Menunggu"   # turun ke urutan terbawah queue-nya
    assert s1["umkm"]["jumlah_timeout"] == 1
    assert s1["posisi_dalam_queue"] == 1                     # (u2 sudah dapat lapak, tinggal dia)
    assert s2["alokasi"]["kode_lapak"] == "A-02"             # ruang yang sama, lapak baru untuk u2
    assert s2["alokasi"]["mulai"] == 0
    log = client.get("/alokasi/log").json()
    assert log[0]["jenis_pelanggaran"] == "Timeout"


def test_timeout_berulang_menggugurkan_pendaftaran(client, db):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    for i in range(1, 4):   # MAKS_TIMEOUT = 3
        jalankan_semua(db, now=utcnow() + timedelta(days=4 * i))          # timeout ke-i
        jalankan_semua(db, now=utcnow() + timedelta(days=4 * i, hours=1))  # dialokasikan lagi
        db.expire_all()
    s = status(client, u)
    assert s["umkm"]["status_pendaftaran"] == "Gugur" and s["umkm"]["jumlah_timeout"] == 3
    assert client.get("/peta").json()["ringkasan"]["kosong_m"] == 2   # ruang tidak tertahan


def test_konfirmasi_setelah_batas_ditolak(client, db):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    row = db.get(AlokasiSewa, u["alokasi"]["id"])
    row.batas_konfirmasi = utcnow() - timedelta(minutes=1)
    db.commit()
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON).status_code == 410


def test_preemption_setelah_14_hari_dan_peringatan_7_hari(client, db):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    aid = u["alokasi"]["id"]
    client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)

    # hari ke-8 tidak aktif -> peringatan aktif, belum dicabut
    row = db.get(AlokasiSewa, aid)
    row.terakhir_aktif = utcnow() - timedelta(days=8)
    db.commit()
    hasil = jalankan_semua(db)
    assert hasil["preemption"] == [] and hasil["peringatan"] == [u["umkm"]["id"]]
    assert jalankan_semua(db)["peringatan"] == []          # peringatan hanya dikirim sekali
    assert status(client, u)["alokasi"]["peringatan"] is True

    # tombol absen mereset hitungan
    assert client.post(f"/alokasi/{kode(u)}/absen", json=PIN_JSON).status_code == 200
    assert status(client, u)["alokasi"]["peringatan"] is False

    # 15 hari tidak aktif -> dicabut
    db.expire_all()
    row = db.get(AlokasiSewa, aid)
    row.terakhir_aktif = utcnow() - timedelta(days=15)
    db.commit()
    assert jalankan_semua(db)["preemption"] == [u["umkm"]["id"]]

    peta = client.get("/peta").json()
    assert peta["zona"][0]["segmen"][0]["warna"] == "hijau"   # merah -> hijau
    assert client.get("/alokasi/log").json()[0]["jenis_pelanggaran"] == "Preemption"
    assert status(client, u)["umkm"]["status_pendaftaran"] == "Dicabut"
    assert client.post(f"/alokasi/{kode(u)}/absen", json=PIN_JSON).status_code == 409


def test_inspeksi_admin_mereset_hitungan_tidak_aktif(client, db):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)
    row = db.get(AlokasiSewa, u["alokasi"]["id"])
    row.terakhir_aktif = utcnow() - timedelta(days=13)
    db.commit()
    assert client.post(f"/alokasi/{u['alokasi']['id']}/inspeksi").json()["hari_tidak_aktif"] == 0
    assert jalankan_semua(db, now=utcnow() + timedelta(days=2))["preemption"] == []


def test_jam_simulasi_memicu_timeout(client):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    r = client.post("/api/admin/jam/majukan", json={"hari": 4}).json()
    assert r["geser_hari"] == 4 and r["siklus"]["timeout"] == [u["umkm"]["id"]]
    assert client.post("/api/admin/jam/reset").json()["geser_hari"] == 0


# ================= PILAR 3: MANAJEMEN PENYIMPANAN =================
def test_masa_sewa_habis_diarsipkan_dan_ruang_dipakai_antrean(client, db):
    tambah_zona(client, "A", 2)
    lama = daftar(client, nama_usaha="Lama")
    client.post(f"/alokasi/{kode(lama)}/konfirmasi", json=PIN_JSON)
    baru = daftar(client, nama_usaha="Baru")
    assert baru["alokasi"] is None

    row = db.get(AlokasiSewa, lama["alokasi"]["id"])
    row.sewa_berakhir = utcnow() - timedelta(days=1)
    db.commit()
    assert jalankan_semua(db)["sewa_berakhir"] == [lama["umkm"]["id"]]

    assert status(client, lama)["umkm"]["status_pendaftaran"] == "Selesai"
    assert status(client, baru)["alokasi"]["status_alokasi"] == "Menunggu Konfirmasi"
    arsip = client.get("/api/admin/arsip").json()
    assert [a["umkm"]["nama_usaha"] for a in arsip] == ["Lama"]            # tidak dihapus
    assert arsip[0]["alokasi_terakhir"]["status_alokasi"] == "Selesai"


def test_lulus_inkubasi_dan_jurnal(client):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)
    r = client.post(f"/alokasi/{u['alokasi']['id']}/lulus")
    assert r.status_code == 200 and r.json()["status_alokasi"] == "Lulus Inkubasi"
    s = status(client, u)
    assert s["umkm"]["status_pendaftaran"] == "Lulus Inkubasi"
    jenis = [x["jenis"] for x in s["riwayat"]]
    assert jenis == ["Lulus Inkubasi", "Konfirmasi", "Alokasi", "Pendaftaran"]
    assert client.get("/peta").json()["ringkasan"]["kosong_m"] == 2

    csv_ = client.get("/api/admin/ekspor.csv")
    assert csv_.status_code == 200 and kode(u) in csv_.text
    assert len(client.get("/api/admin/aktivitas").json()) == 5   # + Zona Baru


def test_data_contoh_mengisi_pasar_sesuai_prioritas(client):
    for k, p in (("A", 20), ("B", 14), ("C", 10)):
        tambah_zona(client, k, p)
    hasil = client.post("/api/admin/demo/isi").json()
    assert hasil["pendaftar_ditambah"] == 16 and hasil["menunggu_verifikasi"] == 3
    assert len(client.get("/api/admin/verifikasi").json()) == 3   # belum masuk antrean
    antre = client.get("/antrean").json()
    assert antre["queue_1"] == [] and antre["queue_2"] == []   # Q1 & Q2 terlayani semua
    assert len(antre["queue_3"]) >= 1                           # sisanya Q3 yang menunggu
    assert client.post("/api/admin/demo/isi").json()["pendaftar_ditambah"] == 0   # aman diulang


# ================= UMUM =================
def test_validasi_dan_404(client):
    assert client.post("/pendaftaran", json={"nama_pemilik": ""}).status_code == 422
    assert client.post("/pendaftaran", json=pendaftar(nik="123")).status_code == 422
    assert client.get("/pendaftaran/STK-TIDAKADA/status").status_code == 404
    assert client.get("/antrean").json() == {"queue_1": [], "queue_2": [], "queue_3": []}
    assert client.get("/info").json()["timeout_hari"] == 3


def test_dashboard_admin_tersedia(client):
    assert 'href="/admin/login"' in client.get("/").text
    response = client.get("/admin")
    assert response.status_code == 200
    assert "Dashboard Admin" in response.text
    assert "/static/css/admin.css" in response.text
    ringkas = client.get("/api/admin/ringkasan").json()
    assert ringkas["total"] == 0 and ringkas["menunggu_verifikasi"] == 0
    for halaman in ("verifikasi", "pendaftar", "denah", "antrean", "penyewa", "deadlock", "arsip"):
        assert client.get(f"/admin/{halaman}").status_code == 200


def test_login_admin_membatasi_dashboard_dan_endpoint_admin(client):
    client.post("/admin/logout")
    page = client.get("/admin", follow_redirects=False)
    assert page.status_code == 303
    assert page.headers["location"] == "/admin/login"
    for jalur in ("/antrean", "/alokasi/aktif", "/alokasi/log", "/api/admin/arsip", "/api/admin/jam",
                  "/api/admin/aktivitas", "/api/admin/ekspor.csv"):
        assert client.get(jalur).status_code == 401
    assert client.post("/api/admin/jam/majukan", json={"hari": 1}).status_code == 401
    assert client.post("/peta/zona", json=dict(kode="Z", nama="Z", panjang=5, kedalaman=3)).status_code == 401

    invalid = client.post("/admin/login", json={"username": "admin", "password": "salah"})
    assert invalid.status_code == 401

    valid = client.post("/admin/login", json={"username": "admin", "password": "admin123"})
    assert valid.status_code == 200
    assert client.get("/admin").status_code == 200
    assert client.get("/antrean").status_code == 200

    client.post("/admin/logout")
    assert client.get("/api/admin/ringkasan").status_code == 401
