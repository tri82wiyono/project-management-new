(() => {
  // Idle-based auto-logout: timer resets while the user is active.
  if (location.pathname.startsWith("/login")) return;

  let timerId = null;
  let warned = false;
  let expiresAtIso = null;
  let timeoutMinutes = 480;
  let lastActivityAt = Date.now();
  let lastExtendAt = 0;
  let extendInFlight = false;

  const ACTIVITY_EVENTS = ["pointerdown", "keydown", "scroll", "touchstart", "mousemove"];
  const EXTEND_EVERY_MS = 45 * 1000; // throttle server slides
  const PRESENCE_EVERY_MS = 60 * 1000;
  const WARN_BEFORE_MS = 2 * 60 * 1000;

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

  function schedule(nextExpiresAtIso) {
    clearTimer();
    if (nextExpiresAtIso) expiresAtIso = nextExpiresAtIso;
    if (!expiresAtIso) return;

    const expiresMs = Date.parse(expiresAtIso);
    if (!Number.isFinite(expiresMs)) return;

    const remaining = expiresMs - Date.now();
    if (remaining <= 0) {
      forceLogout("expired");
      return;
    }

    if (!warned && remaining > WARN_BEFORE_MS + 5000) {
      timerId = setTimeout(() => {
        // If user was active recently, skip warning and re-extend instead.
        if (Date.now() - lastActivityAt < WARN_BEFORE_MS) {
          warned = false;
          touchSession(true);
          return;
        }
        warned = true;
        if (window.pmNotice) {
          window.pmNotice({
            title: "Sesi hampir berakhir",
            message:
              "Tidak ada aktivitas. Anda akan logout otomatis dalam sekitar 2 menit jika tetap idle. Gerakkan mouse atau ketik untuk tetap masuk.",
            tone: "warn",
            icon: "⏱",
            okText: "Saya masih di sini",
          }).then(() => {
            markActivity();
            touchSession(true);
          });
        }
        schedule(expiresAtIso);
      }, remaining - WARN_BEFORE_MS);
      return;
    }

    timerId = setTimeout(() => {
      if (Date.now() - lastActivityAt < 15 * 1000) {
        touchSession(true);
        return;
      }
      forceLogout("expired");
    }, remaining);
  }

  async function pingPresence({ extendSession = false } = {}) {
    if (document.visibilityState === "hidden" && !extendSession) return null;
    try {
      const res = await fetch("/api/auth/heartbeat", {
        method: "POST",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ extend_session: Boolean(extendSession) }),
      });
      if (res.status === 401) {
        forceLogout("expired");
        return null;
      }
      if (!res.ok) return null;
      return await res.json().catch(() => null);
    } catch {
      return null;
    }
  }

  async function touchSession(force = false) {
    const now = Date.now();
    if (!force && now - lastExtendAt < EXTEND_EVERY_MS) return;
    if (extendInFlight) return;
    extendInFlight = true;
    try {
      const data = await pingPresence({ extendSession: true });
      if (!data) return;
      lastExtendAt = Date.now();
      if (data.session_timeout_minutes) {
        timeoutMinutes = Number(data.session_timeout_minutes) || timeoutMinutes;
      }
      if (data.session_expires_at) {
        warned = false;
        schedule(data.session_expires_at);
      } else {
        // Local fallback slide
        const localExpiry = new Date(Date.now() + timeoutMinutes * 60 * 1000).toISOString();
        warned = false;
        schedule(localExpiry);
      }
    } finally {
      extendInFlight = false;
    }
  }

  function markActivity() {
    lastActivityAt = Date.now();
    touchSession(false);
  }

  async function init() {
    try {
      const res = await fetch("/api/auth/me", { credentials: "same-origin" });
      if (res.status === 401) return;
      if (!res.ok) return;
      const data = await res.json();
      timeoutMinutes = Number(data.session_timeout_minutes) || timeoutMinutes;
      schedule(data.session_expires_at);
      // Initial slide so idle clock starts from "now" after page load.
      await touchSession(true);
    } catch {
      /* ignore */
    }
  }

  ACTIVITY_EVENTS.forEach((evt) => {
    document.addEventListener(evt, markActivity, { passive: true, capture: true });
  });

  document.addEventListener("visibilitychange", () => {
    if (document.visibilityState !== "visible") return;
    markActivity();
    if (!timerId) init();
  });

  // Presence for online indicators — does NOT extend idle session.
  window.setInterval(() => {
    pingPresence({ extendSession: false });
  }, PRESENCE_EVERY_MS);

  init();
})();
