import base64
import binascii
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from sqlalchemy.orm import Session

from algoritma.jam import sekarang
from datetime import timedelta

from algoritma.mlq_scoring import NAMA_QUEUE, nilai_queue, penalti_rekam_jejak
from algoritma.penjadwal import (alokasi_otomatis, antrean_menunggu, jalankan_alokasi,
                                 posisi_dalam_queue, rencana_putaran)
from database import config
from database.config import get_db
from database.models import (ArsipPelanggaran, LogAktivitas, StatusAlokasi, StatusPendaftaran, StatusVerifikasi,
                             UMKM, Zona, catat)
from routers.admin_security import (SELLER_COOKIE, SELLER_TTL_SECONDS, create_seller_token,
                                    get_seller_kode, hash_password, require_admin)
from routers.helpers import (alokasi_terkini, alokasi_to_out, catat_gagal, cek_kunci, cek_pin,
                             hapus_kunci, log_to_out, norm_telepon, pastikan_pemilik,
                             samarkan_telepon, umkm_dari_kode)
from schemas import (DokumenIn, LupaKodeIn, MasukPenjualIn, StatusAntreanOut, UMKMCreate,
                     UMKMOut)

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
        "putaran_alokasi": config.PUTARAN_ALOKASI,
        "putaran_harian_jam": config.PUTARAN_HARIAN_JAM,
        "penalti_hari": config.PENALTI_HARI,
        "maks_unggah_mb": MAKS_UNGGAH // (1024 * 1024),
        "nama_queue": NAMA_QUEUE,
    }


@router.get("/pendaftaran/pratinjau")
def pratinjau_queue(domisili: str = "", jenis_usaha: str = "", status_khusus: bool = False,
                    jumlah_cabang: int = 0, sumber_produk: str = "buatan_sendiri"):
    """Hitung jalur antrean tanpa menyimpan apa pun (pratinjau langsung di formulir)."""
    level, alasan = nilai_queue(domisili, jenis_usaha, status_khusus, jumlah_cabang, sumber_produk)
    return {"queue_level": level, "nama_queue": NAMA_QUEUE[level], "alasan": alasan}


def rekam_jejak(db: Session, nik: str, now) -> list[tuple]:
    """Pelanggaran berat milik NIK ini dalam PENALTI_HARI terakhir, terbaru dulu."""
    if config.PENALTI_HARI <= 0:
        return []
    batas = now - timedelta(days=config.PENALTI_HARI)
    hasil = []
    for u in db.query(UMKM).filter(UMKM.nik == nik).all():
        if u.status_pendaftaran == StatusPendaftaran.DICABUT:
            jenis = "Preemption"
        elif u.status_pendaftaran == StatusPendaftaran.GUGUR:
            jenis = "Gugur"
        else:
            continue
        waktu = (db.query(ArsipPelanggaran.waktu_kejadian)
                 .filter(ArsipPelanggaran.umkm_id == u.id)
                 .order_by(ArsipPelanggaran.waktu_kejadian.desc()).limit(1).scalar())
        if waktu and waktu >= batas:
            hasil.append((jenis, f"{waktu:%d-%m-%Y}", waktu))
    hasil.sort(key=lambda x: x[2], reverse=True)
    return [(j, t) for j, t, _ in hasil]


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
    level, alasan = penalti_rekam_jejak(level, alasan, rekam_jejak(db, data.nik, now))
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


def _dengan_sesi(request: Request, kode: str, isi: StatusAntreanOut, status_code: int = 200):
    """Balasan JSON + cookie sesi penjual untuk kode ini."""
    resp = JSONResponse(isi.model_dump(mode="json"), status_code=status_code)
    resp.set_cookie(SELLER_COOKIE, create_seller_token(kode), max_age=SELLER_TTL_SECONDS,
                    httponly=True, samesite="lax", secure=request.url.scheme == "https", path="/")
    return resp


@router.post("/pendaftaran", response_model=StatusAntreanOut, status_code=201)
def daftar_umkm(data: UMKMCreate, request: Request, db: Session = Depends(get_db)):
    """Daftarkan UMKM baru -> skoring MLQ -> (verifikasi) -> antrean -> alokasi Worst-Fit.

    Pendaftar langsung masuk (sesi) karena baru saja membuat PIN-nya sendiri.
    """
    umkm = daftarkan(db, data)
    alokasi_otomatis(db)  # mode "langsung": dibagi seketika; mode "manual": tunggu putaran
    return _dengan_sesi(request, umkm.kode_pendaftaran, _status(db, umkm), 201)


# ---------- Sesi penjual: hanya pemilik kode + PIN yang bisa membuka data pendaftarannya ----------
@router.post("/penjual/masuk", response_model=StatusAntreanOut)
def masuk_penjual(data: MasukPenjualIn, request: Request, db: Session = Depends(get_db)):
    umkm = umkm_dari_kode(db, data.kode)
    cek_pin(umkm, data.pin)
    return _dengan_sesi(request, umkm.kode_pendaftaran, _status(db, umkm))


@router.post("/penjual/keluar")
def keluar_penjual():
    resp = JSONResponse({"ok": True})
    resp.delete_cookie(SELLER_COOKIE, path="/")
    return resp


@router.get("/penjual/saya", response_model=StatusAntreanOut)
def pendaftaran_saya(request: Request, db: Session = Depends(get_db)):
    """Status milik penjual yang sedang masuk di browser ini."""
    kode = get_seller_kode(request)
    if not kode:
        raise HTTPException(401, "Masuk dulu dengan kode pendaftaran dan PIN")
    return _status(db, umkm_dari_kode(db, kode))


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
def unggah_dokumen(kode: str, data: DokumenIn, request: Request, db: Session = Depends(get_db)):
    """Unggah foto/PDF KTP atau bukti status khusus (pemilik: PIN atau sesi masuk)."""
    umkm = umkm_dari_kode(db, kode)
    pastikan_pemilik(request, umkm, data.pin)
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
def status_antrean(kode: str, request: Request, db: Session = Depends(get_db)):
    """Dasbor Status Antrean (khusus pemilik yang sudah masuk dengan kode + PIN)."""
    # Sesi diperiksa lebih dulu supaya orang lain tidak bisa menebak kode mana yang ada
    if get_seller_kode(request) != kode.strip().upper():
        raise HTTPException(401, "Masuk dulu dengan kode pendaftaran dan PIN")
    return _status(db, umkm_dari_kode(db, kode))


@router.get("/antrean")
def daftar_antrean(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Manajemen Antrean MLQ (admin): pendaftar yang mengantre per Queue, sudah terurut."""
    hasil = {"queue_1": [], "queue_2": [], "queue_3": []}
    for u in antrean_menunggu(db).all():
        hasil[f"queue_{u.queue_level}"].append(UMKMOut.model_validate(u))
    return hasil


def _rencana_out(db: Session) -> dict:
    rencana = rencana_putaran(db)
    baris = [{
        "giliran": r.giliran, "id": r.umkm.id, "kode_pendaftaran": r.umkm.kode_pendaftaran,
        "nama_usaha": r.umkm.nama_usaha, "nama_pemilik": r.umkm.nama_pemilik,
        "queue_level": r.umkm.queue_level, "kebutuhan_muka": r.umkm.kebutuhan_muka,
        "waktu_antre": r.umkm.waktu_antre, "jumlah_timeout": r.umkm.jumlah_timeout,
        "alasan_queue": [b for b in (r.umkm.alasan_queue or "").splitlines() if b],
        "dapat": r.hole is not None,
        "zona": r.hole.zona_kode if r.hole else None,
        "mulai": r.hole.mulai if r.hole else None,
    } for r in rencana]
    return {
        "mode": config.PUTARAN_ALOKASI,
        "jumlah_menunggu": len(baris),
        "akan_dapat": sum(1 for b in baris if b["dapat"]),
        "menunggu_verifikasi": db.query(UMKM).filter(
            UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU_VERIFIKASI).count(),
        "rencana": baris,
    }


@router.get("/antrean/putaran")
def pratinjau_putaran(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Pratinjau putaran alokasi: urutan giliran Q1 -> Q2 -> Q3 dan siapa akan dapat ruang di mana."""
    return _rencana_out(db)


@router.post("/antrean/putaran")
def jalankan_putaran(db: Session = Depends(get_db), _admin=Depends(require_admin)):
    """Jalankan satu putaran alokasi MLQ + Worst-Fit untuk semua pendaftar yang menunggu."""
    now = sekarang(db)
    sebelum = db.query(UMKM).filter(UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU).count()
    baru = jalankan_alokasi(db, now)
    catat(db, "Putaran Alokasi", waktu=now, keterangan=(
        f"Putaran dijalankan: {len(baru)} dari {sebelum} pendaftar mendapat lapak "
        f"(urutan Queue 1 -> 2 -> 3)."))
    db.commit()
    return {"dialokasikan": len(baru), "sebelumnya_menunggu": sebelum,
            "lapak": [a.lapak.kode_lapak for a in baru], **_rencana_out(db)}


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
