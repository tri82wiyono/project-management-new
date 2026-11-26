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
    selectedPicIds: [],
    suggestions: [],
    highlightIndex: -1,
    picSearch: "",
    pendingDocs: [],
    existingDocs: [],
    divisions: [],
    bidangsByDivision: {},
    defaultOwnership: null,
  };

  const els = {
    form: document.getElementById("project-form"),
    formError: document.getElementById("form-error"),
    developedBy: document.getElementById("field-developed-by"),
    workType: document.getElementById("field-work-type"),
    workCategoryGrid: document.getElementById("work-category-grid"),
    rbbInfoBox: document.getElementById("rbb-info-box"),
    rbbYear: document.getElementById("field-rbb-year"),
    rbbProgramRef: document.getElementById("field-rbb-program-ref"),
    ownerType: document.getElementById("field-owner-type"),
    ownerDivision: document.getElementById("field-owner-division"),
    ownerBidang: document.getElementById("field-owner-bidang"),
    ownerDivisionField: document.getElementById("owner-division-field"),
    ownerBidangField: document.getElementById("owner-bidang-field"),
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

  function fillRbbYearOptions(selected) {
    if (!els.rbbYear) return;
    const currentYear = new Date().getFullYear();
    const years = [];
    for (let y = currentYear + 1; y >= currentYear - 5; y -= 1) years.push(y);
    const prev = selected != null && selected !== "" ? String(selected) : els.rbbYear.value;
    els.rbbYear.innerHTML =
      `<option value="">Pilih tahun</option>` +
      years.map((y) => `<option value="${y}">${y}</option>`).join("");
    if (prev && years.some((y) => String(y) === prev)) els.rbbYear.value = prev;
  }

  function selectedWorkCategories() {
    const checked = els.workCategoryGrid?.querySelector('input[name="work_category"]:checked');
    return checked?.value ? [checked.value] : [];
  }

  function setWorkCategories(values) {
    const chosen = Array.isArray(values) && values.length ? String(values[0]) : "";
    els.workCategoryGrid?.querySelectorAll('input[name="work_category"]').forEach((el) => {
      el.checked = el.value === chosen;
    });
    syncRbbFieldsVisibility();
  }

  function syncRbbFieldsVisibility() {
    const hasRbb = selectedWorkCategories().includes("rbb");
    if (els.rbbInfoBox) els.rbbInfoBox.hidden = !hasRbb;
    if (!hasRbb) {
      if (els.rbbYear) els.rbbYear.value = "";
      if (els.rbbProgramRef) els.rbbProgramRef.value = "";
    }
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
      ? "Tambah PIC lain…"
      : "Ketik nama PIC terdaftar…";
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

  function positionPicSuggest() {
    if (!els.picDropdown || !els.picWrap || els.picDropdown.hidden) return;
    const rect = els.picWrap.getBoundingClientRect();
    const gap = 6;
    const maxH = 220;
    const spaceBelow = window.innerHeight - rect.bottom - gap - 12;
    const spaceAbove = rect.top - gap - 12;
    const openUp = spaceBelow < 140 && spaceAbove > spaceBelow;
    const height = Math.min(maxH, Math.max(120, openUp ? spaceAbove : spaceBelow));
    els.picDropdown.style.left = `${Math.round(rect.left)}px`;
    els.picDropdown.style.width = `${Math.round(rect.width)}px`;
    els.picDropdown.style.maxHeight = `${Math.round(height)}px`;
    if (openUp) {
      els.picDropdown.style.top = "auto";
      els.picDropdown.style.bottom = `${Math.round(window.innerHeight - rect.top + gap)}px`;
    } else {
      els.picDropdown.style.bottom = "auto";
      els.picDropdown.style.top = `${Math.round(rect.bottom + gap)}px`;
    }
  }

  function renderPicOptions() {
    const q = state.picSearch.trim();
    state.suggestions = q ? availableUsers(q).slice(0, 8) : [];
    if (!q) {
      state.highlightIndex = -1;
      els.picOptions.innerHTML = "";
      return;
    }
    if (!state.suggestions.length) {
      state.highlightIndex = -1;
      els.picOptions.innerHTML = `<div class="pic-empty">Tidak ada nama terdaftar yang cocok dengan “${escapeHtml(q)}”.</div>`;
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

  function openPicSuggest() {
    const q = (els.picSearch?.value || state.picSearch || "").trim();
    if (!q) {
      closePicDropdown();
      return;
    }
    if (els.picDropdown.parentElement !== document.body) {
      document.body.appendChild(els.picDropdown);
    }
    renderPicOptions();
    els.picDropdown.hidden = false;
    els.picWrap.classList.add("open");
    els.picSearch.setAttribute("aria-expanded", "true");
    positionPicSuggest();
  }

  function closePicDropdown() {
    if (!els.picDropdown) return;
    els.picDropdown.hidden = true;
    els.picWrap?.classList.remove("open");
    els.picSearch?.setAttribute("aria-expanded", "false");
    state.highlightIndex = -1;
    state.suggestions = [];
  }

  function addPic(id) {
    const num = Number(id);
    if (!num || state.selectedPicIds.includes(num)) return;
    state.selectedPicIds.push(num);
    state.picSearch = "";
    els.picSearch.value = "";
    syncPicField();
    closePicDropdown();
  }

  /** Commit typed PIC text into a selection before validate/save. */
  function commitPendingPicSearch() {
    const typed = (els.picSearch?.value || state.picSearch || "").trim().toLowerCase();
    if (!typed) return false;
    const matches = availableUsers(typed);
    const exact = matches.find((u) => String(u.name || "").toLowerCase() === typed);
    const pick = exact || state.suggestions[state.highlightIndex] || matches[0];
    if (!pick) return false;
    addPic(pick.id);
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

  function notifyForm(message, { title = "Perhatian", tone = "warn", icon = "!" } = {}) {
    if (window.pmNotice) {
      window.pmNotice({ title, message, tone, icon, okText: "Mengerti" });
      return;
    }
    if (els.formError) {
      els.formError.hidden = false;
      els.formError.textContent = message;
    }
  }

  function addPendingFiles(fileList) {
    const incoming = Array.from(fileList || []);
    if (!incoming.length) return;
    const remaining = MAX_DOCS - totalDocSlotsUsed();
    if (remaining <= 0) {
      notifyForm(`Maksimal ${MAX_DOCS} dokumen per project.`, { title: "Batas dokumen" });
      return;
    }
    const accepted = [];
    for (const file of incoming.slice(0, remaining)) {
      const ext = fileExt(file.name);
      if (!DOC_EXT.has(ext)) {
        notifyForm(`Tipe file tidak diizinkan: ${file.name}`, { title: "File tidak valid" });
        continue;
      }
      if (file.size > MAX_DOC_BYTES) {
        notifyForm(`File terlalu besar (maks 10 MB): ${file.name}`, { title: "File terlalu besar" });
        continue;
      }
      accepted.push({ type: "file", file });
    }
    if (accepted.length) {
      if (els.formError) els.formError.hidden = true;
      state.pendingDocs.push(...accepted);
      renderDocList();
    }
    if (els.docInput) els.docInput.value = "";
  }

  function addPendingUrl() {
    const url = (els.docUrl?.value || "").trim();
    const title = (els.docUrlTitle?.value || "").trim();
    if (!url) {
      notifyForm("Isi URL dokumen terlebih dahulu.", { title: "URL dokumen" });
      return;
    }
    if (!/^https?:\/\//i.test(url)) {
      notifyForm("URL harus dimulai dengan http:// atau https://", { title: "URL tidak valid" });
      return;
    }
    if (totalDocSlotsUsed() >= MAX_DOCS) {
      notifyForm(`Maksimal ${MAX_DOCS} dokumen per project.`, { title: "Batas dokumen" });
      return;
    }
    if (els.formError) els.formError.hidden = true;
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

  async function loadUsers() {
    state.users = await api("/api/team?active_only=true");
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

  async function loadDefaultOwnership() {
    try {
      const me = await api("/api/auth/me");
      state.defaultOwnership = me?.default_ownership || null;
    } catch {
      state.defaultOwnership = null;
    }
  }

  function readWorkspaceBidangId() {
    const raw = new URLSearchParams(window.location.search).get("workspace");
    const id = Number(raw);
    return Number.isFinite(id) && id > 0 ? id : null;
  }

  function findBidangMeta(bidangId) {
    if (!bidangId) return null;
    for (const [divisionId, items] of Object.entries(state.bidangsByDivision)) {
      const found = (items || []).find((b) => Number(b.id) === Number(bidangId));
      if (found) return { ...found, division_id: Number(divisionId) };
    }
    return null;
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
    els.ownerDivision.innerHTML =
      `<option value="">— Pilih Divisi —</option>` +
      state.divisions
        .map(
          (d) =>
            `<option value="${d.id}" ${String(d.id) === String(selectedId) ? "selected" : ""}>${escapeHtml(d.name)}</option>`
        )
        .join("");
  }

  async function loadBidangsForDivision(divisionId, selectedBidangId = "") {
    if (!els.ownerBidang) return;
    if (!divisionId) {
      els.ownerBidang.innerHTML = `<option value="">— Pilih Bidang —</option>`;
      return;
    }
    let items = state.bidangsByDivision[divisionId] || state.bidangsByDivision[String(divisionId)];
    if (!items) {
      await loadOrganizationOptions();
      items = state.bidangsByDivision[divisionId] || state.bidangsByDivision[String(divisionId)] || [];
    }
    els.ownerBidang.innerHTML =
      `<option value="">— Pilih Bidang —</option>` +
      (items || [])
        .map(
          (b) =>
            `<option value="${b.id}" ${String(b.id) === String(selectedBidangId) ? "selected" : ""}>${escapeHtml(b.name)}</option>`
        )
        .join("");
  }

  async function applyOwnershipToForm(project = null) {
    let kind = project?.owner_type || null;
    let divisionId = project?.owner_division_id || null;
    let bidangId = project?.owner_bidang_id || null;

    if (!project) {
      const workspaceBidangId = readWorkspaceBidangId();
      const workspaceMeta = findBidangMeta(workspaceBidangId);
      if (workspaceMeta) {
        kind = "bidang";
        divisionId = workspaceMeta.division_id;
        bidangId = workspaceMeta.id;
      } else if (state.defaultOwnership) {
        kind = state.defaultOwnership.owner_type || "unassigned";
        divisionId = state.defaultOwnership.owner_division_id || null;
        bidangId = state.defaultOwnership.owner_bidang_id || null;
      } else {
        kind = "unassigned";
      }
    }

    if (els.ownerType) els.ownerType.value = kind || "unassigned";
    fillDivisionOptions(divisionId || "");
    syncOwnershipFields();
    if ((kind || "unassigned") === "bidang") {
      await loadBidangsForDivision(divisionId || "", bidangId || "");
    } else if (els.ownerBidang) {
      els.ownerBidang.innerHTML = `<option value="">— Pilih Bidang —</option>`;
    }
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
      if (els.developedBy) els.developedBy.value = project.developed_by || "";
      if (els.workType) els.workType.value = project.work_type || "";
      setWorkCategories(project.work_categories || []);
      fillRbbYearOptions(project.rbb_year);
      if (els.rbbProgramRef) els.rbbProgramRef.value = project.rbb_program_ref || "";
      setBudgetValue(project.budget);
      if (!quill) quill = initQuill(project.description || "");
      else {
        quill.root.innerHTML = project.description || "";
        if (els.description) els.description.value = quill.root.innerHTML;
      }
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
      if (els.developedBy) els.developedBy.value = "";
      if (els.workType) els.workType.value = "";
      setWorkCategories([]);
      fillRbbYearOptions();
      if (els.rbbProgramRef) els.rbbProgramRef.value = "";
      setBudgetValue(null);
      if (!quill) quill = initQuill("");
      else {
        quill.setText("");
        if (els.description) els.description.value = "";
      }
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
    const developedBy = (els.developedBy?.value || "").trim();
    const workType = (els.workType?.value || "").trim();
    const workCategories = selectedWorkCategories();
    const rbbYearRaw = (els.rbbYear?.value || "").trim();
    const rbbYear = rbbYearRaw ? Number(rbbYearRaw) : null;
    const rbbProgramRef = (els.rbbProgramRef?.value || "").trim() || null;
    const budget = syncBudgetFromDisplay();
    const ownerType = (els.ownerType?.value || "unassigned").trim();
    const ownerDivisionId = els.ownerDivision?.value ? Number(els.ownerDivision.value) : null;
    const ownerBidangId = els.ownerBidang?.value ? Number(els.ownerBidang.value) : null;
    const payload = {
      name: document.getElementById("field-name").value.trim(),
      description: getDescriptionHtml(),
      pic: els.fieldPic.value.trim(),
      start_date: document.getElementById("field-start").value,
      end_date: document.getElementById("field-end").value,
      developed_by: developedBy || null,
      work_type: workType || null,
      work_categories: workCategories,
      rbb_year: workCategories.includes("rbb") ? rbbYear : null,
      rbb_program_ref: workCategories.includes("rbb") ? rbbProgramRef : null,
      budget,
      member_ids: state.selectedPicIds.slice(),
      owner_type: ownerType,
      owner_division_id:
        ownerType === "division" || ownerType === "bidang" ? ownerDivisionId : null,
      owner_bidang_id: ownerType === "bidang" ? ownerBidangId : null,
    };

    const missing = [];
    if (!payload.name) missing.push("nama");
    if (!developedBy) missing.push("dikembangkan oleh");
    if (!workType) missing.push("jenis pekerjaan");
    if (!workCategories.length) missing.push("kategori pekerjaan");
    if (workCategories.includes("rbb") && !rbbYear) missing.push("tahun RBB");
    if (ownerType === "division" && !ownerDivisionId) missing.push("divisi");
    if (ownerType === "bidang" && (!ownerDivisionId || !ownerBidangId)) missing.push("divisi/bidang");
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
    });
    els.picSearch.addEventListener("input", () => {
      state.picSearch = els.picSearch.value;
      state.highlightIndex = 0;
      openPicSuggest();
    });
    els.picSearch.addEventListener("keydown", (e) => {
      if (e.key === "Backspace" && !els.picSearch.value && state.selectedPicIds.length) {
        e.preventDefault();
        removePic(state.selectedPicIds[state.selectedPicIds.length - 1]);
        return;
      }
      if (els.picDropdown.hidden) {
        if (e.key === "ArrowDown" && els.picSearch.value.trim()) {
          e.preventDefault();
          openPicSuggest();
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
      if (els.picDropdown.hidden) return;
      const box = document.getElementById("pic-multiselect");
      if (box?.contains(e.target) || els.picDropdown.contains(e.target)) return;
      closePicDropdown();
    });
    window.addEventListener("resize", () => positionPicSuggest());
    document.querySelector(".main-content")?.addEventListener(
      "scroll",
      () => {
        if (!els.picDropdown.hidden) positionPicSuggest();
      },
      { passive: true }
    );
  }

  function wireDocEvents() {
    document.querySelectorAll("[data-doc-mode]").forEach((btn) => {
      btn.addEventListener("click", () => setDocMode(btn.dataset.docMode));
    });
    els.btnAddDocUrl?.addEventListener("click", addPendingUrl);
    els.docDropzone?.addEventListener("click", () => {
      if (totalDocSlotsUsed() >= MAX_DOCS) {
        notifyForm(`Maksimal ${MAX_DOCS} dokumen per project.`, { title: "Batas dokumen" });
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
    fillRbbYearOptions();
    els.workCategoryGrid?.addEventListener("change", syncRbbFieldsVisibility);
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

    await Promise.all([loadUsers(), loadOrganizationOptions(), loadDefaultOwnership()]);

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
