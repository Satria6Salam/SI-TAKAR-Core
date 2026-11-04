# SI-TAKAR Frontend

Antarmuka HTML, CSS, dan JavaScript terhubung ke API FastAPI untuk pendaftaran, antrean, status lapak, konfirmasi, dan aktivitas penyewa.

## Halaman

- `index.html` — beranda publik dan ringkasan ketersediaan kios.
- `pendaftaran.html` — formulir pendaftaran UMKM dengan validasi.
- `status.html` — pencarian status pendaftaran demo.
- `profil.html` — profil dan aktivitas penyewa demo.

## Menjalankan di VS Code

1. Ekstrak ZIP ini.
2. Buka folder `si-takar-frontend` di VS Code.
3. Klik kanan `index.html` lalu pilih **Open with Live Server** (jika ekstensi Live Server tersedia).
4. Jika belum memasang Live Server, buka `index.html` langsung melalui browser.

## Alur yang tersedia

- Formulir mengirim data pendaftaran dan kriteria MLQ ke API.
- Nomor pendaftaran diterbitkan server dan dapat dicari melalui halaman Status.
- Halaman Status menampilkan antrean, verifikasi, alokasi, serta aksi konfirmasi lapak.
- Panel Profil mengirim aktivitas buka kios ke API.
- Dashboard Admin menampilkan antrean, verifikasi, denah lapak, dan log Timeout/Preemption.

Unggah dokumen pendukung belum diimplementasikan. Jalankan `python seed.py` untuk membuat lapak dan akun admin awal pada database development.
