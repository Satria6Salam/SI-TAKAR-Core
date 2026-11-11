from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator


class UMKMCreate(BaseModel):
    # identitas pemilik
    nama_pemilik: str = Field(min_length=1, max_length=120)
    nik: str = Field(pattern=r"^\d{16}$", description="16 digit NIK")
    telepon: str = Field(min_length=6, max_length=20)
    email: str | None = Field(None, max_length=120)

    # data usaha (bahan skoring MLQ)
    nama_usaha: str = Field(min_length=1, max_length=120)
    jenis_usaha: str = Field(min_length=1, max_length=40,
                             description="kriya, seni rupa, antik, kuliner, fesyen, aksesoris, jasa kreatif, lainnya")
    deskripsi: str | None = Field(None, max_length=500)
    domisili: str = Field(min_length=1, max_length=80, description="Kota/Kabupaten sesuai KTP")
    sumber_produk: Literal["buatan_sendiri", "reseller", "waralaba", "impor"] = "buatan_sendiri"
    status_khusus: bool = False
    jumlah_cabang: int = Field(0, ge=0, le=99, description="Jumlah toko/ruko fisik yang sudah dimiliki")

    # kebutuhan ruang (bahan Worst-Fit)
    kebutuhan_muka: float = Field(2, ge=1, le=20, description="Panjang muka lapak yang dibutuhkan (meter)")

    # PIN 6 digit: dipakai bersama kode pendaftaran untuk konfirmasi lapak, absen, unggah dokumen
    pin: str = Field(pattern=r"^\d{6}$", description="PIN 6 digit buatan pendaftar")

    @field_validator("nama_pemilik", "nama_usaha", "domisili", "jenis_usaha", "telepon")
    @classmethod
    def _rapikan(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("tidak boleh kosong")
        return v


class UMKMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    kode_pendaftaran: str
    nama_pemilik: str
    nama_usaha: str
    telepon: str
    email: str | None
    domisili: str
    jenis_usaha: str
    deskripsi: str | None
    sumber_produk: str
    status_khusus: bool
    jumlah_cabang: int
    kebutuhan_muka: float
    queue_level: int
    queue_awal: int
    alasan_queue: list[str] = []
    jumlah_timeout: int
    status_pendaftaran: str
    waktu_daftar: datetime
    waktu_antre: datetime
    status_verifikasi: str
    catatan_verifikasi: str | None = None
    waktu_verifikasi: datetime | None = None
    punya_ktp: bool = False
    punya_dok_khusus: bool = False

    @field_validator("alasan_queue", mode="before")
    @classmethod
    def _pecah(cls, v):
        if isinstance(v, str):
            return [b for b in v.split("\n") if b]
        return v or []


class AlokasiOut(BaseModel):
    id: int
    umkm_id: int
    lapak_id: int
    kode_lapak: str
    zona: str
    mulai: float
    panjang: float
    lebar: float
    luas: float
    status_alokasi: str
    waktu_alokasi: datetime | None
    batas_konfirmasi: datetime | None
    sisa_detik_konfirmasi: int | None = Field(None, description="Untuk countdown Timeout di UI")
    terakhir_aktif: datetime | None
    hari_tidak_aktif: int | None = None
    peringatan: bool = Field(False, description="True jika tidak aktif >= batas peringatan")
    terakhir_absen: datetime | None = None
    sudah_absen_hari_ini: bool = False
    sewa_mulai: datetime | None = None
    sewa_berakhir: datetime | None = None
    sisa_hari_sewa: int | None = None
    waktu_selesai: datetime | None = None


class LogOut(BaseModel):
    id: int
    waktu: datetime | None
    jenis: str
    umkm_id: int | None
    nama_usaha: str | None
    keterangan: str | None


class StatusAntreanOut(BaseModel):
    umkm: UMKMOut
    posisi_dalam_queue: int | None = Field(None, description="None jika sudah tidak mengantre")
    jumlah_di_queue: int = 0
    alokasi: AlokasiOut | None = None
    riwayat: list[LogOut] = []
    waktu_server: datetime


class ZonaCreate(BaseModel):
    kode: str = Field(min_length=1, max_length=4)
    nama: str = Field(min_length=1, max_length=60)
    panjang: float = Field(gt=0, le=200)
    kedalaman: float = Field(gt=0, le=20)


class LogDeadlockOut(BaseModel):
    id: int
    umkm_id: int
    nama_usaha: str
    jenis_pelanggaran: str
    waktu_kejadian: datetime | None
    keterangan: str | None


class MajukanJam(BaseModel):
    hari: float = Field(gt=0, le=365)


PIN_POLA = r"^\d{6}$"


class PinIn(BaseModel):
    """PIN boleh dikosongkan bila penjual sudah masuk (sesi kode + PIN di browser ini)."""
    pin: str | None = Field(None, pattern=PIN_POLA)


class MasukPenjualIn(BaseModel):
    kode: str = Field(min_length=4, max_length=12)
    pin: str = Field(pattern=PIN_POLA)


class DokumenIn(BaseModel):
    pin: str | None = Field(None, pattern=PIN_POLA)
    jenis: Literal["ktp", "khusus"]
    nama_file: str = Field("", max_length=200)
    data_base64: str = Field(min_length=10, description="Isi berkas (JPG/PNG/PDF) dalam base64")


class LupaKodeIn(BaseModel):
    nik: str = Field(pattern=r"^\d{16}$")
    telepon: str = Field(min_length=6, max_length=20)


class VerifikasiIn(BaseModel):
    keputusan: Literal["terima", "tolak_klaim", "tolak"]
    catatan: str | None = Field(None, max_length=300)
