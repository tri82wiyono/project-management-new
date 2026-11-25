(() => {
  const api = async (path, options = {}) => {
    const res = await fetch(path, {
      headers: { "Content-Type": "application/json", ...(options.headers || {}) },
      ...options,
    });
    if (res.status === 204) return null;
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const message =
        typeof detail === "string"
          ? detail
          : Array.isArray(detail)
            ? detail.map((d) => d.msg || JSON.stringify(d)).join(", ")
            : `Request failed (${res.status})`;
      throw new Error(message);
    }
    return data;
  };

  const STATUS_VALUES = ["backlog", "dev", "sit", "uat", "to", "izin", "release"];
  const MAX_DOCS = 3;
  const MAX_DOC_BYTES = 10 * 1024 * 1024;
  const DOC_EXT = new Set([
    ".pdf", ".doc", ".docx", ".xls", ".xlsx", ".ppt", ".pptx",
    ".png", ".jpg", ".jpeg", ".gif", ".txt", ".csv", ".zip",
  ]);

  const page = document.getElementById("project-form-page");
  const mode = page?.dataset.mode || "create";
  const projectId = page?.dataset.projectId || "";

  const state = {
    users: [],
    divisions: [],
    bidangsByDivision: {},
    selectedPicIds: [],
    suggestions: [],
    highlightIndex: -1,
    picSearch: "",
    pendingDocs: [],
    existingDocs: [],
  };

  const els = {
    form: document.getElementById("project-form"),
    formError: document.getElementById("form-error"),
    ownerType: document.getElementById("field-owner-type"),
    ownerDivision: document.getElementById("field-owner-division"),
    ownerBidang: document.getElementById("field-owner-bidang"),
    ownerDivisionField: document.getElementById("owner-division-field"),
    ownerBidangField: document.getElementById("owner-bidang-field"),
    developedBy: document.getElementById("field-developed-by"),
    budgetDisplay: document.getElementById("field-budget"),
    budgetValue: document.getElementById("field-budget-value"),
    description: document.getElementById("field-description"),
    picWrap: document.getElementById("pic-input-wrap"),
    picDropdown: document.getElementById("pic-dropdown"),
    picSearch: document.getElementById("pic-search"),
    picOptions: document.getElementById("pic-options"),
    picChips: document.getElementById("pic-chips"),
    fieldPic: document.getElementById("field-pic"),
    docDropzone: document.getElementById("doc-dropzone"),
    docInput: document.getElementById("field-documents"),
    docList: document.getElementById("doc-file-list"),
    docUrl: document.getElementById("field-doc-url"),
    docUrlTitle: document.getElementById("field-doc-url-title"),
    btnAddDocUrl: document.getElementById("btn-add-doc-url"),
  };

  let quill = null;

  function formatBudgetDisplay(rawDigits) {
    const digits = String(rawDigits || "").replace(/\D/g, "");
    if (!digits) return "";
    return digits.replace(/\B(?=(\d{3})+(?!\d))/g, ".");
  }

  function parseBudgetValue(display) {
    const digits = String(display || "").replace(/\D/g, "");
    if (!digits) return null;
    const num = Number(digits);
    return Number.isFinite(num) ? num : null;
  }

  function syncBudgetFromDisplay() {
    if (!els.budgetDisplay || !els.budgetValue) return null;
    const digits = String(els.budgetDisplay.value || "").replace(/\D/g, "");
    els.budgetDisplay.value = formatBudgetDisplay(digits);
    const value = parseBudgetValue(digits);
    els.budgetValue.value = value == null ? "" : String(value);
    return value;
  }

  function setBudgetValue(value) {
    if (!els.budgetDisplay || !els.budgetValue) return;
    if (value == null || value === "") {
      els.budgetDisplay.value = "";
      els.budgetValue.value = "";
      return;
    }
    els.budgetValue.value = String(value);
    els.budgetDisplay.value = formatBudgetDisplay(String(value));
  }

  function initQuill(initialHtml = "") {
    const host = document.getElementById("description-editor");
    if (!host || typeof Quill === "undefined") return null;
    const editor = new Quill(host, {
      theme: "snow",
      placeholder: "Tulis deskripsi project…",
      modules: {
        toolbar: [
          [{ header: [1, 2, 3, false] }],
          ["bold", "italic", "underline", "strike"],
          [{ list: "ordered" }, { list: "bullet" }],
          ["link"],
          ["clean"],
        ],
      },
    });
    if (initialHtml) {
      editor.root.innerHTML = initialHtml;
    }
    editor.on("text-change", () => {
      if (els.description) els.description.value = editor.root.innerHTML;
    });
    if (els.description) els.description.value = editor.root.innerHTML;
    return editor;
  }

  function getDescriptionHtml() {
    if (quill) {
      const html = quill.root.innerHTML;
      const text = quill.getText().trim();
      return text ? html : null;
    }
    return (els.description?.value || "").trim() || null;
  }

  function escapeHtml(text) {
    return String(text ?? "")
      .replaceAll("&", "&amp;")
      .replaceAll("<", "&lt;")
      .replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;");
  }

  function todayISO() {
    return new Date().toISOString().slice(0, 10);
  }

  function plusDaysISO(days) {
    const d = new Date();
    d.setDate(d.getDate() + days);
    return d.toISOString().slice(0, 10);
  }

  function selectedUsers() {
    return state.users.filter((u) => state.selectedPicIds.includes(u.id));
  }

  function availableUsers(query = "") {
    const q = query.trim().toLowerCase();
    return state.users.filter((user) => {
      if (state.selectedPicIds.includes(user.id)) return false;
      if (!q) return true;
      return (
        user.name.toLowerCase().includes(q) ||
        String(user.email || "").toLowerCase().includes(q) ||
        String(user.role || "").toLowerCase().includes(q)
      );
    });
  }

  function syncPicField() {
    els.fieldPic.value = selectedUsers().map((u) => u.name).join(", ");
    els.picSearch.placeholder = state.selectedPicIds.length
      ? "Tambah nama…"
      : "Ketik nama lalu pilih…";
    renderPicChips();
  }

  function renderPicChips() {
    els.picChips.innerHTML = selectedUsers()
      .map(
        (user) => `
      <span class="pic-chip">
        <span>${escapeHtml(user.name)}</span>
        <button type="button" data-remove-pic="${user.id}" aria-label="Hapus ${escapeHtml(user.name)}">×</button>
      </span>`
      )
      .join("");
  }

  function renderPicOptions() {
    state.suggestions = availableUsers(state.picSearch).slice(0, 12);
    if (!state.suggestions.length) {
      state.highlightIndex = -1;
      els.picOptions.innerHTML = `<div class="pic-empty">${
        state.picSearch.trim() ? "Tidak ada nama yang cocok." : "Semua user sudah dipilih."
      }</div>`;
      return;
    }
    if (state.highlightIndex < 0 || state.highlightIndex >= state.suggestions.length) {
      state.highlightIndex = 0;
    }
    els.picOptions.innerHTML = state.suggestions
      .map(
        (user, index) => `
      <button type="button" class="pic-option${index === state.highlightIndex ? " active" : ""}" role="option" data-pic-id="${user.id}">
        <span>${escapeHtml(user.name)}</span>
        <small>${escapeHtml(user.role || "")}</small>
      </button>`
      )
      .join("");
  }

  function openPicDropdown() {
    els.picDropdown.hidden = false;
    els.picWrap.classList.add("open");
    els.picSearch.setAttribute("aria-expanded", "true");
    renderPicOptions();
  }

  function closePicDropdown() {
    els.picDropdown.hidden = true;
    els.picWrap.classList.remove("open");
    els.picSearch.setAttribute("aria-expanded", "false");
    state.highlightIndex = -1;
  }

  function addPic(id) {
    const num = Number(id);
    if (!num || state.selectedPicIds.includes(num)) return;
    state.selectedPicIds.push(num);
    state.picSearch = "";
    els.picSearch.value = "";
    syncPicField();
    openPicDropdown();
  }

  /** Commit typed PIC text into a selection before validate/save. */
  function commitPendingPicSearch() {
    const typed = (els.picSearch?.value || state.picSearch || "").trim().toLowerCase();
    if (!typed) return false;
    if (!state.suggestions.length) {
      state.suggestions = availableUsers(typed).slice(0, 12);
    }
    const exact = state.suggestions.find((u) => String(u.name || "").toLowerCase() === typed)
      || availableUsers(typed).find((u) => String(u.name || "").toLowerCase() === typed);
    const pick = exact || state.suggestions[state.highlightIndex] || state.suggestions[0];
    if (!pick) return false;
    addPic(pick.id);
    closePicDropdown();
    return true;
  }

  function removePic(id) {
    const num = Number(id);
    state.selectedPicIds = state.selectedPicIds.filter((x) => x !== num);
    syncPicField();
  }

  function setSelectedPicsFromNames(picText) {
    const names = String(picText || "")
      .split(",")
      .map((s) => s.trim().toLowerCase())
      .filter(Boolean);
    state.selectedPicIds = state.users
      .filter((u) => names.includes(String(u.name || "").toLowerCase()))
      .map((u) => u.id);
    syncPicField();
  }

  function formatBytes(n) {
    const size = Number(n) || 0;
    if (size < 1024) return `${size} B`;
    if (size < 1024 * 1024) return `${(size / 1024).toFixed(1)} KB`;
    return `${(size / (1024 * 1024)).toFixed(1)} MB`;
  }

  function fileExt(name) {
    const m = String(name || "").toLowerCase().match(/\.[a-z0-9]+$/);
    return m ? m[0] : "";
  }

  function totalDocSlotsUsed() {
    return state.existingDocs.length + state.pendingDocs.length;
  }

  function setDocMode(modeName) {
    const next = modeName === "url" ? "url" : "file";
    document.querySelectorAll("[data-doc-mode]").forEach((btn) => {
      const active = btn.dataset.docMode === next;
      btn.classList.toggle("is-active", active);
      btn.setAttribute("aria-selected", active ? "true" : "false");
    });
    document.querySelectorAll("[data-doc-panel]").forEach((panel) => {
      panel.hidden = panel.dataset.docPanel !== next;
    });
  }

  function renderDocList() {
    if (!els.docList) return;
    const items = [
      ...state.existingDocs.map((d) => ({
        kind: "existing",
        id: d.id,
        name: d.original_name,
        meta: d.kind === "url" ? "URL / Drive" : formatBytes(d.size_bytes),
        url: d.open_url || d.download_url || d.external_url,
        actionLabel: d.kind === "url" ? "Buka" : "Download",
      })),
      ...state.pendingDocs.map((item, idx) => ({
        kind: "pending",
        id: idx,
        name: item.type === "url" ? item.title || item.url : item.file.name,
        meta:
          item.type === "url"
            ? "URL · siap ditambah"
            : `${formatBytes(item.file.size)} · siap diunggah`,
        url: item.type === "url" ? item.url : null,
        actionLabel: item.type === "url" ? "Buka" : null,
      })),
    ];
    if (!items.length) {
      els.docList.hidden = true;
      els.docList.innerHTML = "";
    } else {
      els.docList.hidden = false;
      els.docList.innerHTML = items
        .map(
          (item) => `
        <li class="doc-file-item" data-kind="${item.kind}" data-id="${item.id}">
          <div class="doc-file-meta">
            <strong title="${escapeHtml(item.name)}">${escapeHtml(item.name)}</strong>
            <span>${escapeHtml(item.meta)}</span>
          </div>
          <div class="doc-file-actions">
            ${item.url && item.actionLabel ? `<a href="${escapeHtml(item.url)}" target="_blank" rel="noopener">${item.actionLabel}</a>` : ""}
            <button type="button" class="is-danger" data-remove-doc="${item.kind}:${item.id}">Hapus</button>
          </div>
        </li>`
        )
        .join("");
    }
    els.docDropzone?.classList.toggle("is-full", totalDocSlotsUsed() >= MAX_DOCS);
  }

  function addPendingFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    const remaining = MAX_DOCS - totalDocSlotsUsed();
    if (remaining <= 0) {
      els.formError.hidden = false;
      els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
      return;
    }
    const accepted = [];
    for (const file of incoming.slice(0, remaining)) {
      const ext = fileExt(file.name);
      if (!DOC_EXT.has(ext)) {
        els.formError.hidden = false;
        els.formError.textContent = `Tipe file tidak diizinkan: ${file.name}`;
        continue;
      }
      if (file.size > MAX_DOC_BYTES) {
        els.formError.hidden = false;
        els.formError.textContent = `File terlalu besar (maks 10 MB): ${file.name}`;
        continue;
      }
      accepted.push({ type: "file", file });
    }
    if (accepted.length) {
      els.formError.hidden = true;
      state.pendingDocs.push(...accepted);
      renderDocList();
    }
    if (els.docInput) els.docInput.value = "";
  }

  function addPendingUrl() {
    const url = (els.docUrl?.value || "").trim();
    const title = (els.docUrlTitle?.value || "").trim();
    if (!url) {
      els.formError.hidden = false;
      els.formError.textContent = "Isi URL dokumen terlebih dahulu.";
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      els.formError.hidden = false;
      els.formError.textContent = "URL harus dimulai dengan http:// atau https://";
      return;
    }
    if (totalDocSlotsUsed() >= MAX_DOCS) {
      els.formError.hidden = false;
      els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
      return;
    }
    els.formError.hidden = true;
    state.pendingDocs.push({ type: "url", url, title });
    if (els.docUrl) els.docUrl.value = "";
    if (els.docUrlTitle) els.docUrlTitle.value = "";
    renderDocList();
  }

  async function removeExistingDoc(docId) {
    const id = document.getElementById("project-id").value;
    if (!id) return;
    await api(`/api/projects/${id}/documents/${docId}`, { method: "DELETE" });
    state.existingDocs = state.existingDocs.filter((d) => d.id !== docId);
    renderDocList();
  }

  async function uploadPendingDocs(id) {
    if (!state.pendingDocs.length) return;
    const files = state.pendingDocs.filter((d) => d.type === "file").map((d) => d.file);
    const urls = state.pendingDocs.filter((d) => d.type === "url");
    if (files.length) {
      const body = new FormData();
      files.forEach((file) => body.append("files", file, file.name));
      const res = await fetch(`/api/projects/${id}/documents`, { method: "POST", body });
      const data = await res.json().catch(() => ({}));
      if (!res.ok) {
        throw new Error(
          typeof data.detail === "string" ? data.detail : `Upload gagal (${res.status})`
        );
      }
    }
    for (const item of urls) {
      await api(`/api/projects/${id}/documents/url`, {
        method: "POST",
        body: JSON.stringify({ url: item.url, title: item.title || null }),
      });
    }
  }

  function syncOwnershipFields() {
    const kind = els.ownerType?.value || "unassigned";
    if (els.ownerDivisionField) els.ownerDivisionField.hidden = kind === "unassigned";
    if (els.ownerBidangField) els.ownerBidangField.hidden = kind !== "bidang";
    if (kind === "unassigned") {
      if (els.ownerDivision) els.ownerDivision.value = "";
      if (els.ownerBidang) els.ownerBidang.value = "";
    }
    if (kind === "division" && els.ownerBidang) els.ownerBidang.value = "";
  }

  function fillDivisionOptions(selectedId = "") {
    if (!els.ownerDivision) return;
    els.ownerDivision.innerHTML = ['<option value="">— Pilih Divisi —</option>']
      .concat(
        state.divisions.map(
          (d) =>
            `<option value="${d.id}" ${String(d.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(d.name)}</option>`
        )
      )
      .join("");
  }

  async function loadBidangsForDivision(divisionId, selectedBidangId = "") {
    if (!els.ownerBidang) return;
    if (!divisionId) {
      els.ownerBidang.innerHTML = '<option value="">— Pilih Bidang —</option>';
      return;
    }
    let items = state.bidangsByDivision[String(divisionId)] || [];
    if (!items.length) {
      await loadOrganizationOptions();
      items = state.bidangsByDivision[String(divisionId)] || [];
    }
    els.ownerBidang.innerHTML = ['<option value="">— Pilih Bidang —</option>']
      .concat(
        items.map(
          (b) =>
            `<option value="${b.id}" ${String(b.id) === String(selectedBidangId) ? "selected" : ""}>${escapeHtml(b.name)}</option>`
        )
      )
      .join("");
  }

  async function applyOwnershipToForm(project = null) {
    const kind = project?.owner_type || "bidang";
    if (els.ownerType) els.ownerType.value = kind;
    fillDivisionOptions(project?.owner_division_id || "");
    syncOwnershipFields();
    if (kind === "bidang") {
      await loadBidangsForDivision(project?.owner_division_id || "", project?.owner_bidang_id || "");
    } else if (els.ownerBidang) {
      els.ownerBidang.innerHTML = '<option value="">— Pilih Bidang —</option>';
    }
  }

  function syncReleaseOption(progress) {
    const select = document.getElementById("field-status");
    const releaseOpt = select?.querySelector('option[value="release"]');
    const hint = document.getElementById("status-release-hint");
    const ready = Math.round(Number(progress) || 0) >= 100;
    if (releaseOpt) {
      releaseOpt.disabled = !ready;
      if (!ready && select.value === "release") select.value = "izin";
    }
    if (hint) hint.hidden = ready;
  }

  async function loadOrganizationOptions() {
    try {
      const data = await api("/api/organization/ownership-options");
      state.divisions = Array.isArray(data.divisions) ? data.divisions : [];
      state.bidangsByDivision = {};
      for (const b of Array.isArray(data.bidangs) ? data.bidangs : []) {
        const key = String(b.division_id);
        if (!state.bidangsByDivision[key]) state.bidangsByDivision[key] = [];
        state.bidangsByDivision[key].push(b);
      }
    } catch {
      state.divisions = [];
      state.bidangsByDivision = {};
    }
  }

  async function loadUsers() {
    state.users = await api("/api/team?active_only=true");
  }

  async function populateForm(project = null) {
    state.selectedPicIds = [];
    state.picSearch = "";
    els.picSearch.value = "";
    closePicDropdown();
    state.pendingDocs = [];
    state.existingDocs = [];
    setDocMode("file");

    if (project) {
      document.getElementById("project-id").value = project.id;
      document.getElementById("field-name").value = project.name || "";
      document.getElementById("field-start").value = project.start_date || "";
      document.getElementById("field-end").value = project.end_date || "";
      document.getElementById("field-status").value = STATUS_VALUES.includes(project.status)
        ? project.status
        : "backlog";
      if (els.developedBy) els.developedBy.value = project.developed_by || "";
      setBudgetValue(project.budget);
      if (!quill) quill = initQuill(project.description || "");
      else {
        quill.root.innerHTML = project.description || "";
        if (els.description) els.description.value = quill.root.innerHTML;
      }
      syncReleaseOption(project.progress);
      setSelectedPicsFromNames(project.pic || "");
      await applyOwnershipToForm(project);
      try {
        const docs = project.documents?.length
          ? project.documents
          : await api(`/api/projects/${project.id}/documents`);
        state.existingDocs = Array.isArray(docs) ? docs : [];
      } catch {
        state.existingDocs = [];
      }
      renderDocList();
    } else {
      document.getElementById("project-id").value = "";
      document.getElementById("field-name").value = "";
      document.getElementById("field-start").value = todayISO();
      document.getElementById("field-end").value = plusDaysISO(90);
      document.getElementById("field-status").value = "backlog";
      if (els.developedBy) els.developedBy.value = "";
      setBudgetValue(null);
      if (!quill) quill = initQuill("");
      else {
        quill.setText("");
        if (els.description) els.description.value = "";
      }
      syncReleaseOption(0);
      syncPicField();
      await applyOwnershipToForm(null);
      renderDocList();
    }
  }

  async function saveProject(event) {
    event.preventDefault();
    els.formError.hidden = true;
    if (!state.selectedPicIds.length) commitPendingPicSearch();
    syncPicField();

    const id = document.getElementById("project-id").value;
    const ownerType = els.ownerType?.value || "unassigned";
    const ownerDivisionId = els.ownerDivision?.value ? Number(els.ownerDivision.value) : null;
    const ownerBidangId = els.ownerBidang?.value ? Number(els.ownerBidang.value) : null;
    const developedBy = (els.developedBy?.value || "").trim();
    const budget = syncBudgetFromDisplay();
    const payload = {
      name: document.getElementById("field-name").value.trim(),
      description: getDescriptionHtml(),
      pic: els.fieldPic.value.trim(),
      start_date: document.getElementById("field-start").value,
      end_date: document.getElementById("field-end").value,
      status: document.getElementById("field-status").value,
      developed_by: developedBy || null,
      budget,
      member_ids: state.selectedPicIds.slice(),
      owner_type: ownerType,
      owner_division_id: ownerType === "division" || ownerType === "bidang" ? ownerDivisionId : null,
      owner_bidang_id: ownerType === "bidang" ? ownerBidangId : null,
    };

    const missing = [];
    if (!payload.name) missing.push("nama");
    if (!developedBy) missing.push("dikembangkan oleh");
    if (!payload.pic || !state.selectedPicIds.length) missing.push("PIC");
    if (!payload.start_date || !payload.end_date) missing.push("tanggal");
    if (missing.length) {
      els.formError.hidden = false;
      const picHint = missing.includes("PIC")
        ? " Untuk PIC, ketik nama lalu pilih dari daftar (klik atau Enter)."
        : "";
      els.formError.textContent = `Lengkapi field wajib: ${missing.join(", ")}.${picHint}`;
      return;
    }
    if (payload.end_date < payload.start_date) {
      els.formError.hidden = false;
      els.formError.textContent = "Target date must be on or after start date.";
      return;
    }
    if (ownerType === "division" && !ownerDivisionId) {
      els.formError.hidden = false;
      els.formError.textContent = "Pilih Divisi pemilik.";
      return;
    }
    if (ownerType === "bidang" && !ownerBidangId) {
      els.formError.hidden = false;
      els.formError.textContent = "Pilih Bidang pemilik.";
      return;
    }

    const saveBtn = document.getElementById("btn-save-project");
    if (saveBtn) saveBtn.disabled = true;
    try {
      const saved = await (id
        ? api(`/api/projects/${id}`, { method: "PATCH", body: JSON.stringify(payload) })
        : api("/api/projects", { method: "POST", body: JSON.stringify(payload) }));
      if (state.pendingDocs.length) {
        await uploadPendingDocs(saved.id);
      }
      window.location.href = `/projects/${saved.id}`;
    } catch (err) {
      els.formError.hidden = false;
      els.formError.textContent = err.message || "Failed to save project.";
      if (saveBtn) saveBtn.disabled = false;
    }
  }

  function wirePicEvents() {
    els.picWrap.addEventListener("click", (e) => {
      if (e.target.closest("[data-remove-pic]")) return;
      els.picSearch.focus();
      openPicDropdown();
    });
    els.picSearch.addEventListener("focus", openPicDropdown);
    els.picSearch.addEventListener("input", () => {
      state.picSearch = els.picSearch.value;
      state.highlightIndex = 0;
      openPicDropdown();
    });
    els.picSearch.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !els.picSearch.value && state.selectedPicIds.length) {
        e.preventDefault();
        removePic(state.selectedPicIds[state.selectedPicIds.length - 1]);
        openPicDropdown();
        return;
      }
      if (els.picDropdown.hidden) {
        if (e.key === "ArrowDown") {
          e.preventDefault();
          openPicDropdown();
        }
        return;
      }
      if (e.key === "ArrowDown") {
        e.preventDefault();
        if (!state.suggestions.length) return;
        state.highlightIndex = (state.highlightIndex + 1) % state.suggestions.length;
        renderPicOptions();
        return;
      }
      if (e.key === "ArrowUp") {
        e.preventDefault();
        if (!state.suggestions.length) return;
        state.highlightIndex =
          (state.highlightIndex - 1 + state.suggestions.length) % state.suggestions.length;
        renderPicOptions();
        return;
      }
      if (e.key === "Enter") {
        e.preventDefault();
        const pick = state.suggestions[state.highlightIndex];
        if (pick) addPic(pick.id);
        return;
      }
      if (e.key === "Escape") {
        e.preventDefault();
        closePicDropdown();
      }
    });
    els.picOptions.addEventListener("mousedown", (e) => {
      const option = e.target.closest("[data-pic-id]");
      if (!option) return;
      e.preventDefault();
      addPic(option.dataset.picId);
    });
    els.picChips.addEventListener("click", (e) => {
      const btn = e.target.closest("[data-remove-pic]");
      if (!btn) return;
      e.preventDefault();
      e.stopPropagation();
      removePic(btn.dataset.removePic);
      els.picSearch.focus();
    });
    document.addEventListener("click", (e) => {
      const box = document.getElementById("pic-multiselect");
      if (!box || els.picDropdown.hidden) return;
      if (!box.contains(e.target)) closePicDropdown();
    });
  }

  function wireDocEvents() {
    document.querySelectorAll("[data-doc-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setDocMode(btn.dataset.docMode));
    });
    els.btnAddDocUrl?.addEventListener("click", addPendingUrl);
    els.docDropzone?.addEventListener("click", () => {
      if (totalDocSlotsUsed() >= MAX_DOCS) {
        els.formError.hidden = false;
        els.formError.textContent = `Maksimal ${MAX_DOCS} dokumen per project.`;
        return;
      }
      els.docInput?.click();
    });
    ["dragenter", "dragover"].forEach((evt) => {
      els.docDropzone?.addEventListener(evt, (e) => {
        e.preventDefault();
        els.docDropzone.classList.add("dragover");
      });
    });
    ["dragleave", "drop"].forEach((evt) => {
      els.docDropzone?.addEventListener(evt, (e) => {
        e.preventDefault();
        els.docDropzone.classList.remove("dragover");
      });
    });
    els.docDropzone?.addEventListener("drop", (e) => addPendingFiles(e.dataTransfer?.files));
    els.docInput?.addEventListener("change", () => addPendingFiles(els.docInput.files));
    els.docList?.addEventListener("click", async (e) => {
      const btn = e.target.closest("[data-remove-doc]");
      if (!btn) return;
      const [kind, idRaw] = String(btn.dataset.removeDoc || "").split(":");
      if (kind === "pending") {
        state.pendingDocs = state.pendingDocs.filter((_, i) => i !== Number(idRaw));
        renderDocList();
        return;
      }
      if (kind === "existing") {
        try {
          await removeExistingDoc(Number(idRaw));
        } catch (err) {
          els.formError.hidden = false;
          els.formError.textContent = err.message || "Gagal menghapus dokumen.";
        }
      }
    });
  }

  async function boot() {
    if (!els.form) return;
    els.form.addEventListener("submit", saveProject);
    wirePicEvents();
    wireDocEvents();
    els.budgetDisplay?.addEventListener("input", syncBudgetFromDisplay);
    els.budgetDisplay?.addEventListener("blur", syncBudgetFromDisplay);
    els.ownerType?.addEventListener("change", async () => {
      syncOwnershipFields();
      if ((els.ownerType?.value || "") === "bidang") {
        await loadBidangsForDivision(els.ownerDivision?.value || "");
      }
    });
    els.ownerDivision?.addEventListener("change", async () => {
      if ((els.ownerType?.value || "") === "bidang") {
        await loadBidangsForDivision(els.ownerDivision.value || "");
      }
    });

    await Promise.all([loadUsers(), loadOrganizationOptions()]);

    if (mode === "edit" && projectId) {
      const project = await api(`/api/projects/${projectId}`);
      await populateForm(project);
    } else {
      await populateForm(null);
    }
  }

  boot().catch((err) => {
    if (els.formError) {
      els.formError.hidden = false;
      els.formError.textContent = err.message || "Gagal memuat form project.";
    }
  });
})();
