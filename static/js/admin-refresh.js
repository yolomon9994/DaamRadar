"use strict";

(() => {
  const panel = document.querySelector("[data-admin-refresh]");
  if (!panel || panel.dataset.active !== "true" || panel.dataset.needsAttention === "true") return;
  const note = panel.querySelector("[data-refresh-poll-note]");
  let failures = 0;
  const schedule = () => setTimeout(poll, 3000);
  async function poll() {
    if (document.hidden) { schedule(); return; }
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 10000);
    try {
      const response = await fetch(panel.dataset.statusUrl, {cache: "no-store", signal: controller.signal});
      if (!response.ok || !response.headers.get("Content-Type")?.includes("application/json")) throw new Error("Progress unavailable");
      const data = await response.json();
      panel.querySelector("[data-refresh-status]").textContent = data.status_label;
      panel.querySelector("[data-refresh-error]").textContent = data.error;
      data.sources.forEach((source) => {
        const row = [...panel.querySelectorAll("[data-refresh-source]")].find((node) => node.dataset.refreshSource === source.retailer);
        if (!row) return;
        row.querySelector("[data-source-outcome]").textContent = source.outcome_label;
        row.querySelector("[data-source-stored]").textContent = source.products_collected;
        row.querySelector("[data-source-requests]").textContent = source.request_count;
        row.querySelector("[data-source-error]").textContent = source.error;
        const progress = row.querySelector("[data-source-progress]");
        progress.max = Math.max(source.target_count, 1);
        progress.value = source.finished_count;
        row.querySelector("[data-source-count]").textContent = `${source.finished_count} of ${source.target_count} URLs finished`;
        const run = row.querySelector("[data-source-run]");
        run.replaceChildren();
        if (source.run_id) {
          const link = document.createElement("a");
          link.href = "/admin/catalog/scraperun/" + Number(source.run_id) + "/change/";
          link.textContent = "Run #" + source.run_id + " · " + source.run_status;
          run.append(link);
        } else run.textContent = "No collection run";
        const results = row.querySelector("[data-source-results]");
        results.replaceChildren();
        source.url_results.forEach((result) => {
          const item = document.createElement("li");
          item.textContent = result.url + " — " + result.status;
          results.append(item);
        });
      });
      failures = 0;
      note.textContent = "Progress updated. Source delays are normal; this page does not initiate additional collection.";
      if (!data.is_active) { location.reload(); return; }
      if (data.needs_attention) { note.textContent = "Operator attention is needed. Inspect the error and owned collection runs before recovery."; return; }
      schedule();
    } catch (_) {
      failures += 1;
      note.textContent = "Progress could not be loaded. Use Refresh progress to retry; no new collection was started.";
      if (failures < 3) schedule();
    } finally {
      clearTimeout(timeout);
    }
  }
  schedule();
})();
