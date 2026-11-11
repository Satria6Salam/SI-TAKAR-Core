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
    assert client.post(f"/alokasi/{kode(u)}/konfirmasi", json={}).status_code == 422
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
