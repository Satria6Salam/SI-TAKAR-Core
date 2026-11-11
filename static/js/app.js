(() => {
  "use strict";
  const KODE_KEY = "si-takar-kode";
  const page = document.body.dataset.page;
  const byId = (id) => document.getElementById(id);

  // ---------- util ----------
  const escapeHtml = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[c],
    );
  // Server menyimpan waktu UTC tanpa zona; tambahkan "Z" supaya tampil di jam lokal.
  const parseTime = (v) => (v ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(v) ? v : v + "Z") : null);
  const fmtDate = (v, withTime = false) => {
    const d = parseTime(v);
    if (!d || Number.isNaN(d.getTime())) return "–";
    return new Intl.DateTimeFormat("id-ID", {
      day: "2-digit", month: "short", year: "numeric",
      ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    }).format(d);
  };
  const meter = (n) => `${Number(n).toLocaleString("id-ID")} m`;
  const getKode = () => {
    try { return localStorage.getItem(KODE_KEY) || ""; } catch { return ""; }
  };
  const setKode = (kode) => {
    try { localStorage.setItem(KODE_KEY, kode); } catch { /* penyimpanan browser tidak tersedia */ }
  };

  async function api(path, options) {
    let response;
    try {
      response = await fetch(path, options);
    } catch {
      throw new Error("Server SI-TAKAR tidak dapat dihubungi. Pastikan aplikasi sedang berjalan.");
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      const text = Array.isArray(detail)
        ? detail.map((d) => `${(d.loc || []).slice(1).join(".")}: ${d.msg}`).join("; ")
        : detail || `Server mengembalikan status ${response.status}`;
      const error = new Error(text);
      error.status = response.status;
      throw error;
    }
    return body;
  }
  const ambilStatus = (kode, pin) =>
    pin
      ? postJson("/penjual/masuk", { kode, pin })
      : api(kode ? `/pendaftaran/${encodeURIComponent(kode)}/status` : "/penjual/saya");
  const postJson = (path, data) =>
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data),
    });

  const QUEUE_NAMA = { 1: "Prioritas Tinggi", 2: "Prioritas Menengah", 3: "Prioritas Rendah" };
  const SUMBER = {
    buatan_sendiri: "Buatan sendiri", reseller: "Reseller", waralaba: "Waralaba", impor: "Impor",
  };
  const STATUS_PILL = {
    "Menunggu Verifikasi": "pill-blue", Ditolak: "pill-red",
    Menunggu: "pill-blue", "Menunggu Konfirmasi": "pill-yellow", Aktif: "pill-green",
    Dicabut: "pill-red", Gugur: "pill-red", Selesai: "pill-grey", "Lulus Inkubasi": "pill-green",
  };
  const JENIS_PILL = {
    Timeout: "pill-yellow", Preemption: "pill-red", Peringatan: "pill-yellow",
    Alokasi: "pill-blue", Konfirmasi: "pill-green", Absen: "pill-green", Inspeksi: "pill-green",
    Verifikasi: "pill-green", Dokumen: "pill-blue", "Reset PIN": "pill-yellow",
  };

  let info = { timeout_hari: 3, peringatan_hari: 7, preemption_hari: 14, domisili_pasar: "" };
  const infoReady = api("/info")
    .then((data) => {
      info = data;
      document.querySelectorAll("[data-info]").forEach((el) => {
        if (data[el.dataset.info] !== undefined) el.textContent = data[el.dataset.info];
      });
    })
    .catch(() => {});

  document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
    button.addEventListener("click", () =>
      document.querySelector("[data-nav]")?.classList.toggle("open"),
    );
  });

  // ---------- denah (dipakai beranda) ----------
  const SEG = { Kosong: "kosong", Dipesan: "dipesan", Terisi: "terisi" };
  function renderStrips(zonaList) {
    if (!zonaList.length) return '<p class="muted small">Belum ada zona pasar yang didaftarkan.</p>';
    return zonaList
      .map((z) => {
        const segs = z.segmen
          .map((s) => {
            const label =
              s.status === "Kosong"
                ? `Ruang kosong ${meter(s.panjang)}`
                : `${s.kode_lapak} · ${s.status} · ${meter(s.panjang)}${s.penyewa ? " · " + s.penyewa : ""}`;
            return `<div class="seg seg-${SEG[s.status] || "kosong"}" style="flex:${s.panjang} 1 0" title="${escapeHtml(label)}">
              <b>${escapeHtml(s.kode_lapak || "kosong")}</b><small>${meter(s.panjang)}</small></div>`;
          })
          .join("");
        return `<div class="zone-strip">
          <div class="zone-strip-head"><b>Zona ${escapeHtml(z.kode)}</b><span>${escapeHtml(z.nama)}</span>
            <em>${meter(z.panjang)} × ${meter(z.kedalaman)} · kosong ${meter(z.kosong_m)}</em></div>
          <div class="strip">${segs}</div></div>`;
      })
      .join("");
  }

  // ---------- animasi: angka menghitung naik & elemen muncul saat digulir ----------
  const kurangiGerak = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function hitungNaik(el, nilai, akhiran = "") {
    if (!el) return;
    const tujuan = Number(nilai) || 0;
    const awal = Number(el.dataset.nilai || 0);
    el.dataset.nilai = tujuan;
    if (kurangiGerak || awal === tujuan) {
      el.textContent = tujuan.toLocaleString("id-ID") + akhiran;
      return;
    }
    const mulai = performance.now();
    const langkah = (t) => {
      const p = Math.min(1, (t - mulai) / 900);
      const v = awal + (tujuan - awal) * (1 - Math.pow(1 - p, 3));
      el.textContent = (Number.isInteger(tujuan) ? Math.round(v) : v.toFixed(1)).toLocaleString("id-ID") + akhiran;
      if (p < 1) requestAnimationFrame(langkah);
    };
    requestAnimationFrame(langkah);
  }
  const pengamat = "IntersectionObserver" in window && !kurangiGerak
    ? new IntersectionObserver((entri) => entri.forEach((e) => {
        if (e.isIntersecting) {
          e.target.classList.add("tampil");
          pengamat.unobserve(e.target);
        }
      }), { threshold: 0.12 })
    : null;
  if (pengamat) {
    document.querySelectorAll(
      ".section-head, .process-card, .ribbon, .queue-card, .split > *, .map-card, .cta-band .inner, .form-card, .side-card, .status-search, .status-result, .business-banner, .info-panel",
    ).forEach((el, i) => {
      el.classList.add("reveal");
      el.style.transitionDelay = `${(i % 4) * 80}ms`;
      pengamat.observe(el);
    });
  }

  // ---------- beranda ----------
  async function loadBeranda() {
    try {
      const peta = await api("/peta");
      const r = peta.ringkasan;
      hitungNaik(byId("avail-empty"), r.kosong_m);
      hitungNaik(byId("avail-total"), r.total_m);
      hitungNaik(byId("hero-empty"), r.kosong_m, " m");
      hitungNaik(byId("hero-filled"), r.terisi);
      hitungNaik(byId("hero-occupancy"), r.keterisian_persen, "%");
      hitungNaik(byId("ribbon-empty"), r.kosong_m);
      byId("avail-updated").textContent =
        `${r.terisi} lapak terisi · ${r.dipesan} menunggu konfirmasi · keterisian ${r.keterisian_persen}%`;
      byId("zone-list").innerHTML = peta.zona
        .map((z) => {
          const persen = z.panjang ? Math.round((z.terpakai_m / z.panjang) * 100) : 0;
          return `<div class="zone-row"><div><span>Zona ${escapeHtml(z.kode)} · ${escapeHtml(z.nama)}</span>
            <b class="${z.kosong_m > 0 ? "" : "coral-text"}">${meter(z.kosong_m)} kosong</b></div>
            <div class="progress"><i class="${persen >= 85 ? "coral-fill" : ""}" style="width:${persen}%"></i></div></div>`;
        })
        .join("");
      const note = byId("avail-note");
      const f = peta.fragmentasi;
      note.hidden = false;
      note.textContent = f.jumlah_hole
        ? `✦ Ruang kosong bersambung terluas saat ini ${meter(f.hole_terbesar_m)}. Lapak berikutnya dipotong dari sana (Worst-Fit).`
        : "✦ Seluruh ruang pasar sedang terpakai. Pendaftar baru menunggu di antrean sampai ada lapak yang dilepas.";
      byId("public-map").innerHTML = renderStrips(peta.zona);
    } catch (error) {
      byId("avail-updated").textContent = error.message;
    }
  }

  // ---------- pendaftaran ----------
  function initPendaftaran() {
    const form = byId("registration-form");
    const message = byId("form-message");
    const kotaWrap = byId("kota-asal-wrap");
    const show = (text, type) => {
      message.className = `inline-message show ${type}`;
      message.textContent = text;
    };
    const domisili = () =>
      form.elements.asal.value === "lokal"
        ? info.domisili_pasar
        : form.elements.kota_asal.value.trim() || "Luar kota";

    async function updatePreview() {
      kotaWrap.hidden = form.elements.asal.value !== "luar";
      form.elements.kota_asal.required = !kotaWrap.hidden;
      const khusus = form.elements.status_khusus.checked;
      byId("khusus-wrap").hidden = !khusus;
      form.elements.dok_khusus.required = khusus;
      const jenis = form.elements.jenis_usaha.value;
      if (!jenis) return;
      await infoReady;
      const params = new URLSearchParams({
        domisili: domisili(), jenis_usaha: jenis,
        status_khusus: form.elements.status_khusus.checked,
        jumlah_cabang: form.elements.jumlah_cabang.value,
        sumber_produk: form.elements.sumber_produk.value,
      });
      try {
        const p = await api(`/pendaftaran/pratinjau?${params}`);
        const badge = byId("preview-badge");
        badge.textContent = `Q${p.queue_level}`;
        badge.className = `queue-big q${p.queue_level}`;
        byId("preview-title").textContent = `Queue ${p.queue_level} · ${p.nama_queue}`;
        byId("preview-sub").textContent = "Dihitung sistem dari jawaban Anda:";
        byId("preview-reasons").innerHTML = p.alasan
          .map((a) => `<li>${escapeHtml(a)}</li>`).join("");
      } catch { /* pratinjau bersifat tambahan; abaikan bila gagal */ }
    }

    async function updateFit() {
      const box = byId("fit-preview");
      const butuh = form.elements.kebutuhan_muka.value;
      try {
        const sim = await api(`/peta/simulasi?kebutuhan=${butuh}`);
        const w = sim.hasil.worst;
        box.className = `fit-preview ${w ? "fit-ok" : "fit-wait"}`;
        box.innerHTML = w
          ? `<b>Ada ruang yang muat.</b> Ruang kosong terluas ada di Zona ${escapeHtml(w.zona)} (${meter(w.hole_panjang_m)}). Bila giliran Anda tiba sekarang, lapak ${meter(butuh)} dipotong dari sana dan tersisa ${meter(w.sisa_potongan_m)}.`
          : `<b>Belum ada ruang bersambung ${meter(butuh)}.</b> Ruang kosong terluas saat ini ${meter(sim.sekarang.hole_terbesar_m)}. Anda tetap bisa mendaftar dan menunggu di antrean.`;
      } catch (error) {
        box.textContent = error.message;
      }
    }

    form.addEventListener("input", updatePreview);
    form.addEventListener("change", updatePreview);
    form.elements.kebutuhan_muka.addEventListener("change", updateFit);
    updatePreview();
    updateFit();

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const el = form.elements;
      el.pin2.setCustomValidity(el.pin.value === el.pin2.value ? "" : "PIN tidak sama");
      for (const input of [el.ktp, el.dok_khusus]) {
        input.setCustomValidity(cekBerkas(input.files[0]));
      }
      if (!form.reportValidity()) return;
      const button = form.querySelector("button[type='submit']");
      const payload = {
        nama_pemilik: el.nama_pemilik.value.trim(),
        nik: el.nik.value.trim(),
        telepon: el.telepon.value.trim(),
        email: el.email.value.trim() || null,
        nama_usaha: el.nama_usaha.value.trim(),
        jenis_usaha: el.jenis_usaha.value,
        deskripsi: el.deskripsi.value.trim() || null,
        domisili: domisili(),
        sumber_produk: el.sumber_produk.value,
        status_khusus: el.status_khusus.checked,
        jumlah_cabang: Number(el.jumlah_cabang.value),
        kebutuhan_muka: Number(el.kebutuhan_muka.value),
        pin: el.pin.value,
      };
      button.disabled = true;
      button.textContent = "Mengirim…";
      let hasil;
      try {
        await infoReady;
        payload.domisili = domisili();
        hasil = await postJson("/pendaftaran", payload);
      } catch (error) {
        show(error.message, "error");
        button.disabled = false;
        button.textContent = "Daftarkan UMKM sekarang →";
        return;
      }
      const kode = hasil.umkm.kode_pendaftaran;
      setKode(kode);
      // Pendaftaran sudah tersimpan; dokumen diunggah sesudahnya. Bila unggah gagal,
      // pendaftar bisa mengulanginya dari halaman Status.
      const gagal = [];
      const berkas = [["ktp", el.ktp.files[0]], ["khusus", payload.status_khusus ? el.dok_khusus.files[0] : null]];
      for (const [jenis, file] of berkas) {
        if (!file) continue;
        try {
          await unggahBerkas(kode, payload.pin, jenis, file);
        } catch (error) {
          gagal.push(`${jenis === "ktp" ? "KTP" : "bukti status khusus"}: ${error.message}`);
        }
      }
      form.hidden = true;
      byId("success-card").hidden = false;
      byId("success-code").textContent = kode;
      byId("success-link").href = "/status?kode=" + encodeURIComponent(kode);
      byId("success-detail").innerHTML = gagal.length
        ? `<span class="inline-message show error">Dokumen belum terkirim (${escapeHtml(gagal.join("; "))}). Unggah ulang dari halaman Status.</span>`
        : `Perkiraan jalur: <b>Queue ${hasil.umkm.queue_level}</b>. ${
            hasil.umkm.status_pendaftaran === "Menunggu Verifikasi"
              ? "Pengelola akan memeriksa dokumen Anda. Urutan antrean tetap dihitung dari waktu daftar hari ini."
              : ""}`;
      byId("copy-code").addEventListener("click", async (e) => {
        try {
          await navigator.clipboard.writeText(kode);
          e.target.textContent = "✓ Tersalin";
        } catch {
          e.target.textContent = "Salin manual";
        }
      });
      window.scrollTo({ top: 0, behavior: "smooth" });
    });
  }

  // ---------- berkas ----------
  const TIPE_BERKAS = ["image/jpeg", "image/png", "application/pdf"];
  function cekBerkas(file) {
    if (!file) return "";
    if (!TIPE_BERKAS.includes(file.type)) return "Berkas harus foto JPG/PNG atau PDF";
    const maks = (info.maks_unggah_mb || 2) * 1024 * 1024;
    if (file.size > maks) return `Ukuran berkas maksimal ${info.maks_unggah_mb || 2} MB`;
    return "";
  }
  const bacaBerkas = (file) =>
    new Promise((resolve, reject) => {
      const r = new FileReader();
      r.onload = () => resolve(r.result);
      r.onerror = () => reject(new Error("Berkas tidak bisa dibaca"));
      r.readAsDataURL(file);
    });
  async function unggahBerkas(kode, pin, jenis, file) {
    const salah = cekBerkas(file);
    if (salah) throw new Error(salah);
    return postJson(`/pendaftaran/${encodeURIComponent(kode)}/dokumen`, {
      pin, jenis, nama_file: file.name, data_base64: await bacaBerkas(file),
    });
  }

  // ---------- status ----------
  function riwayatHtml(rows) {
    if (!rows.length) return '<p class="muted small">Belum ada riwayat.</p>';
    return rows
      .map(
        (r) => `<div class="activity-row"><time>${fmtDate(r.waktu, true)}</time>
          <span>${escapeHtml(r.keterangan || "")}</span>
          <span class="pill ${JENIS_PILL[r.jenis] || "pill-grey"}">${escapeHtml(r.jenis)}</span></div>`,
      )
      .join("");
  }

  function initStatus() {
    const result = byId("status-result");
    const input = byId("status-code");
    let timer = null;
    let poll = null;
    let current = "";

    const hitungMundur = (detik) => {
      const d = Math.floor(detik / 86400);
      const j = Math.floor((detik % 86400) / 3600);
      const m = Math.floor((detik % 3600) / 60);
      const s = detik % 60;
      return `${d} hari ${String(j).padStart(2, "0")}:${String(m).padStart(2, "0")}:${String(s).padStart(2, "0")}`;
    };

    function alokasiHtml(data) {
      const u = data.umkm;
      const a = data.alokasi;
      const st = u.status_pendaftaran;
      if (st === "Menunggu Verifikasi") {
        const dok = (ada, label) => `<li class="${ada ? "doc-ok" : "doc-no"}">${ada ? "✓" : "✗"} ${label} ${ada ? "sudah diunggah" : "belum diunggah"}</li>`;
        const kurang = !u.punya_ktp || (u.status_khusus && !u.punya_dok_khusus);
        return `<div class="notice notice-blue"><b>Data Anda sedang diperiksa pengelola.</b>
          Setelah diterima, Anda langsung masuk antrean Queue ${u.queue_level}. Urutannya dihitung dari waktu daftar, jadi lamanya pemeriksaan tidak merugikan Anda.
          <ul class="doc-status">${dok(u.punya_ktp, "KTP")}${u.status_khusus ? dok(u.punya_dok_khusus, "Bukti status khusus") : ""}</ul></div>
        <form class="upload-form" id="upload-form">
          <b>${kurang ? "Lengkapi dokumen" : "Ganti dokumen (bila perlu)"}</b>
          <div class="upload-row">
            <select name="jenis">
              <option value="ktp">KTP</option>
              ${u.status_khusus ? `<option value="khusus" ${u.punya_ktp ? "selected" : ""}>Bukti status khusus</option>` : ""}
            </select>
            <input type="file" name="berkas" required accept=".jpg,.jpeg,.png,.pdf,image/jpeg,image/png,application/pdf" />
            <input type="password" name="pin" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="PIN" autocomplete="current-password" />
            <button class="btn btn-green" type="submit">Unggah</button>
          </div>
          <p class="form-note" id="upload-msg"></p>
        </form>`;
      }
      if (st === "Ditolak") {
        return `<div class="notice notice-grey"><b>Pendaftaran ditolak pengelola.</b>
          Alasan: ${escapeHtml(u.catatan_verifikasi || "-")}. Anda boleh mendaftar ulang dengan data yang benar.
          <a class="text-link" href="/pendaftaran">Daftar ulang →</a></div>`;
      }
      if (st === "Menunggu") {
        const ulang = u.jumlah_timeout
          ? ` Anda sudah ${u.jumlah_timeout} kali melewati batas konfirmasi; setelah ${info.maks_timeout} kali pendaftaran gugur.`
          : "";
        return `<div class="notice notice-blue"><b>Anda berada di urutan ke-${data.posisi_dalam_queue} dari ${data.jumlah_di_queue} di Queue ${u.queue_level}.</b>
          Lapak dibagikan pada putaran alokasi berikutnya: Queue 1 dilayani lebih dulu, lalu Queue 2, lalu Queue 3, selama ada ruang bersambung minimal ${meter(u.kebutuhan_muka)}.${ulang}</div>`;
      }
      if (st === "Menunggu Konfirmasi" && a) {
        return `<div class="offer-box">
          <div><span class="kicker">LAPAK TERSEDIA UNTUK ANDA</span>
            <strong>${escapeHtml(a.kode_lapak)}</strong>
            <p>Zona ${escapeHtml(a.zona)} · meter ke-${a.mulai} sampai ${a.mulai + a.panjang} · ${a.panjang} × ${a.lebar} m (${a.luas} m²)</p></div>
          <div class="offer-timer"><small>Sisa waktu konfirmasi</small>
            <b id="countdown">${hitungMundur(a.sisa_detik_konfirmasi)}</b>
            <input id="confirm-pin" type="password" inputmode="numeric" pattern="[0-9]{6}" maxlength="6" placeholder="PIN (bila diminta)" autocomplete="current-password" aria-label="PIN" />
            <button class="btn btn-coral" id="confirm-button" type="button">Konfirmasi lapak ini</button>
            <small class="confirm-msg" id="confirm-msg" role="alert"></small></div>
        </div>
        <p class="form-note">Bila tidak dikonfirmasi dalam ${info.timeout_hari} hari, hak atas lapak ini hangus dan Anda dipindah ke urutan terbawah Queue ${u.queue_level}.</p>`;
      }
      if (st === "Aktif" && a) {
        return `<div class="notice notice-green"><b>Anda penyewa aktif lapak ${escapeHtml(a.kode_lapak)}.</b>
          Masa sewa sampai ${fmtDate(a.sewa_berakhir)}. Jangan lupa mencatat kios buka setiap hari berjualan.
          <a class="text-link" href="/profil?kode=${encodeURIComponent(u.kode_pendaftaran)}">Buka halaman Lapak Saya →</a></div>`;
      }
      const pesan = {
        Dicabut: "Hak sewa dicabut karena lapak tidak aktif melewati batas. Lapaknya sudah diberikan ke antrean berikutnya.",
        Gugur: "Pendaftaran gugur karena batas konfirmasi terlewat berulang kali.",
        Selesai: "Masa sewa sudah berakhir. Data usaha Anda tersimpan di arsip pasar.",
        "Lulus Inkubasi": "Selamat, usaha Anda tercatat lulus inkubasi dan pindah ke tempat mandiri.",
      }[st];
      return `<div class="notice notice-grey"><b>${escapeHtml(st)}.</b> ${pesan || ""}
        ${st !== "Lulus Inkubasi" ? '<a class="text-link" href="/pendaftaran">Daftar kembali →</a>' : ""}</div>`;
    }

    function timelineHtml(st) {
      const urutan = ["Menunggu Verifikasi", "Menunggu", "Menunggu Konfirmasi", "Aktif"];
      const idx = urutan.indexOf(st);
      const akhir = idx === -1;
      const steps = [
        ["Terdaftar dan dinilai", "Jalur antrean dihitung sistem (Multilevel Queue)"],
        ["Dokumen diverifikasi", "Pengelola memeriksa KTP dan bukti status khusus"],
        ["Mengantre", "Queue 1 dilayani dulu, di dalam queue berlaku siapa lebih dulu"],
        ["Lapak dialokasikan", `Dipotong dari ruang kosong terluas, konfirmasi maksimal ${info.timeout_hari} hari`],
        ["Aktif berjualan", `Catat kios buka; tutup ${info.preemption_hari} hari berarti hak dicabut`],
      ];
      return steps
        .map(([judul, ket], i) => {
          const selesai = akhir || i <= idx;
          const kini = !akhir && i === idx + 1;
          return `<div class="timeline-item ${selesai ? "done" : kini ? "current" : ""}"><span>${selesai ? "✓" : i + 1}</span>
            <div><b>${judul}</b><small>${ket}</small></div></div>`;
        })
        .join("");
    }

    function render(data) {
      const u = data.umkm;
      window.clearInterval(timer);
      result.innerHTML = `
        <div class="status-top"><div><span class="kicker">KODE PENDAFTARAN</span><h2>${escapeHtml(u.kode_pendaftaran)}</h2>
          <p>${escapeHtml(u.nama_usaha)} · ${escapeHtml(u.nama_pemilik)} · didaftarkan ${fmtDate(u.waktu_daftar)}</p></div>
          <div class="status-top-actions"><span class="pill ${STATUS_PILL[u.status_pendaftaran] || "pill-grey"}">${escapeHtml(u.status_pendaftaran)}</span><button class="btn btn-light" id="status-logout" type="button">Keluar</button></div></div>
        <div class="status-detail-grid">
          <div class="status-detail"><small>Jalur antrean</small><b><span class="queue-chip q${u.queue_level}">Queue ${u.queue_level}</span> ${QUEUE_NAMA[u.queue_level]}</b></div>
          <div class="status-detail"><small>Posisi di queue</small><b>${data.posisi_dalam_queue ? `ke-${data.posisi_dalam_queue} dari ${data.jumlah_di_queue}` : u.status_pendaftaran === "Menunggu Verifikasi" ? "Masuk setelah diverifikasi" : "Sudah tidak mengantre"}</b></div>
          <div class="status-detail"><small>Kebutuhan ruang</small><b>Muka ${meter(u.kebutuhan_muka)}</b></div>
        </div>
        ${alokasiHtml(data)}
        <div class="reason-box"><b>Mengapa Queue ${u.queue_level}?</b>
          <ul class="reason-list">${u.alasan_queue.map((a) => `<li>${escapeHtml(a)}</li>`).join("")}</ul>
          ${u.queue_awal !== u.queue_level ? `<p class="form-note">Awalnya Queue ${u.queue_awal}; naik karena sudah lama menunggu (aging).</p>` : ""}
          ${u.status_verifikasi === "Klaim Khusus Ditolak" ? `<p class="form-note">Klaim status khusus tidak diterima pengelola${u.catatan_verifikasi ? `: ${escapeHtml(u.catatan_verifikasi)}` : ""}. Jalur dihitung ulang tanpa status khusus.</p>` : ""}</div>`;
      byId("process-card").hidden = false;
      byId("process-timeline").innerHTML = timelineHtml(u.status_pendaftaran);
      byId("history-card").hidden = false;
      byId("history-list").innerHTML = riwayatHtml(data.riwayat);

      const cd = byId("countdown");
      if (cd && data.alokasi) {
        let sisa = data.alokasi.sisa_detik_konfirmasi;
        timer = window.setInterval(() => {
          sisa = Math.max(0, sisa - 1);
          cd.textContent = hitungMundur(sisa);
          if (sisa === 0) load(current, true);
        }, 1000);
      }
      byId("confirm-button")?.addEventListener("click", async (event) => {
        const pin = byId("confirm-pin").value.trim();
        event.target.disabled = true;
        try {
          await postJson(`/alokasi/${encodeURIComponent(u.kode_pendaftaran)}/konfirmasi`, pin ? { pin } : {});
          await load(current, true);
        } catch (error) {
          event.target.disabled = false;
          byId("confirm-msg").textContent = error.message;
        }
      });
      byId("status-logout").addEventListener("click", async () => {
        await postJson("/penjual/keluar").catch(() => {});
        mintaPin("Anda sudah keluar", "Masukkan kode pendaftaran dan PIN untuk melihat status lagi.");
      });
      byId("upload-form")?.addEventListener("submit", async (event) => {
        event.preventDefault();
        const f = event.currentTarget;
        const msg = byId("upload-msg");
        const file = f.elements.berkas.files[0];
        f.elements.berkas.setCustomValidity(cekBerkas(file));
        if (!f.reportValidity()) return;
        const tombol = f.querySelector("button");
        tombol.disabled = true;
        msg.textContent = "Mengunggah…";
        try {
          await unggahBerkas(u.kode_pendaftaran, f.elements.pin.value || null, f.elements.jenis.value, file);
          await load(current, true);
        } catch (error) {
          msg.textContent = error.message;
          tombol.disabled = false;
        }
      });
    }

    async function load(kode, diam = false) {
      const target = kode.trim().toUpperCase();
      if (!target) return;
      try {
        await infoReady;
        const pinEl = byId("status-pin");
        const data = await ambilStatus(target, diam ? "" : pinEl.value.trim());
        pinEl.value = "";
        current = target;            // pembaruan otomatis hanya setelah berhasil masuk
        setKode(current);
        render(data);
      } catch (error) {
        if (diam) return;
        window.clearInterval(timer);
        byId("process-card").hidden = true;
        byId("history-card").hidden = true;
        result.innerHTML = `<div class="empty-state"><span class="empty-icon">⌕</span>
          <h2>${error.status === 401 ? "Masukkan PIN Anda" : error.status === 404 ? "Kode pendaftaran tidak ditemukan" : error.status === 403 ? "PIN salah" : "Status tidak dapat dimuat"}</h2>
          <p>${escapeHtml(error.status === 401 ? "Demi privasi, status hanya bisa dibuka pemiliknya dengan kode pendaftaran dan PIN." : error.status === 404 ? "Periksa kembali kode Anda, atau lakukan pendaftaran terlebih dahulu." : error.message)}</p>
          <a class="btn btn-outline" href="/pendaftaran">Daftar UMKM</a></div>`;
      }
    }

    // Seperti Lapak Saya, status selalu meminta PIN setiap kali halaman dibuka.
    const mintaPin = (judul, teks) => {
      window.clearInterval(timer);
      current = "";
      byId("process-card").hidden = true;
      byId("history-card").hidden = true;
      result.innerHTML = `<div class="empty-state"><span class="empty-icon">🔒</span>
        <h2>${judul}</h2><p>${teks}</p>
        <a class="text-link" href="/lupa-kode">Lupa kode pendaftaran?</a></div>`;
    };
    byId("status-search-form").addEventListener("submit", (event) => {
      event.preventDefault();
      if (!input.value.trim() || !/^\d{6}$/.test(byId("status-pin").value.trim())) {
        mintaPin("Masukkan kode dan PIN", "Isi kode pendaftaran dan PIN 6 angka yang Anda buat saat mendaftar.");
        byId(input.value.trim() ? "status-pin" : "status-code").focus();
        return;
      }
      load(input.value);
    });
    input.value = new URLSearchParams(window.location.search).get("kode") || getKode();
    mintaPin("Masuk untuk melihat status", "Demi privasi, status pendaftaran hanya terbuka setelah Anda memasukkan kode pendaftaran dan PIN.");
    poll = window.setInterval(() => current && load(current, true), 20000);
    window.addEventListener("pagehide", () => {
      window.clearInterval(poll);
      window.clearInterval(timer);
    });
  }

  // ---------- lapak saya ----------
  function initProfil() {
    const empty = byId("profile-empty");
    const content = byId("profile-content");
    const button = byId("activity-button");
    const message = byId("activity-message");
    let kode = "";

    function showEmpty(title, text) {
      content.hidden = true;
      empty.hidden = false;
      byId("profile-empty-title").textContent = title;
      byId("profile-empty-text").innerHTML = text;
    }

    function render(data) {
      const u = data.umkm;
      const a = data.alokasi;
      if (u.status_pendaftaran !== "Aktif" || !a) {
        const link = `<a class="text-link" href="/status?kode=${encodeURIComponent(u.kode_pendaftaran)}">Lihat halaman status →</a>`;
        showEmpty(
          `${u.nama_usaha}: ${u.status_pendaftaran}`,
          `Halaman ini hanya untuk penyewa yang lapaknya sudah dikonfirmasi. ${link}`,
        );
        return;
      }
      empty.hidden = true;
      content.hidden = false;
      byId("profile-business").textContent = u.nama_usaha;
      byId("profile-owner").textContent = `Pemilik: ${u.nama_pemilik} · Kode ${u.kode_pendaftaran}`;
      const pill = byId("profile-status");
      pill.className = `pill ${a.peringatan ? "pill-yellow" : "pill-green"}`;
      pill.textContent = a.peringatan ? "Peringatan tidak aktif" : "Kios aktif";
      byId("p-jenis").textContent = u.jenis_usaha;
      byId("p-sumber").textContent = SUMBER[u.sumber_produk] || u.sumber_produk;
      byId("p-domisili").textContent = u.domisili;
      byId("p-queue").textContent = `Queue ${u.queue_level} · ${QUEUE_NAMA[u.queue_level]}`;
      byId("p-deskripsi").textContent = u.deskripsi || "Belum diisi";
      byId("p-pemilik").textContent = u.nama_pemilik;
      byId("p-telepon").textContent = u.telepon;
      byId("p-sewa-mulai").textContent = fmtDate(a.sewa_mulai);
      byId("p-sewa-akhir").textContent = `${fmtDate(a.sewa_berakhir)} (${a.sisa_hari_sewa} hari lagi)`;
      byId("p-lapak").textContent = a.kode_lapak;
      byId("p-lapak-detail").textContent =
        `Zona ${a.zona} · meter ke-${a.mulai} sampai ${a.mulai + a.panjang} · ${a.panjang} × ${a.lebar} m`;
      const hari = a.hari_tidak_aktif;
      const sudah = a.sudah_absen_hari_ini;
      button.className = `btn absen-btn ${sudah ? "sudah" : "belum"}`;
      button.disabled = sudah;
      button.textContent = sudah ? "✓ Kios sudah tercatat buka hari ini" : "☀ Buka kios hari ini";
      const st = byId("absen-status");
      st.className = `absen-status ${sudah ? "sudah" : "belum"}`;
      st.innerHTML = sudah
        ? `<i></i> Sudah absen hari ini, pukul ${new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit" }).format(parseTime(a.terakhir_absen))}`
        : "<i></i> Belum absen hari ini";
      byId("p-terakhir").textContent =
        `Terakhir buka: ${fmtDate(a.terakhir_aktif, true)}${hari ? ` (${hari} hari lalu)` : ""}`;
      const batas = info.preemption_hari || 14;
      const bar = byId("p-meter");
      bar.style.width = `${Math.min(100, Math.max(3, (hari / batas) * 100))}%`;
      bar.className = hari >= info.peringatan_hari ? "danger" : hari >= 3 ? "" : "ok";
      byId("p-meter-text").textContent = a.peringatan
        ? `Peringatan: kios sudah ${hari} hari tutup. Sisa ${Math.max(0, batas - hari)} hari sebelum hak sewa dicabut.`
        : `Kios tercatat tutup ${hari} hari berturut-turut dari batas ${batas} hari.`;
      byId("p-riwayat").innerHTML = riwayatHtml(data.riwayat);
    }

    async function load(k) {
      kode = k.trim().toUpperCase();
      try {
        await infoReady;
        const pinEl = byId("profile-pin");
        const data = await ambilStatus(kode, pinEl.value.trim());
        pinEl.value = "";
        kode = data.umkm.kode_pendaftaran;
        setKode(kode);
        render(data);
      } catch (error) {
        showEmpty(
          error.status === 401 ? "Masuk dengan kode dan PIN" : error.status === 404 ? "Kode pendaftaran tidak ditemukan" : error.status === 403 ? "PIN salah" : "Data tidak dapat dimuat",
          escapeHtml(error.status === 401 ? "Lapak Saya hanya bisa dibuka pemiliknya. Masukkan kode pendaftaran dan PIN Anda." : error.status === 404 ? "Periksa kembali kode Anda." : error.message),
        );
      }
    }

    // Lapak Saya selalu meminta PIN setiap kali dibuka, walaupun browser masih punya sesi.
    byId("profile-code-form").addEventListener("submit", (event) => {
      event.preventDefault();
      const kodeIsi = byId("profile-code").value.trim();
      const pin = byId("profile-pin").value.trim();
      if (!kodeIsi || !/^\d{6}$/.test(pin)) {
        showEmpty("Masukkan kode dan PIN", "Isi kode pendaftaran dan PIN 6 angka yang Anda buat saat mendaftar.");
        byId(kodeIsi ? "profile-pin" : "profile-code").focus();
        return;
      }
      load(kodeIsi);
    });
    byId("profile-logout").addEventListener("click", async () => {
      await postJson("/penjual/keluar").catch(() => {});
      showEmpty("Anda sudah keluar", "Masukkan kode pendaftaran dan PIN untuk membuka Lapak Saya lagi.");
      byId("profile-code").value = kode;
      byId("profile-pin").focus();
    });
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await postJson(`/alokasi/${encodeURIComponent(kode)}/absen`, {});
        message.textContent = "Kios buka tercatat. Hitungan hari tidak aktif kembali ke nol.";
        await load(kode);
      } catch (error) {
        message.textContent = error.message;
        button.disabled = false;
      }
    });
    byId("profile-code").value = new URLSearchParams(window.location.search).get("kode") || getKode();
    showEmpty(
      "Masuk ke Lapak Saya",
      "Demi keamanan, Lapak Saya hanya terbuka setelah Anda memasukkan kode pendaftaran dan PIN.",
    );
    byId(byId("profile-code").value ? "profile-pin" : "profile-code").focus();
  }

  if (page === "beranda") {
    loadBeranda();
    window.setInterval(loadBeranda, 15000);
  }
  if (page === "pendaftaran") initPendaftaran();
  if (page === "status") initStatus();
  if (page === "profil") initProfil();
  if (page === "lupa") initLupa();

  // ---------- lupa kode ----------
  function initLupa() {
    const form = byId("lupa-form");
    const hasil = byId("lupa-result");
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!form.reportValidity()) return;
      const tombol = form.querySelector("button");
      tombol.disabled = true;
      hasil.hidden = false;
      try {
        const rows = await postJson("/pendaftaran/lupa-kode", {
          nik: form.elements.nik.value.trim(), telepon: form.elements.telepon.value.trim(),
        });
        hasil.innerHTML = `<h2 class="result-title">${rows.length} pendaftaran ditemukan</h2>
          <div class="found-list">${rows
            .map((r) => `<a class="found-row" href="/status?kode=${encodeURIComponent(r.kode_pendaftaran)}" data-kode="${escapeHtml(r.kode_pendaftaran)}">
              <div><b>${escapeHtml(r.kode_pendaftaran)}</b><span>${escapeHtml(r.nama_usaha)} · daftar ${fmtDate(r.waktu_daftar)} · Queue ${r.queue_level}</span></div>
              <span class="pill ${STATUS_PILL[r.status_pendaftaran] || "pill-grey"}">${escapeHtml(r.status_pendaftaran)}</span></a>`)
            .join("")}</div>
          <p class="form-note">Klik salah satu untuk membuka statusnya. Catat kodenya agar tidak perlu mencari lagi.</p>`;
        hasil.querySelectorAll("[data-kode]").forEach((a) =>
          a.addEventListener("click", () => setKode(a.dataset.kode)));
      } catch (error) {
        hasil.innerHTML = `<div class="empty-state"><span class="empty-icon">⌕</span>
          <h2>${error.status === 404 ? "Data tidak cocok" : "Pencarian gagal"}</h2>
          <p>${escapeHtml(error.status === 404
            ? "Tidak ada pendaftaran dengan NIK dan nomor telepon tersebut. Periksa kembali, atau hubungi pengelola pasar."
            : error.message)}</p></div>`;
      } finally {
        tombol.disabled = false;
      }
    });
  }
})();
