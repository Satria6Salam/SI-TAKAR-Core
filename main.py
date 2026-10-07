import asyncio
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from algoritma.deadlock_cron import jalankan_semua
from database import models  # penting: supaya semua model ke-load sebelum create_all
from database.config import CRON_INTERVAL_DETIK, SessionLocal, Base, engine
from routers import api_alokasi, api_pendaftaran, api_peta

log = logging.getLogger("si_takar")


def _tick():
    """Satu siklus timer deadlock (jalan di thread terpisah)."""
    db = SessionLocal()
    try:
        hasil = jalankan_semua(db)
        if any(hasil.values()):
            log.info("Siklus deadlock: %s", hasil)
    except Exception:
        log.exception("Siklus deadlock gagal")
    finally:
        db.close()


async def _cron_loop():
    while True:
        await asyncio.sleep(CRON_INTERVAL_DETIK)
        await asyncio.to_thread(_tick)


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(bind=engine)
    task = None
    if CRON_INTERVAL_DETIK > 0:
        task = asyncio.create_task(_cron_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="SI-TAKAR App", version="0.2.0", lifespan=lifespan)

# Izinkan frontend/desainer memanggil API dari origin lain saat development
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(api_pendaftaran.router)
app.include_router(api_alokasi.router)
app.include_router(api_peta.router)

if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", tags=["Root"])
def root():
    return {"message": "SI-TAKAR API is running", "docs": "/docs"}
