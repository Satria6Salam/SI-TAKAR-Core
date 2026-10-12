from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class UMKMCreate(BaseModel):
    nama_pemilik: str = Field(min_length=1)
    nama_usaha: str = Field(min_length=1)
    domisili: str = Field(min_length=1, description="Kota/Kabupaten sesuai KTP")
    jenis_usaha: str = Field(min_length=1, description="mis. kriya, kuliner, fesyen, reseller")
    status_khusus: bool = False
    punya_toko_fisik: bool = False


class UMKMOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    nama_pemilik: str
    nama_usaha: str
    domisili: str
    jenis_usaha: str
    status_khusus: bool
    punya_toko_fisik: bool
    queue_level: int
    status_pendaftaran: str
    waktu_daftar: datetime


class AlokasiOut(BaseModel):
    id: int
    umkm_id: int
    lapak_id: int
    kode_lapak: str
    status_alokasi: str
    waktu_alokasi: datetime | None
    batas_konfirmasi: datetime | None
    sisa_detik_konfirmasi: int | None = Field(None, description="Untuk countdown 3 hari di UI")
    terakhir_aktif: datetime | None
    hari_tidak_aktif: int | None = None
    peringatan: bool = Field(False, description="True jika tidak aktif >= 7 hari (Peringatan 1)")


class StatusAntreanOut(BaseModel):
    umkm: UMKMOut
    posisi_dalam_queue: int | None = Field(None, description="None jika sudah tidak mengantre")
    alokasi: AlokasiOut | None = None


class LapakCreate(BaseModel):
    kode_lapak: str = Field(min_length=1)
    panjang: float = Field(gt=0)
    lebar: float = Field(gt=0)
    posisi_x: int = 0
    posisi_y: int = 0


class LogDeadlockOut(BaseModel):
    id: int
    umkm_id: int
    nama_usaha: str
    jenis_pelanggaran: str
    waktu_kejadian: datetime | None
    keterangan: str | None
