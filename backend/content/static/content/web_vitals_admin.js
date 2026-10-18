/* Superuser Django Admin-only real-user p75 summary. No analytics data is sent off-site. */
(() => {
  "use strict";

  function init() {
    const root = document.getElementById("amaris-web-vitals-dashboard");
    if (!root) return;
    const select = document.getElementById("amaris-rum-period");
    const status = document.getElementById("amaris-rum-status");
    const table = document.getElementById("amaris-rum-table");
    const tbody = table?.tBodies?.[0];
    const endpoint = root.dataset.reportUrl;
    if (!select || !status || !table || !tbody || !endpoint) return;

    let requestCounter = 0;

    async function refresh() {
      const serial = ++requestCounter;
      status.textContent = "Loading private performance report…";
      table.hidden = true;
      tbody.replaceChildren();

      try {
        const days = select.value;
        if (!["7", "28", "90"].includes(days)) throw new Error("Invalid period");
        const url = new URL(endpoint, window.location.origin);
        if (url.origin !== window.location.origin) throw new Error("Unexpected report URL");
        url.searchParams.set("days", days);
        const response = await fetch(url.href, {
          method: "GET",
          credentials: "same-origin",
          headers: { Accept: "application/json" },
          cache: "no-store",
          redirect: "error",
        });
        if (!response.ok) throw new Error("Report unavailable");
        const report = await response.json();
        if (serial !== requestCounter) return;
        if (!Array.isArray(report.groups)) throw new Error("Unexpected report format");

        const metrics = { LCP: "ms", INP: "ms", CLS: "" };
        for (const group of report.groups) {
          if (!Object.hasOwn(metrics, group.metric)) continue;
          const row = document.createElement("tr");
          const n = Number.isInteger(group.samples) && group.samples >= 0 ? group.samples : 0;
          const ready = n >= 20 && Number.isFinite(group.p75) && group.p75 >= 0;
          const fields = [
            group.metric,
            String(group.page || ""),
            String(group.device || ""),
            String(n),
            ready ? (group.metric === "CLS" ? group.p75.toFixed(3) : Math.round(group.p75) + " ms") : "Insufficient data",
            ready ? (group.status === "good" ? "Good" : "Needs improvement") : "Awaiting ≥20 valid samples",
          ];
          for (const field of fields) {
            const cell = document.createElement("td");
            // textContent is intentional: responses never become executable HTML.
            cell.textContent = field;
            row.appendChild(cell);
          }
          tbody.appendChild(row);
        }

        if (tbody.rows.length === 0) {
          status.textContent = "No browser measurements yet for this period. Values will appear only after enough real traffic.";
        } else {
          table.hidden = false;
          status.textContent = `Showing ${tbody.rows.length} metric/page/device groups for the last ${days} days. Fewer than 20 events means insufficient data.`;
        }
      } catch {
        if (serial === requestCounter) {
          status.textContent = "Performance summary could not be loaded. Verify Django superuser access and backend availability.";
        }
      }
    }

    select.addEventListener("change", () => { void refresh(); });
    void refresh();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init, { once: true });
  } else {
    init();
  }
})();
