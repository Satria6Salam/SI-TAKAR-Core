(() => {
  const form = document.getElementById("admin-login-form");
  const error = document.getElementById("login-error");
  const submit = form.querySelector("button[type='submit']");
  const peek = document.getElementById("peek");
  const password = form.elements.password;

  peek?.addEventListener("click", () => {
    const tampil = password.type === "password";
    password.type = tampil ? "text" : "password";
    peek.textContent = tampil ? "Sembunyikan" : "Lihat";
    peek.setAttribute("aria-pressed", String(tampil));
    password.focus();
  });
  if (form.elements.username.value) password.focus();

  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    error.textContent = "";
    submit.disabled = true;
    submit.textContent = "Memverifikasi...";
    try {
      const response = await fetch("/admin/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          username: form.elements.username.value.trim(),
          password: form.elements.password.value,
        }),
      });
      const result = await response.json();
      if (!response.ok) throw new Error(result.detail || "Login gagal.");
      window.location.assign(result.redirect || "/admin");
    } catch (failure) {
      error.textContent = failure.message || "Server tidak dapat dihubungi.";
    } finally {
      submit.disabled = false;
      submit.innerHTML = "Masuk ke dashboard <span>→</span>";
    }
  });
})();
