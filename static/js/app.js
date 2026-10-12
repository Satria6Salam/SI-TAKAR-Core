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
    1: "Prioritas tinggi",
    2: "Prioritas menengah",
    3: "Prioritas reguler",
  };
  const businessTypes = {
    "Kriya / kerajinan": "kriya",
    Kuliner: "kuliner",
    "Fashion / tekstil": "fesyen",
    "Seni dan antik": "seni rupa",
    "Jasa kreatif": "jasa kreatif",
    Lainnya: "lainnya",
  };

  document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
    button.addEventListener("click", () =>
      document.querySelector("[data-nav]")?.classList.toggle("open"),
    );
  });

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
      message.className = `inline-message show ${type}`;
      message.textContent = text;
    };
    const responseMessage = async (response) => {
      const body = await response.json().catch(() => ({}));
      return body.detail || body.pesan || "Permintaan tidak dapat diproses.";
    };
    const showAdmin = async (username, token) => {
      document.getElementById("admin-username").textContent = username;
      loginPanel.hidden = true;
      dashboard.hidden = false;
      document.getElementById("admin-footnote").hidden = true;
      await loadDashboard(token);
    };
    const renderQueue = (elementId, items) => {
      const list = document.getElementById(elementId);
      if (!items?.length) {
        list.innerHTML = '<p class="queue-empty">Belum ada pendaftar.</p>';
        return;
      }
      list.innerHTML = items
        .map(
          (item) =>
            `<article class="queue-applicant"><b>${escapeHtml(item.nama_usaha)}</b><span>${escapeHtml(item.nama_pemilik)} · ${escapeHtml(item.domisili)}</span><small>${escapeHtml(item.jenis_usaha)} · ${escapeHtml(item.status_pendaftaran)}</small></article>`,
        )
        .join("");
    };
    const renderBars = (elementId, entries) => {
      const root = document.getElementById(elementId);
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
      if (!applicants.length) {
        root.innerHTML =
          '<p class="queue-empty">Belum ada pendaftar untuk ditinjau.</p>';
        return;
      }
      root.innerHTML = applicants
        .map((item) => {
          const review = item.verifikasi;
          const reviewText = review
            ? `${escapeHtml(review.status)} oleh ${escapeHtml(review.nama_verifikator)} · ${new Date(review.waktu_verifikasi).toLocaleString("id-ID")}`
            : "Belum diverifikasi";
          return `<article class="review-row"><div class="review-person"><b>${escapeHtml(item.nama_usaha)}</b><span>${escapeHtml(item.nama_pemilik)} · Queue ${item.queue_level}</span><small>${reviewText}${review?.catatan ? ` · ${escapeHtml(review.catatan)}` : ""}</small></div><div class="review-actions"><button class="btn btn-green" data-review-id="${item.id}" data-review-status="Terverifikasi" type="button">Verifikasi</button><button class="btn btn-light" data-review-id="${item.id}" data-review-status="Perlu Perbaikan" type="button">Perlu perbaikan</button></div></article>`;
        })
        .join("");
    };
    const loadDashboard = async (token) => {
      try {
        const headers = { Authorization: `Bearer ${token}` };
        const demoRegistration = getRegistration();
        if (demoRegistration && !demoRegistration.umkmId) {
          const migrated = await fetch(`${apiBase}/pendaftaran`, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
              nama_pemilik: demoRegistration.owner,
              nama_usaha: demoRegistration.business,
              domisili: demoRegistration.domicile || "Kota Contoh",
              jenis_usaha:
                businessTypes[demoRegistration.category] ||
                String(demoRegistration.category || "lainnya").toLowerCase(),
              status_khusus: String(demoRegistration.priority) === "1",
              punya_toko_fisik: false,
            }),
          });
          if (migrated.ok) {
            const migratedStatus = await migrated.json();
            demoRegistration.umkmId = migratedStatus.umkm.id;
            demoRegistration.domicile =
              demoRegistration.domicile || "Kota Contoh";
            saveRegistration(demoRegistration);
          }
        }
        const [queueResponse, mapResponse, applicantsResponse] =
          await Promise.all([
            fetch(`${apiBase}/antrean`, { headers }),
            fetch(`${apiBase}/peta`),
            fetch(`${apiBase}/admin/pendaftar`, { headers }),
          ]);
        if (queueResponse.status === 401)
          throw new Error("Sesi berakhir. Silakan masuk kembali.");
        if (!queueResponse.ok)
          throw new Error(await responseMessage(queueResponse));
        if (!mapResponse.ok)
          throw new Error("Ringkasan kios tidak dapat dimuat.");
        if (!applicantsResponse.ok)
          throw new Error(await responseMessage(applicantsResponse));
        const [queues, map, applicants] = await Promise.all([
          queueResponse.json(),
          mapResponse.json(),
          applicantsResponse.json(),
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
          { label: "Queue 1 · Tinggi", value: queues.queue_1.length },
          { label: "Queue 2 · Menengah", value: queues.queue_2.length },
          { label: "Queue 3 · Reguler", value: queues.queue_3.length },
        ]);
        renderBars("stall-chart", [
          { label: "Kosong", value: map.ringkasan.kosong },
          { label: "Dipesan", value: map.ringkasan.dipesan },
          { label: "Terisi", value: map.ringkasan.terisi },
        ]);
        renderReviews(applicants);
        document.getElementById("dashboard-updated").textContent =
          "Diperbarui " +
          new Date().toLocaleTimeString("id-ID", {
            hour: "2-digit",
            minute: "2-digit",
          });
        showAdminMessage("Data dashboard berhasil dimuat.", "success");
      } catch (error) {
        if (error.message.includes("Sesi berakhir")) {
          sessionStorage.removeItem(tokenKey);
          dashboard.hidden = true;
          loginPanel.hidden = false;
        }
        showAdminMessage(error.message || "Tidak dapat terhubung ke server.");
      }
    };

    document.getElementById("demo-fill").addEventListener("click", () => {
      adminLoginForm.elements.username.value = "admin";
      adminLoginForm.elements.password.value = "admin123";
    });

    document
      .getElementById("dashboard-refresh")
      .addEventListener("click", () => {
        loadDashboard(sessionStorage.getItem(tokenKey));
      });

    document
      .getElementById("applicant-review-list")
      .addEventListener("click", async (event) => {
        const button = event.target.closest("[data-review-id]");
        if (!button) return;
        button.disabled = true;
        try {
          const response = await fetch(
            `${apiBase}/admin/pendaftar/${button.dataset.reviewId}/verifikasi`,
            {
              method: "POST",
              headers: {
                ...{
                  Authorization: `Bearer ${sessionStorage.getItem(tokenKey)}`,
                },
                "Content-Type": "application/json",
              },
              body: JSON.stringify({ status: button.dataset.reviewStatus }),
            },
          );
          if (!response.ok) throw new Error(await responseMessage(response));
          await loadDashboard(sessionStorage.getItem(tokenKey));
          showAdminMessage(
            "Keputusan verifikasi dan nama petugas berhasil dicatat.",
            "success",
          );
        } catch (error) {
          button.disabled = false;
          showAdminMessage(error.message || "Verifikasi gagal disimpan.");
        }
      });

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

    document.getElementById("admin-logout").addEventListener("click", () => {
      sessionStorage.removeItem(tokenKey);
      dashboard.hidden = true;
      loginPanel.hidden = false;
      adminLoginForm.reset();
      showAdminMessage("Anda sudah keluar dari dashboard.", "success");
    });
  }

  const form = document.getElementById("registration-form");
  if (form) {
    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const message = document.getElementById("form-message");
      if (!form.reportValidity()) return;
      const formData = new FormData(form);
      const category = String(formData.get("category") || "");
      const selectedPriority = String(formData.get("priority") || "3");
      const apiBase =
        document.querySelector('meta[name="api-base"]')?.content ||
        window.location.origin;
      const submitButton = form.querySelector('[type="submit"]');
      submitButton.disabled = true;
      let application;
      try {
        const response = await fetch(`${apiBase}/pendaftaran`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            nama_pemilik: String(formData.get("owner") || "").trim(),
            nama_usaha: String(formData.get("business") || "").trim(),
            domisili: String(formData.get("domicile") || "").trim(),
            jenis_usaha: businessTypes[category] || category.toLowerCase(),
            status_khusus: selectedPriority === "1",
            punya_toko_fisik: false,
          }),
        });
        if (!response.ok) {
          const body = await response.json().catch(() => ({}));
          throw new Error(
            body.detail || "Pendaftaran gagal disimpan ke server.",
          );
        }
        application = await response.json();
      } catch (error) {
        message.className = "inline-message show error";
        message.textContent =
          error.message || "Tidak dapat terhubung ke server.";
        submitButton.disabled = false;
        return;
      }
      const data = {
        code:
          "STK-" +
          new Date().getFullYear() +
          "-" +
          Math.random().toString(10).slice(2, 6),
        owner: String(formData.get("owner") || "").trim(),
        nik: String(formData.get("nik") || "").trim(),
        phone: String(formData.get("phone") || "").trim(),
        email: String(formData.get("email") || "").trim(),
        business: String(formData.get("business") || "").trim(),
        category,
        domicile: String(formData.get("domicile") || "").trim(),
        umkmId: application.umkm.id,
        description: String(formData.get("description") || "").trim(),
        stallSize: String(formData.get("stallSize") || ""),
        electricity: String(formData.get("electricity") || ""),
        priority: String(application.umkm.queue_level),
        status: application.verifikasi?.status || "Menunggu verifikasi",
        createdAt: new Date().toLocaleDateString("id-ID", {
          day: "2-digit",
          month: "long",
          year: "numeric",
        }),
      };
      saveRegistration(data);
      message.className = "inline-message show success";
      message.textContent =
        "Pendaftaran demo berhasil disimpan di browser. Nomor pendaftaran: " +
        data.code +
        ". Buka halaman Status untuk melihat ringkasannya.";
      form.reset();
      window.setTimeout(() => {
        window.location.href =
          "status.html?code=" + encodeURIComponent(data.code);
      }, 1200);
    });
  }

  const result = document.getElementById("status-result");
  const searchForm = document.getElementById("status-search-form");
  const codeInput = document.getElementById("status-code");
  const renderStatus = async (data) => {
    if (!result) return;
    if (!data) {
      result.innerHTML =
        '<div class="empty-state"><span class="empty-icon">⌕</span><h2>Data pendaftaran tidak ditemukan</h2><p>Periksa kembali nomor atau lakukan pendaftaran demo terlebih dahulu di browser ini.</p><a class="btn btn-outline" href="pendaftaran.html">Daftar UMKM</a></div>';
      return;
    }
    let liveStatus = null;
    if (data.umkmId) {
      try {
        const response = await fetch(
          `${window.location.origin}/pendaftaran/${encodeURIComponent(data.umkmId)}/status`,
        );
        if (response.ok) liveStatus = await response.json();
      } catch {
        liveStatus = null;
      }
    }
    const verification = liveStatus?.verifikasi || data.verifikasi;
    const statusLabel = verification?.status || data.status;
    const verifierInfo = verification
      ? `<div class="verifier-note"><b>Diproses ${escapeHtml(verification.status.toLowerCase())}</b><span>Verifikator: ${escapeHtml(verification.nama_verifikator)} · ${escapeHtml(new Date(verification.waktu_verifikasi).toLocaleString("id-ID"))}</span>${verification.catatan ? `<small>${escapeHtml(verification.catatan)}</small>` : ""}</div>`
      : '<div class="verifier-note pending"><b>Belum diverifikasi</b><span>Petugas verifikator belum ditetapkan. Silakan cek kembali setelah pengelola meninjau pengajuan.</span></div>';
    result.innerHTML = `
      <div class="status-top"><div><span class="kicker">NOMOR PENDAFTARAN</span><h2>${escapeHtml(data.code)}</h2><p>Didaftarkan pada ${escapeHtml(data.createdAt)}</p></div><span class="pill pill-yellow">${escapeHtml(statusLabel)}</span></div>
      <div class="status-detail-grid">
        <div class="status-detail"><small>Nama usaha</small><b>${escapeHtml(data.business)}</b></div>
        <div class="status-detail"><small>Nama pemilik</small><b>${escapeHtml(data.owner)}</b></div>
        <div class="status-detail"><small>Antrean</small><b>${liveStatus ? `Queue ${liveStatus.umkm.queue_level}` : escapeHtml(priorityLabels[data.priority] || "Belum ditentukan")}</b></div>
      </div>
      ${verifierInfo}
      ${liveStatus?.posisi_dalam_queue ? `<p class="muted small">Posisi saat ini: ${liveStatus.posisi_dalam_queue} dalam antrean.</p>` : ""}`;
    if (liveStatus) {
      const timelineItems = document.querySelectorAll(".timeline-item");
      const isVerified = Boolean(liveStatus.verifikasi);
      const allocation = liveStatus.alokasi;
      const isActive = allocation?.status_alokasi === "Aktif";
      const hasAllocation = Boolean(allocation);
      const stepStates = [
        "done",
        isVerified ? "done" : "current",
        isVerified ? "done" : "",
        isActive ? "done" : hasAllocation ? "current" : "",
      ];
      timelineItems.forEach((item, index) => {
        item.classList.remove("done", "current");
        if (stepStates[index]) item.classList.add(stepStates[index]);
      });
      const verificationSmall = timelineItems[1]?.querySelector("small");
      if (verificationSmall) {
        verificationSmall.textContent = liveStatus.verifikasi
          ? `${liveStatus.verifikasi.status} oleh ${liveStatus.verifikasi.nama_verifikator}`
          : "Menunggu pemeriksaan pengelola";
      }
      const queueSmall = timelineItems[2]?.querySelector("small");
      if (queueSmall)
        queueSmall.textContent = `Queue ${liveStatus.umkm.queue_level}${liveStatus.posisi_dalam_queue ? ` · posisi ${liveStatus.posisi_dalam_queue}` : ""}`;
      const allocationSmall = timelineItems[3]?.querySelector("small");
      if (allocationSmall) {
        allocationSmall.textContent = allocation
          ? `Kios ${allocation.kode_lapak} · ${allocation.status_alokasi}`
          : "Menunggu kios tersedia";
      }
    }
  };
  if (searchForm) {
    const saved = getRegistration();
    const params = new URLSearchParams(window.location.search);
    if (params.get("code")) codeInput.value = params.get("code");
    else if (saved) codeInput.value = saved.code;
    if (saved && (!codeInput.value || codeInput.value === saved.code))
      void renderStatus(saved);
    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = getRegistration();
      const query = codeInput.value.trim().toUpperCase();
      void renderStatus(
        data && query === data.code.toUpperCase() ? data : null,
      );
    });
  }

  const activityButton = document.getElementById("activity-button");
  if (activityButton) {
    activityButton.addEventListener("click", () => {
      const message = document.getElementById("activity-message");
      const now = new Date().toLocaleString("id-ID", {
        dateStyle: "medium",
        timeStyle: "short",
      });
      message.textContent =
        "Aktivitas demo tercatat pada " +
        now +
        ". Data ini belum dikirim ke backend.";
      activityButton.textContent = "✓ Aktivitas tercatat";
      activityButton.disabled = true;
    });
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
    }
  }

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
})();
