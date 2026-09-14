document.addEventListener("DOMContentLoaded", function () {
    initDeleteConfirmation();
    initMobileNav();
    initProjectFilter();
    initFlashDismiss();
});

/* -----------------------------------------------------------------------
   Delete confirmation
   Every form with class "delete-form" gets a confirm() prompt before it
   is allowed to submit.
   ----------------------------------------------------------------------- */
function initDeleteConfirmation() {
    document.querySelectorAll("form.delete-form").forEach(function (form) {
        form.addEventListener("submit", function (event) {
            var confirmed = window.confirm("Are you sure you want to delete this project?");
            if (!confirmed) {
                event.preventDefault();
            }
        });
    });
}

/* -----------------------------------------------------------------------
   Mobile navigation
   Toggles the sidebar in/out on small screens and closes it when the
   overlay behind it is tapped.
   ----------------------------------------------------------------------- */
function initMobileNav() {
    var toggle = document.getElementById("mobileNavToggle");
    var sidebar = document.getElementById("sidebar");
    var overlay = document.getElementById("sidebarOverlay");
    if (!toggle || !sidebar || !overlay) return;

    function closeNav() {
        sidebar.classList.remove("open");
        overlay.classList.remove("visible");
        toggle.setAttribute("aria-expanded", "false");
    }

    function openNav() {
        sidebar.classList.add("open");
        overlay.classList.add("visible");
        toggle.setAttribute("aria-expanded", "true");
    }

    toggle.addEventListener("click", function () {
        var isOpen = sidebar.classList.contains("open");
        if (isOpen) {
            closeNav();
        } else {
            openNav();
        }
    });

    overlay.addEventListener("click", closeNav);

    // Close automatically after choosing a nav link (mobile only).
    sidebar.querySelectorAll("a").forEach(function (link) {
        link.addEventListener("click", closeNav);
    });
}

/* -----------------------------------------------------------------------
   Projects search / status filter
   Filters table rows client-side by client name, project name, and the
   selected status - no page reload required.
   ----------------------------------------------------------------------- */
function initProjectFilter() {
    var searchInput = document.getElementById("projectSearch");
    var statusSelect = document.getElementById("statusFilter");
    var table = document.getElementById("projectsTable");
    var noResults = document.getElementById("noResultsRow");
    if (!table) return;

    var rows = Array.prototype.slice.call(table.querySelectorAll("tbody tr"));

    function applyFilter() {
        var query = searchInput ? searchInput.value.trim().toLowerCase() : "";
        var status = statusSelect ? statusSelect.value : "";
        var visibleCount = 0;

        rows.forEach(function (row) {
            var client = row.getAttribute("data-client") || "";
            var project = row.getAttribute("data-project") || "";
            var rowStatus = row.getAttribute("data-status") || "";

            var matchesQuery = !query || client.indexOf(query) !== -1 || project.indexOf(query) !== -1;
            var matchesStatus = !status || rowStatus === status;
            var visible = matchesQuery && matchesStatus;

            row.hidden = !visible;
            if (visible) visibleCount++;
        });

        if (noResults) {
            noResults.hidden = visibleCount !== 0;
        }
    }

    if (searchInput) searchInput.addEventListener("input", applyFilter);
    if (statusSelect) statusSelect.addEventListener("change", applyFilter);
}

/* -----------------------------------------------------------------------
   Flash message dismissal
   ----------------------------------------------------------------------- */
function initFlashDismiss() {
    document.querySelectorAll(".alert-close").forEach(function (button) {
        button.addEventListener("click", function () {
            var alertEl = button.closest(".alert");
            if (alertEl) alertEl.remove();
        });
    });
}
