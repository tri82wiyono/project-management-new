(() => {
  const $ = (id) => document.getElementById(id);

  const tabs = Array.from(document.querySelectorAll(".settings-tab"));
  const panels = {
    identity: $("panel-identity"),
    security: $("panel-security"),
    menu: $("panel-menu"),
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

  // —— Menu Sidebar order ——
  const navOrderList = $("nav-order-list");
  const navOrderStatus = $("nav-order-status");
  const navOrderReset = $("btn-nav-order-reset");

  function navOrderStorageKey() {
    const uid = document.body?.dataset?.userId;
    return uid ? `pm_nav_order_${uid}` : "pm_nav_order";
  }

  function readNavOrder() {
    try {
      const raw = localStorage.getItem(navOrderStorageKey());
      const order = raw ? JSON.parse(raw) : null;
      return Array.isArray(order) ? order.filter((k) => typeof k === "string") : [];
    } catch {
      return [];
    }
  }

  function writeNavOrder(keys) {
    try {
      localStorage.setItem(navOrderStorageKey(), JSON.stringify(keys));
    } catch {
      /* ignore */
    }
  }

  function currentNavKeys() {
    return [...(navOrderList?.querySelectorAll(".nav-order-item[data-nav-key]") || [])].map(
      (el) => el.dataset.navKey
    );
  }

  function applyOrderToList(order) {
    if (!navOrderList || !order.length) return;
    const map = new Map(
      [...navOrderList.querySelectorAll(".nav-order-item[data-nav-key]")].map((el) => [
        el.dataset.navKey,
        el,
      ])
    );
    order.forEach((key) => {
      const el = map.get(key);
      if (el) navOrderList.appendChild(el);
    });
  }

  function applyOrderToSidebar(order) {
    const nav = document.getElementById("sidebar-nav");
    if (!nav || !order.length) return;
    const map = new Map(
      [...nav.querySelectorAll(".nav-item[data-section]")].map((el) => [
        el.getAttribute("data-section"),
        el,
      ])
    );
    order.forEach((key) => {
      const el = map.get(key);
      if (el) nav.appendChild(el);
    });
  }

  function persistNavOrder(message) {
    const keys = currentNavKeys();
    writeNavOrder(keys);
    applyOrderToSidebar(keys);
    setStatus(navOrderStatus, message || "Urutan menu disimpan.", "ok");
  }

  function moveNavItem(item, direction) {
    if (!navOrderList || !item) return;
    if (direction === "up" && item.previousElementSibling) {
      navOrderList.insertBefore(item, item.previousElementSibling);
      persistNavOrder("Urutan diperbarui.");
    } else if (direction === "down" && item.nextElementSibling) {
      navOrderList.insertBefore(item.nextElementSibling, item);
      persistNavOrder("Urutan diperbarui.");
    }
  }

  if (navOrderList) {
    const saved = readNavOrder();
    if (saved.length) applyOrderToList(saved);

    let dragEl = null;

    navOrderList.addEventListener("dragstart", (event) => {
      const item = event.target.closest(".nav-order-item");
      if (!item) return;
      dragEl = item;
      item.classList.add("is-dragging");
      event.dataTransfer.effectAllowed = "move";
      try {
        event.dataTransfer.setData("text/plain", item.dataset.navKey || "");
      } catch {
        /* ignore */
      }
    });

    navOrderList.addEventListener("dragend", () => {
      dragEl?.classList.remove("is-dragging");
      navOrderList.querySelectorAll(".nav-order-item.is-over").forEach((el) => {
        el.classList.remove("is-over");
      });
      dragEl = null;
    });

    navOrderList.addEventListener("dragover", (event) => {
      event.preventDefault();
      const over = event.target.closest(".nav-order-item");
      if (!over || !dragEl || over === dragEl) return;
      const rect = over.getBoundingClientRect();
      const before = event.clientY < rect.top + rect.height / 2;
      navOrderList.insertBefore(dragEl, before ? over : over.nextSibling);
      navOrderList.querySelectorAll(".nav-order-item.is-over").forEach((el) => {
        el.classList.remove("is-over");
      });
      over.classList.add("is-over");
    });

    navOrderList.addEventListener("drop", (event) => {
      event.preventDefault();
      persistNavOrder("Urutan diperbarui.");
    });

    navOrderList.addEventListener("click", (event) => {
      const btn = event.target.closest("[data-nav-move]");
      if (!btn) return;
      const item = btn.closest(".nav-order-item");
      moveNavItem(item, btn.getAttribute("data-nav-move"));
    });

    navOrderReset?.addEventListener("click", () => {
      const items = [...navOrderList.querySelectorAll(".nav-order-item")].sort(
        (a, b) => Number(a.dataset.defaultIndex) - Number(b.dataset.defaultIndex)
      );
      items.forEach((el) => navOrderList.appendChild(el));
      try {
        localStorage.removeItem(navOrderStorageKey());
      } catch {
        /* ignore */
      }
      applyOrderToSidebar(items.map((el) => el.dataset.navKey));
      setStatus(navOrderStatus, "Urutan dikembalikan ke default.", "ok");
    });
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

  // —— SMTP multi-profile ——
  const providerEl = $("smtp-provider");
  const activateEl = $("smtp-activate");
  const activeBadgeEl = $("smtp-active-badge");
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
  const activateBtn = $("btn-activate-smtp");
  const testBtn = $("btn-test-smtp");

  let passwordTouched = false;
  let smtpState = { active_provider: null, profiles: [] };
  let selectedProvider = "zimbra";

  function profileByProvider(provider) {
    return (smtpState.profiles || []).find((p) => p.provider === provider) || null;
  }

  function updateActiveBadge() {
    const active = smtpState.active_provider;
    const label = active === "gmail" ? "Gmail" : active === "zimbra" ? "Zimbra" : "—";
    if (activeBadgeEl) {
      activeBadgeEl.textContent = `Provider aktif: ${label}`;
    }
  }

  function fillSmtpProfile(data) {
    if (!data) return;
    enabledEl.checked = Boolean(data.enabled);
    hostEl.value = data.host || "";
    portEl.value = data.port || 587;
    encryptionEl.value = data.encryption || "starttls";
    usernameEl.value = data.username || "";
    passwordEl.value = "";
    passwordTouched = false;
    fromEmailEl.value = data.from_email || "";
    fromNameEl.value = data.from_name || "";
    activateEl.checked = Boolean(data.is_active);

    const isGmail = data.provider === "gmail";
    passwordHintEl.textContent = data.password_set
      ? isGmail
        ? "App Password Gmail tersimpan. Isi ulang hanya jika ingin mengganti."
        : "Password tersimpan. Ubah field ini hanya jika ingin mengganti/menghapus password."
      : isGmail
        ? "Untuk Gmail: pakai App Password (bukan password login biasa)."
        : "Password saat ini kosong (sesuai akun Zimbra).";

    hostEl.placeholder = isGmail ? "smtp.gmail.com" : "mail.banksumut.co.id";
    usernameEl.placeholder = isGmail ? "tri82.wiyono@gmail.com" : "notification@banksumut.co.id";
    fromEmailEl.placeholder = usernameEl.placeholder;
  }

  function normalizeSmtpPayload(data) {
    const raw = data && typeof data === "object" ? data : {};
    let profiles = Array.isArray(raw.profiles) ? raw.profiles : [];

    // Kompatibilitas respons lama (satu objek SMTP tanpa profiles)
    if (!profiles.length && (raw.host || raw.provider)) {
      profiles = [
        {
          provider: raw.provider || "zimbra",
          label: raw.label || (raw.provider === "gmail" ? "Gmail" : "Zimbra"),
          is_active: raw.is_active !== false,
          enabled: raw.enabled !== false,
          host: raw.host || "",
          port: raw.port || 587,
          encryption: raw.encryption || "starttls",
          username: raw.username || "",
          password_set: Boolean(raw.password_set),
          from_email: raw.from_email || "",
          from_name: raw.from_name || "",
        },
      ];
    }

    return {
      active_provider:
        raw.active_provider ||
        profiles.find((p) => p && p.is_active)?.provider ||
        profiles[0]?.provider ||
        null,
      profiles,
    };
  }

  function applySmtpPayload(data) {
    smtpState = normalizeSmtpPayload(data);
    updateActiveBadge();
    const preferred =
      profileByProvider(selectedProvider) ||
      profileByProvider(smtpState.active_provider) ||
      (smtpState.profiles && smtpState.profiles[0]) ||
      null;
    if (preferred) {
      selectedProvider = preferred.provider || "zimbra";
      providerEl.value = selectedProvider;
      fillSmtpProfile(preferred);
    }
  }

  passwordEl.addEventListener("input", () => {
    passwordTouched = true;
  });

  providerEl.addEventListener("change", () => {
    selectedProvider = providerEl.value;
    fillSmtpProfile(profileByProvider(selectedProvider));
    setStatus(saveStatusEl, "");
  });

  async function loadSmtp() {
    setStatus(saveStatusEl, "Memuat konfigurasi…");
    try {
      const res = await fetch("/api/settings/smtp");
      if (!res.ok) throw new Error(await res.text());
      applySmtpPayload(await res.json());
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
      provider: providerEl.value,
      enabled: enabledEl.checked,
      host: hostEl.value.trim(),
      port: Number(portEl.value) || 587,
      encryption: encryptionEl.value,
      username: usernameEl.value.trim(),
      from_email: fromEmailEl.value.trim(),
      from_name: fromNameEl.value.trim() || "Project Management System",
      activate: Boolean(activateEl.checked),
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
      selectedProvider = payload.provider;
      applySmtpPayload(data);
      setStatus(
        saveStatusEl,
        payload.activate
          ? `Profil ${payload.provider === "gmail" ? "Gmail" : "Zimbra"} tersimpan dan dijadikan aktif.`
          : `Profil ${payload.provider === "gmail" ? "Gmail" : "Zimbra"} tersimpan (profil lain tidak diubah).`,
        "ok"
      );
    } catch (err) {
      setStatus(saveStatusEl, err.message || "Gagal menyimpan", "err");
    } finally {
      saveBtn.disabled = false;
    }
  });

  activateBtn.addEventListener("click", async () => {
    activateBtn.disabled = true;
    setStatus(saveStatusEl, "Mengaktifkan profil…");
    try {
      const res = await fetch("/api/settings/smtp/activate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ provider: providerEl.value }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal mengaktifkan profil");
      selectedProvider = providerEl.value;
      applySmtpPayload(data);
      setStatus(
        saveStatusEl,
        `Provider aktif sekarang: ${providerEl.value === "gmail" ? "Gmail" : "Zimbra"}.`,
        "ok"
      );
    } catch (err) {
      setStatus(saveStatusEl, err.message || "Gagal mengaktifkan", "err");
    } finally {
      activateBtn.disabled = false;
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

  // —— Security ——
  const securityForm = $("security-form");
  const securitySaveBtn = $("btn-save-security");
  const securityStatus = $("security-save-status");
  const securityFields = {
    max_failed_logins: $("security-max-failed"),
    lockout_minutes: $("security-lockout"),
    session_timeout_minutes: $("security-session-timeout"),
  };

  function fillSecurity(data) {
    Object.entries(securityFields).forEach(([key, el]) => {
      if (!el) return;
      if (data[key] != null) el.value = data[key];
    });
  }

  async function loadSecurity() {
    if (!securityForm) return;
    setStatus(securityStatus, "Memuat keamanan…");
    try {
      const res = await fetch("/api/settings/security");
      if (!res.ok) throw new Error(await res.text());
      fillSecurity(await res.json());
      setStatus(securityStatus, "");
    } catch (err) {
      setStatus(securityStatus, err.message || "Gagal memuat keamanan", "err");
    }
  }

  securityForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    securitySaveBtn.disabled = true;
    setStatus(securityStatus, "Menyimpan…");
    const payload = {
      max_failed_logins: Number(securityFields.max_failed_logins.value) || 6,
      lockout_minutes: Number(securityFields.lockout_minutes.value) || 30,
      session_timeout_minutes: Number(securityFields.session_timeout_minutes.value) || 480,
    };
    try {
      const res = await fetch("/api/settings/security", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(payload),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(data.detail || "Gagal menyimpan keamanan");
      fillSecurity(data);
      setStatus(
        securityStatus,
        "Pengaturan keamanan tersimpan. Timeout sesi berlaku untuk login berikutnya / sisa sesi aktif.",
        "ok"
      );
    } catch (err) {
      setStatus(securityStatus, err.message || "Gagal menyimpan", "err");
    } finally {
      securitySaveBtn.disabled = false;
    }
  });

  loadIdentity();
  loadSecurity();
  loadSmtp();
})();
