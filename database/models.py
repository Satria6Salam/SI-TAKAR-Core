from sqlalchemy import Boolean, Column, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import relationship

from database.config import Base, utcnow


# ---- Konstanta status (dipakai bersama oleh algoritma & router) ----
class StatusLapak:
    KOSONG = "Kosong"      # Hijau  - ruang bebas (hole), tidak disimpan sebagai baris
    DIPESAN = "Dipesan"    # Kuning - sudah dialokasikan, menunggu konfirmasi (<= 3 hari)
    TERISI = "Terisi"      # Merah  - sudah dikonfirmasi & aktif
    DILEPAS = "Dilepas"    # riwayat: ruangnya sudah kembali menjadi hole

    MENEMPATI = (DIPESAN, TERISI)


class StatusAlokasi:
    MENUNGGU = "Menunggu Konfirmasi"
    AKTIF = "Aktif"
    DIBATALKAN = "Dibatalkan"      # Timeout
    DICABUT = "Dicabut"            # Preemption
    SELESAI = "Selesai"            # masa sewa habis
    LULUS = "Lulus Inkubasi"       # pindah ke ruko mandiri

    BERJALAN = (MENUNGGU, AKTIF)


class StatusVerifikasi:
    BELUM = "Belum Diperiksa"
    TERVERIFIKASI = "Terverifikasi"
    KLAIM_DITOLAK = "Klaim Khusus Ditolak"   # diterima, tetapi tanpa status khusus
    DITOLAK = "Ditolak"
    OTOMATIS = "Tanpa Verifikasi"            # verifikasi dimatikan / data contoh

    SUDAH_DIPUTUS = (TERVERIFIKASI, KLAIM_DITOLAK, DITOLAK)


class StatusPendaftaran:
    MENUNGGU_VERIFIKASI = "Menunggu Verifikasi"  # dokumen diperiksa admin
    DITOLAK = "Ditolak"                          # data tidak valid
    MENUNGGU = "Menunggu"                        # di antrean
    MENUNGGU_KONFIRMASI = "Menunggu Konfirmasi"  # sudah dapat lapak, belum konfirmasi
    AKTIF = "Aktif"                              # penyewa sah
    DICABUT = "Dicabut"                          # hak sewa dicabut (Preemption)
    GUGUR = "Gugur"                              # terlalu sering Timeout
    SELESAI = "Selesai"                          # masa sewa habis (arsip)
    LULUS = "Lulus Inkubasi"                     # arsip alumni

    BERJALAN = (MENUNGGU_VERIFIKASI, MENUNGGU, MENUNGGU_KONFIRMASI, AKTIF)
    ARSIP = (DICABUT, GUGUR, SELESAI, LULUS, DITOLAK)


class Admin(Base):
    __tablename__ = "admin"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, nullable=False)
    password_hash = Column(String, nullable=False)


class Pengaturan(Base):
    """Penyimpanan kunci-nilai kecil (mis. pergeseran jam simulasi)."""
    __tablename__ = "pengaturan"
    kunci = Column(String, primary_key=True)
    nilai = Column(String, nullable=False)


class UMKM(Base):
    __tablename__ = "umkm"
    id = Column(Integer, primary_key=True, index=True)
    kode_pendaftaran = Column(String, unique=True, nullable=False, index=True)

    # identitas & kontak
    nama_pemilik = Column(String, nullable=False)
    nik = Column(String, nullable=False, index=True)
    telepon = Column(String, nullable=False)
    email = Column(String)
    pin_hash = Column(String, nullable=False)   # PIN 6 digit untuk aksi penjual

    # dokumen & verifikasi (path berkas di folder unggahan)
    dokumen_ktp = Column(String)
    dokumen_khusus = Column(String)
    status_verifikasi = Column(String, default=StatusVerifikasi.BELUM)
    catatan_verifikasi = Column(Text)
    waktu_verifikasi = Column(DateTime)

    # data usaha = bahan skoring MLQ
    nama_usaha = Column(String, nullable=False)
    jenis_usaha = Column(String, nullable=False)
    deskripsi = Column(Text)
    domisili = Column(String, nullable=False)
    sumber_produk = Column(String, nullable=False, default="buatan_sendiri")
    status_khusus = Column(Boolean, default=False)
    jumlah_cabang = Column(Integer, default=0)

    # kebutuhan ruang = bahan Worst-Fit (panjang muka lapak, meter)
    kebutuhan_muka = Column(Float, nullable=False)

    # hasil skoring & posisi antrean
    queue_level = Column(Integer, nullable=False)
    queue_awal = Column(Integer, nullable=False)
    alasan_queue = Column(Text)
    waktu_daftar = Column(DateTime, default=utcnow)
    waktu_antre = Column(DateTime, default=utcnow)   # kunci urutan FIFO di dalam satu queue
    jumlah_timeout = Column(Integer, default=0)
    status_pendaftaran = Column(String, default=StatusPendaftaran.MENUNGGU)

    alokasi = relationship("AlokasiSewa", back_populates="umkm")
    arsip = relationship("ArsipPelanggaran", back_populates="umkm")

    @property
    def punya_ktp(self) -> bool:
        return bool(self.dokumen_ktp)

    @property
    def punya_dok_khusus(self) -> bool:
        return bool(self.dokumen_khusus)


class Zona(Base):
    """Blok ruang pasar (lorong). Analogi: satu blok memori yang dipotong-potong menjadi lapak."""
    __tablename__ = "zona"
    id = Column(Integer, primary_key=True, index=True)
    kode = Column(String, unique=True, nullable=False)
    nama = Column(String, nullable=False)
    panjang = Column(Float, nullable=False)     # meter, sepanjang lorong
    kedalaman = Column(Float, nullable=False)   # meter, ke belakang

    lapak = relationship("Lapak", back_populates="zona")


class Lapak(Base):
    """Partisi yang dipotong dari sebuah zona saat alokasi (partisi dinamis)."""
    __tablename__ = "lapak"
    id = Column(Integer, primary_key=True, index=True)
    zona_id = Column(Integer, ForeignKey("zona.id"), nullable=False)
    kode_lapak = Column(String, unique=True, nullable=False)
    mulai = Column(Float, nullable=False)     # posisi awal di dalam zona (meter)
    panjang = Column(Float, nullable=False)   # panjang muka
    lebar = Column(Float, nullable=False)     # = kedalaman zona
    luas = Column(Float, nullable=False)
    status_lapak = Column(String, default=StatusLapak.DIPESAN)

    zona = relationship("Zona", back_populates="lapak")
    alokasi = relationship("AlokasiSewa", back_populates="lapak")


class AlokasiSewa(Base):
    __tablename__ = "alokasi_sewa"
    id = Column(Integer, primary_key=True, index=True)
    umkm_id = Column(Integer, ForeignKey("umkm.id"), nullable=False)
    lapak_id = Column(Integer, ForeignKey("lapak.id"), nullable=False)
    waktu_alokasi = Column(DateTime, default=utcnow)
    batas_konfirmasi = Column(DateTime)             # timer Timeout
    terakhir_aktif = Column(DateTime)               # timer Preemption
    peringatan_dikirim = Column(Boolean, default=False)
    sewa_mulai = Column(DateTime)                   # siklus sewa
    sewa_berakhir = Column(DateTime)
    waktu_selesai = Column(DateTime)                # kapan alokasi ini berakhir (apa pun sebabnya)
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


class LogAktivitas(Base):
    """Jurnal kejadian sistem (pendaftaran, alokasi, absen, peringatan, arsip, dst.)."""
    __tablename__ = "log_aktivitas"
    id = Column(Integer, primary_key=True, index=True)
    waktu = Column(DateTime, default=utcnow, index=True)
    jenis = Column(String, nullable=False)
    umkm_id = Column(Integer, ForeignKey("umkm.id"))
    keterangan = Column(Text)

    umkm = relationship("UMKM")


def catat(db, jenis: str, keterangan: str, umkm_id: int | None = None, waktu=None) -> None:
    """Tambahkan satu baris jurnal (belum commit; ikut transaksi pemanggil)."""
    db.add(LogAktivitas(jenis=jenis, keterangan=keterangan, umkm_id=umkm_id,
                        waktu=waktu or utcnow()))
