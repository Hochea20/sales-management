function confirmDelete() {
  return window.confirm("Confirmer la suppression ?");
}

function applyTheme(theme) {
  document.documentElement.setAttribute("data-theme", theme);
  const icon = document.querySelector("#themeToggle i");
  if (icon) {
    icon.className = theme === "dark" ? "bi bi-sun" : "bi bi-moon-stars";
  }
}

function applySidebarState(collapsed) {
  document.body.classList.toggle("sidebar-collapsed", collapsed);
  const icon = document.querySelector("#sidebarToggle i");
  if (icon) {
    icon.className = collapsed ? "bi bi-layout-sidebar" : "bi bi-layout-sidebar-inset";
  }
}

function initSidebar() {
  const toggle = document.getElementById("sidebarToggle");
  if (!toggle) return;
  const saved = localStorage.getItem("crm_sidebar_collapsed") === "1";
  applySidebarState(saved);
  toggle.addEventListener("click", function () {
    const collapsed = !document.body.classList.contains("sidebar-collapsed");
    localStorage.setItem("crm_sidebar_collapsed", collapsed ? "1" : "0");
    applySidebarState(collapsed);
  });
}

function initTheme() {
  const saved = localStorage.getItem("crm_theme");
  const theme = saved === "dark" ? "dark" : "light";
  applyTheme(theme);
  const toggle = document.getElementById("themeToggle");
  if (!toggle) return;
  toggle.addEventListener("click", function () {
    const current = document.documentElement.getAttribute("data-theme") || "light";
    const next = current === "dark" ? "light" : "dark";
    localStorage.setItem("crm_theme", next);
    applyTheme(next);
  });
}

function initAdminUsersPage() {
  const editForm = document.getElementById("editUserForm");
  const createForm = document.getElementById("createUserForm");
  const editButtons = document.querySelectorAll(".user-edit-btn");
  const editModal = document.getElementById("editUserModal");

  // Keep Bootstrap modal at document root to avoid stacking/pointer issues
  // when parent containers use visual effects (e.g. backdrop-filter).
  if (editModal && editModal.parentElement !== document.body) {
    document.body.appendChild(editModal);
  }

  if (createForm) {
    createForm.reset();
  }

  if (editForm && editButtons.length > 0) {
    const usernameInput = document.getElementById("editUsername");
    const emailInput = document.getElementById("editEmail");
    const roleSelect = document.getElementById("editRole");
    const activeSelect = document.getElementById("editIsActive");
    const newPasswordInput = document.getElementById("editNewPassword");
    editButtons.forEach(function (btn) {
      btn.addEventListener("click", function () {
        const userId = btn.getAttribute("data-user-id");
        editForm.action = `/admin/users/${userId}/update`;
        usernameInput.value = btn.getAttribute("data-username") || "";
        emailInput.value = btn.getAttribute("data-email") || "";
        roleSelect.value = btn.getAttribute("data-role") || "sales";
        activeSelect.value = btn.getAttribute("data-is-active") || "1";
        if (newPasswordInput) newPasswordInput.value = "";
      });
    });
  }

  if (editForm && editModal) {
    editModal.addEventListener("hidden.bs.modal", function () {
      editForm.reset();
    });
  }
}

function initClientsProspectionTools() {
  const checks = Array.from(document.querySelectorAll(".client-prospect-check"));
  if (!checks.length) return;

  const selectAll = document.getElementById("selectAllClients");
  const countBadge = document.getElementById("clientProspectCount");
  const copyEmailsBtn = document.getElementById("copySelectedClientEmails");
  const copyPhonesBtn = document.getElementById("copySelectedClientPhones");
  const exportCsvBtn = document.getElementById("exportSelectedClientsCsv");

  function selectedRows() {
    return checks.filter((c) => c.checked);
  }

  function updateCount() {
    if (!countBadge) return;
    const n = selectedRows().length;
    countBadge.textContent = `${n} sélectionné(s)`;
  }

  async function copyText(text, emptyMessage) {
    if (!text) {
      window.alert(emptyMessage);
      return;
    }
    try {
      await navigator.clipboard.writeText(text);
      window.alert("Copié.");
    } catch (_err) {
      window.alert("Impossible de copier automatiquement. Sélectionnez et copiez manuellement.");
    }
  }

  if (selectAll) {
    selectAll.addEventListener("change", function () {
      checks.forEach((c) => {
        c.checked = selectAll.checked;
      });
      updateCount();
    });
  }

  checks.forEach((c) =>
    c.addEventListener("change", function () {
      const allChecked = checks.length > 0 && checks.every((x) => x.checked);
      if (selectAll) selectAll.checked = allChecked;
      updateCount();
    })
  );

  if (copyEmailsBtn) {
    copyEmailsBtn.addEventListener("click", function () {
      const emails = selectedRows()
        .map((c) => (c.getAttribute("data-email") || "").trim())
        .filter((v) => v.length > 0);
      copyText(emails.join("; "), "Aucun email trouvé dans la sélection.");
    });
  }

  if (copyPhonesBtn) {
    copyPhonesBtn.addEventListener("click", function () {
      const phones = selectedRows()
        .map((c) => (c.getAttribute("data-phone") || "").trim())
        .filter((v) => v.length > 0);
      copyText(phones.join("; "), "Aucun téléphone trouvé dans la sélection.");
    });
  }

  if (exportCsvBtn) {
    exportCsvBtn.addEventListener("click", function () {
      const rows = selectedRows();
      if (!rows.length) {
        window.alert("Veuillez sélectionner au moins un client.");
        return;
      }

      const headers = ["Nom", "Entreprise", "Lieu", "Email", "Téléphone"];
      const esc = (v) => `"${String(v || "").replace(/"/g, '""')}"`;
      const lines = [headers.map(esc).join(",")];
      rows.forEach((r) => {
        lines.push(
          [
            r.getAttribute("data-name"),
            r.getAttribute("data-company"),
            r.getAttribute("data-location"),
            r.getAttribute("data-email"),
            r.getAttribute("data-phone"),
          ]
            .map(esc)
            .join(",")
        );
      });

      const blob = new Blob([`\uFEFF${lines.join("\n")}`], { type: "text/csv;charset=utf-8;" });
      const url = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = url;
      a.download = "clients_selection_prospection.csv";
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(url);
    });
  }

  updateCount();
}

function initTableTopScrollSync() {
  const scrollTargets = document.querySelectorAll("[data-top-scroll-sync]");
  const ro = typeof ResizeObserver !== "undefined" ? new ResizeObserver(() => updateAll()) : null;
  const instances = [];

  function setupOne(target, index) {
    const host = target.parentElement;
    if (!host) return;

    host.classList.add("table-scroll-host");

    let topBar = host.querySelector(`.table-top-scrollbar[data-sync-id="${index}"]`);
    if (!topBar) {
      topBar = document.createElement("div");
      topBar.className = "table-top-scrollbar";
      topBar.setAttribute("data-sync-id", String(index));
      const inner = document.createElement("div");
      inner.className = "table-top-scrollbar-inner";
      topBar.appendChild(inner);
      host.insertBefore(topBar, target);
    }
    const topInner = topBar.querySelector(".table-top-scrollbar-inner");
    if (!topInner) return;

    let syncing = false;
    const syncFromTop = function () {
      if (syncing) return;
      syncing = true;
      target.scrollLeft = topBar.scrollLeft;
      syncing = false;
    };
    const syncFromTable = function () {
      if (syncing) return;
      syncing = true;
      topBar.scrollLeft = target.scrollLeft;
      syncing = false;
    };

    topBar.addEventListener("scroll", syncFromTop);
    target.addEventListener("scroll", syncFromTable);

    const update = function () {
      topInner.style.width = `${target.scrollWidth}px`;
      const needsHorizontal = target.scrollWidth > target.clientWidth + 2;
      topBar.style.display = needsHorizontal ? "block" : "none";
      if (!needsHorizontal) {
        target.scrollLeft = 0;
        topBar.scrollLeft = 0;
      }
    };

    if (ro) {
      ro.observe(target);
    }
    instances.push(update);
    update();
  }

  function updateAll() {
    instances.forEach((fn) => fn());
  }

  scrollTargets.forEach((target, idx) => setupOne(target, idx));
  window.addEventListener("resize", updateAll);
  // Some layouts/fonts settle after initial paint.
  window.setTimeout(updateAll, 120);
  window.setTimeout(updateAll, 500);
}

function initExplicitTopScrollbars() {
  function bind(topId, innerId, targetId) {
    const top = document.getElementById(topId);
    const inner = document.getElementById(innerId);
    const target = document.getElementById(targetId);
    if (!top || !inner || !target) return;

    let syncing = false;
    const update = function () {
      inner.style.width = `${target.scrollWidth}px`;
      // Explicit bars: keep visible so users can always discover horizontal scroll.
      top.style.display = "block";
    };

    top.addEventListener("scroll", function () {
      if (syncing) return;
      syncing = true;
      target.scrollLeft = top.scrollLeft;
      syncing = false;
    });
    target.addEventListener("scroll", function () {
      if (syncing) return;
      syncing = true;
      top.scrollLeft = target.scrollLeft;
      syncing = false;
    });
    window.addEventListener("resize", update);
    update();
    window.setTimeout(update, 120);
    window.setTimeout(update, 500);
  }

  bind("clientsTopScrollbar", "clientsTopScrollbarInner", "clientsTableScroll");
  bind("pipelineTopScrollbar", "pipelineTopScrollbarInner", "pipelineBoardScroll");
}

document.addEventListener("DOMContentLoaded", function () {
  initTheme();
  initSidebar();
  initAdminUsersPage();
  initClientsProspectionTools();
  initTableTopScrollSync();
  initExplicitTopScrollbars();
});
