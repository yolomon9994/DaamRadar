"use strict";

window.DaamRadarPreferencesBackup = (() => {
  const watchKey = "daamradar.watchlist.v1";
  const budgetKey = "daamradar.shopping-budget.v1";
  const maximumBytes = 256 * 1024;
  const validSlug = (value) => typeof value === "string" && /^[-a-zA-Z0-9_]{1,280}$/.test(value);
  function money(value, positive = false) {
    if (typeof value !== "string" || !/^[0-9]{1,10}(\.[0-9]{1,2})?$/.test(value)) return null;
    const [whole, fraction = ""] = value.split(".");
    const result = whole.replace(/^0+(?=\d)/, "") + "." + fraction.padEnd(2, "0");
    return positive && !/[1-9]/.test(result) ? null : result;
  }
  function cleanTarget(raw) {
    if (!raw || !validSlug(raw.slug) || !money(raw.target, true) ||
        (raw.name !== undefined && (typeof raw.name !== "string" || raw.name.length > 255)) ||
        (raw.size !== undefined && (typeof raw.size !== "string" || raw.size.length > 80)) ||
        (raw.unresolved !== undefined && typeof raw.unresolved !== "boolean") ||
        (raw.origin_slug !== undefined && !validSlug(raw.origin_slug))) throw new Error("Invalid saved target");
    const item = {slug: raw.slug, target: money(raw.target, true), name: raw.name || raw.slug, size: raw.size || "Size unspecified"};
    if (raw.product !== undefined) item.product = window.DaamRadarListTransfer.cleanProduct(raw.product);
    if (raw.unresolved) Object.assign(item, {unresolved: true, origin_slug: raw.origin_slug || raw.slug});
    return item;
  }
  function readBudgets() {
    const raw = localStorage.getItem(budgetKey);
    if (raw === null) return {demo: null, live: null};
    const data = JSON.parse(raw);
    if (!data || Array.isArray(data) || ["demo", "live"].some((source) => data[source] !== null && money(data[source]) === null)) {
      throw new Error("Saved budgets could not be read. Review them on the shopping-list page first.");
    }
    return {demo: data.demo === null ? null : money(data.demo), live: data.live === null ? null : money(data.live)};
  }
  function mount({page, source, read, hasDrafts, unreadable, applied}) {
    const section = page.querySelector("[data-preferences-backup]");
    section.hidden = false;
    const download = section.querySelector("[data-preferences-download]");
    const fileInput = section.querySelector("[data-preferences-file]");
    const preview = section.querySelector("[data-preferences-preview]");
    const rows = section.querySelector("[data-preferences-rows]");
    const summary = section.querySelector("[data-preferences-summary]");
    const apply = section.querySelector("[data-preferences-apply]");
    const note = section.querySelector("[data-preferences-note]");
    let pending = null;
    let controller;
    let revision = 0;
    const say = (text) => { note.textContent = text; };
    const cell = (row, text) => { const td = document.createElement("td"); td.textContent = text; row.append(td); };
    function reset() {
      if (controller) controller.abort();
      revision += 1;
      pending = null;
      preview.hidden = true;
      rows.replaceChildren();
      fileInput.value = "";
      apply.disabled = true;
    }
    function update() {
      download.disabled = hasDrafts() || unreadable();
      if (pending) { reset(); say("Saved targets changed or a target was edited. Preview the backup again before restoring."); }
    }
    function signature() {
      // Include both catalogs and the raw keys, including queued tab changes.
      return JSON.stringify([read(), localStorage.getItem(watchKey), localStorage.getItem(budgetKey)]);
    }
    download.addEventListener("click", () => {
      if (hasDrafts() || unreadable()) return;
      try {
        const budgets = readBudgets();
        const documentData = {format: "daamradar-planning-preferences", version: 1, source,
          exported_at: new Date().toISOString(), budget: budgets[source], targets: read()[source].map((item) => ({
            slug: item.slug, target: item.target, name: item.name, size: item.size, product: item.product || null,
          }))};
        const blob = new Blob([JSON.stringify(documentData, null, 2) + "\n"], {type: "application/json"});
        if (blob.size > maximumBytes) throw new Error("This backup exceeds 256 KiB. Reduce the saved targets before downloading.");
        const url = URL.createObjectURL(blob);
        const link = document.createElement("a");
        link.href = url;
        link.download = `daamradar-${source}-targets-budget-${new Date().toISOString().slice(0, 10)}.json`;
        document.body.append(link); link.click(); link.remove();
        setTimeout(() => URL.revokeObjectURL(url), 1000);
        say("Backup downloaded with saved targets, product identities and this catalog's budget. Observed prices, alerts and shopping-list items are not included.");
      } catch (error) { say("Backup could not be downloaded. " + (error instanceof SyntaxError ? "Saved budgets are invalid; review them on the shopping-list page." : error.message)); }
    });
    fileInput.addEventListener("change", async () => {
      const file = fileInput.files[0];
      reset();
      if (!file) return;
      if (!file.size || file.size > maximumBytes) { say("Choose a nonempty JSON backup of at most 256 KiB."); return; }
      if (hasDrafts() || unreadable()) { say("Save or discard edited targets and resolve unreadable saved targets before previewing a backup."); return; }
      const fileRevision = revision;
      const requestController = new AbortController();
      controller = requestController;
      const timeout = setTimeout(() => requestController.abort(), 15000);
      say("Checking the backup against the local catalog…");
      try {
        const baseSignature = signature();
        const budgets = readBudgets();
        const text = (await file.text()).replace(/^\uFEFF/, "");
        if (fileRevision !== revision) return;
        const data = JSON.parse(text);
        if (data?.format !== "daamradar-planning-preferences" || data.version !== 1) throw new Error("Choose a supported targets-and-budget backup (version 1). Shopping-list JSON uses its separate transfer controls.");
        if (data.source !== source) throw new Error("This backup belongs to another catalog. Switch to its Demo or Collected watchlist before importing.");
        const response = await fetch(section.dataset.previewUrl, {method: "POST", body: text,
          headers: {"Content-Type": "application/json"}, cache: "no-store", signal: requestController.signal});
        if (!response.ok) throw new Error(response.status === 413 ? "The backup exceeds 256 KiB." : response.status === 429 ?
          "Too many preview requests. Wait a minute and retry." : "The backup could not be validated. Check its format, target amounts and product details.");
        const resolved = await response.json();
        if (fileRevision !== revision) return;
        if (signature() !== baseSignature || hasDrafts()) throw new Error("Saved targets or budgets changed while checking. Preview the backup again.");
        if (resolved.source !== source || !Array.isArray(resolved.targets) || resolved.targets.length > 50 ||
            (resolved.budget !== null && money(resolved.budget) === null)) throw new Error("Invalid preview response.");
        const entries = resolved.targets.map((item) => cleanTarget({slug: item.slug || "backup-missing-" + crypto.randomUUID(),
          target: item.target, name: item.name, size: item.size, product: item.product,
          ...(item.slug ? {} : {unresolved: true, origin_slug: item.original_slug})}));
        if (new Set(entries.map((item) => item.slug)).size !== entries.length) throw new Error("Duplicate target references in preview.");
        resolved.targets.forEach((item) => {
          const row = document.createElement("tr");
          cell(row, item.name); cell(row, item.size); cell(row, "Rs. " + item.target);
          cell(row, item.status === "matched" ? "Matched to local product" : "Unmatched — no price alert"); cell(row, item.reason);
          rows.append(row);
        });
        summary.textContent = `Replace ${read()[source].length} saved target(s) with ${entries.length}; ${entries.filter((item) => item.unresolved).length} need review. Budget: ${budgets[source] === null ? "not set" : "Rs. " + budgets[source]} → ${resolved.budget === null ? "remove budget" : "Rs. " + resolved.budget}. Only this ${source === "demo" ? "Demo" : "Collected"} catalog's targets and budget change. Shopping-list items are kept.`;
        pending = {entries, budget: resolved.budget, baseSignature};
        preview.hidden = false;
        apply.disabled = false;
        say("Preview ready. Review the matches and budget change. Nothing has been restored yet.");
      } catch (error) {
        if (fileRevision === revision) {
          rows.replaceChildren();
          say((error.name === "AbortError" ? "Preview timed out. Check the local server and choose the file again." :
            error instanceof SyntaxError ? "This is not valid JSON." : error.message) + " Your saved preferences are unchanged.");
        }
      } finally { clearTimeout(timeout); }
    });
    section.querySelector("[data-preferences-cancel]").addEventListener("click", () => { reset(); say("Restore cancelled. Your saved preferences are unchanged."); });
    apply.addEventListener("click", () => {
      if (!pending || hasDrafts() || unreadable()) return;
      let originalWatch, originalBudget;
      let next;
      let wroteWatch = false;
      let wroteBudget = false;
      try {
        if (signature() !== pending.baseSignature) { reset(); say("Saved targets or budgets changed. Preview the backup again before restoring."); return; }
        next = {demo: read().demo.map(cleanTarget), live: read().live.map(cleanTarget)};
        next[source] = pending.entries.map(cleanTarget);
        const budgets = readBudgets();
        budgets[source] = pending.budget;
        originalWatch = localStorage.getItem(watchKey);
        originalBudget = localStorage.getItem(budgetKey);
        // Web Storage has no multi-key transaction. Do not change page state
        // until both writes succeed; roll back a successful first write on failure.
        localStorage.setItem(watchKey, JSON.stringify(next)); wroteWatch = true;
        localStorage.setItem(budgetKey, JSON.stringify(budgets)); wroteBudget = true;
      } catch (_) {
        let rolledBack = true;
        for (const [storageKey, original, wrote] of [[budgetKey, originalBudget, wroteBudget], [watchKey, originalWatch, wroteWatch]]) {
          if (!wrote) continue;
          try { if (original === null) localStorage.removeItem(storageKey); else localStorage.setItem(storageKey, original); }
          catch (_) { rolledBack = false; }
        }
        reset();
        say(rolledBack ? "Restore could not be saved. Existing targets and budgets were kept. Allow browser storage or free space, then preview the backup again." :
          "Restore could not finish and browser storage prevented a full rollback. Reload both lists and review targets and budgets before continuing; keep your backup file.");
        return;
      }
      reset();
      applied(next);
      say("Targets and budget restored and saved in this browser. Target checks reload from the local database; shopping-list items are kept.");
    });
    window.addEventListener("storage", (event) => {
      if (![watchKey, budgetKey, null].includes(event.key)) return;
      const hadPreview = pending !== null;
      reset();
      if (hadPreview) say("Saved targets or budgets changed in another tab. Preview the backup again.");
    });
    window.addEventListener("pagehide", reset);
    update();
    return update;
  }
  return Object.freeze({money, cleanTarget, mount});
})();
