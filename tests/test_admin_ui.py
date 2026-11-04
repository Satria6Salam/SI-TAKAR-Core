from database.models import Admin
from seed import hash_password


def test_invited_admin_registration_and_admin_login(client, db, monkeypatch):
    monkeypatch.delenv("ADMIN_REGISTRATION_KEY", raising=False)
    assert client.post(
        "/admin/daftar-undangan",
        json={"username": "belum-aktif", "password": "password123", "kode_undangan": "apa-pun"},
    ).status_code == 503

    monkeypatch.setenv("ADMIN_REGISTRATION_KEY", "kunci-undangan-uji")
    db.add(Admin(username="pengelola", password_hash=hash_password("rahasia123")))
    db.commit()

    admin_page = client.get("/ui/admin.html")
    assert admin_page.status_code == 200
    assert 'id="stall-grid"' in admin_page.text
    assert 'id="deadlock-log"' in admin_page.text
    assert client.post("/admin/daftar", json={"username": "baru", "password": "password123"}).status_code == 401
    assert client.post(
        "/admin/daftar-undangan",
        json={"username": "baru", "password": "password123", "kode_undangan": "salah"},
    ).status_code == 403
    created = client.post(
        "/admin/daftar-undangan",
        json={"username": "baru", "password": "password123", "kode_undangan": "kunci-undangan-uji"},
    )
    assert created.status_code == 201
    assert "berhasil dibuat" in created.json()["pesan"]
    assert client.post(
        "/admin/daftar-undangan",
        json={"username": "baru", "password": "password123", "kode_undangan": "kunci-undangan-uji"},
    ).status_code == 409

    login = client.post(
        "/admin/login",
        data={"username": "baru", "password": "password123"},
    )
    assert login.status_code == 200
    token = login.json()["access_token"]
    headers = {"Authorization": f"Bearer {token}"}
    assert client.get("/antrean").status_code == 401
    assert client.get("/antrean", headers=headers).json() == {
        "queue_1": [],
        "queue_2": [],
        "queue_3": [],
    }
    assert client.get("/peta").json()["ringkasan"] == {
        "kosong": 0,
        "dipesan": 0,
        "terisi": 0,
    }

    applicant = client.post(
        "/pendaftaran",
        json={
            "nama_pemilik": "Sari",
            "nama_usaha": "Kriya Sari",
            "domisili": "Kota Contoh",
            "jenis_usaha": "kriya",
            "nik": "3578012345678901",
            "nomor_telepon": "081234567890",
            "email": "sari@example.com",
            "deskripsi": "Kerajinan tenun ikat lokal khas daerah",
        },
    ).json()
    umkm_id = applicant["umkm"]["id"]
    assert client.get("/admin/pendaftar").status_code == 401
    applicant_rows = client.get("/admin/pendaftar", headers=headers).json()
    assert applicant_rows[0]["nama_usaha"] == "Kriya Sari"
    assert applicant_rows[0]["nik"] == "3578012345678901"
    assert applicant_rows[0]["nomor_telepon"] == "081234567890"
    assert applicant_rows[0]["email"] == "sari@example.com"
    assert applicant_rows[0]["deskripsi"] == "Kerajinan tenun ikat lokal khas daerah"
    assert applicant_rows[0]["verifikasi"] is None

    # Step 1: Admin menandai Perlu Perbaikan
    revision = client.post(
        f"/admin/pendaftar/{umkm_id}/verifikasi",
        json={"status": "Perlu Perbaikan", "catatan": "Foto KTP buram, harap perbarui"},
        headers=headers,
    )
    assert revision.status_code == 200
    user_status = client.get(f"/pendaftaran/{umkm_id}/status").json()
    assert user_status["verifikasi"]["status"] == "Perlu Perbaikan"
    assert user_status["verifikasi"]["catatan"] == "Foto KTP buram, harap perbarui"
    assert user_status["verifikasi"]["nama_verifikator"] == "baru"

    # Step 2: Admin menandai Terverifikasi
    verified = client.post(
        f"/admin/pendaftar/{umkm_id}/verifikasi",
        json={"status": "Terverifikasi", "catatan": "Dokumen lengkap dan sah"},
        headers=headers,
    )
    assert verified.status_code == 200
    assert verified.json()["nama_verifikator"] == "baru"
    public_status = client.get(f"/pendaftaran/{umkm_id}/status").json()
    assert public_status["verifikasi"]["nama_verifikator"] == "baru"
    assert public_status["verifikasi"]["catatan"] == "Dokumen lengkap dan sah"
    assert client.get("/admin/pendaftar", headers=headers).json()[0]["verifikasi"]["status"] == "Terverifikasi"

    created = client.post(
        "/admin/daftar",
        json={"username": "admin-baru", "password": "password123"},
        headers=headers,
    )
    assert created.status_code == 201
    assert created.json()["pesan"] == "Admin 'admin-baru' berhasil didaftarkan"
    assert client.get("/admin/saya", headers=headers).json()["username"] == "baru"
    assert client.post(
        "/admin/daftar",
        json={"username": "admin-baru", "password": "password123"},
        headers=headers,
    ).status_code == 409
