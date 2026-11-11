(() => {
  "use strict";
  const byId = (id) => document.getElementById(id);
  const notice = byId("dashboard-notice");
  let info = { timeout_hari: 3, peringatan_hari: 7, preemption_hari: 14, maks_timeout: 3 };

  // ---------- halaman aktif dari alamat: /admin, /admin/verifikasi, ... ----------
  const HALAMAN = {
    ringkasan: ["PANEL PENGELOLA", "Ringkasan operasional",
      "Antrean prioritas, pemotongan ruang, dan pencegahan lapak tertahan berjalan otomatis."],
    verifikasi: ["VERIFIKASI DOKUMEN", "Pendaftar menunggu pemeriksaan",
      "Periksa KTP dan bukti status khusus. Hanya pendaftar yang diterima yang masuk antrean; urutannya tetap dihitung dari waktu daftar."],
    pendaftar: ["DATA PENDAFTAR", "Cari pendaftar",
      "Cari pemilik yang lupa kode, lihat dokumen dan riwayatnya, atau atur ulang PIN setelah mencocokkan KTP asli."],
    antrean: ["PILAR 1 · MANAJEMEN PROSES", "Antrean Multilevel Queue",
      "Lapak dibagikan per putaran: dalam satu putaran Queue 1 dilayani sampai habis, lalu Queue 2, lalu Queue 3. Di dalam satu queue berlaku siapa lebih dulu mendaftar."],
    denah: ["PILAR 2 · MANAJEMEN MEMORI", "Denah pasar dan ruang kosong",
      "Lapak dipotong dari ruang kosong terluas (Worst-Fit) sepanjang kebutuhan pendaftar."],
    penyewa: ["PILAR 3 · SIKLUS SEWA", "Penyewa dan masa sewa",
      "Lapak yang sedang ditempati beserta timer konfirmasi, hari tidak aktif, dan sisa masa sewa."],
    deadlock: ["PILAR 4 · PENANGANAN DEADLOCK", "Monitor timeout dan preemption",
      "Lapak yang ditahan tanpa dipakai dilepas otomatis dan diberikan ke antrean berikutnya."],
    arsip: ["PILAR 3 · MANAJEMEN PENYIMPANAN", "Jurnal dan arsip",
      "Seluruh kejadian tercatat. UMKM yang keluar dari pasar diarsipkan, tidak dihapus."],
  };
  const slug = location.pathname.replace(/\/+$/, "").split("/")[2] || "ringkasan";
  const PAGE = HALAMAN[slug] ? slug : "ringkasan";
  const [eyebrow, judul, desk] = HALAMAN[PAGE];
  byId("page-eyebrow").textContent = eyebrow;
  byId("page-title").textContent = judul;
  byId("page-desc").textContent = desk;
  byId("crumb").textContent = judul;
  document.title = `${judul} | SI-TAKAR`;
  document.querySelector(`[data-page="${PAGE}"]`).hidden = false;
  document.querySelectorAll("[data-show]").forEach((el) => {
    el.hidden = !el.dataset.show.split(" ").includes(PAGE);
  });
  document.querySelectorAll("[data-nav]").forEach((a) => {
    const aktif = a.dataset.nav === PAGE;
    a.classList.toggle("selected", aktif);
    if (aktif) a.setAttribute("aria-current", "page");
  });
  byId("nav-toggle").addEventListener("click", () => byId("admin-nav").classList.toggle("open"));

  // ---------- util ----------
  const escapeHtml = (value) =>
    String(value ?? "").replace(
      /[&<>"']/g,
      (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#039;" })[c],
    );
  // Server menyimpan waktu UTC tanpa zona; tambahkan "Z" supaya tampil di jam lokal.
  const parseTime = (v) => (v ? new Date(/[zZ]|[+-]\d\d:\d\d$/.test(v) ? v : v + "Z") : null);
  const formatDate = (value, withTime = true) => {
    const date = parseTime(value);
    if (!date || Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("id-ID", {
      day: "2-digit", month: "short", year: "numeric",
      ...(withTime ? { hour: "2-digit", minute: "2-digit" } : {}),
    }).format(date);
  };
  const meter = (n) => `${Number(n).toLocaleString("id-ID")} m`;
  // angka kartu metrik menghitung naik (dimatikan bila pengguna memilih kurangi gerakan)
  const kurangiGerak = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  function hitungNaik(el, nilai, akhiran = "") {
    const tujuan = Number(nilai) || 0;
    const awal = Number(el.dataset.nilai || 0);
    el.dataset.nilai = tujuan;
    if (kurangiGerak || awal === tujuan) {
      el.textContent = tujuan.toLocaleString("id-ID") + akhiran;
      return;
    }
    const mulai = performance.now();
    const langkah = (t) => {
      const p = Math.min(1, (t - mulai) / 800);
      el.textContent = Math.round(awal + (tujuan - awal) * (1 - Math.pow(1 - p, 3))).toLocaleString("id-ID") + akhiran;
      if (p < 1) requestAnimationFrame(langkah);
    };
    requestAnimationFrame(langkah);
  }
  const setNotice = (text, type = "info") => {
    notice.textContent = text;
    notice.className = `notice-bar ${type}`;
    notice.hidden = !text;
  };

  async function api(path, options) {
    const response = await fetch(path, options);
    if (response.status === 401) {
      window.location.assign("/admin/login");
      throw new Error("Sesi admin berakhir");
    }
    const body = await response.json().catch(() => null);
    if (!response.ok) {
      const detail = body?.detail;
      throw new Error(
        Array.isArray(detail)
          ? detail.map((d) => d.msg).join("; ")
          : detail || `Server mengembalikan status ${response.status}`,
      );
    }
    return body;
  }
  const post = (path, data) =>
    api(path, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: data === undefined ? undefined : JSON.stringify(data),
    });

  const STATUS_KELAS = {
    Aktif: "status-active", "Lulus Inkubasi": "status-active", "Menunggu Konfirmasi": "status-pending",
    "Menunggu Verifikasi": "status-pending", Dicabut: "violation-chip", Gugur: "violation-chip",
    Ditolak: "violation-chip",
  };
  const chip = (st) => `<span class="status-chip ${STATUS_KELAS[st] || "status-waiting"}">${escapeHtml(st)}</span>`;
  const qBadge = (q) => `<span class="queue-badge q${Number(q)}">Q${Number(q)}</span>`;

  // ---------- badge menu (semua halaman) ----------
  async function loadBadges() {
    const r = await api("/api/admin/ringkasan");
    const set = (id, n) => {
      const el = byId(id);
      el.hidden = !n;
      el.textContent = n;
    };
    set("badge-verifikasi", r.menunggu_verifikasi);
    set("badge-deadlock", r.penyewa_peringatan);
    return r;
  }

  // ================= RINGKASAN =================
  async function loadRingkasan() {
    const [summary, queues, peta, violations, journal] = await Promise.all([
      loadBadges(), api("/antrean"), api("/peta"), api("/alokasi/log"), api("/api/admin/aktivitas?limit=10"),
    ]);
    const perQ = [1, 2, 3].map((l) => (queues[`queue_${l}`] || []).length);
    hitungNaik(byId("metric-applicants"), summary.total);
    byId("metric-active").textContent = summary.status.Aktif || 0;
    hitungNaik(byId("metric-queue"), perQ[0] + perQ[1] + perQ[2]);
    byId("metric-queue-split").textContent = `Q1 ${perQ[0]} · Q2 ${perQ[1]} · Q3 ${perQ[2]}`;
    hitungNaik(byId("metric-empty"), peta.ringkasan.kosong_m, " m");
    byId("metric-occupancy").textContent = `${peta.ringkasan.keterisian_persen}%`;
    hitungNaik(byId("metric-violations"), violations.length);

    const tugas = [
      [summary.menunggu_verifikasi, "pendaftar menunggu verifikasi dokumen", "/admin/verifikasi", "Periksa"],
      [summary.menunggu_konfirmasi, "lapak menunggu konfirmasi penjual (timer Timeout berjalan)", "/admin/penyewa", "Lihat"],
      [summary.penyewa_peringatan, `penyewa sudah tutup ≥ ${info.peringatan_hari} hari (berisiko Preemption)`, "/admin/penyewa", "Inspeksi"],
      [perQ[0] + perQ[1] + perQ[2], "pendaftar terverifikasi menunggu putaran alokasi (Q1 → Q2 → Q3)", "/admin/antrean", "Jalankan putaran"],
    ];
    byId("todo-list").innerHTML = tugas
      .map(([n, teks, href, aksi]) =>
        `<a class="todo-row ${n ? "" : "todo-done"}" href="${href}"><b>${n}</b><span>${teks}</span><em>${n ? aksi + " →" : "✓"}</em></a>`)
      .join("");
    byId("recent-journal").innerHTML = journalHtml(journal);
  }

  // ================= VERIFIKASI =================
  const docHtml = (url, jenis, label) => {
    if (!url) return `<div class="doc-box doc-missing"><b>${label}</b><span>Belum diunggah</span></div>`;
    const pratinjau = jenis === "pdf"
      ? `<span class="doc-pdf">PDF</span>`
      : `<img src="${url}" alt="${label}" loading="lazy" />`;
    return `<a class="doc-box" href="${url}" target="_blank" rel="noopener">${pratinjau}<b>${label}</b><span>Buka ukuran penuh ↗</span></a>`;
  };

  async function loadVerifikasi() {
    const [rows] = await Promise.all([api("/api/admin/verifikasi"), loadBadges()]);
    byId("verify-list").innerHTML = rows.length
      ? rows
          .map((u) => `<article class="panel verify-card" data-id="${u.id}">
          <div class="verify-head">
            <div><span class="section-index">${escapeHtml(u.kode_pendaftaran)} · DAFTAR ${formatDate(u.waktu_daftar)}</span>
              <h2>${escapeHtml(u.nama_usaha)}</h2>
              <p>${escapeHtml(u.nama_pemilik)} · NIK ${escapeHtml(u.nik)} · ${escapeHtml(u.telepon)}</p></div>
            <div class="verify-queue">${qBadge(u.queue_level)}<small>dinilai sistem</small></div>
          </div>
          <div class="verify-body">
            <dl class="claim-list">
              <div><dt>Domisili KTP</dt><dd>${escapeHtml(u.domisili)}</dd></div>
              <div><dt>Jenis usaha</dt><dd>${escapeHtml(u.jenis_usaha)}</dd></div>
              <div><dt>Asal produk</dt><dd>${escapeHtml(u.sumber_produk.replace("_", " "))}</dd></div>
              <div><dt>Toko dimiliki</dt><dd>${u.jumlah_cabang}</dd></div>
              <div><dt>Status khusus</dt><dd>${u.status_khusus ? "<b class='claim-yes'>Diajukan</b>" : "Tidak"}</dd></div>
              <div><dt>Kebutuhan</dt><dd>Muka ${meter(u.kebutuhan_muka)}</dd></div>
            </dl>
            <div class="doc-grid">
              ${docHtml(u.url_ktp, u.jenis_ktp, "KTP")}
              ${u.status_khusus ? docHtml(u.url_khusus, u.jenis_khusus, "Bukti status khusus") : ""}
            </div>
          </div>
          <p class="verify-hint">Cocokkan nama dan NIK di KTP dengan data di atas. Pastikan domisili sesuai.${
            u.status_khusus ? " Bukti status khusus harus menyebut nama yang sama." : ""}</p>
          <div class="verify-actions">
            <input class="verify-note" maxlength="300" placeholder="Catatan untuk pendaftar (wajib bila menolak)" />
            <button class="btn-admin btn-primary" data-decide="terima" type="button" ${u.url_ktp ? "" : "disabled title='KTP belum diunggah'"}>Terima</button>
            ${u.status_khusus ? `<button class="btn-admin btn-ghost" data-decide="tolak_klaim" type="button" ${u.url_ktp ? "" : "disabled"}>Terima tanpa status khusus</button>` : ""}
            <button class="btn-admin btn-danger" data-decide="tolak" type="button">Tolak</button>
          </div>
        </article>`)
          .join("")
      : '<section class="panel"><p class="table-message">Tidak ada pendaftar yang menunggu verifikasi. ✓</p></section>';
  }

  byId("verify-list").addEventListener("click", (event) => {
    const tombol = event.target.closest("[data-decide]");
    if (!tombol) return;
    const kartu = tombol.closest("[data-id]");
    const catatan = kartu.querySelector(".verify-note").value.trim();
    const keputusan = tombol.dataset.decide;
    if (keputusan === "tolak" && !catatan) {
      setNotice("Tuliskan alasan penolakan di kolom catatan agar pendaftar mengetahuinya.", "error");
      kartu.querySelector(".verify-note").focus();
      return;
    }
    aksi(tombol, async () => {
      const u = await post(`/api/admin/umkm/${kartu.dataset.id}/verifikasi`, { keputusan, catatan });
      return {
        terima: `${u.nama_usaha} diterima dan masuk antrean Queue ${u.queue_level}.`,
        tolak_klaim: `${u.nama_usaha} diterima tanpa status khusus; dinilai ulang ke Queue ${u.queue_level}.`,
        tolak: `${u.nama_usaha} ditolak.`,
      }[keputusan];
    });
  });

  // ================= CARI PENDAFTAR =================
  async function loadPendaftar() {
    const q = byId("search-q").value.trim();
    const status = byId("search-status").value;
    const rows = await api(`/api/admin/pendaftar?${new URLSearchParams({ q, status })}`);
    byId("search-body").innerHTML = rows.length
      ? rows
          .map((u) => `<tr class="click-row" data-detail="${u.id}" tabindex="0">
            <td><b>${escapeHtml(u.kode_pendaftaran)}</b></td>
            <td><b>${escapeHtml(u.nama_usaha)}</b><small>${escapeHtml(u.nama_pemilik)} · ${escapeHtml(u.telepon)}</small></td>
            <td>${escapeHtml(u.nik)}</td>
            <td>${qBadge(u.queue_level)}</td>
            <td>${chip(u.status_pendaftaran)}</td>
            <td>${formatDate(u.waktu_daftar, false)}</td></tr>`)
          .join("")
      : '<tr><td colspan="6" class="table-message">Tidak ada pendaftar yang cocok.</td></tr>';
    byId("search-foot").textContent =
      `${rows.length} pendaftar${q ? ` untuk "${q}"` : ""} · klik baris untuk melihat detail, dokumen, dan mengatur ulang PIN`;
  }

  async function bukaDetail(id) {
    const d = await api(`/api/admin/umkm/${id}`);
    const u = d.umkm;
    const a = d.alokasi;
    byId("drawer-kode").textContent = u.kode_pendaftaran;
    byId("drawer-title").textContent = u.nama_usaha;
    byId("drawer-body").innerHTML = `
      <div class="drawer-status">${chip(u.status_pendaftaran)} ${qBadge(u.queue_level)}
        <small>Verifikasi: ${escapeHtml(u.status_verifikasi)}</small></div>
      <dl class="claim-list">
        <div><dt>Pemilik</dt><dd>${escapeHtml(u.nama_pemilik)}</dd></div>
        <div><dt>NIK</dt><dd>${escapeHtml(u.nik)}</dd></div>
        <div><dt>Telepon</dt><dd>${escapeHtml(u.telepon)}</dd></div>
        <div><dt>Email</dt><dd>${escapeHtml(u.email || "–")}</dd></div>
        <div><dt>Domisili</dt><dd>${escapeHtml(u.domisili)}</dd></div>
        <div><dt>Usaha</dt><dd>${escapeHtml(u.jenis_usaha)} · ${escapeHtml(u.sumber_produk.replace("_", " "))}</dd></div>
        <div><dt>Toko dimiliki</dt><dd>${u.jumlah_cabang}</dd></div>
        <div><dt>Kebutuhan</dt><dd>Muka ${meter(u.kebutuhan_muka)}</dd></div>
        <div><dt>Posisi antrean</dt><dd>${d.posisi_dalam_queue ? `ke-${d.posisi_dalam_queue} di Q${u.queue_level}` : "–"}</dd></div>
        <div><dt>Timeout / pelanggaran</dt><dd>${u.jumlah_timeout} / ${d.jumlah_pelanggaran}</dd></div>
      </dl>
      ${u.catatan_verifikasi ? `<p class="drawer-note">Catatan verifikasi: ${escapeHtml(u.catatan_verifikasi)}</p>` : ""}
      <h3>Alasan jalur</h3>
      <ul class="reason-list">${u.alasan_queue.map((x) => `<li>${escapeHtml(x)}</li>`).join("")}</ul>
      <h3>Dokumen</h3>
      <div class="doc-grid">${docHtml(u.url_ktp, u.jenis_ktp, "KTP")}${
        u.url_khusus || u.status_khusus ? docHtml(u.url_khusus, u.jenis_khusus, "Bukti status khusus") : ""}</div>
      <h3>Lapak</h3>
      ${a ? `<p><b>${escapeHtml(a.kode_lapak)}</b> · Zona ${escapeHtml(a.zona)} · ${a.panjang} × ${a.lebar} m · ${escapeHtml(a.status_alokasi)}</p>`
          : "<p class='muted-text'>Belum pernah mendapat lapak.</p>"}
      <h3>PIN penjual</h3>
      <p class="muted-text">Atur ulang hanya setelah mencocokkan KTP asli pemilik. PIN baru tampil sekali.</p>
      <button class="btn-admin btn-ghost" id="reset-pin" type="button" data-id="${u.id}">Atur ulang PIN</button>
      <div id="pin-result"></div>
      <h3>Riwayat</h3>
      <div class="journal flat">${journalHtml(d.riwayat)}</div>`;
    byId("drawer").hidden = false;
    byId("drawer-backdrop").hidden = false;
    byId("drawer-close").focus();
  }
  const tutupDetail = () => {
    byId("drawer").hidden = true;
    byId("drawer-backdrop").hidden = true;
  };
  byId("drawer-close").addEventListener("click", tutupDetail);
  byId("drawer-backdrop").addEventListener("click", tutupDetail);
  document.addEventListener("keydown", (e) => e.key === "Escape" && tutupDetail());
  byId("drawer-body").addEventListener("click", async (event) => {
    const tombol = event.target.closest("#reset-pin");
    if (!tombol) return;
    if (!window.confirm("Atur ulang PIN pendaftar ini? PIN lama tidak berlaku lagi.")) return;
    tombol.disabled = true;
    try {
      const r = await post(`/api/admin/umkm/${tombol.dataset.id}/reset-pin`);
      byId("pin-result").innerHTML = `<div class="pin-box"><small>PIN baru untuk ${escapeHtml(r.kode_pendaftaran)}</small>
        <b>${escapeHtml(r.pin_baru)}</b><small>Sampaikan langsung ke pemilik. PIN ini tidak bisa dilihat lagi.</small></div>`;
    } catch (error) {
      setNotice(error.message, "error");
      tombol.disabled = false;
    }
  });
  const searchBody = byId("search-body");
  searchBody.addEventListener("click", (e) => {
    const row = e.target.closest("[data-detail]");
    if (row) bukaDetail(row.dataset.detail).catch((err) => setNotice(err.message, "error"));
  });
  searchBody.addEventListener("keydown", (e) => {
    const row = e.target.closest("[data-detail]");
    if (row && (e.key === "Enter" || e.key === " ")) {
      e.preventDefault();
      bukaDetail(row.dataset.detail).catch((err) => setNotice(err.message, "error"));
    }
  });
  byId("search-form").addEventListener("submit", (e) => {
    e.preventDefault();
    loadPendaftar().catch((err) => setNotice(err.message, "error"));
  });
  byId("search-status").addEventListener("change", () => loadPendaftar().catch(() => {}));

  // ================= ANTREAN (putaran alokasi MLQ) =================
  async function loadAntrean() {
    const [p] = await Promise.all([api("/antrean/putaran"), loadBadges()]);
    [1, 2, 3].forEach((level) => {
      const rows = p.rencana.filter((r) => r.queue_level === level);
      byId(`lane-count-${level}`).textContent = rows.length;
      byId(`lane-${level}`).innerHTML = rows.length
        ? rows
            .map((r, i) => `<li class="${r.dapat ? "akan-dapat" : "belum-muat"}">
              <span class="turn">#${r.giliran}</span>
              <div><b>${escapeHtml(r.nama_usaha)}</b>
                <small>ke-${i + 1} di Q${level} · butuh ${meter(r.kebutuhan_muka)} · daftar ${formatDate(r.waktu_antre)}${r.jumlah_timeout ? ` · ${r.jumlah_timeout}× timeout` : ""}</small>
                <small class="why">${escapeHtml(r.alasan_queue.join("; "))}</small></div>
              <em>${r.dapat ? `Zona ${escapeHtml(r.zona)} · m ke-${r.mulai}` : "belum muat"}</em></li>`)
            .join("")
        : '<li class="lane-empty">Tidak ada yang mengantre</li>';
    });
    const manual = p.mode !== "langsung";
    byId("round-button").disabled = !p.akan_dapat;
    byId("dispatch-summary").innerHTML = p.jumlah_menunggu
      ? `<b>${p.jumlah_menunggu}</b> pendaftar terverifikasi menunggu. Putaran berikutnya memberi lapak kepada <b>${p.akan_dapat}</b> pendaftar${
          p.akan_dapat < p.jumlah_menunggu ? `; ${p.jumlah_menunggu - p.akan_dapat} lainnya belum muat dan tetap di antrean` : ""}.`
      : `Antrean kosong.${p.menunggu_verifikasi ? ` Ada <b>${p.menunggu_verifikasi}</b> pendaftar yang belum diverifikasi; mereka masuk antrean setelah diterima di menu Verifikasi.` : ""}`;
    if (!manual) byId("dispatch-summary").innerHTML += " <small>(Mode langsung: lapak dibagikan seketika saat pendaftar siap.)</small>";
  }
  byId("round-button").addEventListener("click", (e) =>
    aksi(e.currentTarget, async () => {
      const h = await post("/antrean/putaran");
      return h.dialokasikan
        ? `Putaran selesai: ${h.dialokasikan} pendaftar mendapat lapak (${h.lapak.join(", ")}). Mereka punya ${info.timeout_hari} hari untuk konfirmasi.`
        : "Putaran selesai: tidak ada ruang bersambung yang muat untuk pendaftar yang menunggu.";
    }));

  // ================= DENAH =================
  const SEG = { Kosong: "kosong", Dipesan: "dipesan", Terisi: "terisi" };
  async function loadDenah() {
    const [peta] = await Promise.all([api("/peta"), loadBadges()]);
    const r = peta.ringkasan;
    const f = peta.fragmentasi;
    byId("stall-empty").textContent = `${meter(r.kosong_m)} · ${r.kosong} bagian`;
    byId("stall-reserved").textContent = `${r.dipesan} lapak · ${meter(r.dipesan_m)}`;
    byId("stall-occupied").textContent = `${r.terisi} lapak · ${meter(r.terisi_m)}`;
    byId("frag-largest").textContent = meter(f.hole_terbesar_m);
    byId("frag-percent").textContent = `${f.fragmentasi_persen}%`;
    byId("stall-map").innerHTML = peta.zona.length
      ? peta.zona
          .map((z) => {
            const segs = z.segmen
              .map((s) => {
                const label = s.status === "Kosong"
                  ? `Ruang kosong ${meter(s.panjang)} (meter ke-${s.mulai} sampai ${s.mulai + s.panjang})`
                  : `${s.kode_lapak}: ${s.status}, ${meter(s.panjang)}${s.penyewa ? `, ${s.penyewa} (Q${s.queue_level})` : ""}`;
                const isi = s.status === "Kosong"
                  ? `<b>kosong</b><small>${meter(s.panjang)}</small>`
                  : `<b>${escapeHtml(s.kode_lapak)}</b><small>${escapeHtml(s.penyewa || s.status)}</small>`;
                return `<div class="seg seg-${SEG[s.status] || "kosong"}" style="flex:${s.panjang} 1 0" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}">${isi}</div>`;
              })
              .join("");
            const ticks = Array.from({ length: Math.floor(z.panjang / 2) + 1 }, (_, i) => i * 2)
              .map((m) => `<i style="left:${(m / z.panjang) * 100}%">${m}</i>`).join("");
            return `<div class="zone-strip">
              <div class="zone-strip-head"><b>Zona ${escapeHtml(z.kode)}</b><span>${escapeHtml(z.nama)}</span>
                <em>${meter(z.panjang)} × ${meter(z.kedalaman)} · terpakai ${meter(z.terpakai_m)} · kosong ${meter(z.kosong_m)}</em></div>
              <div class="strip">${segs}</div><div class="ruler">${ticks}</div></div>`;
          })
          .join("")
      : '<p class="empty-map">Belum ada zona. Tambahkan zona di bawah.</p>';
  }
  const STRATEGI = [["worst", "Worst-Fit", "dipakai sistem"], ["best", "Best-Fit", "pembanding"], ["first", "First-Fit", "pembanding"]];
  async function runSimulation() {
    const need = Number(byId("sim-need").value) || 2;
    const sim = await api(`/peta/simulasi?kebutuhan=${need}`);
    byId("sim-result").innerHTML = STRATEGI.map(([key, nama, peran]) => {
      const h = sim.hasil[key];
      return `<div class="sim-card ${key === "worst" ? "sim-used" : ""}"><span>${nama} <em>${peran}</em></span>${
        h ? `<b>Zona ${escapeHtml(h.zona)}, meter ke-${h.mulai}</b>
             <small>dari ruang ${meter(h.hole_panjang_m)} · sisa potongan ${meter(h.sisa_potongan_m)}</small>
             <small>setelahnya: kosong terluas ${meter(h.setelah.hole_terbesar_m)}, terkecil ${meter(h.setelah.hole_terkecil_m)}, ${h.setelah.jumlah_hole} bagian</small>`
          : `<b>Tidak muat</b><small>Tidak ada ruang bersambung ${meter(need)}</small>`}</div>`;
    }).join("");
  }
  byId("sim-form").addEventListener("submit", (e) => {
    e.preventDefault();
    runSimulation().catch((err) => setNotice(err.message, "error"));
  });
  byId("zone-form").addEventListener("submit", (event) => {
    event.preventDefault();
    const f = event.currentTarget;
    aksi(f.querySelector("button"), async () => {
      const h = await post("/peta/zona", {
        kode: f.elements.kode.value.trim(), nama: f.elements.nama.value.trim(),
        panjang: Number(f.elements.panjang.value), kedalaman: Number(f.elements.kedalaman.value),
      });
      f.reset();
      return `Zona ${h.kode} ditambahkan; ${h.alokasi_baru} pendaftar di antrean langsung mendapat lapak.`;
    });
  });

  // ================= PENYEWA =================
  function durasi(detik) {
    const d = Math.floor(detik / 86400);
    const j = Math.floor((detik % 86400) / 3600);
    return d ? `${d} hari ${j} jam` : `${j} jam ${Math.floor((detik % 3600) / 60)} menit`;
  }
  async function loadPenyewa() {
    const [rows] = await Promise.all([api("/alokasi/aktif"), loadBadges()]);
    byId("tenant-table-body").innerHTML = rows.length
      ? rows
          .map((r) => {
            const aktif = r.status_alokasi === "Aktif";
            let timer;
            if (aktif) {
              const persen = Math.min(100, (r.hari_tidak_aktif / info.preemption_hari) * 100);
              const kelas = r.peringatan ? "danger" : r.hari_tidak_aktif >= 3 ? "warn" : "ok";
              timer = `<div class="mini-meter ${kelas}"><i style="width:${Math.max(4, persen)}%"></i></div>
                <small>${r.peringatan ? "Peringatan · " : ""}tutup ${r.hari_tidak_aktif} dari ${info.preemption_hari} hari</small>`;
            } else {
              timer = `<b>${durasi(r.sisa_detik_konfirmasi || 0)}</b><small>sisa waktu konfirmasi</small>`;
            }
            return `<tr>
              <td><b>${escapeHtml(r.kode_lapak)}</b><small>Zona ${escapeHtml(r.zona)} · m ke-${r.mulai}–${r.mulai + r.panjang} · ${r.luas} m²</small></td>
              <td><b>${escapeHtml(r.nama_usaha)}</b><small>${escapeHtml(r.nama_pemilik)} · ${escapeHtml(r.kode_pendaftaran)}</small></td>
              <td>${qBadge(r.queue_level)}</td>
              <td>${chip(r.status_alokasi)}</td>
              <td class="timer-cell">${timer}</td>
              <td>${aktif ? `<b>${r.sisa_hari_sewa} hari lagi</b><small>sampai ${formatDate(r.sewa_berakhir, false)}</small>` : "—"}</td>
              <td class="row-actions">${aktif
                ? `<button class="text-action" data-inspect="${r.id}" type="button" title="Catat bahwa kios terlihat buka saat inspeksi">Catat buka</button>
                   <button class="text-action" data-graduate="${r.id}" data-name="${escapeHtml(r.nama_usaha)}" type="button" title="UMKM pindah ke ruko mandiri">Luluskan</button>`
                : "<small>menunggu penjual</small>"}</td></tr>`;
          })
          .join("")
      : '<tr><td colspan="7" class="table-message">Belum ada lapak yang ditempati.</td></tr>';
    const aktif = rows.filter((r) => r.status_alokasi === "Aktif").length;
    byId("tenant-foot").textContent = `${aktif} penyewa aktif · ${rows.length - aktif} lapak menunggu konfirmasi`;
  }
  byId("tenant-table-body").addEventListener("click", (event) => {
    const inspect = event.target.closest("[data-inspect]");
    const graduate = event.target.closest("[data-graduate]");
    if (inspect) {
      aksi(inspect, async () => {
        await post(`/alokasi/${inspect.dataset.inspect}/inspeksi`);
        return "Inspeksi dicatat: hitungan hari tidak aktif kembali ke nol.";
      });
    } else if (graduate) {
      const nama = graduate.dataset.name;
      if (!window.confirm(`Luluskan ${nama}? Lapaknya dilepas ke antrean dan datanya masuk arsip.`)) return;
      aksi(graduate, async () => {
        await post(`/alokasi/${graduate.dataset.graduate}/lulus`);
        return `${nama} dicatat lulus inkubasi. Lapaknya kembali menjadi ruang kosong.`;
      });
    }
  });

  // ================= DEADLOCK =================
  async function loadDeadlock() {
    const [rows] = await Promise.all([api("/alokasi/log"), loadBadges()]);
    byId("rule-grid").innerHTML = [
      ["Timeout", `${info.timeout_hari} hari`, "Lapak yang tidak dikonfirmasi penjual dilepas; penjual dipindah ke urutan terbawah queue-nya."],
      ["Batas timeout", `${info.maks_timeout} kali`, "Setelah sekian kali timeout pendaftaran gugur, supaya tidak berputar terus (livelock)."],
      ["Peringatan", `${info.peringatan_hari} hari`, "Penyewa yang tutup sekian hari berturut-turut diberi peringatan."],
      ["Preemption", `${info.preemption_hari} hari`, "Hak sewa dicabut paksa dan lapaknya diberikan ke antrean."],
    ].map(([n, v, k]) => `<article class="rule-card"><span>${n}</span><b>${v}</b><p>${k}</p></article>`).join("");
    byId("activity-table-body").innerHTML = rows.length
      ? rows.map((row) => `<tr>
          <td>${formatDate(row.waktu_kejadian)}</td>
          <td><b>${escapeHtml(row.nama_usaha)}</b></td>
          <td><span class="violation-chip ${row.jenis_pelanggaran === "Timeout" ? "timeout-chip" : "preemption-chip"}">${escapeHtml(row.jenis_pelanggaran)}</span></td>
          <td class="activity-note">${escapeHtml(row.keterangan || "")}</td></tr>`).join("")
      : '<tr><td colspan="4" class="table-message">Belum ada lapak yang tertahan.</td></tr>';
  }

  // ================= ARSIP =================
  const JENIS_KELAS = {
    Timeout: "timeout-chip", Preemption: "violation-chip", Peringatan: "timeout-chip",
    Konfirmasi: "status-active", Absen: "status-active", Inspeksi: "status-active",
    "Lulus Inkubasi": "status-active", Verifikasi: "status-active", "Sewa Berakhir": "preemption-chip",
    Aging: "preemption-chip", "Reset PIN": "timeout-chip",
  };
  function journalHtml(rows) {
    return rows.length
      ? rows.map((r) => `<div class="journal-row"><time>${formatDate(r.waktu)}</time>
          <span class="status-chip ${JENIS_KELAS[r.jenis] || "status-waiting"}">${escapeHtml(r.jenis)}</span>
          <p>${r.nama_usaha ? `<b>${escapeHtml(r.nama_usaha)}</b> ` : ""}${escapeHtml(r.keterangan || "")}</p></div>`).join("")
      : '<p class="table-message">Belum ada kejadian tercatat.</p>';
  }
  async function loadArsip() {
    const [journal, archive] = await Promise.all([api("/api/admin/aktivitas?limit=200"), api("/api/admin/arsip"), loadBadges()]);
    byId("journal-list").innerHTML = journalHtml(journal);
    byId("archive-table-body").innerHTML = archive.length
      ? archive.map((r) => {
          const a = r.alokasi_terakhir;
          return `<tr>
            <td><b>${escapeHtml(r.umkm.nama_usaha)}</b><small>${escapeHtml(r.umkm.nama_pemilik)} · Q${r.umkm.queue_level}</small></td>
            <td>${chip(r.umkm.status_pendaftaran)}${r.umkm.catatan_verifikasi && r.umkm.status_pendaftaran === "Ditolak" ? `<small>${escapeHtml(r.umkm.catatan_verifikasi)}</small>` : ""}</td>
            <td>${a ? `<b>${escapeHtml(a.kode_lapak)}</b><small>selesai ${formatDate(a.waktu_selesai, false)}</small>` : "—"}</td>
            <td>${r.jumlah_pelanggaran}</td></tr>`;
        }).join("")
      : '<tr><td colspan="4" class="table-message">Arsip masih kosong.</td></tr>';
  }

  // ---------- jam sistem ----------
  async function loadClock() {
    const jam = await api("/api/admin/jam");
    const maju = jam.geser_hari > 0;
    byId("today-label").textContent = maju ? `Mode demo: jam dimajukan ${jam.geser_hari} hari` : "";
    if (byId("clock-now").offsetParent === null) return;
    byId("clock-now").textContent = new Intl.DateTimeFormat("id-ID", {
      weekday: "long", day: "numeric", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit",
    }).format(parseTime(jam.waktu_sistem));
    byId("clock-shift").textContent = maju ? `Dimajukan ${jam.geser_hari} hari dari jam laptop (mode demo)` : "Mengikuti jam laptop";
    byId("clock-shift").classList.toggle("shifted", maju);
  }

  const LOADER = {
    ringkasan: loadRingkasan, verifikasi: loadVerifikasi, pendaftar: () => Promise.all([loadPendaftar(), loadBadges()]),
    antrean: loadAntrean, denah: () => Promise.all([loadDenah(), runSimulation()]), penyewa: loadPenyewa,
    deadlock: loadDeadlock, arsip: loadArsip,
  };
  async function muat() {
    byId("refresh-button").disabled = true;
    try {
      await Promise.all([LOADER[PAGE](), loadClock()]);
      byId("last-updated").textContent = `Disinkronkan ${new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit", second: "2-digit" }).format(new Date())}`;
      if (notice.classList.contains("error") && notice.dataset.sumber === "muat") setNotice("");
    } catch (error) {
      setNotice(`Data gagal dimuat: ${error.message}. Pastikan aplikasi SI-TAKAR berjalan.`, "error");
      notice.dataset.sumber = "muat";
    } finally {
      byId("refresh-button").disabled = false;
    }
  }

  function ringkasSiklus(s) {
    const bagian = [];
    if (s.timeout?.length) bagian.push(`${s.timeout.length} timeout`);
    if (s.peringatan?.length) bagian.push(`${s.peringatan.length} peringatan`);
    if (s.preemption?.length) bagian.push(`${s.preemption.length} preemption`);
    if (s.sewa_berakhir?.length) bagian.push(`${s.sewa_berakhir.length} sewa berakhir`);
    if (s.aging?.length) bagian.push(`${s.aging.length} naik queue`);
    if (s.alokasi_baru?.length) bagian.push(`${s.alokasi_baru.length} alokasi baru`);
    return bagian.length ? bagian.join(", ") : "tidak ada perubahan";
  }
  async function aksi(button, kerja) {
    if (button) button.disabled = true;
    try {
      const pesan = await kerja();
      if (pesan) {
        setNotice(pesan, "success");
        notice.dataset.sumber = "aksi";
      }
      await muat();
    } catch (error) {
      setNotice(error.message, "error");
      notice.dataset.sumber = "aksi";
    } finally {
      if (button && button.isConnected) button.disabled = false;
    }
  }

  byId("refresh-button").addEventListener("click", muat);
  byId("logout-button").addEventListener("click", async () => {
    await fetch("/admin/logout", { method: "POST" });
    window.location.assign("/admin/login");
  });
  byId("deadlock-button").addEventListener("click", (e) =>
    aksi(e.currentTarget, async () => `Pemeriksaan selesai: ${ringkasSiklus(await post("/alokasi/jalankan-deadlock"))}.`));
  byId("demo-button").addEventListener("click", (e) =>
    aksi(e.currentTarget, async () => {
      const h = await post("/api/admin/demo/isi");
      return h.pendaftar_ditambah || h.menunggu_verifikasi
        ? `${h.pendaftar_ditambah} pendaftar contoh masuk antrean (${h.dikonfirmasi} langsung konfirmasi) dan ${h.menunggu_verifikasi} menunggu verifikasi. PIN semua data contoh: ${h.pin}.`
        : "Data contoh sudah pernah dimasukkan.";
    }));
  document.querySelectorAll("[data-advance]").forEach((button) => {
    button.addEventListener("click", () =>
      aksi(button, async () => {
        const h = await post("/api/admin/jam/majukan", { hari: Number(button.dataset.advance) });
        return `Jam dimajukan ${button.dataset.advance} hari. Hasil pemeriksaan: ${ringkasSiklus(h.siklus)}.`;
      }));
  });
  byId("clock-reset").addEventListener("click", (e) =>
    aksi(e.currentTarget, async () => {
      await post("/api/admin/jam/reset");
      return "Jam sistem kembali mengikuti jam laptop.";
    }));

  api("/info").then((data) => (info = data)).catch(() => {}).finally(muat);
  // Halaman berisi isian (verifikasi, pencarian) tidak dimuat ulang otomatis supaya ketikan tidak hilang
  if (!["verifikasi", "pendaftar"].includes(PAGE)) window.setInterval(muat, 10000);
})();
