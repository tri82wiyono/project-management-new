(() => {
  const modal = document.getElementById("pm-confirm-modal");
  if (!modal) return;

  const card = modal.querySelector(".pm-confirm-card");
  const iconEl = document.getElementById("pm-confirm-icon");
  const titleEl = document.getElementById("pm-confirm-title");
  const messageEl = document.getElementById("pm-confirm-message");
  const metaEl = document.getElementById("pm-confirm-meta");
  const cancelBtn = document.getElementById("pm-confirm-cancel");
  const okBtn = document.getElementById("pm-confirm-ok");

  let resolver = null;

  function close(result) {
    modal.hidden = true;
    if (resolver) {
      const resolve = resolver;
      resolver = null;
      resolve(result);
    }
  }

  function openDialog({
    title = "Konfirmasi",
    message = "Apakah Anda yakin?",
    meta = "",
    tone = "primary",
    icon = "?",
    okText = "Lanjutkan",
    cancelText = "Batal",
    notice = false,
  } = {}) {
    return new Promise((resolve) => {
      resolver = resolve;
      card.classList.remove("is-danger", "is-success", "is-warn", "is-notice", "is-primary");
      if (tone === "danger") card.classList.add("is-danger");
      else if (tone === "success") card.classList.add("is-success");
      else if (tone === "warn") card.classList.add("is-warn");
      else card.classList.add("is-primary");
      if (notice) card.classList.add("is-notice");

      iconEl.textContent = icon;
      titleEl.textContent = title;
      messageEl.textContent = message;
      if (meta) {
        metaEl.hidden = false;
        metaEl.textContent = meta;
      } else {
        metaEl.hidden = true;
        metaEl.textContent = "";
      }
      okBtn.textContent = okText;
      cancelBtn.textContent = cancelText;
      modal.hidden = false;
      okBtn.focus();
    });
  }

  window.pmConfirm = (options = {}) => openDialog({ notice: false, ...options });
  window.pmNotice = (options = {}) =>
    openDialog({
      notice: true,
      tone: "success",
      icon: "✓",
      okText: "Mengerti",
      ...options,
    });

  cancelBtn.addEventListener("click", () => close(false));
  okBtn.addEventListener("click", () => close(true));
  modal.addEventListener("click", (event) => {
    if (event.target === modal) close(false);
  });
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !modal.hidden) close(false);
  });
})();
