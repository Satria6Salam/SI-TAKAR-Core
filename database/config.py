import os
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker

load_dotenv()

# Default pakai SQLite dulu (mudah untuk development/MVP)
DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./si_takar.db")

# ---- Parameter aturan (keputusan Ketua, bisa diubah lewat .env) ----
DOMISILI_PASAR = os.getenv("DOMISILI_PASAR", "Kota Contoh")
TIMEOUT_HARI = int(os.getenv("TIMEOUT_HARI", "3"))
PREEMPTION_HARI = int(os.getenv("PREEMPTION_HARI", "14"))
PERINGATAN_HARI = int(os.getenv("PERINGATAN_HARI", "7"))
CRON_INTERVAL_DETIK = int(os.getenv("CRON_INTERVAL_DETIK", "60"))

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {},
)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


def utcnow() -> datetime:
    """Waktu UTC (naive). Pengganti datetime.utcnow() yang sudah deprecated."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
