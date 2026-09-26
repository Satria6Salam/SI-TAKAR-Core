from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import os

# 1. Inisialisasi Aplikasi Utama
app = FastAPI(
    title="API SI-TAKAR",
    description="Sistem Tata Kelola Kios Pasar Seni (Sistem Operasi MLQ & Worst-Fit)",
    version="1.0.0"
)

# 2. Pengaturan CORS (Agar frontend/desainer bisa mengakses API tanpa diblokir)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 3. Menghubungkan Folder Static (Untuk file CSS/JS dari Desainer)
if os.path.exists("static"):
    app.mount("/static", StaticFiles(directory="static"), name="static")

# 4. Root Endpoint (Untuk tes apakah server menyala)
@app.get("/")
def home():
    return {
        "status": "Aktif",
        "pesan": "Selamat datang di Server SI-TAKAR! Mesin siap digunakan."
    }

# ==========================================
# CATATAN UNTUK PROGRAMMER (FAJAR):
# Nanti ketika folder 'routers' sudah diisi, aktifkan (uncomment) kode di bawah ini:
# ==========================================
# from routers import api_pendaftaran, api_alokasi, api_peta
# app.include_router(api_pendaftaran.router, prefix="/api/pendaftaran")
# app.include_router(api_alokasi.router, prefix="/api/alokasi")
# app.include_router(api_peta.router, prefix="/api/peta")