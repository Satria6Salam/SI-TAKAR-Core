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

  document.querySelectorAll("[data-menu-toggle]").forEach((button) => {
    button.addEventListener("click", () =>
      document.querySelector("[data-nav]")?.classList.toggle("open"),
    );
  });

  const form = document.getElementById("registration-form");
  if (form) {
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      const message = document.getElementById("form-message");
      if (!form.reportValidity()) return;
      const formData = new FormData(form);
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
        category: String(formData.get("category") || ""),
        description: String(formData.get("description") || "").trim(),
        stallSize: String(formData.get("stallSize") || ""),
        electricity: String(formData.get("electricity") || ""),
        priority: String(formData.get("priority") || "3"),
        status: "Menunggu verifikasi",
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
        window.location.href = "/status?code=" + encodeURIComponent(data.code);
      }, 1200);
    });
  }

  const result = document.getElementById("status-result");
  const searchForm = document.getElementById("status-search-form");
  const codeInput = document.getElementById("status-code");
  const renderStatus = (data) => {
    if (!result) return;
    if (!data) {
      result.innerHTML =
        '<div class="empty-state"><span class="empty-icon">⌕</span><h2>Data pendaftaran tidak ditemukan</h2><p>Periksa kembali nomor atau lakukan pendaftaran demo terlebih dahulu di browser ini.</p><a class="btn btn-outline" href="/pendaftaran">Daftar UMKM</a></div>';
      return;
    }
    result.innerHTML = `
      <div class="status-top"><div><span class="kicker">NOMOR PENDAFTARAN</span><h2>${escapeHtml(data.code)}</h2><p>Didaftarkan pada ${escapeHtml(data.createdAt)}</p></div><span class="pill pill-yellow">${escapeHtml(data.status)}</span></div>
      <div class="status-detail-grid">
        <div class="status-detail"><small>Nama usaha</small><b>${escapeHtml(data.business)}</b></div>
        <div class="status-detail"><small>Nama pemilik</small><b>${escapeHtml(data.owner)}</b></div>
        <div class="status-detail"><small>Kategori prioritas</small><b>${escapeHtml(priorityLabels[data.priority] || "Belum ditentukan")}</b></div>
      </div>
      <p class="muted small">Ini adalah simulasi frontend. Status antrean dan verifikasi belum terhubung ke backend.</p>`;
  };
  if (searchForm) {
    const saved = getRegistration();
    const params = new URLSearchParams(window.location.search);
    if (params.get("code")) codeInput.value = params.get("code");
    else if (saved) codeInput.value = saved.code;
    if (saved && (!codeInput.value || codeInput.value === saved.code))
      renderStatus(saved);
    searchForm.addEventListener("submit", (event) => {
      event.preventDefault();
      const data = getRegistration();
      const query = codeInput.value.trim().toUpperCase();
      renderStatus(data && query === data.code.toUpperCase() ? data : null);
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
