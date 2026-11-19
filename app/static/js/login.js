(() => {
  const emailEl = document.getElementById("login-email");
  const passwordEl = document.getElementById("login-password");
  const captchaIdEl = document.getElementById("captcha-id");
  const captchaAnswerEl = document.getElementById("login-captcha");
  const captchaImageEl = document.getElementById("captcha-image");
  const statusEl = document.getElementById("login-status");
  const formEl = document.getElementById("login-form");
  const btnLogin = document.getElementById("btn-login");
  const btnRefresh = document.getElementById("btn-refresh-captcha");
  const btnTogglePassword = document.getElementById("btn-toggle-password");
  const rememberEl = document.getElementById("login-remember");
  const btnForgot = document.getElementById("btn-forgot-password");
  const REMEMBER_KEY = "pm_login_email";

  const mfaForm = document.getElementById("mfa-form");
  const mfaCodeEl = document.getElementById("login-mfa-code");
  const mfaStatusEl = document.getElementById("mfa-login-status");
  const btnMfaLogin = document.getElementById("btn-mfa-login");
  const btnMfaBack = document.getElementById("btn-mfa-back");

  const deviceCard = document.getElementById("device-confirm-card");
  const deviceCopy = document.getElementById("device-confirm-copy");
  const deviceEmail = document.getElementById("device-confirm-email");
  const deviceLabel = document.getElementById("device-confirm-device");
  const deviceStatus = document.getElementById("device-confirm-status");
  const btnDeviceResend = document.getElementById("btn-device-resend");
  const btnDeviceBack = document.getElementById("btn-device-back");

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
      return detail.map((item) => item.msg || JSON.stringify(item)).join(", ");
    }
    return fallback;
  }

  function showStep(step) {
    if (formEl) formEl.hidden = step !== "login";
    if (mfaForm) mfaForm.hidden = step !== "mfa";
    if (deviceCard) deviceCard.hidden = step !== "device";
  }

  function showDeviceStep(data) {
    showStep("device");
    if (deviceCopy) {
      deviceCopy.textContent =
        data.message ||
        "Perangkat tidak dikenal. Login dari perangkat baru memerlukan konfirmasi email.";
    }
    if (deviceEmail) {
      deviceEmail.textContent = data.email_masked
        ? `Email: ${data.email_masked}`
        : "";
    }
    if (deviceLabel) {
      deviceLabel.textContent = data.device_label
        ? `Perangkat: ${data.device_label}`
        : "";
    }
    setStatus(
      deviceStatus,
      data.email_sent === false
        ? data.email_error || "Email gagal dikirim. Coba kirim ulang."
        : "Cek inbox email Anda, lalu klik tautan konfirmasi.",
      data.email_sent === false ? "err" : "ok"
    );
  }

  async function ensureSessionOrThrow() {
    const me = await fetch("/api/auth/me", {
      credentials: "same-origin",
      cache: "no-store",
    });
    if (!me.ok) {
      throw new Error("Login gagal menyimpan sesi. Silakan coba lagi.");
    }
  }

  function safeNextPath(raw) {
    if (!raw || typeof raw !== "string") return "/";
    if (!raw.startsWith("/") || raw.startsWith("//")) return "/";
    // Reject asset probes that AuthGuard may have stuffed into ?next=
    const leaf = raw.split("/").pop() || "";
    if (leaf.includes(".")) return "/";
    return raw;
  }

  async function finishLogin(statusTarget) {
    setStatus(statusTarget, "Berhasil masuk. Memeriksa sesi…", "ok");
    await ensureSessionOrThrow();
    setStatus(statusTarget, "Berhasil masuk. Mengalihkan…", "ok");
    const next = new URLSearchParams(window.location.search).get("next");
    window.location.href = safeNextPath(next);
  }

  async function loadCaptcha() {
    captchaImageEl.innerHTML = "<small>Memuat…</small>";
    captchaAnswerEl.value = "";
    try {
      const res = await fetch("/api/auth/captcha", {
        cache: "no-store",
        credentials: "same-origin",
      });
      if (!res.ok) throw new Error("Gagal memuat captcha");
      const data = await res.json();
      captchaIdEl.value = data.captcha_id || "";
      captchaImageEl.innerHTML = data.image_svg || "";
    } catch (err) {
      captchaImageEl.innerHTML = "";
      setStatus(statusEl, err.message || "Captcha gagal dimuat", "err");
    }
  }

  btnRefresh?.addEventListener("click", () => {
    setStatus(statusEl, "");
    loadCaptcha();
  });

  btnTogglePassword?.addEventListener("click", () => {
    if (!passwordEl) return;
    const show = passwordEl.type === "password";
    passwordEl.type = show ? "text" : "password";
    const eye = btnTogglePassword.querySelector(".ico-eye");
    const eyeOff = btnTogglePassword.querySelector(".ico-eye-off");
    if (eye) eye.hidden = show;
    if (eyeOff) eyeOff.hidden = !show;
    btnTogglePassword.setAttribute(
      "aria-label",
      show ? "Sembunyikan password" : "Tampilkan password"
    );
  });

  btnForgot?.addEventListener("click", () => {
    setStatus(
      statusEl,
      "Reset password dilakukan oleh admin. Hubungi administrator sistem.",
      "err"
    );
  });

  try {
    const saved = localStorage.getItem(REMEMBER_KEY);
    if (saved && emailEl) {
      emailEl.value = saved;
      if (rememberEl) rememberEl.checked = true;
    }
  } catch {
    /* ignore */
  }

  formEl?.addEventListener("submit", async (event) => {
    event.preventDefault();
    btnLogin.disabled = true;
    setStatus(statusEl, "Memverifikasi…");

    try {
      const email = emailEl.value.trim();
      const res = await fetch("/api/auth/login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          email,
          password: passwordEl.value,
          captcha_id: captchaIdEl.value,
          captcha_answer: captchaAnswerEl.value.trim(),
        }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Login gagal"));

      try {
        if (rememberEl?.checked && email) localStorage.setItem(REMEMBER_KEY, email);
        else localStorage.removeItem(REMEMBER_KEY);
      } catch {
        /* ignore */
      }

      if (data.mfa_required) {
        setStatus(statusEl, "");
        showStep("mfa");
        setStatus(mfaStatusEl, "");
        if (mfaCodeEl) {
          mfaCodeEl.value = "";
          mfaCodeEl.focus();
        }
        return;
      }

      if (data.device_confirmation_required) {
        showDeviceStep(data);
        return;
      }

      await finishLogin(statusEl);
    } catch (err) {
      setStatus(statusEl, typeof err.message === "string" ? err.message : "Login gagal", "err");
      await loadCaptcha();
    } finally {
      btnLogin.disabled = false;
    }
  });

  mfaForm?.addEventListener("submit", async (event) => {
    event.preventDefault();
    const code = (mfaCodeEl?.value || "").trim();
    if (!code) {
      setStatus(mfaStatusEl, "Masukkan kode MFA atau backup code.", "err");
      return;
    }

    btnMfaLogin.disabled = true;
    setStatus(mfaStatusEl, "Memverifikasi MFA…");
    try {
      const res = await fetch("/api/auth/mfa/verify-login", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ code }),
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Verifikasi MFA gagal"));

      if (data.device_confirmation_required) {
        showDeviceStep(data);
        return;
      }

      await finishLogin(mfaStatusEl);
    } catch (err) {
      setStatus(mfaStatusEl, err.message || "Verifikasi MFA gagal", "err");
    } finally {
      btnMfaLogin.disabled = false;
    }
  });

  btnMfaBack?.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    } catch {
      /* ignore */
    }
    showStep("login");
    setStatus(statusEl, "");
    await loadCaptcha();
  });

  btnDeviceResend?.addEventListener("click", async () => {
    btnDeviceResend.disabled = true;
    setStatus(deviceStatus, "Mengirim ulang…");
    try {
      const res = await fetch("/api/auth/device/resend", {
        method: "POST",
        credentials: "same-origin",
      });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) throw new Error(detailMessage(data, "Gagal mengirim ulang"));
      setStatus(deviceStatus, data.message || "Email dikirim ulang.", "ok");
    } catch (err) {
      setStatus(deviceStatus, err.message || "Gagal mengirim ulang", "err");
    } finally {
      btnDeviceResend.disabled = false;
    }
  });

  btnDeviceBack?.addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    } catch {
      /* ignore */
    }
    showStep("login");
    setStatus(statusEl, "");
    await loadCaptcha();
  });

  const params = new URLSearchParams(window.location.search);
  const deviceParam = params.get("device");
  if (deviceParam === "confirmed") {
    showStep("login");
    setStatus(
      statusEl,
      "Perangkat dikonfirmasi. Silakan login kembali di browser ini.",
      "ok"
    );
  } else if (deviceParam === "invalid") {
    showStep("login");
    setStatus(
      statusEl,
      "Konfirmasi gagal. Buka tautan email di browser yang sama saat login, atau login ulang untuk kirim email baru.",
      "err"
    );
  } else if (params.get("session") === "expired") {
    // Quiet redirect after timeout — no banner on login.
  } else if (params.get("next")) {
    // Quiet redirect when session cookie missing/rejected — no banner on login.
  }

  loadCaptcha();
})();
