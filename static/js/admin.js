(() => {
  const byId = (id) => document.getElementById(id);
  const queueBody = byId("queue-table-body");
  const activityBody = byId("activity-table-body");
  const notice = byId("dashboard-notice");
  let queueRows = [];
  let selectedQueue = "all";

  byId("today-label").textContent = new Intl.DateTimeFormat("id-ID", {
    weekday: "long",
    day: "numeric",
    month: "long",
    year: "numeric",
  }).format(new Date());

  const escapeHtml = (value) =>
    String(value ?? "").replace(
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

  const setNotice = (text, type = "info") => {
    notice.textContent = text;
    notice.className = `notice-bar ${type}`;
    notice.hidden = !text;
  };

  const formatDate = (value) => {
    if (!value) return "—";
    const date = new Date(value);
    return Number.isNaN(date.getTime())
      ? "—"
      : new Intl.DateTimeFormat("id-ID", {
          day: "2-digit",
          month: "short",
          year: "numeric",
        }).format(date);
  };

  const statusClass = (status) => {
    if (status === "Aktif") return "status-active";
    if (status === "Menunggu Konfirmasi") return "status-pending";
    return "status-waiting";
  };

  function renderQueue() {
    const visible =
      selectedQueue === "all"
        ? queueRows
        : queueRows.filter((row) => String(row.queue_level) === selectedQueue);
    queueBody.innerHTML = visible.length
      ? visible
          .map(
            (row) => `<tr>
          <td><b>${escapeHtml(row.nama_usaha)}</b><small>Daftar ${formatDate(row.waktu_daftar)}</small></td>
          <td>${escapeHtml(row.nama_pemilik)}</td>
          <td><span class="queue-badge q${Number(row.queue_level)}">Q${Number(row.queue_level)}</span></td>
          <td><span class="status-chip ${statusClass(row.status_pendaftaran)}">${escapeHtml(row.status_pendaftaran)}</span></td>
        </tr>`,
          )
          .join("")
      : '<tr><td colspan="4" class="table-message">Tidak ada pendaftar pada antrean ini.</td></tr>';
    byId("queue-foot").textContent =
      `${visible.length} pendaftar ditampilkan · antrean MLQ diurutkan berdasarkan prioritas dan waktu daftar`;
  }

  function renderStalls(mapData) {
    const summary = mapData.ringkasan || { kosong: 0, dipesan: 0, terisi: 0 };
    const stalls = mapData.lapak || [];
    const total = stalls.length;
    const occupied = Number(summary.terisi || 0) + Number(summary.dipesan || 0);
    byId("metric-empty").textContent = Number(summary.kosong || 0);
    byId("metric-occupancy").textContent =
      `${total ? Math.round((occupied / total) * 100) : 0}%`;
    byId("stall-empty").textContent = Number(summary.kosong || 0);
    byId("stall-reserved").textContent = Number(summary.dipesan || 0);
    byId("stall-occupied").textContent = Number(summary.terisi || 0);
    const map = byId("stall-map");
    map.innerHTML = stalls.length
      ? stalls
          .map((stall) => {
            const state =
              stall.status === "Kosong"
                ? "empty"
                : stall.status === "Dipesan"
                  ? "reserved"
                  : "occupied";
            const label = `${stall.kode_lapak}: ${stall.status}${stall.penyewa ? `, ${stall.penyewa}` : ""}`;
            return `<div class="stall-tile stall-${state}" title="${escapeHtml(label)}" aria-label="${escapeHtml(label)}"><b>${escapeHtml(stall.kode_lapak)}</b><small>${escapeHtml(stall.status)}</small></div>`;
          })
          .join("")
      : '<p class="empty-map">Belum ada data lapak.</p>';
  }

  function renderActivity(rows) {
    byId("metric-violations").textContent = rows.length;
    activityBody.innerHTML = rows.length
      ? rows
          .slice(0, 8)
          .map(
            (row) => `<tr>
          <td>${formatDate(row.waktu_kejadian)}</td>
          <td><b>${escapeHtml(row.nama_usaha)}</b><small>ID UMKM ${escapeHtml(row.umkm_id)}</small></td>
          <td><span class="violation-chip ${row.jenis_pelanggaran === "Timeout" ? "timeout-chip" : "preemption-chip"}">${escapeHtml(row.jenis_pelanggaran)}</span></td>
          <td class="activity-note">${escapeHtml(row.keterangan || "Tidak ada catatan")}</td>
        </tr>`,
          )
          .join("")
      : '<tr><td colspan="4" class="table-message">Belum ada catatan pelanggaran.</td></tr>';
  }

  async function loadDashboard() {
    byId("refresh-button").disabled = true;
    byId("activity-refresh").disabled = true;
    try {
      const responses = await Promise.all([
        fetch("/antrean"),
        fetch("/peta"),
        fetch("/alokasi/log"),
        fetch("/admin/ringkasan"),
      ]);
      const failed = responses.find((response) => !response.ok);
      if (failed)
        throw new Error(`Server mengembalikan status ${failed.status}`);
      const [queues, mapData, activities, summary] = await Promise.all(
        responses.map((response) => response.json()),
      );
      queueRows = [1, 2, 3].flatMap((level) => queues[`queue_${level}`] || []);
      byId("metric-applicants").textContent = summary.total;
      byId("metric-queue").textContent = summary.status?.Menunggu || 0;
      ["all", "1", "2", "3"].forEach((level) => {
        const count =
          level === "all"
            ? queueRows.length
            : queueRows.filter((row) => String(row.queue_level) === level)
                .length;
        byId(level === "all" ? "tab-all" : `tab-q${level}`).textContent = count;
      });
      renderQueue();
      renderStalls(mapData);
      renderActivity(activities);
      byId("last-updated").textContent =
        `Disinkronkan ${new Intl.DateTimeFormat("id-ID", { hour: "2-digit", minute: "2-digit" }).format(new Date())}`;
      setNotice("");
    } catch (error) {
      setNotice(
        `Data dashboard gagal dimuat: ${error.message}. Pastikan API SI-TAKAR berjalan.`,
        "error",
      );
      queueBody.innerHTML =
        '<tr><td colspan="4" class="table-message">Data antrean tidak dapat dimuat.</td></tr>';
      activityBody.innerHTML =
        '<tr><td colspan="4" class="table-message">Data aktivitas tidak dapat dimuat.</td></tr>';
    } finally {
      byId("refresh-button").disabled = false;
      byId("activity-refresh").disabled = false;
    }
  }

  document.querySelectorAll("[data-queue-filter]").forEach((button) => {
    button.addEventListener("click", () => {
      selectedQueue = button.dataset.queueFilter;
      document.querySelectorAll("[data-queue-filter]").forEach((tab) => {
        const active = tab === button;
        tab.classList.toggle("active", active);
        tab.setAttribute("aria-pressed", String(active));
      });
      renderQueue();
    });
  });

  byId("refresh-button").addEventListener("click", loadDashboard);
  byId("activity-refresh").addEventListener("click", loadDashboard);
  const logoutButton = byId("logout-button");
  if (logoutButton) {
    logoutButton.addEventListener("click", async () => {
      await fetch("/admin/logout", { method: "POST" });
      window.location.assign("/admin/login");
    });
  }
  byId("deadlock-button").addEventListener("click", async () => {
    const button = byId("deadlock-button");
    button.disabled = true;
    button.innerHTML = "<span>↻</span> Memeriksa...";
    try {
      const response = await fetch("/alokasi/jalankan-deadlock", {
        method: "POST",
      });
      if (!response.ok)
        throw new Error(`Server mengembalikan status ${response.status}`);
      const result = await response.json();
      const count =
        (result.timeout || []).length + (result.preemption || []).length;
      setNotice(
        count
          ? `Pemeriksaan selesai. ${count} pelanggaran diproses.`
          : "Pemeriksaan selesai. Tidak ada timeout atau preemption baru.",
        "success",
      );
      await loadDashboard();
    } catch (error) {
      setNotice(`Pemeriksaan gagal: ${error.message}.`, "error");
    } finally {
      button.disabled = false;
      button.innerHTML = "<span>↻</span> Jalankan pemeriksaan";
    }
  });

  loadDashboard();
})();
