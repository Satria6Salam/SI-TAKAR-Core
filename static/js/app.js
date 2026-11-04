(() => {
  const STORAGE_KEY = "si-takar-demo-registration";

  const getRegistration = () => {
    try {
      return JSON.parse(localStorage.getItem(STORAGE_KEY) || "null");
    } catch {
      return null;
    }
  };

  const saveRegistration = (data) =>
    localStorage.setItem(STORAGE_KEY, JSON.stringify(data));

  const priorityLabels = {
    1: "Queue 1 · Prioritas Utama (Afirmasi & Pelestarian)",
    2: "Queue 2 · Prioritas Pendukung (Ekosistem Lokal)",
    3: "Queue 3 · Prioritas Reguler (Komersial & Ekspansi)",
  };

  const priorityBadgeClasses = {
    1: "badge-q1",
    2: "badge-q2",
    3: "badge-q3",
  };

  const businessTypes = {
    "Kriya / kerajinan": "kriya",
    "Seni dan antik": "seni rupa",
    "Kuliner": "kuliner",
    "Fashion / tekstil": "fesyen",
    "Aksesoris & Suvenir": "aksesoris",
    "Jasa kreatif": "jasa kreatif",
    "Reseller / Franchise / Impor": "reseller",
    "Lainnya": "lainnya",
  };

  function escapeHtml(value) {
    return String(value ?? "").replace(
      /[&<>"']/g,
      (char) =>
        ({
          "&": "&amp;",
          "<": "&lt;",
          ">": "&gt;",
          '"': "&quot;",
          "'": "&#039;",
        })[char],
    );
  }

  // Nav menu toggle mobile
  document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
    button.addEventListener("click", () =>
      document.querySelector("[data-nav]")?.classList.toggle("open"),
    );
  });

  // Home page public stall summary
  const publicStallSummary = document.getElementById("public-stall-summary");
  if (publicStallSummary) {
    fetch(`${window.location.origin}/peta`)
      .then((response) => {
        if (!response.ok) throw new Error();
        return response.json();
      })
      .then((map) => {
        const summary = map.ringkasan;
        const emptyCount = document.getElementById("empty-count");
        const totalCount = document.getElementById("total-count");
        if (emptyCount) emptyCount.textContent = summary.kosong;
        if (totalCount) totalCount.textContent = map.lapak.length;
        publicStallSummary.innerHTML = [
          ["Kosong (Siap Dialokasikan)", summary.kosong, ""],
          ["Dipesan (Menunggu Konfirmasi < 1 Menit)", summary.dipesan, "coral-text"],
          ["Terisi (Aktif Berjualan)", summary.terisi, "coral-text"],
        ]
          .map(
            ([label, count, className]) =>
              `<div class="zone-row"><div><span>${label}</span><b class="${className}">${count} lapak</b></div><div class="progress"><i style="width:${map.lapak.length ? Math.round((count / map.lapak.length) * 100) : 0}%"></i></div></div>`,
          )
          .join("");
      })
      .catch(() => {
        publicStallSummary.textContent = "Status lapak belum tersedia.";
      });
  }

  // ==========================================
  // ADMIN DASHBOARD & LOGIN
  // ==========================================
  const adminLoginForm = document.getElementById("admin-login-form");
  if (adminLoginForm) {
    const tokenKey = "si-takar-admin-token";
    const loginPanel = document.getElementById("admin-login-panel");
    const dashboard = document.getElementById("admin-dashboard");
    const message = document.getElementById("admin-message");
    const apiBase =
      document.querySelector('meta[name="api-base"]')?.content ||
      window.location.origin;

    const showAdminMessage = (text, type = "error") => {
      if (!message) return;
      message.className = `inline-message show ${type}`;
      message.textContent = text;
    };

    const responseMessage = async (response) => {
      const body = await response.json().catch(() => ({}));
      return body.detail || body.pesan || "Permintaan tidak dapat diproses.";
    };

    const showAdmin = async (username, token) => {
      const userEl = document.getElementById("admin-username");
      if (userEl) userEl.textContent = username;
      loginPanel.hidden = true;
      dashboard.hidden = false;
      const footnote = document.getElementById("admin-footnote");
      if (footnote) footnote.hidden = true;
      await loadDashboard(token);
    };

    // Tab Navigation
    const tabButtons = document.querySelectorAll(".admin-tabs .tab-btn");
    const tabPanes = document.querySelectorAll(".tab-pane");
    tabButtons.forEach((btn) => {
      btn.addEventListener("click", () => {
        tabButtons.forEach((b) => {
          b.classList.remove("active", "btn-green");
          b.classList.add("btn-light");
        });
        btn.classList.remove("btn-light");
        btn.classList.add("active", "btn-green");

        const targetId = btn.dataset.tab;
        tabPanes.forEach((pane) => {
          pane.style.display = pane.id === targetId ? "block" : "none";
        });
      });
    });

    const renderQueue = (elementId, items) => {
      const list = document.getElementById(elementId);
      if (!list) return;
      if (!items?.length) {
        list.innerHTML = '<p class="queue-empty">Belum ada pendaftar di antrean ini.</p>';
        return;
      }
      list.innerHTML = items
        .map(
          (item, idx) =>
            `<article class="queue-applicant">
              <div style="display:flex; justify-content:space-between; align-items:center;">
                <b>${idx + 1}. ${escapeHtml(item.nama_usaha)}</b>
                <span class="muted small">${escapeHtml(item.nomor_pendaftaran || "")}</span>
              </div>
              <span>${escapeHtml(item.nama_pemilik)} · ${escapeHtml(item.domisili)}</span>
              <small>${escapeHtml(item.jenis_usaha)} ${item.status_khusus ? "· [Status Khusus]" : ""} · ${escapeHtml(item.status_pendaftaran)}</small>
            </article>`,
        )
        .join("");
    };

    const renderBars = (elementId, entries) => {
      const root = document.getElementById(elementId);
      if (!root) return;
      const maximum = Math.max(1, ...entries.map((entry) => entry.value));
      root.innerHTML = entries
        .map(
          (entry) =>
            `<div class="chart-row"><span>${escapeHtml(entry.label)}</span><div class="chart-track"><i style="width:${Math.max(entry.value ? 4 : 0, (entry.value / maximum) * 100)}%"></i></div><b>${entry.value}</b></div>`,
        )
        .join("");
    };

    const renderReviews = (applicants) => {
      const root = document.getElementById("applicant-review-list");
      if (!root) return;
      if (!applicants.length) {
        root.innerHTML = '<p class="queue-empty">Belum ada pendaftar untuk diverifikasi.</p>';
        return;
      }

      root.innerHTML = applicants
        .map((item) => {
          const review = item.verifikasi;
          const qClass = priorityBadgeClasses[item.queue_level] || "badge-q3";
          const statusPillClass =
            item.status_pendaftaran === "Aktif"
              ? "pill-green"
              : item.status_pendaftaran === "Dicabut"
              ? "pill-coral"
              : "pill-yellow";

          return `
            <article class="applicant-card" id="applicant-card-${item.id}">
              <div class="applicant-header">
                <div>
                  <span class="queue-badge ${qClass}">Queue ${item.queue_level}</span>
                  <h3 style="margin: 4px 0 2px; font-size: 16px; font-weight: 700;">${escapeHtml(item.nama_usaha)}</h3>
                  <small class="muted">
                    No. Pendaftaran: <b>${escapeHtml(item.nomor_pendaftaran || "-")}</b> · 
                    Didaftarkan: ${item.waktu_daftar ? new Date(item.waktu_daftar).toLocaleString("id-ID") : "-"}
                  </small>
                </div>
                <span class="pill ${statusPillClass}">${escapeHtml(item.status_pendaftaran)}</span>
              </div>
              
              <div class="applicant-grid">
                <div><small>Nama Pemilik (KTP)</small><b>${escapeHtml(item.nama_pemilik)}</b></div>
                <div><small>Nomor KTP / NIK</small><b>${escapeHtml(item.nik || "Tidak diisi")}</b></div>
                <div><small>WhatsApp / No HP</small><b>${item.nomor_telepon ? `<a href="tel:${escapeHtml(item.nomor_telepon)}" style="color:var(--green); text-decoration:underline;">${escapeHtml(item.nomor_telepon)}</a>` : "Tidak diisi"}</b></div>
                <div><small>Alamat Email</small><b>${escapeHtml(item.email || "Tidak diisi")}</b></div>
                <div><small>Domisili Asal</small><b>${escapeHtml(item.domisili)}</b></div>
                <div><small>Kategori Produk</small><b>${escapeHtml(item.jenis_usaha)}</b></div>
                <div><small>Kebutuhan Kios</small><b>${item.kebutuhan_luas} m²</b></div>
                <div>
                  <small>Kriteria Verifikasi</small>
                  <div style="display:flex; flex-wrap:wrap; gap:4px; margin-top:2px;">
                    ${item.status_khusus ? '<span class="pill pill-green" style="font-size:10px; padding:2px 6px;">✓ Afirmasi Khusus</span>' : ""}
                    ${item.punya_toko_fisik ? '<span class="pill" style="font-size:10px; padding:2px 6px;">Toko Fisik: Ada</span>' : '<span class="pill pill-light" style="font-size:10px; padding:2px 6px;">Toko Fisik: Belum</span>'}
                    ${item.produksi_sendiri ? '<span class="pill pill-green" style="font-size:10px; padding:2px 6px;">Produksi: Sendiri</span>' : '<span class="pill pill-light" style="font-size:10px; padding:2px 6px;">Reseller</span>'}
                    <span class="pill pill-light" style="font-size:10px; padding:2px 6px;">Cabang: ${item.jumlah_cabang}</span>
                    ${item.modal_besar ? '<span class="pill pill-yellow" style="font-size:10px; padding:2px 6px;">Modal &gt;50Jt</span>' : '<span class="pill pill-green" style="font-size:10px; padding:2px 6px;">Modal Mikro</span>'}
                  </div>
                </div>
              </div>

              ${item.deskripsi ? `<div style="background:#f9fbf9; padding:8px 12px; border-radius:6px; font-size:12px; margin-bottom:12px; border:1px solid #edf2ed;"><small class="muted" style="display:block; font-weight:600;">Deskripsi Usaha Pemohon:</small><span>${escapeHtml(item.deskripsi)}</span></div>` : ""}

              <div class="verification-action-box">
                <div style="flex: 1 1 100%; display: flex; justify-content: space-between; align-items: center; margin-bottom: 4px;">
                  <span style="font-size: 13px; font-weight: 600;">
                    Status Verifikasi: 
                    <span class="${review?.status === "Terverifikasi" ? "green-text" : review?.status === "Perlu Perbaikan" ? "coral-text" : "muted"}">
                      ${review ? `${escapeHtml(review.status)} oleh ${escapeHtml(review.nama_verifikator)}` : "Belum Diverifikasi"}
                    </span>
                  </span>
                  ${review?.waktu_verifikasi ? `<small class="muted">${new Date(review.waktu_verifikasi).toLocaleString("id-ID")}</small>` : ""}
                </div>
                
                <input 
                  type="text" 
                  class="review-note-input" 
                  placeholder="Ketik catatan / alasan verifikasi untuk pendaftar (opsional)..." 
                  value="${escapeHtml(review?.catatan || "")}" 
                  style="padding: 8px 12px; border: 1px solid var(--line); border-radius: 6px; font-size: 13px; flex:1; min-width:240px;"
                />
                
                <button class="btn btn-green btn-verify" data-review-id="${item.id}" data-review-status="Terverifikasi" type="button" style="padding: 8px 16px; font-size: 13px;">
                  ✓ Setujui Verifikasi
                </button>
                <button class="btn btn-light btn-revision" data-review-id="${item.id}" data-review-status="Perlu Perbaikan" type="button" style="padding: 8px 16px; font-size: 13px; color: #c76042;">
                  ⚠️ Perlu Perbaikan
                </button>
              </div>
            </article>
          `;
        })
        .join("");
    };

    const renderStallGrid = (stalls) => {
      const root = document.getElementById("stall-grid");
      if (!root) return;
      root.innerHTML = stalls.length
        ? stalls
          .map(
            (stall) =>
              `<article class="stall-tile stall-${escapeHtml(stall.warna)}">
                  <b>${escapeHtml(stall.kode_lapak)}</b>
                  <span>${escapeHtml(stall.status)}</span>
                  <small>${stall.penyewa ? escapeHtml(stall.penyewa) : `${stall.panjang}x${stall.lebar} (${stall.luas} m²)`}</small>
                </article>`,
          )
          .join("")
        : '<p class="queue-empty">Belum ada lapak pada denah.</p>';
    };

    const renderDeadlockLog = (entries) => {
      const root = document.getElementById("deadlock-log");
      if (!root) return;
      root.innerHTML = entries.length
        ? entries
          .map(
            (entry) =>
              `<article class="deadlock-row">
                  <b><span class="pill ${entry.jenis_pelanggaran === "Timeout" ? "pill-yellow" : "pill-coral"}">${escapeHtml(entry.jenis_pelanggaran)}</span></b>
                  <span>${escapeHtml(entry.nama_usaha)}</span>
                  <small>${escapeHtml(entry.keterangan || "")}</small>
                  <time>${entry.waktu_kejadian ? new Date(entry.waktu_kejadian).toLocaleString("id-ID") : "-"}</time>
                </article>`,
          )
          .join("")
        : '<p class="queue-empty">Belum ada catatan pelanggaran Timeout atau Preemption.</p>';
    };

    const loadDashboard = async (token) => {
      try {
        const headers = { Authorization: `Bearer ${token}` };
        const [queueResponse, mapResponse, applicantsResponse, logResponse] =
          await Promise.all([
            fetch(`${apiBase}/antrean`, { headers }),
            fetch(`${apiBase}/peta`),
            fetch(`${apiBase}/admin/pendaftar`, { headers }),
            fetch(`${apiBase}/alokasi/log`, { headers }),
          ]);
        if (queueResponse.status === 401)
          throw new Error("Sesi berakhir. Silakan masuk kembali.");
        if (!queueResponse.ok)
          throw new Error(await responseMessage(queueResponse));
        if (!mapResponse.ok)
          throw new Error("Ringkasan lapak tidak dapat dimuat.");
        if (!applicantsResponse.ok)
          throw new Error(await responseMessage(applicantsResponse));
        if (!logResponse.ok)
          throw new Error(await responseMessage(logResponse));
        const [queues, map, applicants, deadlockLog] = await Promise.all([
          queueResponse.json(),
          mapResponse.json(),
          applicantsResponse.json(),
          logResponse.json(),
        ]);
        const applicantCount =
          queues.queue_1.length + queues.queue_2.length + queues.queue_3.length;
        document.getElementById("metric-applicants").textContent =
          applicantCount;
        document.getElementById("metric-empty-stalls").textContent =
          map.ringkasan.kosong;
        document.getElementById("metric-booked-stalls").textContent =
          map.ringkasan.dipesan;
        document.getElementById("metric-occupied-stalls").textContent =
          map.ringkasan.terisi;
        renderQueue("queue-1", queues.queue_1);
        renderQueue("queue-2", queues.queue_2);
        renderQueue("queue-3", queues.queue_3);
        renderBars("queue-chart", [
          { label: "Queue 1 · Afirmasi & Pelestarian", value: queues.queue_1.length },
          { label: "Queue 2 · Pendukung Ekosistem", value: queues.queue_2.length },
          { label: "Queue 3 · Komersial & Ekspansi", value: queues.queue_3.length },
        ]);
        renderBars("stall-chart", [
          { label: "Kosong (Hijau)", value: map.ringkasan.kosong },
          { label: "Dipesan (Kuning)", value: map.ringkasan.dipesan },
          { label: "Terisi (Merah)", value: map.ringkasan.terisi },
        ]);
        renderReviews(applicants);
        renderStallGrid(map.lapak);
        renderDeadlockLog(deadlockLog);
        const updatedEl = document.getElementById("dashboard-updated");
        if (updatedEl) {
          updatedEl.textContent =
            "Diperbarui " +
            new Date().toLocaleTimeString("id-ID", {
              hour: "2-digit",
              minute: "2-digit",
              second: "2-digit",
            });
        }
      } catch (error) {
        if (error.message.includes("Sesi berakhir")) {
          sessionStorage.removeItem(tokenKey);
          dashboard.hidden = true;
          loginPanel.hidden = false;
        }
        showAdminMessage(error.message || "Tidak dapat terhubung ke server.");
      }
    };

    const demoFill = document.getElementById("demo-fill");
    if (demoFill) {
      demoFill.addEventListener("click", () => {
        adminLoginForm.elements.username.value = "admin";
        adminLoginForm.elements.password.value = "admin123";
      });
    }

    const refreshBtn = document.getElementById("dashboard-refresh");
    if (refreshBtn) {
      refreshBtn.addEventListener("click", () => {
        loadDashboard(sessionStorage.getItem(tokenKey));
      });
    }

    const deadlockRun = document.getElementById("deadlock-run");
    if (deadlockRun) {
      deadlockRun.addEventListener("click", async (event) => {
        const button = event.currentTarget;
        button.disabled = true;
        try {
          const response = await fetch(`${apiBase}/alokasi/jalankan-deadlock`, {
            method: "POST",
            headers: {
              Authorization: `Bearer ${sessionStorage.getItem(tokenKey)}`,
            },
          });
          if (!response.ok) throw new Error(await responseMessage(response));
          const hasil = await response.json();
          const info = `Pemeriksaan selesai. Timeout dibatalkan: ${hasil.timeout.length}, Preemption dicabut: ${hasil.preemption.length}, Alokasi baru: ${hasil.alokasi_baru.length}.`;
          await loadDashboard(sessionStorage.getItem(tokenKey));
          showAdminMessage(info, "success");
        } catch (error) {
          showAdminMessage(error.message || "Pemeriksaan deadlock gagal.");
        } finally {
          button.disabled = false;
        }
      });
    }

    // Tambah Lapak Baru
    const addStallForm = document.getElementById("add-stall-form");
    if (addStallForm) {
      addStallForm.addEventListener("submit", async (e) => {
        e.preventDefault();
        const token = sessionStorage.getItem(tokenKey);
        if (!token) return showAdminMessage("Sesi admin tidak aktif.");
        const formData = new FormData(addStallForm);
        try {
          const res = await fetch(`${apiBase}/peta/lapak`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              Authorization: `Bearer ${token}`,
            },
            body: JSON.stringify({
              kode_lapak: String(formData.get("kode_lapak")).trim().toUpperCase(),
              panjang: parseFloat(formData.get("panjang")),
              lebar: parseFloat(formData.get("lebar")),
              posisi_x: parseInt(formData.get("posisi_x") || "0", 10),
              posisi_y: parseInt(formData.get("posisi_y") || "0", 10),
            }),
          });
          if (!res.ok) throw new Error(await responseMessage(res));
          addStallForm.reset();
          showAdminMessage("Lapak baru berhasil ditambahkan ke denah pasar.", "success");
          await loadDashboard(token);
        } catch (err) {
          showAdminMessage(err.message || "Gagal menambah lapak.");
        }
      });
    }

    // Admin Verification Click Handler (with Note sync)
    const reviewList = document.getElementById("applicant-review-list");
    if (reviewList) {
      reviewList.addEventListener("click", async (event) => {
        const button = event.target.closest("[data-review-id]");
        if (!button) return;
        const applicantId = button.dataset.reviewId;
        const status = button.dataset.reviewStatus;
        const card = document.getElementById(`applicant-card-${applicantId}`);
        const noteInput = card?.querySelector(".review-note-input");
        const catatan = noteInput?.value?.trim() || "";

        button.disabled = true;
        try {
          const response = await fetch(
            `${apiBase}/admin/pendaftar/${applicantId}/verifikasi`,
            {
              method: "POST",
              headers: {
                Authorization: `Bearer ${sessionStorage.getItem(tokenKey)}`,
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ status, catatan }),
            },
          );
          if (!response.ok) throw new Error(await responseMessage(response));
          await loadDashboard(sessionStorage.getItem(tokenKey));
          showAdminMessage(
            `Verifikasi untuk pendaftar #${applicantId} dicatat sebagai "${status}". Catatan telah disinkronkan ke user.`,
            "success",
          );
        } catch (error) {
          button.disabled = false;
          showAdminMessage(error.message || "Verifikasi gagal disimpan.");
        }
      });
    }

    const token = sessionStorage.getItem(tokenKey);
    if (token) {
      fetch(`${apiBase}/admin/saya`, {
        headers: { Authorization: `Bearer ${token}` },
      })
        .then(async (response) => {
          if (!response.ok) throw new Error(await responseMessage(response));
          return response.json();
        })
        .then((admin) => showAdmin(admin.username, token))
        .catch(() => sessionStorage.removeItem(tokenKey));
    }

    adminLoginForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      if (!adminLoginForm.reportValidity()) return;
      const formData = new FormData(adminLoginForm);
      const body = new URLSearchParams({
        username: String(formData.get("username")),
        password: String(formData.get("password")),
      });
      try {
        const response = await fetch(`${apiBase}/admin/login`, {
          method: "POST",
          headers: { "Content-Type": "application/x-www-form-urlencoded" },
          body,
        });
        if (!response.ok) throw new Error(await responseMessage(response));
        const result = await response.json();
        sessionStorage.setItem(tokenKey, result.access_token);
        await showAdmin(String(formData.get("username")), result.access_token);
      } catch (error) {
        showAdminMessage(error.message || "Tidak dapat terhubung ke server.");
      }
    });

    const logoutBtn = document.getElementById("admin-logout");
    if (logoutBtn) {
      logoutBtn.addEventListener("click", () => {
        sessionStorage.removeItem(tokenKey);
        dashboard.hidden = true;
        loginPanel.hidden = false;
        adminLoginForm.reset();
        showAdminMessage("Anda sudah keluar dari dashboard.", "success");
      });
    }
  }

  // ==========================================
  // PENDAFTARAN FORM SUBMISSION
  // ==========================================
  const form = document.getElementById("registration-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = document.getElementById("form-message");
      if (!form.reportValidity()) return;
      const formData = new FormData(form);
      const category = String(formData.get("category") || "");
      const apiBase =
        document.querySelector('meta[name="api-base"]')?.content ||
        window.location.origin;
      const submitButton = form.querySelector('[type="submit"]');
      submitButton.disabled = true;
      let application;
      try {
        const payload = {
          nama_pemilik: String(formData.get("owner") || "").trim(),
          nik: String(formData.get("nik") || "").trim(),
          nomor_telepon: String(formData.get("phone") || "").trim(),
          email: String(formData.get("email") || "").trim(),
          nama_usaha: String(formData.get("business") || "").trim(),
          domisili: String(formData.get("domicile") || "").trim(),
          jenis_usaha: businessTypes[category] || category.toLowerCase(),
          deskripsi: String(formData.get("description") || "").trim(),
          status_khusus: formData.has("statusKhusus"),
          punya_toko_fisik: formData.has("physicalShop"),
          produksi_sendiri: formData.has("produksiSendiri"),
          jumlah_cabang: Number(formData.get("branches") || 1),
          modal_besar: formData.has("largeCapital"),
          kebutuhan_luas:
            {
              "2 × 2 meter": 4,
              "2 × 3 meter": 6,
              "3 × 3 meter": 9,
            }[String(formData.get("stallSize"))] || 0,
        };

        const response = await fetch(`${apiBase}/pendaftaran`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(
            body.detail || "Pendaftaran gagal disimpan ke server.",
          );
        }
        application = await response.json();
      } catch (error) {
        if (message) {
          message.className = "inline-message show error";
          message.textContent =
            error.message || "Tidak dapat terhubung ke server.";
        }
        submitButton.disabled = false;
        return;
      }

      const data = {
        code: application.umkm.nomor_pendaftaran,
        owner: application.umkm.nama_pemilik,
        nik: application.umkm.nik,
        phone: application.umkm.nomor_telepon,
        email: application.umkm.email,
        business: application.umkm.nama_usaha,
        category: application.umkm.jenis_usaha,
        domicile: application.umkm.domisili,
        umkmId: application.umkm.id,
        description: application.umkm.deskripsi,
        stallSize: String(formData.get("stallSize") || ""),
        priority: String(application.umkm.queue_level),
        status: application.umkm.status_pendaftaran || "Menunggu",
        createdAt: new Date().toLocaleDateString("id-ID", {
          day: "2-digit",
          month: "long",
          year: "numeric",
        }),
      };
      saveRegistration(data);

      if (message) {
        message.className = "inline-message show success";
        message.textContent =
          "Pendaftaran berhasil! Nomor Pendaftaran Anda: " +
          data.code +
          ". Otomatis berada di Queue " +
          application.umkm.queue_level +
          ". Mengarahkan ke halaman status...";
      }
      form.reset();
      window.setTimeout(() => {
        window.location.href =
          "status.html?code=" + encodeURIComponent(data.code);
      }, 1200);
    });
  }

  // ==========================================
  // REAL-TIME COUNTDOWN TIMER (1 MENIT TIMEOUT)
  // ==========================================
  let countdownTimerId = null;
  const startLiveCountdown = (sisaDetikAwal) => {
    if (countdownTimerId) clearInterval(countdownTimerId);
    let sisa = Math.max(0, Math.floor(sisaDetikAwal));

    const renderClock = () => {
      const jam = Math.floor(sisa / 3600);
      const menit = Math.floor((sisa % 3600) / 60);
      const detik = sisa % 60;
      const elH = document.getElementById("cd-h");
      const elM = document.getElementById("cd-m");
      const elS = document.getElementById("cd-s");
      if (elH) elH.textContent = String(jam).padStart(2, "0");
      if (elM) elM.textContent = String(menit).padStart(2, "0");
      if (elS) elS.textContent = String(detik).padStart(2, "0");

      if (sisa <= 0) {
        clearInterval(countdownTimerId);
        const notice = document.getElementById("cd-notice");
        if (notice) {
          notice.innerHTML = '<b style="color:#d25b4d; font-size:13px;">⚠️ WAKTU KONFIRMASI TELAH HABIS (TIMEOUT 1 MENIT). Hak sewa otomatis dibatalkan dan nomor Anda dipindahkan ke antrean terbawah.</b>';
        }
      }
      sisa--;
    };

    renderClock();
    countdownTimerId = setInterval(renderClock, 1000);
  };

  // ==========================================
  // STATUS PAGE LOOKUP & RENDERING
  // ==========================================
  const result = document.getElementById("status-result");
  const searchForm = document.getElementById("status-search-form");
  const codeInput = document.getElementById("status-code");

  const renderStatus = async (statusData) => {
    if (!result) return;
    if (countdownTimerId) {
      clearInterval(countdownTimerId);
      countdownTimerId = null;
    }

    if (!statusData || !statusData.umkm) {
      result.innerHTML = `
        <div class="empty-state">
          <span class="empty-icon">🔍</span>
          <h2>Data Pendaftaran Tidak Ditemukan</h2>
          <p>Pastikan nomor pendaftaran (contoh: <code>STK-2026-000001</code>) sudah benar.</p>
          <a class="btn btn-outline" href="pendaftaran.html">Daftar UMKM Baru</a>
        </div>`;
      return;
    }

    const umkm = statusData.umkm;
    const alokasi = statusData.alokasi;
    const verifikasi = statusData.verifikasi;
    const posisi = statusData.posisi_dalam_queue;

    const queueLevel = umkm.queue_level || 3;
    const queueBadgeClass = priorityBadgeClasses[queueLevel] || "badge-q3";
    const queueLabel = priorityLabels[queueLevel] || `Queue ${queueLevel}`;
    const statusPendaftaran = umkm.status_pendaftaran || "Menunggu";

    // 1. KOTAK VERIFIKASI ADMIN (SINKRONISASI DUA ARAH)
    let verifikasiCallout = "";
    if (verifikasi) {
      if (verifikasi.status === "Terverifikasi") {
        verifikasiCallout = `
          <div style="background:#eef7f0; border:1px solid #c2e2cb; border-left:5px solid #37895f; padding:14px 18px; border-radius:10px; margin:16px 0;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <b style="color:#236844; font-size:14px;">✅ Berkas Telah Diverifikasi Pengelola Pasar</b>
              <span class="muted small">${verifikasi.waktu_verifikasi ? new Date(verifikasi.waktu_verifikasi).toLocaleString("id-ID") : ""}</span>
            </div>
            <p style="margin:6px 0 0; color:#1e4d34; font-size:13px;">
              Petugas verifikator: <b>${escapeHtml(verifikasi.nama_verifikator)}</b>.<br />
              ${verifikasi.catatan ? `<b>Catatan Petugas:</b> "${escapeHtml(verifikasi.catatan)}"` : "Seluruh berkas identitas dan syarat pendaftaran dinyatakan lengkap."}
            </p>
          </div>
        `;
      } else if (verifikasi.status === "Perlu Perbaikan") {
        verifikasiCallout = `
          <div style="background:#fff9f0; border:1px solid #ffe3b3; border-left:5px solid #d5a522; padding:14px 18px; border-radius:10px; margin:16px 0;">
            <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px;">
              <b style="color:#8a6100; font-size:14px;">⚠️ Perhatian: Berkas Perlu Perbaikan</b>
              <span class="muted small">${verifikasi.waktu_verifikasi ? new Date(verifikasi.waktu_verifikasi).toLocaleString("id-ID") : ""}</span>
            </div>
            <p style="margin:6px 0 0; color:#6b4c00; font-size:13px;">
              Petugas <b>${escapeHtml(verifikasi.nama_verifikator)}</b> memberikan catatan:<br />
              <em style="display:block; margin-top:4px; font-weight:600;">"${escapeHtml(verifikasi.catatan || "Mohon periksa kembali kesesuaian data identitas Anda.")}"</em>
            </p>
          </div>
        `;
      }
    } else {
      verifikasiCallout = `
        <div style="background:#f4f6f8; border:1px solid #d9e0e6; border-left:5px solid #6b7280; padding:12px 16px; border-radius:10px; margin:16px 0;">
          <b style="color:#374151; font-size:13px;">⏳ Berkas Menunggu Verifikasi Admin</b>
          <p style="margin:4px 0 0; color:#4b5563; font-size:12px;">
            Petugas pengelola pasar sedang memeriksa berkas Anda. Penempatan antrean dan alokasi kios tetap berjalan otomatis di latar belakang.
          </p>
        </div>
      `;
    }

    // 2. HEADER RINGKASAN DATA PENDAFTAR
    const topHtml = `
      <div class="status-top">
        <div>
          <span class="kicker">NOMOR PENDAFTARAN RESMI</span>
          <h2 style="margin:4px 0;">${escapeHtml(umkm.nomor_pendaftaran)}</h2>
          <p style="margin:0; font-size:12px; color:var(--muted);">
            Didaftarkan pada: ${umkm.waktu_daftar ? new Date(umkm.waktu_daftar).toLocaleDateString("id-ID", { day: "2-digit", month: "long", year: "numeric", hour: "2-digit", minute: "2-digit" }) : "-"}
          </p>
        </div>
        <span class="pill ${statusPendaftaran === "Aktif" ? "pill-green" : statusPendaftaran === "Dicabut" ? "pill-coral" : "pill-yellow"}">${escapeHtml(statusPendaftaran)}</span>
      </div>

      ${verifikasiCallout}

      <div class="status-detail-grid">
        <div class="status-detail"><small>Nama Usaha</small><b>${escapeHtml(umkm.nama_usaha)}</b></div>
        <div class="status-detail"><small>Nama Pemilik</small><b>${escapeHtml(umkm.nama_pemilik)}</b></div>
        <div class="status-detail"><small>Nomor KTP / NIK</small><b>${escapeHtml(umkm.nik || "-")}</b></div>
        <div class="status-detail"><small>WhatsApp / No. HP</small><b>${escapeHtml(umkm.nomor_telepon || "-")}</b></div>
        <div class="status-detail"><small>Domisili KTP</small><b>${escapeHtml(umkm.domisili)}</b></div>
        <div class="status-detail"><small>Kategori Usaha</small><b>${escapeHtml(umkm.jenis_usaha)}</b></div>
        <div class="status-detail"><small>Kebutuhan Kios</small><b>${umkm.kebutuhan_luas} m²</b></div>
        <div class="status-detail"><small>Jalur Prioritas Keadilan Sosial</small><b class="queue-badge ${queueBadgeClass}">${escapeHtml(queueLabel)}</b></div>
      </div>
    `;

    // 3. FASE STATUS (MENUNGGU / TIMEOUT 1 MENIT / PREEMPTION)
    let phaseHtml = "";

    if (statusPendaftaran === "Menunggu" && !alokasi) {
      phaseHtml = `
        <section class="card" style="margin-top:20px; border-left: 5px solid #2875b9; background:#f8faff;">
          <div class="dashboard-section-heading">
            <div>
              <span class="kicker">DASBOR STATUS ANTREAN MLQ</span>
              <h2>Sedang Menunggu Ketersediaan Kios</h2>
            </div>
            <span class="queue-badge ${queueBadgeClass}">${escapeHtml(queueLabel)}</span>
          </div>
          <p style="font-size:15px; margin: 12px 0;">
            ${posisi ? `Posisi Anda saat ini: <b>Urutan ke-${posisi}</b> di ${queueLabel}.` : "Anda berada di antrean prioritas sistem."}
          </p>
          <div class="info-box">
            ℹ️ Sistem terus mencocokkan luas kios yang kosong dengan kebutuhan Anda (<b>${umkm.kebutuhan_luas} m²</b>) menggunakan algoritma <b>Worst-Fit</b>. Bila ada kios yang cocok atau penyewa sebelumnya timeout/batal, kios akan langsung disiapkan untuk Anda.
          </div>
        </section>
      `;
    } else if (alokasi && alokasi.status_alokasi === "Menunggu Konfirmasi") {
      // DEADLOCK 1: TIMEOUT 1 MENIT
      const sisaDetik = alokasi.sisa_detik_konfirmasi ?? 60;
      phaseHtml = `
        <section class="cta-allocation">
          <div class="cta-allocation-header">
            <div>
              <span class="kicker">KIOS BERHASIL DITEMUKAN (DEADLOCK 1)</span>
              <h2>Kios ${escapeHtml(alokasi.kode_lapak)} Tersedia! Segera Konfirmasi Kios Anda</h2>
            </div>
            <span class="pill pill-yellow">Menunggu Konfirmasi</span>
          </div>
          <p style="font-size:14px; margin:10px 0;">
            Algoritma Worst-Fit telah memasangkan usaha Anda dengan <b>Lapak ${escapeHtml(alokasi.kode_lapak)}</b> di Pasar Seni Kota.
          </p>
          
          <div class="countdown-container">
            <div class="countdown-title">Batas Waktu Konfirmasi Anda (Simulasi: 1 Menit / 60 Detik)</div>
            <div class="countdown-display">
              <div class="countdown-box"><strong id="cd-h">00</strong><small>Jam</small></div>
              <span class="countdown-colon">:</span>
              <div class="countdown-box"><strong id="cd-m">00</strong><small>Menit</small></div>
              <span class="countdown-colon">:</span>
              <div class="countdown-box"><strong id="cd-s">--</strong><small>Detik</small></div>
            </div>
            <p id="cd-notice" style="margin-top:10px; font-size:12px; color:#cfd8d3;">
              Waktu berjalan mundur otomatis. Segera klik tombol konfirmasi di bawah ini.
            </p>
          </div>

          <div class="timeout-notice">
            <b>Aturan Penanganan Deadlock (Timeout 1 Menit):</b><br />
            Untuk menjamin keadilan bagi pendaftar lain, bila konfirmasi tidak ditekan dalam waktu 1 menit, sistem otomatis membatalkan hak kios ini, memindahkan urutan pendaftaran Anda ke posisi paling belakang antrean, dan menawarkan kios ke pendaftar berikutnya.
          </div>

          <div style="display:flex; gap:12px; align-items:center; flex-wrap:wrap;">
            <button class="btn btn-green" data-allocation-action="konfirmasi" data-allocation-id="${alokasi.id}" type="button" style="font-size:15px; padding:12px 28px; font-weight:700;">
              ✓ Setuju &amp; Ambil Kios ${escapeHtml(alokasi.kode_lapak)} Sekarang
            </button>
            <span class="muted small">Lapak akan resmi aktif dan warna denah berubah menjadi Terisi (Merah).</span>
          </div>
        </section>
      `;
    } else if (alokasi && alokasi.status_alokasi === "Aktif") {
      // DEADLOCK 2: PREEMPTION (2 MENIT / 120 DETIK)
      const detikTutup = alokasi.detik_tidak_aktif ?? 0;
      const batasPreemption = 120; // 2 menit simulasi
      const pctPreemption = Math.min(100, Math.round((detikTutup / batasPreemption) * 100));
      const isWarning = alokasi.peringatan || detikTutup >= 30;
      const barColorClass = detikTutup >= batasPreemption ? "bar-danger" : isWarning ? "bar-warning" : "bar-safe";

      phaseHtml = `
        <section class="panel-lapak-aktif">
          <div class="dashboard-section-heading">
            <div>
              <span class="kicker">PANEL KIOS AKTIF (DEADLOCK 2 - PREEMPTION)</span>
              <h2>Kios ${escapeHtml(alokasi.kode_lapak)} · Sah &amp; Sedang Digunakan</h2>
            </div>
            <span class="pill pill-green">Lapak Terisi</span>
          </div>
          
          <div class="stall-box">
            <small>Nomor Kios Resmi Anda</small>
            <strong>Lapak ${escapeHtml(alokasi.kode_lapak)}</strong>
            <small>Pasar Seni Kota · Status Denah: Terisi (Merah di Peta Live Grid)</small>
          </div>

          <div style="margin: 16px 0;">
            <button class="btn btn-green full-width" data-allocation-action="absen" data-allocation-id="${alokasi.id}" type="button" style="padding:14px; font-size:15px; font-weight:700;">
              ✓ Buka Toko Hari Ini (Absensi Kehadiran)
            </button>
            <p class="muted small" style="margin-top: 6px; text-align: center;">
              Klik tombol ini saat Anda berjualan untuk mereset durasi tidak aktif kembali ke 0.
            </p>
          </div>

          <div class="preemption-meter-wrap">
            <div style="display:flex; justify-content:space-between; font-size:12px; font-weight:600;">
              <span>Status Aktivitas Berjualan:</span>
              <b>${detikTutup} Detik Tidak Aktif (Maksimal 120 Detik / 2 Menit)</b>
            </div>
            <div class="preemption-bar">
              <div class="preemption-bar-fill ${barColorClass}" style="width: ${pctPreemption}%;"></div>
            </div>
            <div style="display:flex; justify-content:space-between; font-size:10px; color:var(--muted);">
              <span>0s (Buka Toko)</span>
              <span>30s (Peringatan Dini)</span>
              <span>120s (Preemption / Cabut Hak)</span>
            </div>
          </div>

          ${
            isWarning
              ? `<div class="warning-preemption">
                  <b>⚠️ Peringatan Dini Pengelola: Lapak Berisiko Dicabut!</b><br />
                  Sistem mendeteksi lapak Anda tidak ada aktivitas lebih dari 30 detik. Segera lakukan absensi dengan menekan tombol <b>"Buka Toko Hari Ini"</b> sebelum mencapai 120 detik agar hak sewa kios tidak dicabut paksa.
                </div>`
              : ""
          }

          <div class="info-box" style="margin-top:14px;">
            <b>Aturan Deadlock Preemption:</b> Kios yang dibiarkan tutup terus-menerus tanpa aktivitas hingga 2 menit akan dicabut sepihak oleh sistem dan dialokasikan ke UMKM lain yang membutuhkan.
          </div>
        </section>
      `;
    } else if (statusPendaftaran === "Dicabut" || alokasi?.status_alokasi === "Dicabut") {
      phaseHtml = `
        <div class="warning-preemption" style="margin-top:20px; padding:20px;">
          <h2 style="margin:0 0 8px;">⛔ Hak Sewa Kios Dicabut (Preemption)</h2>
          <p style="margin:0; font-size:13px;">
            Hak sewa lapak Anda telah dicabut sepihak oleh sistem pengelola pasar karena tidak ada aktivitas operasional melebihi batas waktu maksimal. Lapak telah dikembalikan ke status Kosong (Hijau) untuk disalurkan ke antrean berikutnya.
          </p>
        </div>
      `;
    }

    result.innerHTML = topHtml + phaseHtml;

    // Start live countdown if pending
    if (alokasi && alokasi.status_alokasi === "Menunggu Konfirmasi") {
      startLiveCountdown(alokasi.sisa_detik_konfirmasi ?? 60);
    }

    // Synchronize Timeline Steps (1 to 4)
    const t1 = document.getElementById("step-1");
    const t2 = document.getElementById("step-2");
    const t3 = document.getElementById("step-3");
    const t4 = document.getElementById("step-4");
    if (t1 && t2 && t3 && t4) {
      [t1, t2, t3, t4].forEach((el) => el.classList.remove("done", "current"));
      t1.classList.add("done");

      if (verifikasi && verifikasi.status === "Terverifikasi") {
        t2.classList.add("done");
      } else {
        t2.classList.add("current");
      }

      if (alokasi) {
        t2.classList.add("done");
        if (alokasi.status_alokasi === "Menunggu Konfirmasi") {
          t3.classList.add("current");
        } else if (alokasi.status_alokasi === "Aktif") {
          t3.classList.add("done");
          t4.classList.add("current");
        }
      }
    }
  };

  if (searchForm) {
    const params = new URLSearchParams(window.location.search);
    const savedReg = getRegistration();

    // Show Quick Check Pill if user registered on this device
    const pill = document.getElementById("recent-registration-pill");
    const codeSpan = document.getElementById("recent-reg-code");
    const businessSpan = document.getElementById("recent-reg-business");
    const quickBtn = document.getElementById("btn-quick-check");

    if (savedReg && pill && codeSpan && businessSpan) {
      pill.style.display = "block";
      codeSpan.textContent = savedReg.code;
      businessSpan.textContent = savedReg.business || "Usaha Anda";

      if (quickBtn) {
        quickBtn.addEventListener("click", () => {
          codeInput.value = savedReg.code;
          void lookupStatus(savedReg.code);
        });
      }
    }

    if (params.get("code")) {
      codeInput.value = params.get("code");
    } else if (savedReg) {
      codeInput.value = savedReg.code;
    }

    const lookupStatus = async (number) => {
      const apiBase =
        document.querySelector('meta[name="api-base"]')?.content ||
        window.location.origin;
      try {
        const response = await fetch(
          `${apiBase}/pendaftaran/nomor/${encodeURIComponent(number)}/status`,
        );
        if (!response.ok) {
          await renderStatus(null);
          return;
        }
        const status = await response.json();
        await renderStatus(status);
      } catch {
        await renderStatus(null);
      }
    };

    if (codeInput.value) {
      void lookupStatus(codeInput.value.trim().toUpperCase());
    }

    // Auto-refresh status every 10s to reflect cron deadlock or admin verification
    window.setInterval(() => {
      if (codeInput.value.trim()) {
        void lookupStatus(codeInput.value.trim().toUpperCase());
      }
    }, 10000);

    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      void lookupStatus(codeInput.value.trim().toUpperCase());
    });

    result.addEventListener("click", async (event) => {
      const button = event.target.closest("[data-allocation-action]");
      if (!button) return;
      button.disabled = true;
      const action = button.dataset.allocationAction;
      try {
        const response = await fetch(
          `${window.location.origin}/alokasi/${button.dataset.allocationId}/${action}`,
          { method: "POST" },
        );
        if (!response.ok) throw new Error("Permintaan tidak dapat diproses.");
        await lookupStatus(codeInput.value.trim().toUpperCase());
      } catch (error) {
        button.disabled = false;
        button.textContent = error.message;
      }
    });
  }

  // ==========================================
  // PROFILE PAGE (profil.html)
  // ==========================================
  const activityButton = document.getElementById("activity-button");
  if (activityButton) {
    const data = getRegistration();
    if (data) {
      const name = document.getElementById("profile-business");
      const owner = document.getElementById("profile-owner");
      const ownerDetail = document.getElementById("profile-owner-detail");
      const category = document.getElementById("profile-category");
      const phone = document.getElementById("profile-phone");
      const email = document.getElementById("profile-email");
      if (name) name.textContent = data.business;
      if (owner)
        owner.textContent =
          "Pemilik: " + data.owner + " · Status: " + data.status;
      if (ownerDetail) ownerDetail.textContent = data.owner;
      if (category) category.textContent = data.category;
      if (phone) phone.textContent = data.phone || "Belum diisi";
      if (email) email.textContent = data.email || "Belum diisi";

      const apiBase =
        document.querySelector('meta[name="api-base"]')?.content ||
        window.location.origin;
      const status = document.getElementById("activity-message");
      const stall = document.querySelector(".stall-box");

      const refreshProfile = async () => {
        if (!data.umkmId) {
          if (status) status.textContent = "Belum ada data penyewa dari server.";
          activityButton.disabled = true;
          return;
        }
        try {
          const response = await fetch(
            `${apiBase}/alokasi/umkm/${data.umkmId}`,
          );
          if (!response.ok) throw new Error();
          const allocation = await response.json();
          const isActive = allocation.status_alokasi === "Aktif";
          activityButton.disabled = !isActive;
          activityButton.textContent = isActive
            ? "✓ Buka Kios Hari Ini"
            : "Menunggu Konfirmasi Lapak";
          if (stall)
            stall.innerHTML = `<small>Nomor Kios</small><strong>${escapeHtml(allocation.kode_lapak)}</strong><small>Status: ${escapeHtml(allocation.status_alokasi)}</small>`;
          if (status) {
            status.textContent = isActive
              ? `Aktivitas terakhir: ${allocation.detik_tidak_aktif ?? 0} detik lalu${allocation.peringatan ? ". ⚠️ Peringatan: lapak berisiko dicabut." : "."}`
              : "Lapak belum aktif.";
          }
        } catch {
          activityButton.disabled = true;
          activityButton.textContent = "Belum ada lapak aktif";
          if (status) status.textContent = "Alokasi lapak belum tersedia.";
        }
      };

      activityButton.addEventListener("click", async () => {
        activityButton.disabled = true;
        try {
          const allocation = await fetch(
            `${apiBase}/alokasi/umkm/${data.umkmId}`,
          ).then((response) => response.json());
          const response = await fetch(
            `${apiBase}/alokasi/${allocation.id}/absen`,
            { method: "POST" },
          );
          if (!response.ok) throw new Error();
          if (status) status.textContent = "Kehadiran hari ini berhasil dicatat.";
          await refreshProfile();
        } catch {
          if (status) status.textContent = "Aktivitas tidak dapat dicatat. Coba lagi.";
          activityButton.disabled = false;
        }
      });
      void refreshProfile();
    }
  }
})();
