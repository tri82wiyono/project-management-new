(() => {
  const $ = (id) => document.getElementById(id);

  const tabs = Array.from(document.querySelectorAll(".settings-tab"));
  const panels = {
    identity: $("panel-identity"),
    email: $("panel-email"),
  };

  function activateTab(key) {
    const valid = panels[key] ? key : "identity";
    tabs.forEach((tab) => {
      const active = tab.dataset.tab === valid;
      tab.classList.toggle("active", active);
      tab.setAttribute("aria-selected", active ? "true" : "false");
    });
    Object.entries(panels).forEach(([name, panel]) => {
      if (!panel) return;
      const active = name === valid;
      panel.classList.toggle("active", active);
      panel.hidden = !active;
    });
    history.replaceState(null, "", `#${valid}`);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => activateTab(tab.dataset.tab));
  });

  const hash = (location.hash || "").replace("#", "");
  activateTab(hash === "roles" ? "identity" : hash || "identity");

  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
  }

  // —— Identity ——
  const identityForm = $("identity-form");
  const identitySaveBtn = $("btn-save-identity");
  const identityStatus = $("identity-save-status");
  const identityFields = {
    app_name: $("identity-app-name"),
    brand_name: $("identity-brand-name"),
    brand_mark: $("identity-brand-mark"),
    brand_tagline: $("identity-brand-tagline"),
    workspace_label: $("identity-workspace-label"),
    workspace_name: $("identity-workspace-name"),
    organization_name: $("identity-organization"),
    support_email: $("identity-support-email"),
    app_url: $("identity-app-url"),
    footer_note: $("identity-footer-note"),
  };

  function fillIdentity(data) {
    Object.entries(identityFields).forEach(([key, el]) => {
      if (el) el.value = data[key] || "";
    });
  }

  async function loadIdentity() {
    setStatus(identityStatus, "Memuat identitas…");
    try {
      const res = await fetch("/api/settings/identity");
      if (!res.ok) throw new Error(await res.text());
      fillIdentity(await res.json());
      setStatus(identityStatus, "");
    } catch (err) {
      setStatus(identityStatus, err.message || "Gagal memuat identitas", "err");
    }
  }

  identityForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    identitySaveBtn.disabled = true;
    setStatus(identityStatus, "Menyimpan…");

    const payload = {};
    Object.entries(identityFields).forEach(([key, el]) => {
      payload[key] = (el.value || "").trim();
    });

    try {
      const res = await fetch("/api/settings/identity", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menyimpan identitas");
      fillIdentity(data);
      setStatus(
        identityStatus,
        "Identitas aplikasi tersimpan. Muat ulang halaman untuk melihat perubahan di sidebar.",
        "ok"
      );
    } catch (err) {
      setStatus(identityStatus, err.message || "Gagal menyimpan", "err");
    } finally {
      identitySaveBtn.disabled = false;
    }
  });

  // —— SMTP ——
  const enabledEl = $("smtp-enabled");
  const hostEl = $("smtp-host");
  const portEl = $("smtp-port");
  const encryptionEl = $("smtp-encryption");
  const usernameEl = $("smtp-username");
  const passwordEl = $("smtp-password");
  const passwordHintEl = $("smtp-password-hint");
  const fromEmailEl = $("smtp-from-email");
  const fromNameEl = $("smtp-from-name");
  const saveStatusEl = $("smtp-save-status");
  const testToEl = $("smtp-test-to");
  const testNameEl = $("smtp-test-name");
  const testTemplateEl = $("smtp-test-template");
  const testStatusEl = $("smtp-test-status");
  const formEl = $("smtp-form");
  const testFormEl = $("smtp-test-form");
  const saveBtn = $("btn-save-smtp");
  const testBtn = $("btn-test-smtp");
  let passwordTouched = false;

  function fillSmtp(data) {
    enabledEl.checked = Boolean(data.enabled);
    hostEl.value = data.host || "";
    portEl.value = data.port || 587;
    encryptionEl.value = data.encryption || "starttls";
    usernameEl.value = data.username || "";
    passwordEl.value = "";
    passwordTouched = false;
    fromEmailEl.value = data.from_email || "";
    fromNameEl.value = data.from_name || "";
    passwordHintEl.textContent = data.password_set
      ? "Password tersimpan. Ubah field ini hanya jika ingin mengganti/menghapus password."
      : "Password saat ini kosong (sesuai akun Zimbra).";
  }

  passwordEl.addEventListener("input", () => {
    passwordTouched = true;
  });

  async function loadSmtp() {
    setStatus(saveStatusEl, "Memuat konfigurasi…");
    try {
      const res = await fetch("/api/settings/smtp");
      if (!res.ok) throw new Error(await res.text());
      fillSmtp(await res.json());
      setStatus(saveStatusEl, "");
    } catch (err) {
      setStatus(saveStatusEl, err.message || "Gagal memuat settings", "err");
    }
  }

  formEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    saveBtn.disabled = true;
    setStatus(saveStatusEl, "Menyimpan…");

    const payload = {
      enabled: enabledEl.checked,
      host: hostEl.value.trim(),
      port: Number(portEl.value) || 587,
      encryption: encryptionEl.value,
      username: usernameEl.value.trim(),
      from_email: fromEmailEl.value.trim(),
      from_name: fromNameEl.value.trim() || "Project Management System",
    };
    if (passwordTouched) {
      payload.password = passwordEl.value;
    }

    try {
      const res = await fetch("/api/settings/smtp", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menyimpan konfigurasi");
      fillSmtp(data);
      setStatus(saveStatusEl, "Konfigurasi SMTP tersimpan.", "ok");
    } catch (err) {
      setStatus(saveStatusEl, err.message || "Gagal menyimpan", "err");
    } finally {
      saveBtn.disabled = false;
    }
  });

  testFormEl.addEventListener("submit", async (event) => {
    event.preventDefault();
    testBtn.disabled = true;
    setStatus(testStatusEl, "Mengirim email uji…");

    try {
      const res = await fetch("/api/settings/smtp/test", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          to_email: testToEl.value.trim(),
          template: testTemplateEl.value,
          name: (testNameEl.value || "").trim() || "Pengguna Uji",
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal mengirim email uji");
      setStatus(testStatusEl, data.message || "Email uji terkirim.", "ok");
    } catch (err) {
      setStatus(testStatusEl, err.message || "Gagal mengirim email uji", "err");
    } finally {
      testBtn.disabled = false;
    }
  });

  loadIdentity();
  loadSmtp();
})();
