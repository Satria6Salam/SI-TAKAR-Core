import csv
import io
import secrets
from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import FileResponse, JSONResponse, RedirectResponse, Response
from pydantic import BaseModel
from sqlalchemy import func, or_
from sqlalchemy.orm import Session

import seed
from algoritma import jam
from algoritma.deadlock_cron import jalankan_semua
from algoritma.mlq_scoring import nilai_queue
from algoritma.penjadwal import jalankan_alokasi, posisi_dalam_queue
from database import config
from database.config import get_db
from database.models import (Admin, AlokasiSewa, ArsipPelanggaran, LogAktivitas,
                             StatusAlokasi, StatusPendaftaran, StatusVerifikasi, UMKM, catat)
from routers.admin_security import (
    SESSION_COOKIE,
    SESSION_TTL_SECONDS,
    create_session_token,
    get_admin_session,
    hash_password,
    require_admin,
    verify_password,
)
from routers.helpers import (alokasi_terkini, alokasi_to_out, hapus_kunci, log_to_out,
                             norm_telepon)
from schemas import LogOut, MajukanJam, UMKMOut, VerifikasiIn

router = APIRouter(tags=["Admin"])
api = APIRouter(prefix="/api/admin", tags=["Admin"], dependencies=[Depends(require_admin)])
TEMPLATES_DIR = Path(__file__).resolve().parents[1] / "templates"

# Halaman dashboard admin. Semuanya memakai satu kerangka HTML; admin.js menampilkan
# bagian yang sesuai alamatnya, jadi tiap menu punya URL dan halaman sendiri.
HALAMAN_ADMIN = ("", "verifikasi", "pendaftar", "denah", "antrean", "penyewa", "deadlock", "arsip")


class AdminLogin(BaseModel):
    username: str
    password: str


@router.get("/admin/login", include_in_schema=False)
def admin_login_page(request: Request, db: Session = Depends(get_db)):
    if get_admin_session(request, db):
        return RedirectResponse("/admin", status_code=303)
    return FileResponse(TEMPLATES_DIR / "admin_login.html")


@router.post("/admin/login")
def admin_login(data: AdminLogin, request: Request, db: Session = Depends(get_db)):
    admin = db.query(Admin).filter(Admin.username == data.username).first()
    if admin is None or not verify_password(data.password, admin.password_hash):
        raise HTTPException(status_code=401, detail="Username atau password tidak sesuai")

    response = JSONResponse({"ok": True, "redirect": "/admin"})
    response.set_cookie(
        SESSION_COOKIE,
        create_session_token(admin.username),
        max_age=SESSION_TTL_SECONDS,
        httponly=True,
        secure=request.url.scheme == "https",
        samesite="lax",
        path="/",
    )
    return response


@router.post("/admin/logout")
def admin_logout():
    response = JSONResponse({"ok": True, "redirect": "/admin/login"})
    response.delete_cookie(SESSION_COOKIE, path="/")
    return response


def _halaman_admin(request: Request, db: Session = Depends(get_db)):
    if get_admin_session(request, db) is None:
        return RedirectResponse("/admin/login", status_code=303)
    return FileResponse(TEMPLATES_DIR / "admin.html")


for _slug in HALAMAN_ADMIN:
    router.add_api_route(f"/admin/{_slug}".rstrip("/"), _halaman_admin, methods=["GET"],
                         include_in_schema=False, name=f"halaman_admin_{_slug or 'ringkasan'}")
router.add_api_route("/admin.html", _halaman_admin, methods=["GET"], include_in_schema=False)


# ================= API admin (semua wajib login) =================
@api.get("/ringkasan")
def admin_summary(db: Session = Depends(get_db)):
    counts = dict(
        db.query(UMKM.status_pendaftaran, func.count(UMKM.id))
        .group_by(UMKM.status_pendaftaran)
        .all()
    )
    now = jam.sekarang(db)
    berjalan = (db.query(AlokasiSewa)
                .filter(AlokasiSewa.status_alokasi.in_(StatusAlokasi.BERJALAN)).all())
    diperingatkan = sum(1 for a in berjalan if alokasi_to_out(a, now).peringatan)
    return {
        "total": sum(counts.values()), "status": counts,
        "menunggu_verifikasi": counts.get(StatusPendaftaran.MENUNGGU_VERIFIKASI, 0),
        "menunggu_konfirmasi": counts.get(StatusPendaftaran.MENUNGGU_KONFIRMASI, 0),
        "penyewa_peringatan": diperingatkan,
    }


# ---------- Jam simulasi (untuk mendemokan Timeout / Preemption / masa sewa) ----------
def _jam_out(db: Session) -> dict:
    g = jam.geser(db)
    return {"waktu_sistem": jam.sekarang(db), "geser_hari": round(g.total_seconds() / 86400, 2)}


@api.get("/jam")
def lihat_jam(db: Session = Depends(get_db)):
    return _jam_out(db)


@api.post("/jam/majukan")
def majukan_jam(data: MajukanJam, db: Session = Depends(get_db)):
    """Majukan jam sistem N hari lalu langsung jalankan satu siklus timer deadlock."""
    jam.majukan(db, data.hari)
    return {**_jam_out(db), "siklus": jalankan_semua(db)}


@api.post("/jam/reset")
def reset_jam(db: Session = Depends(get_db)):
    jam.atur_ulang(db)
    return _jam_out(db)


# ---------- Verifikasi dokumen ----------
def _umkm_admin(u: UMKM) -> dict:
    """Data UMKM lengkap untuk admin (termasuk NIK dan alamat dokumen)."""
    return {
        **UMKMOut.model_validate(u).model_dump(mode="json"),
        "nik": u.nik,
        "url_ktp": f"/api/admin/dokumen/{u.id}/ktp" if u.dokumen_ktp else None,
        "url_khusus": f"/api/admin/dokumen/{u.id}/khusus" if u.dokumen_khusus else None,
        "jenis_ktp": Path(u.dokumen_ktp).suffix[1:] if u.dokumen_ktp else None,
        "jenis_khusus": Path(u.dokumen_khusus).suffix[1:] if u.dokumen_khusus else None,
    }


def _get_umkm(db: Session, umkm_id: int) -> UMKM:
    u = db.get(UMKM, umkm_id)
    if u is None:
        raise HTTPException(404, "UMKM tidak ditemukan")
    return u


@api.get("/verifikasi")
def antrean_verifikasi(db: Session = Depends(get_db)):
    """Pendaftar yang menunggu pemeriksaan dokumen, yang paling lama di atas."""
    rows = (db.query(UMKM).filter(UMKM.status_pendaftaran == StatusPendaftaran.MENUNGGU_VERIFIKASI)
            .order_by(UMKM.waktu_daftar, UMKM.id).all())
    return [_umkm_admin(u) for u in rows]


@api.post("/umkm/{umkm_id}/verifikasi")
def putuskan_verifikasi(umkm_id: int, data: VerifikasiIn, db: Session = Depends(get_db)):
    """terima = data sah; tolak_klaim = sah tetapi tanpa status khusus (dinilai ulang); tolak = ditolak."""
    u = _get_umkm(db, umkm_id)
    if u.status_pendaftaran != StatusPendaftaran.MENUNGGU_VERIFIKASI:
        raise HTTPException(409, f"Pendaftar berstatus '{u.status_pendaftaran}', bukan menunggu verifikasi")
    now = jam.sekarang(db)
    catatan = (data.catatan or "").strip() or None

    if data.keputusan == "tolak":
        if not catatan:
            raise HTTPException(422, "Tuliskan alasan penolakan agar pendaftar mengetahuinya")
        u.status_pendaftaran = StatusPendaftaran.DITOLAK
        u.status_verifikasi = StatusVerifikasi.DITOLAK
        teks = f"Pendaftaran ditolak pengelola: {catatan}"
    else:
        if not u.dokumen_ktp:
            raise HTTPException(422, "KTP belum diunggah; pendaftar belum bisa diterima")
        if data.keputusan == "terima":
            if u.status_khusus and not u.dokumen_khusus:
                raise HTTPException(422, "Bukti status khusus belum ada. Pilih 'Terima tanpa status "
                                         "khusus' atau minta pendaftar mengunggahnya.")
            u.status_verifikasi = StatusVerifikasi.TERVERIFIKASI
            teks = f"Data terverifikasi; masuk antrean Queue {u.queue_level}."
        else:
            if not u.status_khusus:
                raise HTTPException(422, "Pendaftar ini tidak mengajukan status khusus")
            lama = u.queue_level
            u.status_khusus = False
            level, alasan = nilai_queue(u.domisili, u.jenis_usaha, False, u.jumlah_cabang,
                                        u.sumber_produk)
            u.queue_level = u.queue_awal = level
            u.alasan_queue = "\n".join(alasan)
            u.status_verifikasi = StatusVerifikasi.KLAIM_DITOLAK
            teks = (f"Klaim status khusus tidak terbukti; dinilai ulang dari Queue {lama} "
                    f"ke Queue {level}.")
        # urutan dihitung dari waktu daftar, bukan waktu diverifikasi
        u.status_pendaftaran = StatusPendaftaran.MENUNGGU
        if catatan:
            teks += f" Catatan: {catatan}"

    u.catatan_verifikasi = catatan
    u.waktu_verifikasi = now
    catat(db, "Verifikasi", teks, umkm_id=u.id, waktu=now)
    db.commit()
    jalankan_alokasi(db)
    db.refresh(u)
    return _umkm_admin(u)


@api.get("/dokumen/{umkm_id}/{jenis}")
def lihat_dokumen(umkm_id: int, jenis: str, db: Session = Depends(get_db)):
    u = _get_umkm(db, umkm_id)
    nama = {"ktp": u.dokumen_ktp, "khusus": u.dokumen_khusus}.get(jenis)
    if not nama:
        raise HTTPException(404, "Dokumen tidak ada")
    folder = Path(config.UNGGAHAN_DIR).resolve()
    path = (folder / nama).resolve()
    if folder not in path.parents or not path.is_file():
        raise HTTPException(404, "Dokumen tidak ditemukan di folder unggahan")
    jenis_media = {".png": "image/png", ".jpg": "image/jpeg", ".pdf": "application/pdf"}
    return FileResponse(path, media_type=jenis_media.get(path.suffix, "application/octet-stream"),
                        headers={"Cache-Control": "no-store"})


# ---------- Pendaftar: cari, detail, atur ulang PIN ----------
@api.get("/pendaftar")
def cari_pendaftar(q: str = "", status: str = "", db: Session = Depends(get_db)):
    """Cari berdasarkan nama usaha/pemilik, NIK, kode, atau nomor telepon."""
    query = db.query(UMKM)
    q = q.strip()
    if q:
        pola = f"%{q}%"
        angka = "".join(ch for ch in q if ch.isdigit())
        syarat = [UMKM.nama_usaha.ilike(pola), UMKM.nama_pemilik.ilike(pola),
                  UMKM.kode_pendaftaran.ilike(pola)]
        if len(angka) >= 4:
            syarat += [UMKM.nik.contains(angka), UMKM.telepon.contains(norm_telepon(angka))]
        query = query.filter(or_(*syarat))
    if status:
        query = query.filter(UMKM.status_pendaftaran == status)
    return [_umkm_admin(u) for u in query.order_by(UMKM.id.desc()).limit(200).all()]


@api.get("/umkm/{umkm_id}")
def detail_umkm(umkm_id: int, db: Session = Depends(get_db)):
    u = _get_umkm(db, umkm_id)
    now = jam.sekarang(db)
    a = alokasi_terkini(db, u.id)
    riwayat = (db.query(LogAktivitas).filter(LogAktivitas.umkm_id == u.id)
               .order_by(LogAktivitas.id.desc()).all())
    return {
        "umkm": _umkm_admin(u),
        "posisi_dalam_queue": posisi_dalam_queue(db, u),
        "alokasi": alokasi_to_out(a, now).model_dump(mode="json") if a else None,
        "jumlah_pelanggaran": db.query(ArsipPelanggaran).filter_by(umkm_id=u.id).count(),
        "riwayat": [log_to_out(r).model_dump(mode="json") for r in riwayat],
    }


@api.post("/umkm/{umkm_id}/reset-pin")
def atur_ulang_pin(umkm_id: int, db: Session = Depends(get_db)):
    """Untuk pendaftar yang lupa PIN (setelah admin mencocokkan KTP aslinya). PIN baru tampil sekali."""
    u = _get_umkm(db, umkm_id)
    pin = f"{secrets.randbelow(10 ** 6):06d}"
    u.pin_hash = hash_password(pin)
    hapus_kunci(f"pin:{u.kode_pendaftaran}")
    catat(db, "Reset PIN", "PIN diatur ulang oleh pengelola.", umkm_id=u.id, waktu=jam.sekarang(db))
    db.commit()
    return {"kode_pendaftaran": u.kode_pendaftaran, "pin_baru": pin}


# ---------- Penyimpanan: jurnal, arsip, ekspor ----------
@api.get("/aktivitas", response_model=list[LogOut])
def jurnal_aktivitas(limit: int = 60, db: Session = Depends(get_db)):
    """Jurnal seluruh kejadian sistem, terbaru dulu."""
    rows = (db.query(LogAktivitas).order_by(LogAktivitas.id.desc())
            .limit(max(1, min(limit, 500))).all())
    return [log_to_out(r) for r in rows]


@api.get("/arsip")
def arsip_umkm(db: Session = Depends(get_db)):
    """Buku arsip: UMKM yang sudah tidak menempati pasar (lulus, selesai, dicabut, gugur, ditolak)."""
    now = jam.sekarang(db)
    hasil = []
    rows = (db.query(UMKM).filter(UMKM.status_pendaftaran.in_(StatusPendaftaran.ARSIP))
            .order_by(UMKM.id.desc()).all())
    for u in rows:
        a = alokasi_terkini(db, u.id)
        hasil.append({
            "umkm": UMKMOut.model_validate(u).model_dump(mode="json"),
            "alokasi_terakhir": alokasi_to_out(a, now).model_dump(mode="json") if a else None,
            "jumlah_pelanggaran": db.query(ArsipPelanggaran).filter_by(umkm_id=u.id).count(),
        })
    return hasil


@api.get("/ekspor.csv")
def ekspor_csv(db: Session = Depends(get_db)):
    """Cadangan buku induk UMKM dalam bentuk CSV (bisa dibuka di Excel)."""
    now = jam.sekarang(db)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["kode_pendaftaran", "nama_usaha", "nama_pemilik", "telepon", "domisili",
                "jenis_usaha", "sumber_produk", "status_khusus", "jumlah_cabang",
                "kebutuhan_muka_m", "queue_awal", "queue_sekarang", "status",
                "status_verifikasi", "jumlah_timeout", "waktu_daftar", "lapak_terakhir",
                "status_alokasi", "sewa_mulai", "sewa_berakhir"])
    for u in db.query(UMKM).order_by(UMKM.id).all():
        a = alokasi_terkini(db, u.id)
        o = alokasi_to_out(a, now) if a else None
        w.writerow([u.kode_pendaftaran, u.nama_usaha, u.nama_pemilik, u.telepon, u.domisili,
                    u.jenis_usaha, u.sumber_produk, "ya" if u.status_khusus else "tidak",
                    u.jumlah_cabang, u.kebutuhan_muka, u.queue_awal, u.queue_level,
                    u.status_pendaftaran, u.status_verifikasi, u.jumlah_timeout, u.waktu_daftar,
                    o.kode_lapak if o else "", o.status_alokasi if o else "",
                    (o.sewa_mulai or "") if o else "", (o.sewa_berakhir or "") if o else ""])
    return Response(
        "﻿" + buf.getvalue(), media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="si-takar-buku-induk.csv"'},
    )


# ---------- Data contoh untuk uji coba ----------
@api.post("/demo/isi")
def isi_data_contoh(db: Session = Depends(get_db)):
    """Masukkan pendaftar fiktif (dummy) melalui jalur skoring & alokasi yang sama."""
    return seed.isi_demo(db)


router.include_router(api)
