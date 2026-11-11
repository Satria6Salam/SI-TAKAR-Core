import base64
import binascii
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from algoritma.mlq_scoring import NAMA_QUEUE, nilai_queue
from algoritma.penjadwal import antrean_menunggu, jalankan_alokasi, posisi_dalam_queue
from database import config
from database.config import get_db
from database.models import (LogAktivitas, StatusAlokasi, StatusPendaftaran, StatusVerifikasi,
                             UMKM, Zona, catat)
from routers.admin_security import hash_password, require_admin
from routers.helpers import (alokasi_terkini, alokasi_to_out, catat_gagal, cek_kunci, cek_pin,
                             hapus_kunci, log_to_out, norm_telepon, samarkan_telepon,
                             umkm_dari_kode)
from schemas import DokumenIn, LupaKodeIn, StatusAntreanOut, UMKMCreate, UMKMOut

router = APIRouter(tags=["Pendaftaran & Antrean"])

_ALFABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # tanpa huruf/angka yang mirip (0/O, 1/I)
MAKS_UNGGAH = 2 * 1024 * 1024
_TANDA_BERKAS = ((b"\x89PNG\r\n\x1a\n", ".png"), (b"\xff\xd8\xff", ".jpg"), (b"%PDF-", ".pdf"))


def _kode_baru(db: Session) -> str:
    while True:
        kode = "STK-" + "".join(secrets.choice(_ALFABET) for _ in range(6))
        if not db.query(UMKM).filter(UMKM.kode_pendaftaran == kode).first():
            return kode


@router.get("/info")
def info_aturan():
    """Aturan yang berlaku (dipakai halaman publik untuk menjelaskan sistem)."""
    return {
        "domisili_pasar": config.DOMISILI_PASAR,
        "timeout_hari": config.TIMEOUT_HARI,
        "peringatan_hari": config.PERINGATAN_HARI,
        "preemption_hari": config.PREEMPTION_HARI,
        "maks_timeout": config.MAKS_TIMEOUT,
        "sewa_hari": config.SEWA_HARI,
        "aging_hari": config.AGING_HARI,
        "verifikasi_wajib": config.VERIFIKASI_WAJIB,
        "maks_unggah_mb": MAKS_UNGGAH // (1024 * 1024),
        "nama_queue": NAMA_QUEUE,
    }


@router.get("/pendaftaran/pratinjau")
def pratinjau_queue(domisili: str = "", jenis_usaha: str = "", status_khusus: bool = False,
                    jumlah_cabang: int = 0, sumber_produk: str = "buatan_sendiri"):
    """Hitung jalur antrean tanpa menyimpan apa pun (pratinjau langsung di formulir)."""
    level, alasan = nilai_queue(domisili, jenis_usaha, status_khusus, jumlah_cabang, sumber_produk)
    return {"queue_level": level, "nama_queue": NAMA_QUEUE[level], "alasan": alasan}


def daftarkan(db: Session, data: UMKMCreate, now=None, langsung_antre: bool | None = None) -> UMKM:
    """Skoring MLQ lalu simpan pendaftar (dipakai endpoint dan pengisi data contoh).

    Bila verifikasi wajib, pendaftar menunggu pemeriksaan dokumen dulu. Urutan antreannya tetap
    dihitung dari waktu daftar, jadi lamanya pemeriksaan tidak merugikan pendaftar.
    """
    now = now or sekarang(db)
    wajib = config.VERIFIKASI_WAJIB if langsung_antre is None else not langsung_antre
    ganda = (db.query(UMKM)
             .filter(UMKM.nik == data.nik,
                     UMKM.status_pendaftaran.in_(StatusPendaftaran.BERJALAN)).first())
    if ganda:
        raise HTTPException(409, "NIK ini masih memiliki pendaftaran yang berjalan "
                                 f"({ganda.nama_usaha}). Satu pemilik hanya boleh satu antrean. "
                                 "Bila lupa kodenya, gunakan menu Lupa Kode.")
    zona_terpanjang = max((z.panjang for z in db.query(Zona).all()), default=None)
    if zona_terpanjang is not None and data.kebutuhan_muka > zona_terpanjang:
        raise HTTPException(422, f"Kebutuhan {data.kebutuhan_muka:g} m melebihi zona terpanjang "
                                 f"di pasar ({zona_terpanjang:g} m).")

    level, alasan = nilai_queue(data.domisili, data.jenis_usaha, data.status_khusus,
                                data.jumlah_cabang, data.sumber_produk)
    isian = data.model_dump(exclude={"pin"})
    isian["telepon"] = norm_telepon(data.telepon)
    umkm = UMKM(
        **isian, kode_pendaftaran=_kode_baru(db), pin_hash=hash_password(data.pin),
        queue_level=level, queue_awal=level, alasan_queue="\n".join(alasan),
        waktu_daftar=now, waktu_antre=now,
        status_pendaftaran=(StatusPendaftaran.MENUNGGU_VERIFIKASI if wajib
                            else StatusPendaftaran.MENUNGGU),
        status_verifikasi=StatusVerifikasi.BELUM if wajib else StatusVerifikasi.OTOMATIS,
    )
    db.add(umkm)
    db.flush()
    lanjut = ("menunggu verifikasi dokumen oleh pengelola" if wajib
              else f"butuh muka {umkm.kebutuhan_muka:g} m")
    catat(db, "Pendaftaran", umkm_id=umkm.id, waktu=now, keterangan=(
        f"{umkm.nama_usaha} dinilai Queue {level} ({NAMA_QUEUE[level]}); {lanjut}."))
    db.commit()
    return umkm


@router.post("/pendaftaran", response_model=StatusAntreanOut, status_code=201)
def daftar_umkm(data: UMKMCreate, db: Session = Depends(get_db)):
    """Daftarkan UMKM baru -> skoring MLQ -> (verifikasi) -> antrean -> alokasi Worst-Fit."""
    umkm = daftarkan(db, data)
    jalankan_alokasi(db)  # kalau sudah boleh mengantre dan ada ruang yang muat, langsung dipanggil
    return _status(db, umkm)


# ---------- Dokumen (KTP & bukti status khusus) ----------
def simpan_dokumen(db: Session, umkm: UMKM, jenis: str, isi: bytes) -> str:
    """Validasi lalu simpan berkas ke folder unggahan lokal. Mengganti berkas lama bila ada."""
    if len(isi) > MAKS_UNGGAH:
        raise HTTPException(413, f"Ukuran berkas maksimal {MAKS_UNGGAH // (1024 * 1024)} MB")
    ext = next((e for tanda, e in _TANDA_BERKAS if isi.startswith(tanda)), None)
    if ext is None:
        raise HTTPException(415, "Berkas harus berupa foto JPG/PNG atau PDF")
    folder = Path(config.UNGGAHAN_DIR)
    folder.mkdir(parents=True, exist_ok=True)
    nama = f"{umkm.id}-{jenis}-{secrets.token_hex(4)}{ext}"
    (folder / nama).write_bytes(isi)

    kolom = "dokumen_ktp" if jenis == "ktp" else "dokumen_khusus"
    lama = getattr(umkm, kolom)
    if lama:
        (folder / lama).unlink(missing_ok=True)
    setattr(umkm, kolom, nama)
    return nama


@router.post("/pendaftaran/{kode}/dokumen")
def unggah_dokumen(kode: str, data: DokumenIn, db: Session = Depends(get_db)):
    """Unggah foto/PDF KTP atau bukti status khusus (wajib kode + PIN)."""
    umkm = umkm_dari_kode(db, kode)
    cek_pin(umkm, data.pin)
    if umkm.status_verifikasi in StatusVerifikasi.SUDAH_DIPUTUS:
        raise HTTPException(409, "Data sudah diputus pengelola; dokumen tidak bisa diganti lagi")
    if data.jenis == "khusus" and not umkm.status_khusus:
        raise HTTPException(422, "Pendaftaran ini tidak mengajukan status khusus")
    teks = data.data_base64.split(",", 1)[1] if data.data_base64.startswith("data:") else data.data_base64
    try:
        isi = base64.b64decode(teks, validate=True)
    except (binascii.Error, ValueError):
        raise HTTPException(422, "Isi berkas tidak terbaca")
    simpan_dokumen(db, umkm, data.jenis, isi)
    nama_jenis = "KTP" if data.jenis == "ktp" else "bukti status khusus"
    catat(db, "Dokumen", f"{nama_jenis} diunggah ({len(isi) // 1024} KB).",
          umkm_id=umkm.id, waktu=sekarang(db))
    db.commit()
    return {"jenis": data.jenis, "ukuran_kb": len(isi) // 1024}


# ---------- Lupa kode ----------
@router.post("/pendaftaran/lupa-kode")
def lupa_kode(data: LupaKodeIn, db: Session = Depends(get_db)):
    """Tampilkan semua pendaftaran milik NIK ini bila nomor teleponnya cocok."""
    kunci = f"lupa:{data.nik}"
    cek_kunci(kunci)
    telp = norm_telepon(data.telepon)
    rows = [u for u in db.query(UMKM).filter(UMKM.nik == data.nik).order_by(UMKM.id.desc()).all()
            if norm_telepon(u.telepon) == telp]
    if not rows:
        catat_gagal(kunci)
        raise HTTPException(404, "Tidak ada pendaftaran dengan NIK dan nomor telepon tersebut")
    hapus_kunci(kunci)
    return [{
        "kode_pendaftaran": u.kode_pendaftaran, "nama_usaha": u.nama_usaha,
        "status_pendaftaran": u.status_pendaftaran, "queue_level": u.queue_level,
        "waktu_daftar": u.waktu_daftar,
    } for u in rows]


# ---------- Status & antrean ----------
@router.get("/pendaftaran/{kode}/status", response_model=StatusAntreanOut)
def status_antrean(kode: str, db: Session = Depends(get_db)):
    """Dasbor Status Antrean: jalur queue, posisi, alokasi terkini, dan riwayat."""
    return _status(db, umkm_dari_kode(db, kode))


@router.get("/antrean")
def daftar_antrean(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Manajemen Antrean MLQ (admin): pendaftar yang mengantre per Queue, sudah terurut."""
    hasil = {"queue_1": [], "queue_2": [], "queue_3": []}
    for u in antrean_menunggu(db).all():
        hasil[f"queue_{u.queue_level}"].append(UMKMOut.model_validate(u))
    return hasil


def _status(db: Session, umkm: UMKM) -> StatusAntreanOut:
    db.refresh(umkm)
    now = sekarang(db)
    a = alokasi_terkini(db, umkm.id)
    if a and a.status_alokasi == StatusAlokasi.DIBATALKAN and \
            umkm.status_pendaftaran == StatusPendaftaran.MENUNGGU:
        a = None  # sudah kembali ke antrean, alokasi lama cukup terlihat di riwayat

    riwayat = (db.query(LogAktivitas).filter(LogAktivitas.umkm_id == umkm.id)
               .order_by(LogAktivitas.id.desc()).limit(15).all())
    out = UMKMOut.model_validate(umkm)
    out.telepon = samarkan_telepon(out.telepon)   # halaman publik cukup dengan kode
    return StatusAntreanOut(
        umkm=out,
        posisi_dalam_queue=posisi_dalam_queue(db, umkm),
        jumlah_di_queue=antrean_menunggu(db).filter(UMKM.queue_level == umkm.queue_level).count(),
        alokasi=alokasi_to_out(a, now) if a else None,
        riwayat=[log_to_out(r) for r in riwayat],
        waktu_server=now,
    )
