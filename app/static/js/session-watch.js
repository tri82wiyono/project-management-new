(() => {
  // Auto-logout when admin-configured session timeout elapses.
  if (location.pathname.startsWith("/login")) return;

  let timerId = null;
  let warned = false;

  function clearTimer() {
    if (timerId) {
      clearTimeout(timerId);
      timerId = null;
    }
  }

  async function forceLogout(reason) {
    clearTimer();
    try {
      await fetch("/api/auth/logout", { method: "POST", credentials: "same-origin" });
    } catch {
      /* ignore */
    }
    const q = new URLSearchParams({ next: "/", session: reason || "expired" });
    window.location.href = `/login?${q.toString()}`;
  }

  function schedule(expiresAtIso) {
    clearTimer();
    if (!expiresAtIso) return;
    const expiresMs = Date.parse(expiresAtIso);
    if (!Number.isFinite(expiresMs)) return;

    const remaining = expiresMs - Date.now();
    if (remaining <= 0) {
      forceLogout("expired");
      return;
    }

    // Warn ~2 minutes before expiry (if session longer than 3 minutes)
    const warnBefore = 2 * 60 * 1000;
    if (!warned && remaining > warnBefore + 5000) {
      timerId = setTimeout(() => {
        warned = true;
        if (window.pmNotice) {
          window.pmNotice({
            title: "Sesi hampir berakhir",
            message: "Anda akan logout otomatis dalam sekitar 2 menit. Simpan pekerjaan Anda.",
            tone: "warn",
            icon: "⏱",
            okText: "Mengerti",
          });
        }
        schedule(expiresAtIso);
      }, remaining - warnBefore);
      return;
    }

    timerId = setTimeout(() => forceLogout("expired"), remaining);
  }

  async function pingPresence() {
    if (document.visibilityState === "hidden") return;
    try {
      await fetch("/api/auth/heartbeat", {
        method: "POST",
        credentials: "same-origin",
      });
    } catch {
      /* ignore */
    }
  }

  async function init() {
    try {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (res.status === 401) return;
      if (!res.ok) return;
      const data = await res.json();
      schedule(data.session_expires_at);
      pingPresence();
    } catch {
      /* ignore */
    }
  }

  // Jangan refetch /api/auth/me setiap kali tab fokus — cukup cek timer lokal.
  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    // If timer already scheduled, nothing to do; only recover if missing.
    if (!timerId) init();
    else pingPresence();
  });

  init();
  window.setInterval(pingPresence, 60000);
})();
