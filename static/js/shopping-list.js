"use strict";

(() => {
  const key = "daamradar.shopping-list.v1";
  const page = document.querySelector("[data-shopping-list]");
  const feedback = document.querySelector("[data-list-feedback]");
  let storageWarning = "";
  let state = {demo: [], live: []};
  let controller;
  let revision = 0;
  const names = new Map();
  const source = page ? page.dataset.source : null;
  const validSource = (value) => value === "demo" || value === "live";
  const validSlug = (value) => typeof value === "string" && value.length > 0 && value.length <= 280 && !/[^-a-zA-Z0-9_]/.test(value);

  function load() {
    try {
      const raw = localStorage.getItem(key);
      if (raw === null) return {demo: [], live: []};
      const saved = JSON.parse(raw);
      for (const catalog of ["demo", "live"]) {
        const entries = saved[catalog];
        if (!Array.isArray(entries) || entries.length > 50) throw new Error("Invalid saved list");
        const seen = new Set();
        for (const item of entries) {
          if (!item || !validSlug(item.slug) || !Number.isInteger(item.quantity) ||
              item.quantity < 1 || item.quantity > 99 || seen.has(item.slug)) throw new Error("Invalid saved item");
          seen.add(item.slug);
        }
      }
      return {demo: saved.demo.map(({slug, quantity}) => ({slug, quantity})),
        live: saved.live.map(({slug, quantity}) => ({slug, quantity}))};
    } catch (_) {
      storageWarning = "Saved lists could not be read. This page will use an empty list until you add products.";
      return {demo: [], live: []};
    }
  }

  function notify(message, catalog) {
    if (!feedback) return;
    feedback.hidden = false;
    feedback.replaceChildren(document.createTextNode(message + " "));
    if (validSource(catalog)) {
      const link = document.createElement("a");
      link.href = "/shopping-list/?source=" + catalog;
      link.textContent = "View list";
      feedback.append(link);
    }
  }

  function save() {
    try {
      localStorage.setItem(key, JSON.stringify(state));
      return true;
    } catch (_) {
      notify("Browser storage is unavailable or full. Changes last only on this page.");
      return false;
    }
  }

  function updateCounts() {
    document.querySelectorAll("[data-list-total]").forEach((node) => {
      node.textContent = state.demo.length + state.live.length;
    });
    document.querySelectorAll("[data-list-count]").forEach((node) => {
      node.textContent = state[node.dataset.listCount].length;
    });
  }

  state = load();
  updateCounts();
  if (storageWarning) notify(storageWarning);
  document.querySelectorAll("[data-list-add]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", () => {
      const catalog = button.dataset.listSource;
      const slug = button.dataset.listAdd;
      if (!validSource(catalog) || !validSlug(slug)) return;
      const item = state[catalog].find((entry) => entry.slug === slug);
      if (item && item.quantity === 99) return notify("This product already has the maximum quantity of 99.", catalog);
      if (!item && state[catalog].length === 50) return notify("Your list has 50 products. Remove one before adding another.", catalog);
      if (item) item.quantity += 1;
      else state[catalog].push({slug, quantity: 1});
      const persisted = save();
      updateCounts();
      if (persisted) notify("Product added to your " + (catalog === "demo" ? "demo" : "collected") + " list.", catalog);
    });
  });

  // Keep separate tabs synchronized; the server never stores the shopping list.
  window.addEventListener("storage", (event) => {
    if (event.key !== key && event.key !== null) return;
    state = load();
    updateCounts();
    if (page) refresh(true);
  });
  if (!page) return;

  const list = page.querySelector("[data-list-items]");
  const content = page.querySelector("[data-list-content]");
  const empty = page.querySelector("[data-list-empty]");
  const message = page.querySelector("[data-list-message]");
  const estimates = page.querySelector("[data-list-estimates]");
  const refreshButton = page.querySelector("[data-list-refresh]");
  const statusLabels = {
    included: "Included", missing: "Not listed by this retailer", product_unavailable: "Product removed or unavailable in this catalog",
    stale: "Stale observation — excluded", availability_unknown: "Stock unknown — excluded",
    out_of_stock: "Out of stock — excluded", area_ambiguous: "Multiple delivery areas — choose an area before estimating",
  };
  const money = (value) => "Rs. " + Number(value).toLocaleString("en-PK", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  function updateNames() {
    list.querySelectorAll("[data-item-name]").forEach((node) => {
      const info = names.get(node.dataset.itemName);
      node.textContent = info ? info.name : node.dataset.itemName;
      if (info && !info.available) {
        node.removeAttribute("href");
        node.setAttribute("aria-disabled", "true");
      } else {
        node.href = "/products/" + encodeURIComponent(node.dataset.itemName) + "/";
        node.removeAttribute("aria-disabled");
      }
      const row = node.closest("li");
      if (info && row) {
        row.querySelector("input").setAttribute("aria-label", "Quantity for " + info.name);
        row.querySelector("button").setAttribute("aria-label", "Remove " + info.name);
      }
    });
  }
  function renderItems() {
    list.replaceChildren();
    state[source].forEach((item) => {
      const row = element("li", undefined, "shopping-item");
      const link = element("a", item.slug);
      link.href = "/products/" + encodeURIComponent(item.slug) + "/";
      link.dataset.itemName = item.slug;
      const quantityLabel = element("label", "Packs ");
      const input = document.createElement("input");
      Object.assign(input, {type: "number", min: "1", max: "99", step: "1", value: item.quantity});
      input.setAttribute("aria-label", "Quantity for " + (names.get(item.slug)?.name || item.slug));
      input.addEventListener("input", () => {
        if (!input.validity.valid || !/^[1-9][0-9]?$/.test(input.value)) {
          if (controller) controller.abort();
          revision += 1;
          input.setAttribute("aria-invalid", "true");
          estimates.replaceChildren();
          estimates.removeAttribute("aria-busy");
          message.textContent = "Enter a whole quantity from 1 to 99 to update estimates. The last valid quantity is saved.";
          return;
        }
        input.removeAttribute("aria-invalid");
        item.quantity = Number(input.value);
        save();
        refresh(false);
      });
      quantityLabel.append(input);
      const remove = element("button", "Remove", "list-action");
      remove.type = "button";
      remove.setAttribute("aria-label", "Remove " + (names.get(item.slug)?.name || item.slug));
      remove.addEventListener("click", () => {
        state[source] = state[source].filter((entry) => entry.slug !== item.slug);
        save();
        updateCounts();
        refresh(true);
        // Keep keyboard focus in the list after its button is removed.
        (list.querySelector("button") || page.querySelector("a")).focus();
      });
      row.append(link, quantityLabel, remove);
      list.append(row);
    });
    updateNames();
  }
  function renderEstimates(data) {
    estimates.replaceChildren();
    if (!data.retailers.length) {
      estimates.append(element("p", "No retailer observations are available for this catalog. Your saved items have been kept."));
    }
    data.retailers.forEach((retailer) => {
      const card = element("article", undefined, "basket-card");
      card.append(element("h3", retailer.name), element("p", `${retailer.covered_count} of ${retailer.item_count} products included`));
      card.append(element("strong", retailer.total !== null ? money(retailer.total) : "Full estimate unavailable", "basket-total"));
      card.append(element("p", retailer.is_complete ? (source === "demo" ? "Complete sample estimate" : "Complete observed item-price estimate") : "Incomplete coverage or conflicting delivery areas"));
      if (!retailer.is_complete) {
        card.append(element("p", retailer.subtotal !== null ? "Covered-items subtotal: " + money(retailer.subtotal) : "No eligible prices to subtotal"));
      }
      if (retailer.has_unverified_areas) card.append(element("p", "Delivery areas unverified. Confirm these items can be ordered together.", "basket-warning"));
      if (retailer.has_mixed_areas) card.append(element("p", "Delivery-area information differs across items; a full basket estimate is withheld.", "basket-warning"));
      const details = element("details");
      details.append(element("summary", "Item breakdown"));
      const breakdown = element("ul", undefined, "basket-breakdown");
      retailer.lines.forEach((line) => {
        const row = element("li");
        row.append(element("strong", names.get(line.slug)?.name || line.slug));
        row.append(element("span", `${line.quantity} pack(s) · ${statusLabels[line.status] || line.status}`));
        if (line.line_total !== null) {
          row.append(element("span", money(line.unit_price) + " each · " + money(line.line_total) + " total"));
          const time = element("time", "Checked " + new Date(line.last_checked).toLocaleString() + " (your local time)");
          time.dateTime = line.last_checked;
          row.append(time, element("span", line.delivery_area || "Area unspecified"));
        }
        breakdown.append(row);
      });
      details.append(breakdown);
      card.append(details);
      estimates.append(card);
    });
  }
  async function refresh(rebuild) {
    if (controller) controller.abort();
    const requestRevision = ++revision;
    if (rebuild) renderItems();
    empty.hidden = state[source].length > 0;
    content.hidden = state[source].length === 0;
    estimates.replaceChildren();
    estimates.removeAttribute("aria-busy");
    if (!state[source].length) { message.textContent = ""; return; }
    if (list.querySelector("[aria-invalid='true']")) {
      message.textContent = "Enter a whole quantity from 1 to 99 to update estimates.";
      return;
    }
    message.textContent = "Updating estimates from the local catalog…";
    estimates.setAttribute("aria-busy", "true");
    controller = new AbortController();
    const query = new URLSearchParams({source});
    state[source].forEach((item) => query.append("item", item.slug + ":" + item.quantity));
    try {
      const response = await fetch(page.dataset.estimateUrl + "?" + query, {signal: controller.signal, cache: "no-store"});
      if (!response.ok) throw new Error("Estimate request failed");
      const data = await response.json();
      if (requestRevision !== revision) return;
      data.items.forEach((item) => names.set(item.slug, item));
      updateNames();
      renderEstimates(data);
      message.textContent = "Estimates updated. Prices are dated observations; delivery and checkout charges are excluded.";
    } catch (error) {
      if (error.name !== "AbortError" && requestRevision === revision) {
        estimates.replaceChildren();
        message.textContent = "Estimates could not be loaded. Your list is kept; check the local server and try Refresh estimates.";
      }
    } finally {
      if (requestRevision === revision) estimates.removeAttribute("aria-busy");
    }
  }
  page.querySelector("[data-list-clear]").addEventListener("click", () => {
    state[source] = [];
    save();
    updateCounts();
    refresh(true);
    page.querySelector("a").focus();
  });
  refreshButton.addEventListener("click", () => refresh(false));
  refresh(true);
})();
