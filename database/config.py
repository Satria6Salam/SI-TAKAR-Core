import logging
import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

log = logging.getLogger("si_takar")

# Default pakai SQLite dulu (mudah untuk development/MVP)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./si_takar.db")

# ---- Parameter aturan (keputusan Ketua, bisa diubah lewat .env) ----
DOMISILI_PASAR = os.getenv("DOMISILI_PASAR", "Kota Contoh")

# Penanganan deadlock
TIMEOUT_HARI = int(os.getenv("TIMEOUT_HARI", "3"))          # batas konfirmasi lapak
PREEMPTION_HARI = int(os.getenv("PREEMPTION_HARI", "14"))   # tidak aktif -> hak dicabut
PERINGATAN_HARI = int(os.getenv("PERINGATAN_HARI", "7"))    # tidak aktif -> peringatan 1
MAKS_TIMEOUT = int(os.getenv("MAKS_TIMEOUT", "3"))          # sekian kali timeout -> gugur (cegah livelock)
CRON_INTERVAL_DETIK = int(os.getenv("CRON_INTERVAL_DETIK", "60"))

# Manajemen proses: aging (0 = nonaktif, MLQ murni sesuai Project Charter)
AGING_HARI = int(os.getenv("AGING_HARI", "0"))

# Manajemen penyimpanan: lama satu siklus sewa
SEWA_HARI = int(os.getenv("SEWA_HARI", "180"))

# Pendaftar baru menunggu verifikasi dokumen oleh admin sebelum masuk antrean (1 = ya)
VERIFIKASI_WAJIB = os.getenv("VERIFIKASI_WAJIB", "1") == "1"

# Folder penyimpanan unggahan KTP / dokumen pendukung (di laptop lokal)
UNGGAHAN_DIR = os.getenv("UNGGAHAN_DIR", "./unggahan")

# Isi zona contoh + akun admin demo otomatis saat database masih kosong
AUTO_SEED = os.getenv("AUTO_SEED", "1") == "1"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    """Waktu UTC (naive) dari jam laptop. Untuk logika aturan pakai algoritma.jam.sekarang()."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def siapkan_database() -> None:
    """Buat semua tabel. Database SQLite versi lama (skema lapak tetap) disimpan sebagai cadangan."""
    from database import models  # noqa: F401  (supaya semua model terdaftar)

    insp = inspect(engine)
    usang = insp.has_table("umkm") and "pin_hash" not in {
        c["name"] for c in insp.get_columns("umkm")
    }
    if usang:
        berkas = engine.url.database
        if not DATABASE_URL.startswith("sqlite") or not berkas or berkas == ":memory:":
            raise RuntimeError(
                "Skema database masih versi lama. Kosongkan database lalu jalankan ulang aplikasi."
            )
        engine.dispose()
        cadangan = f"{berkas}.lama-{datetime.now():%Y%m%d-%H%M%S}"
        os.replace(berkas, cadangan)
        log.warning("Skema database versi lama terdeteksi; berkas lama dipindah ke %s", cadangan)
    Base.metadata.create_all(bind=engine)
