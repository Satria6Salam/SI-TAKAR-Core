import asyncio
import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

import seed
from algoritma.deadlock_cron import jalankan_semua
from database.config import AUTO_SEED, CRON_INTERVAL_DETIK, SessionLocal, siapkan_database
from routers import api_admin, api_alokasi, api_pendaftaran, api_peta

# Konfigurasi Direktori Frontend & Templates
BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"

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
    siapkan_database()
    if AUTO_SEED:
        db = SessionLocal()
        try:
            seed.isi_awal(db)
        finally:
            db.close()
    task = None
    if CRON_INTERVAL_DETIK > 0:
        task = asyncio.create_task(_cron_loop())
    yield
    if task:
        task.cancel()


app = FastAPI(title="SI-TAKAR App", version="1.0.0", lifespan=lifespan)

# Izinkan frontend/desainer memanggil API dari origin lain saat development
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

# Pendaftaran Endpoint Router Backend
app.include_router(api_pendaftaran.router)
app.include_router(api_alokasi.router)
app.include_router(api_peta.router)
app.include_router(api_admin.router)

# Menghubungkan folder static (CSS, JS, Images)
if (BASE_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def serve_page(filename: str) -> FileResponse:
    return FileResponse(TEMPLATES_DIR / filename)


# --- Rute Penyajian Halaman Frontend (HTML Slicing) ---

@app.get("/", include_in_schema=False)
@app.get("/index.html", include_in_schema=False)
def home_page():
    return serve_page("index.html")


@app.get("/pendaftaran", include_in_schema=False)
@app.get("/pendaftaran.html", include_in_schema=False)
def registration_page():
    return serve_page("pendaftaran.html")


@app.get("/status", include_in_schema=False)
@app.get("/status.html", include_in_schema=False)
def status_page():
    return serve_page("status.html")


@app.get("/profil", include_in_schema=False)
@app.get("/profil.html", include_in_schema=False)
def profile_page():
    return serve_page("profil.html")


@app.get("/lupa-kode", include_in_schema=False)
def forgot_code_page():
    return serve_page("lupa_kode.html")


# Cek Status API (Root Endpoint untuk Backend)
@app.get("/api-status", tags=["Root"])
def api_status():
    return {"message": "SI-TAKAR API is running", "docs": "/docs"}
