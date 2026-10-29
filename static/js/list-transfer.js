"use strict";

// File transfers store identities/quantities only. Catalog prices never enter a file.
window.DaamRadarListTransfer = (() => {
  const maximumBytes = 256 * 1024;
  const validSlug = (value) => typeof value === "string" && value.length > 0 && value.length <= 280 && !/[^-a-zA-Z0-9_]/.test(value);
  const fields = {name: 255, brand: 100, unit: 2, variant: 120, packaging: 40, gtin: 14, size: 80};
  function cleanProduct(raw) {
    if (raw === null || raw === undefined) return null;
    if (typeof raw !== "object" || Array.isArray(raw)) throw new Error("Invalid saved product details");
    const product = {};
    for (const [field, limit] of Object.entries(fields)) {
      const value = raw[field] ?? (field === "size" ? "Size unspecified" : undefined);
      if (typeof value !== "string" || value.length > limit) throw new Error("Invalid saved product details");
      product[field] = value;
    }
    if (!product.name || !["", "ml", "g", "pc"].includes(product.unit) ||
        !Number.isInteger(raw.pack_count) || raw.pack_count < 1 || raw.pack_count > 32767 ||
        (raw.quantity !== null && (typeof raw.quantity !== "string" || !/^\d{1,7}(\.\d{1,3})?$/.test(raw.quantity) || Number(raw.quantity) <= 0)) ||
        (raw.quantity === null) !== (product.unit === "")) throw new Error("Invalid saved product details");
    product.quantity = raw.quantity;
    product.pack_count = raw.pack_count;
    return product;
  }
  function cleanEntry(raw) {
    if (!raw || !validSlug(raw.slug) || !Number.isInteger(raw.quantity) || raw.quantity < 1 || raw.quantity > 99 ||
        (raw.origin_slug !== undefined && !validSlug(raw.origin_slug)) ||
        (raw.unresolved !== undefined && typeof raw.unresolved !== "boolean")) throw new Error("Invalid saved list item");
    const item = {slug: raw.slug, quantity: raw.quantity};
    if (raw.product !== undefined) item.product = cleanProduct(raw.product);
    if (raw.unresolved) {
      item.unresolved = true;
      item.origin_slug = raw.origin_slug || raw.slug;
    }
    return item;
  }
  function mergeKey(item) {
    return item.unresolved ? JSON.stringify(["unpriced", item.origin_slug, item.product || null]) : "product:" + item.slug;
  }
  function mergeEntries(current, incoming, replace) {
    const entries = (replace ? [] : current).map((item) => cleanEntry(item));
    const keys = new Map(entries.map((item, index) => [mergeKey(item), index]));
    for (const raw of incoming) {
      const item = cleanEntry(raw);
      const key = mergeKey(item);
      if (keys.has(key)) {
        const existing = entries[keys.get(key)];
        if (existing.quantity + item.quantity > 99) throw new Error("Combining these lists would exceed 99 packs for a product. Adjust quantities or choose Replace.");
        existing.quantity += item.quantity;
      } else {
        keys.set(key, entries.length);
        entries.push(item);
      }
    }
    if (entries.length > 50) throw new Error("The combined list would exceed 50 products. Remove some items or choose Replace.");
    return entries;
  }

  function mount({page, source, read, commit, hasInvalidQuantities}) {
    const section = page.querySelector("[data-list-transfer]");
    if (!section) return () => {};
    section.hidden = false;
    const download = section.querySelector("[data-list-download]");
    const input = section.querySelector("[data-list-file]");
    const preview = section.querySelector("[data-transfer-preview]");
    const rows = section.querySelector("[data-transfer-rows]");
    const note = section.querySelector("[data-transfer-note]");
    const summary = section.querySelector("[data-transfer-summary]");
    const apply = section.querySelector("[data-transfer-apply]");
    let pending = null;
    let proposed = null;
    let baseSignature = "";
    let revision = 0;
    let controller;
    const say = (message) => { note.textContent = message; };
    const cell = (row, text) => { const node = document.createElement("td"); node.textContent = text; row.append(node); };
    function reset() {
      if (controller) controller.abort();
      revision += 1;
      pending = proposed = null;
      preview.hidden = true;
      rows.replaceChildren();
      input.value = "";
      apply.disabled = true;
    }
    function update() {
      download.disabled = !read().length || hasInvalidQuantities();
      if (!pending) return;
      const replace = section.querySelector("[data-transfer-mode]:checked").value === "replace";
      try {
        if (hasInvalidQuantities()) throw new Error("Correct the current list's quantities before applying a file.");
        const current = read();
        proposed = mergeEntries(current, pending.entries, replace);
        baseSignature = JSON.stringify(current);
        const unmatched = proposed.filter((item) => item.unresolved).length;
        summary.textContent = `${replace ? "Replace" : "Merge"}: ${current.length} current → ${proposed.length} resulting products. ${unmatched} unpriced item(s) will need review. Only this ${source === "demo" ? "demo" : "collected"} list changes.`;
        apply.textContent = replace ? "Replace current list" : "Apply merge";
        apply.disabled = false;
      } catch (error) {
        proposed = null;
        summary.textContent = error.message;
        apply.disabled = true;
      }
    }
    download.addEventListener("click", () => {
      const current = read();
      if (!current.length || hasInvalidQuantities()) return;
      const documentData = {format: "daamradar-shopping-list", version: 1, source,
        exported_at: new Date().toISOString(), items: current.map((item) => ({
          slug: item.slug, quantity: item.quantity, product: item.product || null,
        }))};
      const blob = new Blob([JSON.stringify(documentData, null, 2) + "\n"], {type: "application/json"});
      if (blob.size > maximumBytes) { say("This list exceeds the 256 KiB file limit. Reduce its size before exporting."); return; }
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = `daamradar-${source}-list-${new Date().toISOString().slice(0, 10)}.json`;
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 1000);
      say("List downloaded with identities and quantities only. Prices and purchase marks are not included.");
    });
    input.addEventListener("change", async () => {
      const file = input.files[0];
      reset();
      if (!file) return;
      if (file.size === 0 || file.size > maximumBytes) { say("Choose a nonempty JSON list file of at most 256 KiB."); return; }
      const fileRevision = revision;
      const requestController = new AbortController();
      controller = requestController;
      const timeout = setTimeout(() => requestController.abort(), 15000);
      say("Checking the file against the local catalog…");
      try {
        const text = (await file.text()).replace(/^\uFEFF/, "");
        if (fileRevision !== revision) return;
        const data = JSON.parse(text);
        if (!data || data.format !== "daamradar-shopping-list" || data.version !== 1 || !["demo", "live"].includes(data.source)) throw new Error("Choose a supported DaamRadar shopping-list JSON export (version 1).");
        if (data.source !== source) throw new Error(`This file contains a ${data.source === "demo" ? "demo" : "collected"} list. Switch to that catalog's list before importing.`);
        const response = await fetch(page.dataset.transferUrl, {method: "POST", body: text,
          headers: {"Content-Type": "application/json"}, cache: "no-store", signal: requestController.signal});
        if (!response.ok) throw new Error(response.status === 413 ? "The file exceeds 256 KiB." :
          response.status === 429 ? "Too many preview requests. Wait a minute and retry." : "The file could not be validated. Check its format, quantities and product details; no list was changed.");
        const resolved = await response.json();
        if (fileRevision !== revision) return;
        const entries = resolved.items.map((item) => {
          const product = cleanProduct(item.product);
          const previous = !item.slug && read().find((saved) => saved.unresolved &&
            (saved.slug === item.original_slug || saved.origin_slug === item.original_slug) &&
            JSON.stringify(saved.product || null) === JSON.stringify(product));
          return cleanEntry({slug: item.slug || previous?.slug || "transfer-missing-" + crypto.randomUUID(),
            quantity: item.quantity, product, ...(item.slug ? {} : {unresolved: true, origin_slug: previous?.origin_slug || item.original_slug})});
        });
        pending = {entries};
        rows.replaceChildren();
        resolved.items.forEach((item) => {
          const row = document.createElement("tr");
          cell(row, item.imported_name);
          cell(row, item.product?.size || "Size unavailable");
          cell(row, item.quantity);
          cell(row, item.status === "matched" ? "Matched: " + item.product.name : "Unpriced — review needed");
          cell(row, item.reason);
          rows.append(row);
        });
        preview.hidden = false;
        update();
        say("Preview ready. Review the matches and choose Merge or Replace. Nothing has been applied yet.");
      } catch (error) {
        if (fileRevision === revision) say(error.name === "AbortError" ? "Preview timed out. Check the local server and choose the file again; your list is unchanged." :
          error instanceof SyntaxError ? "This file is not valid JSON. Your list is unchanged." : error.message);
      } finally {
        clearTimeout(timeout);
      }
    });
    section.querySelectorAll("[data-transfer-mode]").forEach((node) => node.addEventListener("change", update));
    section.querySelector("[data-transfer-cancel]").addEventListener("click", () => { reset(); say("Import cancelled. Your list is unchanged."); });
    apply.addEventListener("click", () => {
      if (!pending || !proposed || hasInvalidQuantities()) return;
      if (JSON.stringify(read()) !== baseSignature) {
        update();
        say("The current list changed. Review the updated totals before applying again.");
        return;
      }
      const next = proposed.map((item) => cleanEntry(item));
      reset();
      const persisted = commit(next);
      say(persisted ? "List applied and saved in this browser. Estimates are reloaded from the local database." :
        "List applied on this page only; browser storage is unavailable. Download it to keep a copy.");
    });
    update();
    return update;
  }
  return Object.freeze({cleanEntry, cleanProduct, mount});
})();
