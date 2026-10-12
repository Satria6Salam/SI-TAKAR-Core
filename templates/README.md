# SI-TAKAR Frontend — Starter

Frontend awal berbasis HTML, CSS, dan JavaScript murni dengan visual terinspirasi dari file Figma SI-TAKAR yang diberikan.

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

## Interaksi saat ini
- Navigasi antarhalaman.
- Validasi dasar pada formulir.
- Formulir demo menyimpan data di `localStorage` browser.
- Halaman Status membaca data demo tersebut.
- Tombol aktivitas di Profil memberi umpan balik di halaman.

## Penting
Ini adalah prototype frontend, belum terhubung ke FastAPI atau database. Data formulir disimpan hanya pada browser yang sama. File upload hanya tampil sebagai input dan belum mengirim berkas. Nilai statistik/kios pada beranda dan profil adalah data contoh. Sebelum integrasi, sesuaikan URL endpoint, nama field, skema backend, dan aturan validasi dengan kode Fajar. Jangan menimpa file di repository tim; bandingkan dulu dan pindahkan perubahan ke branch frontend Mahsa.
