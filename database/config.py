import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Default pakai SQLite dulu (mudah untuk development/MVP)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./si_takar.db")

# ---- Parameter aturan & simulasi Deadlock ----
DOMISILI_PASAR = os.getenv("DOMISILI_PASAR", "Kota Contoh")

# Mode simulasi Deadlock cepat (Default: 60 detik = 1 menit)
TIMEOUT_DETIK = int(os.getenv("TIMEOUT_DETIK", "60"))
PREEMPTION_DETIK = int(os.getenv("PREEMPTION_DETIK", "120"))
PERINGATAN_DETIK = int(os.getenv("PERINGATAN_DETIK", "30"))

# Interval cron background: cek deadlock tiap N detik (default 3 detik agar responsif di simulasi)
CRON_INTERVAL_DETIK = int(os.getenv("CRON_INTERVAL_DETIK", "3"))

TIMEOUT_HARI = max(1, TIMEOUT_DETIK // 86400)
PREEMPTION_HARI = max(1, PREEMPTION_DETIK // 86400)
PERINGATAN_HARI = max(1, PERINGATAN_DETIK // 86400)

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    """Waktu UTC (naive). Pengganti datetime.utcnow() yang sudah deprecated."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def migrate_schema() -> None:
    """Tambahkan kolom skema baru secara otomatis ke SQLite jika belum ada."""
    inspector = inspect(engine)
    if "umkm" not in inspector.get_table_names():
        return
    columns = {column["name"] for column in inspector.get_columns("umkm")}
    additions = {
        "kebutuhan_luas": "FLOAT NOT NULL DEFAULT 0",
        "produksi_sendiri": "BOOLEAN NOT NULL DEFAULT 1",
        "jumlah_cabang": "INTEGER NOT NULL DEFAULT 1",
        "modal_besar": "BOOLEAN NOT NULL DEFAULT 0",
        "nomor_pendaftaran": "VARCHAR",
        "nik": "VARCHAR",
        "nomor_telepon": "VARCHAR",
        "email": "VARCHAR",
        "deskripsi": "TEXT",
    }
    with engine.begin() as connection:
        for name, definition in additions.items():
            if name not in columns:
                connection.execute(text(f"ALTER TABLE umkm ADD COLUMN {name} {definition}"))


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
