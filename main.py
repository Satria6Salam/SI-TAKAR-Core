from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database import models  # Penting: supaya semua model ke-load sebelum create_all
from database.config import Base, engine
from routers import api_alokasi, api_pendaftaran, api_peta

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Membuat tabel database secara otomatis saat server dinyalakan
    Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(title="SI-TAKAR App", version="0.1.0", lifespan=lifespan)

# Izinkan frontend/desainer memanggil API saat development
app.add_middleware(
    CORSMiddleware, 
    allow_origins=["*"], 
    allow_methods=["*"], 
    allow_headers=["*"]
)

# Mendaftarkan rute endpoint sesuai tahap fondasi saat ini
app.include_router(api_pendaftaran.router)
app.include_router(api_alokasi.router)
app.include_router(api_peta.router)

# Menghubungkan folder static jika tersedia
if (BASE_DIR / "static").is_dir():
    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")


def serve_page(filename: str) -> FileResponse:
    return FileResponse(TEMPLATES_DIR / filename)


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
