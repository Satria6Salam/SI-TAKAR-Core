
"""Autentikasi Admin: login, pendaftaran akun admin baru, dan verifikasi berkas pendaftar."""
import hashlib
import hmac
import os

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from database.config import get_db
from database.models import Admin, UMKM, VerifikasiPendaftaran
from routers.auth import buat_token, get_current_admin, verify_password

router = APIRouter(prefix="/admin", tags=["Admin & Autentikasi"])


# ---- Schema ----

class Token(BaseModel):
    access_token: str
    token_type: str = "bearer"


class AdminCreate(BaseModel):
    username: str = Field(min_length=3, description="Minimal 3 karakter")
    password: str = Field(min_length=6, description="Minimal 6 karakter")


class AdminInviteCreate(AdminCreate):
    kode_undangan: str = Field(min_length=1)


class VerifikasiCreate(BaseModel):
    status: str = Field(pattern="^(Terverifikasi|Perlu Perbaikan)$")
    catatan: str | None = None


# ---- Helpers ----

def _hash_password(password: str) -> str:
    """Hash password dengan PBKDF2-HMAC-SHA256 + random salt (format: salt_hex$dk_hex)."""
    salt = os.urandom(16)
    dk = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100_000)
    return f"{salt.hex()}${dk.hex()}"


# ---- Endpoints ----

@router.post("/login", response_model=Token, summary="Login admin")
def login_admin(
    form: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    admin = db.query(Admin).filter(Admin.username == form.username).first()
    if not admin or not verify_password(form.password, admin.password_hash):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Username atau password salah",
            headers={"WWW-Authenticate": "Bearer"},
        )
    token = buat_token({"sub": admin.username})
    return Token(access_token=token)


@router.post("/daftar", status_code=201, summary="Tambah akun admin baru")
def daftar_admin(
    data: AdminCreate,
    db: Session = Depends(get_db),
    _admin: Admin = Depends(get_current_admin),
):
    if db.query(Admin).filter(Admin.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username sudah dipakai")
    db.add(Admin(username=data.username, password_hash=_hash_password(data.password)))
    db.commit()
    return {"pesan": f"Admin '{data.username}' berhasil didaftarkan"}


@router.post("/daftar-undangan", status_code=201, summary="Daftar akun admin dengan kode undangan")
def daftar_admin_dengan_undangan(data: AdminInviteCreate, db: Session = Depends(get_db)):
    kode_server = os.getenv("ADMIN_REGISTRATION_KEY")
    if not kode_server:
        raise HTTPException(status_code=503, detail="Pendaftaran admin belum diaktifkan")
    if not hmac.compare_digest(data.kode_undangan, kode_server):
        raise HTTPException(status_code=403, detail="Kode undangan tidak valid")
    if db.query(Admin).filter(Admin.username == data.username).first():
        raise HTTPException(status_code=409, detail="Username sudah dipakai")
    db.add(Admin(username=data.username, password_hash=_hash_password(data.password)))
    db.commit()
    return {"pesan": f"Akun admin '{data.username}' berhasil dibuat. Silakan masuk."}


@router.get("/saya", summary="Info admin yang sedang login")
def info_admin(admin: Admin = Depends(get_current_admin)):
    return {"id": admin.id, "username": admin.username}


@router.get("/pendaftar", summary="Daftar pendaftar lengkap untuk verifikasi")
def daftar_pendaftar(
    db: Session = Depends(get_db),
    _admin: Admin = Depends(get_current_admin),
):
    """Menampilkan seluruh input yang dimasukkan oleh pendaftar UMKM agar dibaca oleh Admin."""
    rows = db.query(UMKM).order_by(UMKM.waktu_daftar.desc(), UMKM.id.desc()).all()
    return [
        {
            "id": row.id,
            "nama_pemilik": row.nama_pemilik,
            "nama_usaha": row.nama_usaha,
            "domisili": row.domisili,
            "jenis_usaha": row.jenis_usaha,
            "nik": row.nik,
            "nomor_telepon": row.nomor_telepon,
            "email": row.email,
            "deskripsi": row.deskripsi,
            "status_khusus": row.status_khusus,
            "punya_toko_fisik": row.punya_toko_fisik,
            "produksi_sendiri": row.produksi_sendiri,
            "jumlah_cabang": row.jumlah_cabang,
            "modal_besar": row.modal_besar,
            "kebutuhan_luas": row.kebutuhan_luas,
            "nomor_pendaftaran": row.nomor_pendaftaran,
            "queue_level": row.queue_level,
            "status_pendaftaran": row.status_pendaftaran,
            "waktu_daftar": row.waktu_daftar,
            "verifikasi": (
                {
                    "status": row.verifikasi.status,
                    "nama_verifikator": row.verifikasi.admin.username,
                    "waktu_verifikasi": row.verifikasi.waktu_verifikasi,
                    "catatan": row.verifikasi.catatan,
                }
                if row.verifikasi
                else None
            ),
        }
        for row in rows
    ]


@router.post("/pendaftar/{umkm_id}/verifikasi", summary="Catat verifikasi pendaftar")
def verifikasi_pendaftar(
    umkm_id: int,
    data: VerifikasiCreate,
    db: Session = Depends(get_db),
    admin: Admin = Depends(get_current_admin),
):
    """Admin memberikan keputusan verifikasi (Terverifikasi/Perlu Perbaikan) & catatan."""
    umkm = db.get(UMKM, umkm_id)
    if umkm is None:
        raise HTTPException(status_code=404, detail="Pendaftar tidak ditemukan")

    verifikasi = db.query(VerifikasiPendaftaran).filter_by(umkm_id=umkm_id).first()
    if verifikasi is None:
        verifikasi = VerifikasiPendaftaran(umkm_id=umkm_id, admin_id=admin.id)
        db.add(verifikasi)
    verifikasi.admin_id = admin.id
    verifikasi.status = data.status
    verifikasi.catatan = data.catatan.strip() if data.catatan else None
    db.commit()
    db.refresh(verifikasi)
    return {
        "umkm_id": umkm_id,
        "status": verifikasi.status,
        "nama_verifikator": admin.username,
        "waktu_verifikasi": verifikasi.waktu_verifikasi,
        "catatan": verifikasi.catatan,
    }
