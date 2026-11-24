(() => {
  const STORAGE_KEY = "pm_sidebar_collapsed";
  const LEGACY_KEY = "pm_sidebar_hidden";
  const shell = document.querySelector(".app-shell");
  const sidebar = document.querySelector(".sidebar");

  // Remove old floating / bar toggles from previous version
  document.querySelectorAll(
    "[data-sidebar-toggle='float'], [data-sidebar-toggle='bar'], [data-sidebar-toggle='top'], .sidebar-reopen"
  ).forEach((el) => el.remove());

  if (shell && sidebar) {
    function isCollapsed() {
      return shell.classList.contains("sidebar-collapsed");
    }

    function persist(collapsed) {
      try {
        localStorage.setItem(STORAGE_KEY, collapsed ? "1" : "0");
        localStorage.removeItem(LEGACY_KEY);
      } catch (_) {
        /* ignore */
      }
    }

    function syncButtons(collapsed) {
      document.querySelectorAll("[data-sidebar-toggle]").forEach((btn) => {
        btn.setAttribute("aria-expanded", collapsed ? "false" : "true");
        btn.setAttribute(
          "aria-label",
          collapsed ? "Perbesar sidebar" : "Ciutkan sidebar"
        );
        btn.title = collapsed
          ? "Perbesar sidebar (Ctrl/⌘+B)"
          : "Ciutkan sidebar (Ctrl/⌘+B)";
        const icon = btn.querySelector("[data-sidebar-icon]");
        if (icon) icon.textContent = collapsed ? "›" : "‹";
      });

      document.querySelectorAll(".nav-item").forEach((item) => {
        const label = item.querySelector(".nav-label");
        if (label) item.title = collapsed ? label.textContent.trim() : "";
      });
    }

    function setCollapsed(collapsed) {
      shell.classList.toggle("sidebar-collapsed", Boolean(collapsed));
      document.body.classList.toggle("has-sidebar-collapsed", Boolean(collapsed));
      shell.classList.remove("sidebar-hidden");
      document.body.classList.remove("has-sidebar-hidden");
      persist(Boolean(collapsed));
      syncButtons(Boolean(collapsed));
    }

    function toggle() {
      setCollapsed(!isCollapsed());
    }

    let preferred = false;
    try {
      const modern = localStorage.getItem(STORAGE_KEY);
      if (modern === "1" || modern === "0") {
        preferred = modern === "1";
      } else {
        preferred = localStorage.getItem(LEGACY_KEY) === "1";
      }
    } catch (_) {
      preferred = false;
    }
    setCollapsed(preferred);

    document.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-sidebar-toggle]");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      toggle();
    });

    document.addEventListener("keydown", (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === "b") {
        e.preventDefault();
        toggle();
      }
    });
  }

  // Mobile bottom nav press + pulse animation
  const mobileNav = document.getElementById("mobile-nav");
  if (mobileNav) {
    mobileNav.addEventListener("pointerdown", (e) => {
      const item = e.target.closest(".mobile-nav-item");
      if (!item) return;
      item.classList.add("is-pressed");
    });

    const clearPress = (e) => {
      const item = e.target.closest?.(".mobile-nav-item") || mobileNav.querySelector(".is-pressed");
      if (item) item.classList.remove("is-pressed");
    };

    mobileNav.addEventListener("pointerup", clearPress);
    mobileNav.addEventListener("pointercancel", clearPress);
    mobileNav.addEventListener("pointerleave", clearPress);

    mobileNav.addEventListener("click", (e) => {
      const item = e.target.closest(".mobile-nav-item");
      if (!item) return;
      item.classList.add("pulse");
      window.setTimeout(() => item.classList.remove("pulse"), 450);
    });
  }

  // Account sheet (Profil / Ubah Password / Logout)
  const accountBtn = document.getElementById("btn-account-menu");
  const accountSheet = document.getElementById("account-sheet");
  if (accountBtn && accountSheet) {
    const openSheet = () => {
      accountSheet.hidden = false;
      accountBtn.setAttribute("aria-expanded", "true");
      accountBtn.classList.add("active", "pulse");
      document.body.classList.add("account-sheet-open");
    };

    const closeSheet = () => {
      accountSheet.hidden = true;
      accountBtn.setAttribute("aria-expanded", "false");
      document.body.classList.remove("account-sheet-open");
      if (!window.location.pathname.startsWith("/account")) {
        accountBtn.classList.remove("active");
      }
    };

    accountBtn.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (accountSheet.hidden) openSheet();
      else closeSheet();
    });

    accountSheet.addEventListener("click", (e) => {
      if (e.target.closest("[data-account-close]")) {
        e.preventDefault();
        closeSheet();
      }
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape" && !accountSheet.hidden) closeSheet();
    });
  }

  // Topbar avatar dropdown: Profil / Keamanan / Logout
  document.querySelectorAll("[data-user-menu]").forEach((menu) => {
    const toggle = menu.querySelector("[data-user-menu-toggle]");
    const panel = menu.querySelector("[data-user-menu-panel]");
    if (!toggle || !panel) return;

    const closeMenu = () => {
      panel.hidden = true;
      menu.classList.remove("open");
      toggle.setAttribute("aria-expanded", "false");
    };

    const openMenu = () => {
      // close other open menus first
      document.querySelectorAll("[data-user-menu].open").forEach((other) => {
        if (other !== menu) {
          other.classList.remove("open");
          const otherPanel = other.querySelector("[data-user-menu-panel]");
          const otherToggle = other.querySelector("[data-user-menu-toggle]");
          if (otherPanel) otherPanel.hidden = true;
          if (otherToggle) otherToggle.setAttribute("aria-expanded", "false");
        }
      });
      document.querySelectorAll("[data-notif-menu].open").forEach((notif) => {
        notif.classList.remove("open");
        const notifPanel = notif.querySelector("[data-notif-panel]");
        const notifToggle = notif.querySelector("[data-notif-toggle]");
        if (notifPanel) notifPanel.hidden = true;
        if (notifToggle) notifToggle.setAttribute("aria-expanded", "false");
      });
      panel.hidden = false;
      menu.classList.add("open");
      toggle.setAttribute("aria-expanded", "true");
    };

    toggle.addEventListener("click", (e) => {
      e.preventDefault();
      e.stopPropagation();
      if (panel.hidden) openMenu();
      else closeMenu();
    });

    document.addEventListener("click", (e) => {
      if (!menu.contains(e.target)) closeMenu();
    });

    document.addEventListener("keydown", (e) => {
      if (e.key === "Escape") closeMenu();
    });
  });
})();
