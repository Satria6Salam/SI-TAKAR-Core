# SI-TAKAR Frontend

Halaman HTML yang disajikan langsung oleh FastAPI (`main.py`). Semua data berasal dari API; tidak ada lagi data contoh yang ditulis di HTML.

| Berkas | Alamat | Sumber data |
| --- | --- | --- |
| `index.html` | `/` | `GET /peta`, `GET /info` |
| `pendaftaran.html` | `/pendaftaran` | `GET /pendaftaran/pratinjau`, `GET /peta/simulasi`, `POST /pendaftaran` |
| `status.html` | `/status` | `GET /pendaftaran/{kode}/status`, `POST /alokasi/{kode}/konfirmasi` |
| `profil.html` | `/profil` | `GET /pendaftaran/{kode}/status`, `POST /alokasi/{kode}/absen` |
| `admin.html` | `/admin` | endpoint admin (perlu login) |
| `admin_login.html` | `/admin/login` | `POST /admin/login` |

Logika halaman publik ada di `static/js/app.js` (dipilih lewat atribut `data-page` pada `<body>`), dashboard di `static/js/admin.js`. Browser hanya menyimpan kode pendaftaran terakhir di `localStorage` supaya pengguna tidak perlu mengetik ulang.

Buka halaman lewat server (`http://127.0.0.1:8000/`), bukan dengan membuka berkas HTML langsung, karena halaman memanggil API di alamat yang sama.
