# SI-TAKAR Core

Sistem Tata Kelola Kios Pasar Seni. Purwarupa ini membagi lapak pasar kepada UMKM dengan meminjam empat konsep Sistem Operasi, lalu memperlihatkan cara kerjanya di layar.

Aplikasi berjalan **di laptop lokal** (tanpa hosting): **FastAPI** + **SQLite** sebagai backend, dan HTML, CSS, JavaScript murni yang disajikan dari server yang sama.

## Empat pilar Sistem Operasi

| Pilar | Konsep OS | Penerapan di pasar | Kode |
| --- | --- | --- | --- |
| Manajemen Proses | Multilevel Queue (MLQ) | Pendaftar dinilai sistem ke Queue 1, 2, atau 3. Queue 1 dilayani sampai habis, lalu Queue 2, lalu Queue 3. Di dalam satu queue berlaku FIFO. | `algoritma/mlq_scoring.py`, `algoritma/penjadwal.py` |
| Manajemen Memori | Partisi dinamis + Worst-Fit | Tiap lorong (zona) adalah satu blok ruang. Lapak dipotong dari ruang kosong terluas sepanjang kebutuhan pendaftar. Ruang yang dilepas menyatu kembali dengan ruang kosong di sebelahnya. | `algoritma/worst_fit.py` |
| Manajemen Penyimpanan | Siklus hidup data + arsip + jurnal | Masa sewa dicatat mulai dan berakhirnya. UMKM yang keluar tidak dihapus, hanya diarsipkan. Semua kejadian masuk jurnal, dan buku induk bisa diunduh sebagai CSV. | `database/models.py`, `routers/api_admin.py` |
| Penanganan Deadlock | Timeout + Preemption | Lapak yang tidak dikonfirmasi 3 hari hangus. Lapak yang tutup 14 hari dicabut (peringatan di hari ke-7). Ruangnya langsung diberikan ke antrean. | `algoritma/deadlock_cron.py` |

Rincian aturan:

- **Skoring MLQ.** Queue 3 bila KTP luar kota, produk bukan buatan sendiri (reseller, waralaba, impor), atau punya lebih dari satu toko. Queue 1 bila warga lokal dengan status khusus, atau pengrajin kriya/seni/antik yang belum punya toko. Sisanya Queue 2. Pendaftar tidak memilih prioritasnya sendiri; alasan penilaian disimpan dan ditampilkan.
- **Worst-Fit.** Ukuran permintaan adalah panjang muka lapak (meter). Bila pendaftar terdepan butuh ruang yang belum tersedia secara bersambung, ia tetap di posisinya dan giliran diberikan ke pendaftar berikutnya yang muat, supaya ruang tidak menganggur.
- **Timeout.** Pendaftar yang kena timeout dilempar ke urutan terbawah queue-nya. Setelah `MAKS_TIMEOUT` kali, pendaftarannya gugur supaya tidak berputar terus.
- **Mutex.** Timer background dan request browser berjalan di thread berbeda. Bagian "baca ruang kosong lalu potong lapak" dilindungi satu kunci (`penjadwal.KUNCI`) agar satu ruang tidak terpotong untuk dua UMKM.
- **Verifikasi dokumen.** Pendaftar mengunggah KTP (dan bukti bila mengajukan status khusus). Pengelola menerima, menerima tanpa status khusus (jalur dinilai ulang), atau menolak dengan alasan. Urutan antrean tetap dihitung dari waktu daftar, jadi lamanya pemeriksaan tidak merugikan pendaftar. Matikan dengan `VERIFIKASI_WAJIB=0`.
- **Aging (opsional).** Isi `AGING_HARI` di `.env` untuk menaikkan pendaftar Queue 2/3 yang terlalu lama menunggu. Bawaan `0` (nonaktif), sesuai Project Charter.

## Menjalankan

Persyaratan: Python 3.10 atau lebih baru. Dari folder proyek, di PowerShell:

```powershell
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Dua baris pertama cukup sekali. Saat pertama dijalankan, aplikasi membuat database, tiga zona contoh, dan akun admin demo secara otomatis.

- Beranda: http://127.0.0.1:8000/
- Login admin: http://127.0.0.1:8000/admin/login
- Dokumentasi API: http://127.0.0.1:8000/docs

Isi `DOMISILI_PASAR` di `.env` dengan kota lokasi pasar. Nilai ini menentukan siapa yang dihitung warga lokal.

### Akun admin demo

| Username | Password   |
| -------- | ---------- |
| `admin`  | `admin123` |

Hanya untuk laptop lokal.

### Data awal dan data contoh

```powershell
.venv\Scripts\python.exe seed.py          # zona contoh + admin (aman diulang)
.venv\Scripts\python.exe seed.py --demo   # tambah 16 pendaftar fiktif + 3 yang menunggu verifikasi
.venv\Scripts\python.exe seed.py --reset  # kosongkan SELURUH data lalu isi ulang data awal
```

Database versi lama (skema lapak tetap) tidak dihapus: saat aplikasi dijalankan, berkasnya dipindah menjadi `si_takar.db.lama-<tanggal>`.

## Alur demo yang disarankan

1. Login admin, klik **Isi data contoh**. Enam belas pendaftar fiktif masuk; yang besar sengaja mendaftar lebih dulu, tetapi Queue 1 tetap dilayani lebih dulu. Tiga lainnya menunggu di menu **Verifikasi** (KTP berupa PDF contoh). PIN semua data contoh: `123456`.
2. Di **Verifikasi**: terima "Tenun Ikat Nur", coba terima "Keripik Maya" (ditolak sistem karena bukti status khusus tidak ada), lalu pilih **Terima tanpa status khusus**; jalurnya turun dari Queue 1 ke Queue 2.
3. Lihat **Denah & zona**: tiap lorong terpotong menjadi lapak, dan pendaftar Queue 3 tersisa di antrean.
4. Buka `/pendaftaran` di tab lain, daftarkan satu UMKM dengan KTP dan PIN, verifikasi di admin, lalu konfirmasi lapaknya di halaman Status memakai PIN.
5. Di **Ringkasan** atau **Monitor deadlock**, klik **+3 hari** lalu **+1 hari**: lapak yang belum dikonfirmasi kena Timeout dan ruangnya pindah ke antrean.
6. Klik **+7 hari** dua kali: penyewa yang tidak pernah mencatat kios buka mendapat peringatan, lalu dicabut (Preemption) dan masuk arsip.
7. Coba **Simulator penempatan** (menu Denah & zona) untuk membandingkan Worst-Fit, Best-Fit, dan First-Fit pada keadaan pasar saat itu.
8. Klik **Kembalikan** untuk mengembalikan jam sistem ke jam laptop.

Jam sistem yang dimajukan hanya menggeser jam di dalam aplikasi; jam laptop tidak berubah.

## Halaman

| Alamat | Untuk | Isi |
| --- | --- | --- |
| `/` | Publik | Ketersediaan ruang dan denah pasar langsung dari sistem |
| `/pendaftaran` | UMKM | Formulir dengan pratinjau jalur, unggah KTP, dan pembuatan PIN |
| `/status` | UMKM | Jalur, posisi antrean, alasan penilaian, hitung mundur dan tombol konfirmasi lapak |
| `/profil` | Penyewa | Lapak Saya: tombol "Buka kios hari ini", masa sewa, riwayat |
| `/lupa-kode` | UMKM | Cari kode pendaftaran dengan NIK + nomor telepon |
| `/admin` | Pengelola | Ringkasan dan daftar hal yang perlu ditindaklanjuti |
| `/admin/verifikasi` | Pengelola | Periksa KTP dan bukti status khusus, lalu terima atau tolak |
| `/admin/pendaftar` | Pengelola | Cari pendaftar (nama, NIK, kode, HP), lihat detail dan dokumen, atur ulang PIN |
| `/admin/antrean`, `/admin/denah`, `/admin/penyewa`, `/admin/deadlock`, `/admin/arsip` | Pengelola | Satu halaman untuk tiap pilar OS |

### Keamanan akun penjual

- Penjual dikenali lewat **kode pendaftaran** (contoh `STK-7K4M2Q`) dan **PIN 6 angka** yang dibuat sendiri saat mendaftar.
- Kode saja cukup untuk *melihat* status (nomor telepon disamarkan). Konfirmasi lapak, mencatat kios buka, dan mengunggah dokumen wajib memakai PIN.
- PIN salah 5 kali berturut-turut mengunci aksi selama 15 menit. Begitu juga pencarian lupa kode.
- **Lupa kode:** buka `/lupa-kode`, masukkan NIK dan nomor telepon saat mendaftar.
- **Lupa PIN:** PIN disimpan terenkripsi sehingga tidak bisa ditampilkan. Pengelola mencocokkan KTP asli, lalu menekan **Atur ulang PIN** di halaman Cari pendaftar; PIN baru tampil sekali.
- Berkas unggahan disimpan di folder `unggahan/` di laptop dan hanya bisa dibuka admin yang sudah login.

## Struktur

```
main.py                  server, penyajian halaman, timer background
seed.py                  data awal dan data contoh
schemas.py               bentuk data request/response
database/config.py       koneksi dan parameter aturan (.env)
database/models.py       tabel: umkm, zona, lapak, alokasi_sewa, arsip_pelanggaran, log_aktivitas, admin
algoritma/mlq_scoring.py skoring Queue 1/2/3
algoritma/penjadwal.py   dispatcher antrean MLQ, mutex, aging
algoritma/worst_fit.py   ruang kosong, Worst/Best/First-Fit, fragmentasi
algoritma/deadlock_cron.py Timeout, Preemption, masa sewa
algoritma/jam.py         jam sistem (bisa dimajukan untuk demo)
routers/                 endpoint API (API admin di bawah /api/admin)
unggahan/                berkas KTP dan bukti status khusus (dibuat otomatis, tidak masuk git)
templates/, static/      halaman web
tests/                   tes otomatis
```

## Menjalankan tes

```powershell
.venv\Scripts\python.exe -m pytest -q
```

Tes memakai database SQLite sementara dan tidak menyentuh data lokal.
