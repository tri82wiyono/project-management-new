(() => {
  function setStatus(el, message, kind) {
    if (!el) return;
    el.textContent = message || "";
    el.classList.remove("ok", "err");
    if (kind) el.classList.add(kind);
  }

  function detailMessage(data, fallback) {
    const detail = data?.detail;
    if (typeof detail === "string") return detail;
    if (Array.isArray(detail)) {
      return detail.map((d) => d.msg || JSON.stringify(d)).join(", ");
    }
    return fallback;
  }

  // Profile: name + photo
  const profileForm = document.getElementById("profile-form");
  const profileStatus = document.getElementById("profile-status");
  const profileBtn = document.getElementById("btn-save-profile");
  const nameInput = document.getElementById("profile-name");
  const photoInput = document.getElementById("profile-photo");
  const preview = document.getElementById("profile-avatar-preview");

  photoInput?.addEventListener("change", () => {
    const file = photoInput.files?.[0];
    if (!file || !preview) return;
    if (file.size > 2 * 1024 * 1024) {
      setStatus(profileStatus, "Ukuran foto maksimal 2 MB.", "err");
      photoInput.value = "";
      return;
    }
    preview.src = URL.createObjectURL(file);
  });

  profileForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = (nameInput?.value || "").trim();
    if (name.length < 2) {
      setStatus(profileStatus, "Nama minimal 2 karakter.", "err");
      return;
    }

    const body = new FormData();
    body.append("name", name);
    const file = photoInput?.files?.[0];
    if (file) body.append("photo", file);

    profileBtn.disabled = true;
    setStatus(profileStatus, "Menyimpan…");
    try {
      const res = await fetch("/api/auth/profile", {
        method: "PATCH",
        body,
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal menyimpan profil"));

      if (data.user?.avatar_url && preview) preview.src = data.user.avatar_url;
      if (data.user?.name) {
        document.querySelectorAll(".user-menu-head strong").forEach((el) => {
          el.textContent = data.user.name;
        });
        document.querySelectorAll(".user-menu .avatar, .user-menu-head img").forEach((img) => {
          if (data.user.avatar_url) img.src = data.user.avatar_url;
        });
      }
      if (photoInput) photoInput.value = "";
      setStatus(profileStatus, data.message || "Profil berhasil diperbarui.", "ok");
    } catch (err) {
      setStatus(profileStatus, err.message || "Gagal menyimpan profil", "err");
    } finally {
      profileBtn.disabled = false;
    }
  });

  // Password (Keamanan page only)
  const form = document.getElementById("change-password-form");
  const statusEl = document.getElementById("password-status");
  const btn = document.getElementById("btn-change-password");

  form?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const currentPassword = document.getElementById("current-password").value;
    const newPassword = document.getElementById("new-password").value;
    const confirmPassword = document.getElementById("confirm-password").value;

    if (!currentPassword || !newPassword) {
      setStatus(statusEl, "Lengkapi semua field.", "err");
      return;
    }
    if (newPassword.length < 8) {
      setStatus(statusEl, "Password baru minimal 8 karakter.", "err");
      return;
    }
    if (newPassword !== confirmPassword) {
      setStatus(statusEl, "Konfirmasi password tidak cocok.", "err");
      return;
    }

    btn.disabled = true;
    setStatus(statusEl, "Menyimpan…");
    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          current_password: currentPassword,
          new_password: newPassword,
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal mengubah password"));
      form.reset();
      setStatus(statusEl, data.message || "Password berhasil diubah.", "ok");
    } catch (err) {
      setStatus(statusEl, err.message || "Gagal mengubah password", "err");
    } finally {
      btn.disabled = false;
    }
  });

  // MFA (Keamanan page only)
  const securityPage = document.getElementById("account-security-page");
  if (!securityPage) return;

  const mfaIdle = document.getElementById("mfa-idle");
  const mfaSetup = document.getElementById("mfa-setup");
  const mfaActive = document.getElementById("mfa-active");
  const mfaBadge = document.getElementById("mfa-badge");
  const mfaStatus = document.getElementById("mfa-status");
  const mfaSetupStatus = document.getElementById("mfa-setup-status");
  const mfaActiveStatus = document.getElementById("mfa-active-status");
  const mfaQr = document.getElementById("mfa-qr");
  const mfaSecret = document.getElementById("mfa-secret");
  const mfaEnableCode = document.getElementById("mfa-enable-code");
  const mfaBackupRemaining = document.getElementById("mfa-backup-remaining");
  const backupDialog = document.getElementById("mfa-backup-dialog");
  const backupList = document.getElementById("mfa-backup-list");
  const backupCopyStatus = document.getElementById("mfa-backup-copy-status");
  const confirmDialog = document.getElementById("mfa-confirm-dialog");
  const confirmTitle = document.getElementById("mfa-confirm-title");
  const confirmDesc = document.getElementById("mfa-confirm-desc");
  const confirmPassword = document.getElementById("mfa-confirm-password");
  const confirmCode = document.getElementById("mfa-confirm-code");
  const confirmStatus = document.getElementById("mfa-confirm-status");
  const confirmSubmit = document.getElementById("btn-mfa-confirm-submit");

  let confirmMode = null;
  let lastBackupCodes = [];

  function setMfaEnabledUI(enabled, remaining) {
    securityPage.dataset.mfaEnabled = enabled ? "true" : "false";
    securityPage.dataset.mfaBackupRemaining = String(remaining || 0);
    if (mfaBadge) {
      mfaBadge.textContent = enabled ? "Aktif" : "Nonaktif";
      mfaBadge.classList.toggle("is-on", enabled);
      mfaBadge.classList.toggle("is-off", !enabled);
    }
    if (mfaIdle) mfaIdle.hidden = enabled;
    if (mfaSetup) mfaSetup.hidden = true;
    if (mfaActive) mfaActive.hidden = !enabled;
    if (mfaBackupRemaining) mfaBackupRemaining.textContent = String(remaining || 0);
  }

  function showBackupCodes(codes) {
    lastBackupCodes = codes || [];
    if (!backupList) return;
    backupList.innerHTML = lastBackupCodes.map((code) => `<li>${code}</li>`).join("");
    setStatus(backupCopyStatus, "");
    backupDialog?.showModal();
  }

  document.getElementById("btn-copy-backup")?.addEventListener("click", async () => {
    try {
      await navigator.clipboard.writeText(lastBackupCodes.join("\n"));
      setStatus(backupCopyStatus, "Backup code disalin.", "ok");
    } catch {
      setStatus(backupCopyStatus, "Gagal menyalin. Salin manual dari daftar.", "err");
    }
  });

  document.getElementById("btn-mfa-start")?.addEventListener("click", async () => {
    setStatus(mfaStatus, "Menyiapkan MFA…");
    try {
      const res = await fetch("/api/auth/mfa/setup", { method: "POST" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal memulai setup MFA"));
      if (mfaQr) mfaQr.innerHTML = data.qr_svg || "";
      if (mfaSecret) mfaSecret.textContent = data.secret_display || data.secret || "";
      if (mfaEnableCode) mfaEnableCode.value = "";
      if (mfaIdle) mfaIdle.hidden = true;
      if (mfaSetup) mfaSetup.hidden = false;
      setStatus(mfaStatus, "");
      setStatus(mfaSetupStatus, "Scan QR lalu masukkan kode 6 digit.");
    } catch (err) {
      setStatus(mfaStatus, err.message || "Gagal memulai setup MFA", "err");
    }
  });

  document.getElementById("btn-mfa-cancel")?.addEventListener("click", () => {
    if (mfaSetup) mfaSetup.hidden = true;
    if (mfaIdle) mfaIdle.hidden = false;
    setStatus(mfaSetupStatus, "");
  });

  document.getElementById("btn-mfa-confirm")?.addEventListener("click", async () => {
    const code = (mfaEnableCode?.value || "").trim();
    if (!code) {
      setStatus(mfaSetupStatus, "Masukkan kode dari aplikasi autentikator.", "err");
      return;
    }
    setStatus(mfaSetupStatus, "Mengaktifkan…");
    try {
      const res = await fetch("/api/auth/mfa/enable", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal mengaktifkan MFA"));
      setMfaEnabledUI(true, data.backup_codes_remaining || data.backup_codes?.length || 0);
      setStatus(mfaActiveStatus, data.message || "MFA aktif.", "ok");
      showBackupCodes(data.backup_codes || []);
    } catch (err) {
      setStatus(mfaSetupStatus, err.message || "Gagal mengaktifkan MFA", "err");
    }
  });

  function openConfirm(mode, title, desc) {
    confirmMode = mode;
    if (confirmTitle) confirmTitle.textContent = title;
    if (confirmDesc) confirmDesc.textContent = desc;
    if (confirmPassword) confirmPassword.value = "";
    if (confirmCode) confirmCode.value = "";
    setStatus(confirmStatus, "");
    confirmDialog?.showModal();
  }

  document.getElementById("btn-mfa-disable")?.addEventListener("click", () => {
    openConfirm(
      "disable",
      "Nonaktifkan MFA",
      "Masukkan password dan kode MFA (atau backup code) untuk menonaktifkan."
    );
  });

  document.getElementById("btn-mfa-regen")?.addEventListener("click", () => {
    openConfirm(
      "regen",
      "Buat ulang backup code",
      "Backup code lama akan diganti. Masukkan password dan kode MFA saat ini."
    );
  });

  confirmSubmit?.addEventListener("click", async () => {
    const password = (confirmPassword?.value || "").trim();
    const code = (confirmCode?.value || "").trim();
    if (!password || !code) {
      setStatus(confirmStatus, "Lengkapi password dan kode.", "err");
      return;
    }

    confirmSubmit.disabled = true;
    setStatus(confirmStatus, "Memproses…");
    try {
      if (confirmMode === "disable") {
        const res = await fetch("/api/auth/mfa/disable", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password, code }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(detailMessage(data, "Gagal menonaktifkan MFA"));
        setMfaEnabledUI(false, 0);
        setStatus(mfaStatus, data.message || "MFA dinonaktifkan.", "ok");
        confirmDialog?.close();
      } else if (confirmMode === "regen") {
        const res = await fetch("/api/auth/mfa/regenerate-backup-codes", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ password, code }),
        });
        const data = await res.json().catch(() => ({}));
        if (!res.ok) throw new Error(detailMessage(data, "Gagal membuat backup code"));
        if (mfaBackupRemaining) {
          mfaBackupRemaining.textContent = String(
            data.backup_codes_remaining || data.backup_codes?.length || 0
          );
        }
        setStatus(mfaActiveStatus, data.message || "Backup code diperbarui.", "ok");
        confirmDialog?.close();
        showBackupCodes(data.backup_codes || []);
      }
    } catch (err) {
      setStatus(confirmStatus, err.message || "Gagal memproses", "err");
    } finally {
      confirmSubmit.disabled = false;
    }
  });

  // Trusted devices
  const deviceList = document.getElementById("trusted-device-list");
  const devicesStatus = document.getElementById("devices-status");

  function formatDeviceTime(value) {
    if (!value) return "-";
    try {
      return new Date(value).toLocaleString("id-ID", {
        day: "2-digit",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });
    } catch {
      return value;
    }
  }

  async function loadTrustedDevices() {
    if (!deviceList) return;
    setStatus(devicesStatus, "");
    try {
      const res = await fetch("/api/auth/devices");
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal memuat perangkat"));
      const items = data.items || [];
      if (!items.length) {
        deviceList.innerHTML =
          `<p class="account-mfa-note">Belum ada perangkat tepercaya.</p>`;
        return;
      }
      deviceList.innerHTML = items
        .map(
          (item) => `
          <div class="account-device-item" data-device-id="${item.id}">
            <div class="account-device-meta">
              <strong>
                ${item.label || "Browser"}
                ${item.is_current ? '<span class="account-device-current">Saat ini</span>' : ""}
              </strong>
              <span>${item.browser || "-"} · ${item.os || "-"} · IP ${item.ip_address || "-"}</span>
              <span>Terakhir aktif: ${formatDeviceTime(item.last_seen_at)}</span>
            </div>
            <button type="button" class="btn btn-ghost account-device-revoke" data-revoke-device="${item.id}">
              Cabut
            </button>
          </div>`
        )
        .join("");
    } catch (err) {
      deviceList.innerHTML = "";
      setStatus(devicesStatus, err.message || "Gagal memuat perangkat", "err");
    }
  }

  deviceList?.addEventListener("click", async (event) => {
    const btn = event.target.closest("[data-revoke-device]");
    if (!btn) return;
    const id = btn.getAttribute("data-revoke-device");
    if (!id) return;
    const ok = window.pmConfirm
      ? await window.pmConfirm({
          title: "Cabut kepercayaan perangkat?",
          message:
            "Login berikutnya dari perangkat ini akan meminta konfirmasi email lagi.",
          tone: "danger",
          icon: "!",
          okText: "Cabut",
          cancelText: "Batal",
        })
      : window.confirm(
          "Cabut kepercayaan perangkat ini? Login berikutnya dari perangkat itu akan meminta konfirmasi email."
        );
    if (!ok) return;
    btn.disabled = true;
    try {
      const res = await fetch(`/api/auth/devices/${id}`, { method: "DELETE" });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal mencabut perangkat"));
      setStatus(devicesStatus, data.message || "Perangkat dicabut.", "ok");
      await loadTrustedDevices();
    } catch (err) {
      setStatus(devicesStatus, err.message || "Gagal mencabut perangkat", "err");
      btn.disabled = false;
    }
  });

  loadTrustedDevices();
})();
