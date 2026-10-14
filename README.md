# SI-TAKAR Core

Sistem demonstrasi pengelolaan pendaftaran UMKM, antrean Multi-Level Queue (MLQ), alokasi lapak Worst-Fit, dan pemantauan aktivitas pasar.

Aplikasi ini menggunakan **FastAPI** sebagai backend dan menyajikan antarmuka HTML, CSS, serta JavaScript dari server yang sama. Proyek ini bukan aplikasi Flutter; belum ada kode Dart atau `lib/main.dart` untuk dijalankan dengan `flutter run`.

## Fitur

- Pendaftaran UMKM dan klasifikasi antrean Q1, Q2, dan Q3.
- Alokasi lapak dengan algoritma Worst-Fit.
- Pemantauan status lapak, timeout, dan preemption.
- Dashboard admin dengan autentikasi sesi.
- Halaman publik untuk beranda, pendaftaran, status, dan profil.

## Persyaratan

- Python 3.10 atau lebih baru.
- Git.
- Windows PowerShell (langkah di bawah mengikuti Windows). Perintah Git dan Python dapat disesuaikan untuk macOS/Linux.

## Mengambil Repository dari GitHub

### Clone pertama kali

Di VS Code, buka terminal pada folder tempat repository akan disimpan, lalu jalankan:

```powershell
cd D:\projek
git clone https://github.com/Satria6Salam/SI-TAKAR-Core.git
cd .\SI-TAKAR-Core
```

Jika folder repository sudah ada, jangan jalankan `git clone` lagi ke dalam folder tersebut. Gunakan langkah **Pull perubahan terbaru**.

### Pull perubahan terbaru

Pada workspace yang sudah digunakan, root Git berada di `SI-TAKAR-Core`. Buka terminal VS Code dan jalankan:

```powershell
cd D:\projek\SI-TAKAR\SI-TAKAR-Core
git status --short --branch
```

Jika ada perubahan lokal, simpan dahulu dengan commit pada file yang memang ingin disimpan. Alternatifnya, simpan sementara perubahan tracked dan untracked dengan stash:

```powershell
git stash push -u -m "Simpan pekerjaan sebelum pull"
```

Lalu ambil perubahan dari branch utama:

```powershell
git pull --ff-only origin main
```

Jika tadi memakai stash, terapkan kembali perubahan setelah pull:

```powershell
git stash pop
```

Periksa `git status` sesudahnya. Jika muncul konflik saat `stash pop`, selesaikan konflik di VS Code sebelum melanjutkan. Jangan gunakan `reset --hard` untuk mengatasi konflik karena dapat menghapus perubahan lokal.

## Menyiapkan dan Menjalankan di VS Code

Buka folder workspace `D:\projek\SI-TAKAR` di VS Code. Repository backend ada di subfolder `SI-TAKAR-Core`, sedangkan virtual environment workspace yang tersedia ada di `D:\projek\SI-TAKAR\.venv`.

Di terminal PowerShell VS Code, jalankan:

```powershell
cd D:\projek\SI-TAKAR\SI-TAKAR-Core
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
if (-not (Test-Path .env)) { Copy-Item .env.example .env }
..\.venv\Scripts\python.exe seed.py
..\.venv\Scripts\python.exe -m uvicorn main:app --reload
```

Jika `.venv` belum tersedia, buat dan isi environment terlebih dahulu dari folder `SI-TAKAR-Core`:

```powershell
py -m venv ..\.venv
..\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

`seed.py` aman dijalankan berulang kali: ia menambahkan lapak contoh dan membuat akun admin demo jika akun tersebut belum ada. File `.env` dan database SQLite lokal tidak seharusnya dibagikan ke GitHub.

Setelah Uvicorn menampilkan alamat server, buka:

- Beranda: http://127.0.0.1:8000/
- Login admin: http://127.0.0.1:8000/admin/login
- Dashboard admin: http://127.0.0.1:8000/admin
- Dokumentasi API: http://127.0.0.1:8000/docs

Hentikan server dengan `Ctrl+C` di terminal yang menjalankan Uvicorn.

## Akun Demonstrasi

Pada database lokal baru setelah menjalankan `seed.py`:

| Username | Password   |
| -------- | ---------- |
| `admin`  | `admin123` |

Akun ini hanya untuk demonstrasi lokal. `seed.py` tidak mengganti password jika akun `admin` sudah tersimpan. Jangan gunakan kredensial tersebut pada deployment publik.

Untuk menetapkan secret sesi yang stabil, isi `ADMIN_SESSION_SECRET` pada `.env` dengan nilai acak yang panjang. Jika variabel itu kosong, aplikasi membuat secret acak saat proses mulai; sesi admin yang sedang aktif akan berakhir ketika server dimulai ulang.

## Menjalankan Tes

Dari folder `SI-TAKAR-Core`:

```powershell
..\.venv\Scripts\python.exe -m pytest -q
```

Tes menggunakan database SQLite sementara dan tidak memakai database demo lokal.
