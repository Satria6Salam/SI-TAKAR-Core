import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from database import models  # Penting: supaya semua model ke-load sebelum create_all
from database.config import Base, engine
from routers import api_alokasi, api_pendaftaran, api_peta


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
if os.path.isdir("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")


@app.get("/", tags=["Root"])
def root():
    return {"message": "SI-TAKAR API is running", "docs": "/docs"}
