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
DOMISILI_PASAR = os.getenv("DOMISILI_PASAR", "Kabupaten Malang")

# Penanganan deadlock
TIMEOUT_HARI = int(os.getenv("TIMEOUT_HARI", "3"))          # batas konfirmasi lapak
PREEMPTION_HARI = int(os.getenv("PREEMPTION_HARI", "14"))   # tidak aktif -> hak dicabut
PERINGATAN_HARI = int(os.getenv("PERINGATAN_HARI", "7"))    # tidak aktif -> peringatan 1
MAKS_TIMEOUT = int(os.getenv("MAKS_TIMEOUT", "3"))          # sekian kali timeout -> gugur (cegah livelock)
CRON_INTERVAL_DETIK = int(os.getenv("CRON_INTERVAL_DETIK", "60"))

# Manajemen proses: aging (0 = nonaktif, MLQ murni sesuai Project Charter)
AGING_HARI = int(os.getenv("AGING_HARI", "0"))

# Zona waktu pasar (WIB = UTC+7), dipakai untuk menentukan "hari ini" pada absen harian
ZONA_WAKTU_JAM = int(os.getenv("ZONA_WAKTU_JAM", "7"))

# Manajemen penyimpanan: lama satu siklus sewa
SEWA_HARI = int(os.getenv("SEWA_HARI", "180"))

# Pembagian lapak: "manual" = per putaran alokasi yang dijalankan admin (MLQ dibandingkan
# bersama, Q1 benar-benar didahulukan); "langsung" = dibagi seketika saat pendaftar siap
PUTARAN_ALOKASI = os.getenv("PUTARAN_ALOKASI", "manual").strip().lower()

# Mode manual: putaran juga dijalankan otomatis sekali sehari mulai jam ini (WIB), supaya ruang
# yang dilepas tidak menganggur bila admin lupa. -1 = hanya lewat tombol admin.
PUTARAN_HARIAN_JAM = int(os.getenv("PUTARAN_HARIAN_JAM", "7"))

# Rekam jejak: pendaftar yang pernah dicabut (Preemption) atau gugur (Timeout berulang) dalam
# sekian hari terakhir turun satu tingkat prioritas saat mendaftar ulang. 0 = nonaktif.
PENALTI_HARI = int(os.getenv("PENALTI_HARI", "180"))

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

    # Kolom baru yang boleh kosong ditambahkan langsung (data lama tetap utuh).
    # Bila ada kolom wajib yang hilang, skema dianggap usang dan berkas lama dicadangkan.
    insp = inspect(engine)
    tambahan, usang = [], False
    for t in Base.metadata.sorted_tables:
        if not insp.has_table(t.name):
            continue
        ada = {c["name"] for c in insp.get_columns(t.name)}
        for kolom in t.columns:
            if kolom.name in ada:
                continue
            if kolom.nullable and not kolom.primary_key:
                tambahan.append((t.name, kolom))
            else:
                usang = True
    if tambahan and not usang:
        with engine.begin() as conn:
            for tabel, kolom in tambahan:
                tipe = kolom.type.compile(dialect=engine.dialect)
                conn.exec_driver_sql(f'ALTER TABLE "{tabel}" ADD COLUMN "{kolom.name}" {tipe}')
                log.warning("Kolom baru %s.%s ditambahkan ke database", tabel, kolom.name)
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
