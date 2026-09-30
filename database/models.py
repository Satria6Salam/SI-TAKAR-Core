from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database.config import Base, utcnow


# ---- Konstanta status (dipakai bersama oleh algoritma & router) ----
class StatusLapak:
    KOSONG = "Kosong"      # Hijau  - bisa dialokasikan
    DIPESAN = "Dipesan"    # Kuning - sudah dialokasikan, menunggu konfirmasi (<= 3 hari)
    TERISI = "Terisi"      # Merah  - sudah dikonfirmasi & aktif


class StatusAlokasi:
    MENUNGGU = "Menunggu Konfirmasi"
    AKTIF = "Aktif"
    DIBATALKAN = "Dibatalkan"  # Timeout
    DICABUT = "Dicabut"        # Preemption


class StatusPendaftaran:
    MENUNGGU = "Menunggu"                      # di antrean
    MENUNGGU_KONFIRMASI = "Menunggu Konfirmasi"  # sudah dapat lapak, belum konfirmasi
    AKTIF = "Aktif"                            # penyewa sah
    DICABUT = "Dicabut"                        # hak sewa dicabut (Preemption)


class Admin(Base):
    __tablename__ = "admin"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


class UMKM(Base):
    __tablename__ = "umkm"
    id = Column(Integer, primary_key=True, index=True)
    nama_pemilik = Column(String, nullable=False)
    nama_usaha = Column(String, nullable=False)
    domisili = Column(String, nullable=False)
    jenis_usaha = Column(String, nullable=False)
    status_khusus = Column(Boolean, default=False)
    punya_toko_fisik = Column(Boolean, default=False)
    queue_level = Column(Integer, nullable=False)
    status_pendaftaran = Column(String, default=StatusPendaftaran.MENUNGGU)
    waktu_daftar = Column(DateTime, default=utcnow)

    alokasi = relationship("AlokasiSewa", back_populates="umkm")
    arsip = relationship("ArsipPelanggaran", back_populates="umkm")


class Lapak(Base):
    __tablename__ = "lapak"
    id = Column(Integer, primary_key=True, index=True)
    kode_lapak = Column(String, unique=True, nullable=False)
    panjang = Column(Float, nullable=False)
    lebar = Column(Float, nullable=False)
    luas = Column(Float, nullable=False)
    posisi_x = Column(Integer)
    posisi_y = Column(Integer)
    status_lapak = Column(String, default=StatusLapak.KOSONG)

    alokasi = relationship("AlokasiSewa", back_populates="lapak")


class AlokasiSewa(Base):
    __tablename__ = "alokasi_sewa"
    id = Column(Integer, primary_key=True, index=True)
    umkm_id = Column(Integer, ForeignKey("umkm.id"), nullable=False)
    lapak_id = Column(Integer, ForeignKey("lapak.id"), nullable=False)
    waktu_alokasi = Column(DateTime, default=utcnow)
    batas_konfirmasi = Column(DateTime)
    terakhir_aktif = Column(DateTime)
    status_alokasi = Column(String, default=StatusAlokasi.MENUNGGU)

    umkm = relationship("UMKM", back_populates="alokasi")
    lapak = relationship("Lapak", back_populates="alokasi")


class ArsipPelanggaran(Base):
    __tablename__ = "arsip_pelanggaran"
    id = Column(Integer, primary_key=True, index=True)
    umkm_id = Column(Integer, ForeignKey("umkm.id"), nullable=False)
    jenis_pelanggaran = Column(String, nullable=False)  # "Timeout" / "Preemption"
    waktu_kejadian = Column(DateTime, default=utcnow)
    keterangan = Column(Text)

    umkm = relationship("UMKM", back_populates="arsip")
