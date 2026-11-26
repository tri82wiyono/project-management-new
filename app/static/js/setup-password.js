(() => {
  const form = document.getElementById("setup-password-form");
  const tokenEl = document.getElementById("setup-token");
  const modeEl = document.getElementById("setup-mode");
  const titleEl = document.getElementById("setup-title");
  const emailEl = document.getElementById("setup-email");
  const tempWrap = document.getElementById("setup-temp-wrap");
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

  function applyMode(mode, projectName) {
    const invite = mode === "invite";
    if (modeEl) modeEl.value = invite ? "invite" : "welcome";
    if (titleEl) titleEl.textContent = invite ? "Gabung Project" : "Atur Password";
    if (tempWrap) tempWrap.hidden = invite;
    if (tempEl) {
      tempEl.required = !invite;
      if (invite) tempEl.value = "";
    }
    if (accountLabel && invite && projectName) {
      accountLabel.textContent = `Undangan project · ${projectName}`;
    }
  }

  async function loadAccount() {
    const token = (tokenEl?.value || "").trim();
    if (!token) {
      setStatus("Tautan tidak lengkap. Buka ulang dari email undangan.", "err");
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
      applyMode(data.mode || "welcome", data.project_name || "");
      if (accountLabel) {
        if (data.mode === "invite" && data.project_name) {
          accountLabel.textContent = `${data.name || data.email} · ${data.project_name}`;
        } else {
          accountLabel.textContent = data.name
            ? `${data.name} · ${data.email || ""}`
            : data.email || "Akun siap diatur";
        }
      }
      setStatus("");
      if (data.mode === "invite") newEl?.focus();
      else tempEl?.focus();
    } catch (err) {
      setStatus(err.message || "Tautan tidak valid", "err");
      if (saveBtn) saveBtn.disabled = true;
      if (accountLabel) accountLabel.textContent = "Tautan tidak valid / kedaluwarsa";
    }
  }

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const token = (tokenEl?.value || "").trim();
    const mode = modeEl?.value || "welcome";
    const temporaryPassword = tempEl?.value || "";
    const newPassword = newEl?.value || "";
    const confirmPassword = confirmEl?.value || "";

    if (!token) {
      setStatus("Tautan tidak lengkap.", "err");
      return;
    }
    if (mode !== "invite" && !temporaryPassword) {
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
    if (mode !== "invite" && newPassword === temporaryPassword) {
      setStatus("Password baru harus berbeda dari password sementara.", "err");
      return;
    }

    if (saveBtn) saveBtn.disabled = true;
    setStatus("Menyimpan password…");
    try {
      const body = {
        token,
        new_password: newPassword,
        confirm_password: confirmPassword,
      };
      if (mode !== "invite") body.temporary_password = temporaryPassword;
      const res = await fetch("/api/auth/setup-password", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal menyimpan password"));
      setStatus(data.message || "Password tersimpan…", "ok");
      const redirect = data.redirect || "/login?setup=ok";
      window.setTimeout(() => {
        window.location.href = redirect;
      }, 700);
    } catch (err) {
      setStatus(err.message || "Gagal menyimpan password", "err");
      if (saveBtn) saveBtn.disabled = false;
    }
  });

  bindPasswordToggles();
  loadAccount();
})();
