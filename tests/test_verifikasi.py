"""PIN penjual, unggah dokumen, verifikasi admin, lupa kode, dan atur ulang PIN."""
import base64

import pytest

from database import config
from seed import pdf_contoh
from tests.test_alur import PIN, PIN_JSON, daftar, kode, pendaftar, status, tambah_zona

PNG = b"\x89PNG\r\n\x1a\n" + b"\0" * 64


def b64(isi: bytes) -> str:
    return base64.b64encode(isi).decode()


def unggah(c, hasil, jenis="ktp", isi=None, pin=PIN):
    return c.post(f"/pendaftaran/{kode(hasil)}/dokumen",
                  json={"pin": pin, "jenis": jenis, "nama_file": "ktp.png",
                        "data_base64": b64(isi or PNG)})


def nik_dari(c, uid):
    return c.get(f"/api/admin/umkm/{uid}").json()["umkm"]["nik"]


@pytest.fixture()
def wajib(monkeypatch):
    monkeypatch.setattr(config, "VERIFIKASI_WAJIB", True)


# ---------- PIN ----------
def test_aksi_penjual_wajib_pin_benar(client):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={"pin": "000000"}).status_code == 403
    client.post("/penjual/keluar")                       # tanpa sesi dan tanpa PIN -> ditolak
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={}).status_code == 401
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={"pin": "12"}).status_code == 422
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON).status_code == 200


def test_pin_terkunci_setelah_5_kali_salah(client):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    for _ in range(5):
        assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={"pin": "999999"}).status_code == 403
    # PIN benar pun ditolak sementara
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON).status_code == 429


def test_pin_wajib_6_digit_saat_daftar(client):
    assert client.post("/pendaftaran", json=pendaftar(pin="12")).status_code == 422


def test_status_publik_menyamarkan_telepon(client):
    u = daftar(client, telepon="081234567890")
    assert status(client, u)["umkm"]["telepon"] == "0812*****890"


# ---------- Verifikasi ----------
def test_pendaftar_menunggu_verifikasi_dan_tidak_dialokasikan(client, wajib):
    tambah_zona(client, "A", 10)
    u = daftar(client)
    assert u["umkm"]["status_pendaftaran"] == "Menunggu Verifikasi"
    assert u["alokasi"] is None and u["posisi_dalam_queue"] is None
    assert client.get("/antrean").json()["queue_1"] == []
    assert [x["id"] for x in client.get("/api/admin/verifikasi").json()] == [u["umkm"]["id"]]


def test_terima_butuh_ktp_lalu_langsung_dapat_lapak(client, wajib):
    tambah_zona(client, "A", 10)
    u = daftar(client)
    uid = u["umkm"]["id"]
    r = client.post(f"/api/admin/umkm/{uid}/verifikasi", json={"keputusan": "terima"})
    assert r.status_code == 422 and "KTP" in r.json()["detail"]

    assert unggah(client, u).status_code == 200
    detail = client.get(f"/api/admin/umkm/{uid}").json()
    assert detail["umkm"]["punya_ktp"] and detail["umkm"]["url_ktp"]
    berkas = client.get(detail["umkm"]["url_ktp"])
    assert berkas.status_code == 200 and berkas.headers["content-type"] == "image/png"

    r = client.post(f"/api/admin/umkm/{uid}/verifikasi", json={"keputusan": "terima"})
    assert r.status_code == 200 and r.json()["status_verifikasi"] == "Terverifikasi"
    s = status(client, u)
    assert s["umkm"]["status_pendaftaran"] == "Menunggu Konfirmasi"
    assert s["alokasi"]["kode_lapak"] == "A-01"
    # setelah diputus, dokumen tidak bisa diganti
    assert unggah(client, u).status_code == 409


def test_klaim_khusus_tanpa_bukti_dinilai_ulang(client, wajib):
    u = daftar(client, jenis_usaha="kuliner", status_khusus=True)
    assert u["umkm"]["queue_level"] == 1
    unggah(client, u)
    uid = u["umkm"]["id"]
    assert client.post(f"/api/admin/umkm/{uid}/verifikasi",
                       json={"keputusan": "terima"}).status_code == 422   # bukti belum ada
    r = client.post(f"/api/admin/umkm/{uid}/verifikasi",
                    json={"keputusan": "tolak_klaim", "catatan": "Surat tidak dilampirkan"}).json()
    assert r["queue_level"] == 2 and r["status_khusus"] is False
    assert r["status_verifikasi"] == "Klaim Khusus Ditolak"
    assert status(client, u)["umkm"]["status_pendaftaran"] == "Menunggu"


def test_tolak_wajib_alasan_dan_masuk_arsip(client, wajib):
    u = daftar(client)
    uid = u["umkm"]["id"]
    assert client.post(f"/api/admin/umkm/{uid}/verifikasi", json={"keputusan": "tolak"}).status_code == 422
    r = client.post(f"/api/admin/umkm/{uid}/verifikasi",
                    json={"keputusan": "tolak", "catatan": "KTP tidak terbaca"})
    assert r.json()["status_pendaftaran"] == "Ditolak"
    assert status(client, u)["umkm"]["catatan_verifikasi"] == "KTP tidak terbaca"
    assert [a["umkm"]["id"] for a in client.get("/api/admin/arsip").json()] == [uid]
    # NIK yang sama boleh mendaftar ulang setelah ditolak
    assert client.post("/pendaftaran", json=pendaftar(nik=nik_dari(client, uid))).status_code == 201


def test_urutan_antrean_mengikuti_waktu_daftar_bukan_waktu_verifikasi(client, wajib):
    awal = daftar(client, nama_usaha="Daftar Duluan")
    akhir = daftar(client, nama_usaha="Daftar Belakangan")
    for u in (akhir, awal):   # yang daftar belakangan diverifikasi lebih dulu
        unggah(client, u)
        client.post(f"/api/admin/umkm/{u['umkm']['id']}/verifikasi", json={"keputusan": "terima"})
    assert status(client, awal)["posisi_dalam_queue"] == 1
    assert status(client, akhir)["posisi_dalam_queue"] == 2


def test_validasi_berkas_unggahan(client, wajib):
    u = daftar(client)
    assert unggah(client, u, isi=b"bukan gambar sama sekali").status_code == 415
    assert unggah(client, u, isi=PNG + b"\0" * (2 * 1024 * 1024)).status_code == 413
    assert unggah(client, u, pin="111111").status_code == 403
    assert unggah(client, u, jenis="khusus").status_code == 422   # tidak mengajukan status khusus
    assert unggah(client, u, isi=pdf_contoh("KTP")).status_code == 200


# ---------- Lupa kode & reset PIN ----------
def test_lupa_kode_dengan_nik_dan_telepon(client):
    u = daftar(client, telepon="0812-3456-789")
    nik = nik_dari(client, u["umkm"]["id"])
    r = client.post("/pendaftaran/lupa-kode", json={"nik": nik, "telepon": "+62 812 3456 789"})
    assert r.status_code == 200 and r.json()[0]["kode_pendaftaran"] == kode(u)
    assert client.post("/pendaftaran/lupa-kode",
                       json={"nik": nik, "telepon": "0899999999"}).status_code == 404


def test_lupa_kode_terkunci_setelah_5_kali_salah(client):
    u = daftar(client, telepon="081111111111")
    nik = nik_dari(client, u["umkm"]["id"])
    for _ in range(5):
        client.post("/pendaftaran/lupa-kode", json={"nik": nik, "telepon": "0800000000"})
    r = client.post("/pendaftaran/lupa-kode", json={"nik": nik, "telepon": "081111111111"})
    assert r.status_code == 429


def test_admin_cari_dan_atur_ulang_pin(client):
    tambah_zona(client, "A", 2)
    u = daftar(client, nama_usaha="Gerabah Unik", telepon="081277788899")
    assert [x["kode_pendaftaran"] for x in client.get("/api/admin/pendaftar?q=gerabah").json()] == [kode(u)]
    assert len(client.get("/api/admin/pendaftar?q=0812777").json()) == 1
    assert len(client.get(f"/api/admin/pendaftar?q={kode(u)}").json()) == 1

    baru = client.post(f"/api/admin/umkm/{u['umkm']['id']}/reset-pin").json()["pin_baru"]
    assert len(baru) == 6 and baru.isdigit()
    if baru != PIN:
        assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON).status_code == 403
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={"pin": baru}).status_code == 200


def test_api_admin_baru_wajib_login(client):
    client.post("/admin/logout")
    for jalur in ("/api/admin/verifikasi", "/api/admin/pendaftar", "/api/admin/umkm/1",
                  "/api/admin/dokumen/1/ktp"):
        assert client.get(jalur).status_code == 401
    assert client.post("/api/admin/umkm/1/reset-pin").status_code == 401
    assert client.get("/admin/verifikasi", follow_redirects=False).status_code == 303


# ---------- Privasi antar-penjual & absen harian ----------
def test_penjual_tidak_bisa_membuka_status_penjual_lain(client):
    a = daftar(client, nama_usaha="Penjual A")
    b = daftar(client, nama_usaha="Penjual B")          # browser kini masuk sebagai B
    assert client.get(f"/pendaftaran/{kode(a)}/status").status_code == 401
    assert client.get(f"/pendaftaran/{kode(b)}/status").status_code == 200
    assert client.get("/penjual/saya").json()["umkm"]["kode_pendaftaran"] == kode(b)
    # kode orang lain tanpa PIN yang benar tetap tertutup
    assert client.post("/penjual/masuk", json={"kode": kode(a), "pin": "000000"}).status_code == 403
    client.post("/penjual/keluar")
    assert client.get("/penjual/saya").status_code == 401
    assert client.get(f"/pendaftaran/{kode(b)}/status").status_code == 401


def test_sesi_admin_tidak_berlaku_sebagai_sesi_penjual(client):
    u = daftar(client)
    client.post("/penjual/keluar")
    assert client.get(f"/pendaftaran/{kode(u)}/status").status_code == 401   # admin masih login


def test_aksi_tanpa_pin_butuh_sesi_pemilik(client):
    tambah_zona(client, "A", 4)
    a = daftar(client, nama_usaha="A")
    b = daftar(client, nama_usaha="B")                   # sesi milik B
    assert client.post(f"/alokasi/{kode(a)}/konfirmasi").status_code == 401
    assert client.post(f"/alokasi/{kode(b)}/konfirmasi").status_code == 200


def test_absen_harian_tercatat(client):
    tambah_zona(client, "A", 2)
    u = daftar(client)
    client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)
    awal = status(client, u)["alokasi"]
    assert awal["sudah_absen_hari_ini"] is False and awal["terakhir_absen"] is None   # konfirmasi bukan absen
    r = client.post(f"/alokasi/{kode(u)}/absen").json()                             # pakai sesi
    assert r["sudah_absen_hari_ini"] is True and r["terakhir_absen"]
    # keesokan harinya kembali "belum"
    client.post("/api/admin/jam/majukan", json={"hari": 1})
    assert status(client, u)["alokasi"]["sudah_absen_hari_ini"] is False


# ---------- Putaran alokasi MLQ (mode manual) ----------
@pytest.fixture()
def manual(monkeypatch):
    monkeypatch.setattr(config, "PUTARAN_ALOKASI", "manual")


def test_putaran_mendahulukan_queue1_walau_q3_siap_lebih_dulu(client, manual):
    tambah_zona(client, "A", 4)
    q3 = daftar(client, nama_usaha="Reseller Cepat", sumber_produk="reseller", kebutuhan_muka=3)
    q2 = daftar(client, nama_usaha="Kuliner", jenis_usaha="kuliner", kebutuhan_muka=2)
    q1 = daftar(client, nama_usaha="Pengrajin", kebutuhan_muka=2)
    # mode manual: belum ada yang langsung mendapat lapak
    assert all(u["alokasi"] is None for u in (q3, q2, q1))

    pra = client.get("/antrean/putaran").json()
    assert [r["nama_usaha"] for r in pra["rencana"]] == ["Pengrajin", "Kuliner", "Reseller Cepat"]
    assert [r["dapat"] for r in pra["rencana"]] == [True, True, False]   # 4 m: 2 + 2, Q3 tidak muat

    hasil = client.post("/antrean/putaran").json()
    assert hasil["dialokasikan"] == 2 and hasil["jumlah_menunggu"] == 1
    assert status(client, q1)["alokasi"]["mulai"] == 0
    assert status(client, q3)["umkm"]["status_pendaftaran"] == "Menunggu"


def test_putaran_wajib_admin(client):
    client.post("/admin/logout")
    assert client.get("/antrean/putaran").status_code == 401
    assert client.post("/antrean/putaran").status_code == 401


# ---------- Logika lanjutan ----------
def test_pernah_dicabut_turun_satu_tingkat_saat_daftar_ulang(client, db):
    from datetime import timedelta

    from algoritma.deadlock_cron import jalankan_semua
    from database.config import utcnow
    from database.models import AlokasiSewa

    tambah_zona(client, "A", 2)
    u = daftar(client, nik="5555000000000001")
    client.post(f"/alokasi/{kode(u)}/konfirmasi", json=PIN_JSON)
    row = db.get(AlokasiSewa, u["alokasi"]["id"])
    row.terakhir_aktif = utcnow() - timedelta(days=15)
    db.commit()
    assert jalankan_semua(db)["preemption"] == [u["umkm"]["id"]]

    ulang = daftar(client, nik="5555000000000001")          # kriya lokal = Q1, tapi pernah dicabut
    assert ulang["umkm"]["queue_level"] == 2 and ulang["umkm"]["queue_awal"] == 2
    assert any("Rekam jejak" in a for a in ulang["umkm"]["alasan_queue"])
    # NIK lain tanpa riwayat tetap Q1
    assert daftar(client, nik="5555000000000002")["umkm"]["queue_level"] == 1


def test_putaran_harian_otomatis_sekali_sehari(client, db, manual, monkeypatch):
    from datetime import datetime

    from algoritma.deadlock_cron import jalankan_semua

    monkeypatch.setattr(config, "PUTARAN_HARIAN_JAM", 7)
    tambah_zona(client, "A", 4)
    u = daftar(client)
    pagi = datetime(2026, 11, 12, 1, 0)            # 08.00 WIB
    assert jalankan_semua(db, now=pagi)["putaran_harian"] == 1
    db.expire_all()
    assert status(client, u)["alokasi"]["kode_lapak"] == "A-01"
    daftar(client, nama_usaha="Kedua")
    assert jalankan_semua(db, now=pagi.replace(hour=5))["putaran_harian"] == 0   # hari yang sama
    subuh = datetime(2026, 11, 12, 22, 0)          # 05.00 WIB besoknya, belum jam 7
    assert jalankan_semua(db, now=subuh)["putaran_harian"] == 0
    besok = datetime(2026, 11, 13, 0, 30)          # 07.30 WIB
    assert jalankan_semua(db, now=besok)["putaran_harian"] == 1
