(() => {
  const form = document.getElementById("setup-password-form");
  const tokenEl = document.getElementById("setup-token");
  const emailEl = document.getElementById("setup-email");
  const tempEl = document.getElementById("setup-temp-password");
  const newEl = document.getElementById("setup-new-password");
  const confirmEl = document.getElementById("setup-confirm-password");
  const statusEl = document.getElementById("setup-status");
  const accountLabel = document.getElementById("setup-account-label");
  const saveBtn = document.getElementById("btn-setup-save");

  function setStatus(message, kind) {
    if (!statusEl) return;
    statusEl.textContent = message || "";
    statusEl.classList.remove("ok", "err");
    if (kind) statusEl.classList.add(kind);
  }

  function detailMessage(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
    }
    return fallback;
  }

  function bindPasswordToggles() {
    document.querySelectorAll("[data-toggle-password]").forEach((btn) => {
      btn.addEventListener("click", () => {
        const id = btn.getAttribute("data-toggle-password");
        const input = id ? document.getElementById(id) : null;
        if (!input) return;
        const show = input.type === "password";
        input.type = show ? "text" : "password";
        const eye = btn.querySelector(".ico-eye");
        const eyeOff = btn.querySelector(".ico-eye-off");
        if (eye) eye.hidden = show;
        if (eyeOff) eyeOff.hidden = !show;
        btn.setAttribute(
          "aria-label",
          show ? "Sembunyikan password" : "Tampilkan password"
        );
      });
    });
  }

  async function loadAccount() {
    const token = (tokenEl?.value || "").trim();
    if (!token) {
      setStatus("Tautan tidak lengkap. Buka ulang dari email welcome.", "err");
      if (saveBtn) saveBtn.disabled = true;
      if (accountLabel) accountLabel.textContent = "Tautan tidak valid";
      return;
    }
    try {
      const res = await fetch(
        `/api/auth/setup-password?token=${encodeURIComponent(token)}`,
        { credentials: "same-origin", cache: "no-store" }
      );
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Tautan tidak valid"));
      if (emailEl) emailEl.value = data.email || "";
      if (accountLabel) {
        accountLabel.textContent = data.name
          ? `${data.name} · ${data.email || ""}`
          : data.email || "Akun siap diatur";
      }
      setStatus("");
      tempEl?.focus();
    } catch (err) {
      setStatus(err.message || "Tautan tidak valid", "err");
      if (saveBtn) saveBtn.disabled = true;
      if (accountLabel) accountLabel.textContent = "Tautan tidak valid / kedaluwarsa";
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = (tokenEl?.value || "").trim();
    const temporaryPassword = tempEl?.value || "";
    const newPassword = newEl?.value || "";
    const confirmPassword = confirmEl?.value || "";

    if (!token) {
      setStatus("Tautan tidak lengkap.", "err");
      return;
    }
    if (!temporaryPassword) {
      setStatus("Masukkan password sementara dari email.", "err");
      return;
    }
    if (newPassword.length < 8) {
      setStatus("Password baru minimal 8 karakter.", "err");
      return;
    }
    if (newPassword !== confirmPassword) {
      setStatus("Konfirmasi password baru tidak cocok.", "err");
      return;
    }
    if (newPassword === temporaryPassword) {
      setStatus("Password baru harus berbeda dari password sementara.", "err");
      return;
    }

    if (saveBtn) saveBtn.disabled = true;
    setStatus("Menyimpan password…");
    try {
      const res = await fetch("/api/auth/setup-password", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          token,
          temporary_password: temporaryPassword,
          new_password: newPassword,
          confirm_password: confirmPassword,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal menyimpan password"));
      setStatus(data.message || "Password tersimpan. Mengalihkan ke login…", "ok");
      const email = encodeURIComponent(data.email || emailEl?.value || "");
      window.setTimeout(() => {
        window.location.href = `/login?setup=ok${email ? `&email=${email}` : ""}`;
      }, 700);
    } catch (err) {
      setStatus(err.message || "Gagal menyimpan password", "err");
      if (saveBtn) saveBtn.disabled = false;
    }
  });

  bindPasswordToggles();
  loadAccount();
})();
