"use strict";

(() => {
  const key = "daamradar.shopping-list.v1";
  const budgetKey = "daamradar.shopping-budget.v1";
  const transfer = window.DaamRadarListTransfer;
  const page = document.querySelector("[data-shopping-list]");
  const feedback = document.querySelector("[data-list-feedback]");
  let storageWarning = "";
  let state = {demo: [], live: []};
  let budgets = {demo: null, live: null};
  let budgetWarning = "";
  let budgetDraft = false;
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
      return {demo: saved.demo.map(transfer.cleanEntry), live: saved.live.map(transfer.cleanEntry)};
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
    if (event.key !== key && event.key !== budgetKey && event.key !== null) return;
    if (event.key !== budgetKey) { state = load(); updateCounts(); }
    if (page) {
      if (event.key !== key) { budgets = loadBudgets(); renderBudget(); }
      refresh(event.key !== budgetKey);
    }
  });
  if (!page) return;

  const list = page.querySelector("[data-list-items]");
  const content = page.querySelector("[data-list-content]");
  const empty = page.querySelector("[data-list-empty]");
  const message = page.querySelector("[data-list-message]");
  const estimates = page.querySelector("[data-list-estimates]");
  const refreshButton = page.querySelector("[data-list-refresh]");
  const budgetSection = page.querySelector("[data-list-budget]");
  const budgetInput = page.querySelector("[data-budget-input]");
  const budgetNote = page.querySelector("[data-budget-note]");
  let updateTransfer = () => {};
  const printSection = page.querySelector("[data-list-print]");
  const printSheet = page.querySelector("[data-print-sheet]");
  const printUnavailable = page.querySelector("[data-print-unavailable]");
  const printRetailerSelect = page.querySelector("[data-print-retailer]");
  const previewToggle = page.querySelector("[data-print-preview-toggle]");
  const pickedUp = new Set();
  let printData = null;
  let printRetailer = null;
  document.body.classList.add("shopping-list-page");
  const statusLabels = {
    included: "Included", missing: "Not listed by this retailer", product_unavailable: "Product removed or unavailable in this catalog",
    stale: "Stale observation — excluded", availability_unknown: "Stock unknown — excluded",
    out_of_stock: "Out of stock — excluded", area_ambiguous: "Multiple delivery areas — choose an area before estimating",
  };
  const money = (value) => "Rs. " + Number(value).toLocaleString("en-PK", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  function normalizeBudget(value) {
    if (typeof value !== "string" || !/^\d{1,10}(\.\d{1,2})?$/.test(value.trim())) return null;
    const [whole, fraction = ""] = value.trim().split(".");
    return whole.replace(/^0+(?=\d)/, "") + "." + fraction.padEnd(2, "0");
  }
  function loadBudgets() {
    try {
      budgetWarning = "";
      const raw = localStorage.getItem(budgetKey);
      if (raw === null) return {demo: null, live: null};
      const saved = JSON.parse(raw);
      if (!saved || Array.isArray(saved)) throw new Error("Invalid saved budgets");
      for (const catalog of ["demo", "live"]) {
        if (saved[catalog] !== null && normalizeBudget(saved[catalog]) === null) throw new Error("Invalid saved budget");
      }
      return {demo: saved.demo === null ? null : normalizeBudget(saved.demo), live: saved.live === null ? null : normalizeBudget(saved.live)};
    } catch (_) {
      budgetWarning = "Saved budgets could not be read. No budget has been applied; your shopping lists are kept.";
      return {demo: null, live: null};
    }
  }
  function saveBudgets() {
    try { localStorage.setItem(budgetKey, JSON.stringify(budgets)); budgetWarning = ""; }
    catch (_) { budgetWarning = "Browser storage is unavailable or full. Budget changes last only on this page."; }
  }
  function renderBudget() {
    budgetDraft = false;
    budgetInput.value = budgets[source] ?? "";
    budgetInput.setCustomValidity("");
    budgetInput.removeAttribute("aria-invalid");
    page.querySelector("[data-budget-remove]").hidden = budgets[source] === null;
    budgetNote.textContent = [budgetWarning, budgets[source] === null ? "No budget set for this list." : "Saved item-price budget: " + money(budgets[source]) + ". Full estimates are needed to assess it."].filter(Boolean).join(" ");
  }
  function budgetDescription(assessment) {
    if (budgetDraft || !assessment || assessment.status === "not_set") return null;
    if (assessment.status === "incomplete") return "Cannot assess full budget";
    if (assessment.status === "over_budget") return money(assessment.over_by) + " over budget";
    if (assessment.status === "at_budget") return "Exactly at budget · " + money(assessment.remaining) + " remaining";
    return money(assessment.remaining) + " remaining in budget";
  }
  budgetSection.hidden = false;
  budgetInput.addEventListener("input", () => {
    budgetDraft = true;
    const valid = normalizeBudget(budgetInput.value) !== null;
    budgetInput.setCustomValidity(valid ? "" : "Enter a PKR budget from 0 to 9999999999.99 with at most two decimal places.");
    budgetInput.setAttribute("aria-invalid", String(!valid));
    estimates.querySelectorAll("[data-budget-assessment]").forEach((node) => node.remove());
    budgetNote.textContent = [budgetWarning, "Save this budget to compare estimates. The last saved budget is unchanged."].filter(Boolean).join(" ");
    renderPrintSheet();
  });
  page.querySelector("[data-budget-form]").addEventListener("submit", (event) => {
    event.preventDefault();
    const amount = normalizeBudget(budgetInput.value);
    if (amount === null) {
      budgetInput.setCustomValidity("Enter a PKR budget from 0 to 9999999999.99 with at most two decimal places.");
      budgetInput.reportValidity();
      return;
    }
    budgets[source] = amount; saveBudgets(); renderBudget(); refresh(false);
  });
  page.querySelector("[data-budget-remove]").addEventListener("click", () => {
    budgets[source] = null; saveBudgets(); renderBudget(); refresh(false); budgetInput.focus();
  });
  budgets = loadBudgets();
  renderBudget();
  function element(tag, text, className) {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  }
  const printTime = (value) => new Intl.DateTimeFormat("en-PK", {
    dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Karachi",
  }).format(new Date(value)) + " PKT";

  function invalidatePrint(reason) {
    printData = null;
    printSection.hidden = true;
    printSheet.replaceChildren();
    printUnavailable.hidden = false;
    printUnavailable.textContent = reason;
  }

  function renderPrintSheet() {
    printSheet.replaceChildren();
    if (!printData) return;
    const retailer = printData.retailers.find((row) => row.slug === printRetailer);
    const title = element("h2", "DaamRadar · Shopping checklist");
    const catalog = source === "demo" ? "DEMO — fictional sample prices" : "Collected catalog — observed item prices";
    printSheet.append(title, element("p", catalog, "print-catalog"));
    printSheet.append(element("h3", retailer ? retailer.name : "Items only — no retailer selected"));
    printSheet.append(element("p", "Estimate snapshot: " + printTime(printData.estimated_at) + ". All check times below are in Pakistan time (PKT)."));
    const table = element("table", undefined, "print-checklist");
    const head = table.createTHead().insertRow();
    const headings = ["Picked up", "Product / pack size", "Packs", "Status / last observation"];
    if (retailer) headings.push("Pack / unit rate (PKR)", "Line (PKR)");
    headings.forEach((text) => {
      const cell = element("th", text);
      cell.scope = "col";
      head.append(cell);
    });
    const body = table.createTBody();
    const lines = new Map(retailer ? retailer.lines.map((line) => [line.slug, line]) : []);
    printData.items.forEach((item) => {
      const row = body.insertRow();
      const check = document.createElement("input");
      check.type = "checkbox";
      check.checked = pickedUp.has(item.slug);
      check.setAttribute("aria-label", "Picked up " + item.name);
      check.addEventListener("change", () => {
        if (check.checked) pickedUp.add(item.slug);
        else pickedUp.delete(item.slug);
      });
      const label = element("label", undefined, "print-purchase-check");
      const box = element("span", undefined, "print-checkbox");
      box.setAttribute("aria-hidden", "true");
      label.append(check, box);
      row.insertCell().append(label);
      const name = element("th", item.name);
      name.scope = "row";
      name.append(element("small", item.size || "Size unspecified"));
      row.append(name);
      row.insertCell().textContent = item.quantity;
      const line = lines.get(item.slug);
      const status = row.insertCell();
      status.append(element("span", line ? (statusLabels[line.status] || line.status) :
        item.available ? "Not priced — items-only checklist" : "Product unavailable in this catalog"));
      const checkedAt = line && (line.last_checked || line.last_observed_at);
      status.append(element("small", checkedAt ? "Checked " + printTime(checkedAt) : "No price-check date available"));
      if (line && line.delivery_area) status.append(element("small", line.delivery_area));
      if (retailer) {
        const priceCell = row.insertCell();
        priceCell.textContent = line && line.unit_price !== null ? money(line.unit_price) : "Excluded";
        if (line && line.unit_price !== null) priceCell.append(element("small", line.standard_unit_price?.display || "Unit price unavailable"));
        row.insertCell().textContent = line && line.line_total !== null ? money(line.line_total) : "Excluded";
      }
    });
    printSheet.append(table);
    const summary = element("div", undefined, "print-estimate-summary");
    if (retailer) {
      summary.append(element("p", `${retailer.covered_count} of ${retailer.item_count} products included in the estimate.`));
      summary.append(element("strong", retailer.total !== null ?
        (source === "demo" ? "Full sample estimate: " : "Full observed item-price estimate: ") + money(retailer.total) : "Full estimate unavailable"));
      if (retailer.total === null) summary.append(element("p", retailer.subtotal !== null ?
        "Covered-items subtotal only: " + money(retailer.subtotal) : "No eligible prices to subtotal."));
      if (retailer.has_unverified_areas) summary.append(element("p", "Delivery areas unverified. Confirm these items can be ordered together."));
      if (retailer.has_mixed_areas) summary.append(element("p", "Delivery-area information conflicts; a full basket estimate is withheld."));
      const budgetText = budgetDescription(retailer.budget_assessment);
      if (budgetText) {
        summary.append(element("p", "Item-price budget: " + money(printData.budget)), element("p", budgetText));
      } else if (budgetDraft) summary.append(element("p", "Budget not assessed: save pending budget changes first."));
    } else {
      summary.append(element("p", "Items-only checklist: no retailer prices or basket total are shown."));
    }
    summary.append(element("p", "Quantities count packs of the exact size shown. Missing, stale, unavailable or ambiguous offers are excluded from estimates, but stay on this checklist."));
    summary.append(element("p", source === "demo" ? "Fictional demo data — not current retailer quotes." :
      "Dated observations, not a current quote or stock reservation. Confirm prices, stock and delivery area with the retailer."));
    summary.append(element("p", "Delivery fees and checkout charges are excluded. Checkboxes do not change the estimate."));
    printSheet.append(summary);
  }

  function preparePrint(data) {
    printData = data;
    const slugs = new Set(data.items.map((item) => item.slug));
    for (const slug of pickedUp) if (!slugs.has(slug)) pickedUp.delete(slug);
    if (printRetailer === null) printRetailer = data.retailers[0]?.slug || "";
    if (printRetailer && !data.retailers.some((row) => row.slug === printRetailer)) printRetailer = "";
    printRetailerSelect.replaceChildren(new Option("Items only — no prices", ""));
    data.retailers.forEach((retailer) => printRetailerSelect.add(new Option(retailer.name, retailer.slug)));
    printRetailerSelect.value = printRetailer;
    renderPrintSheet();
    printSection.hidden = false;
    printUnavailable.hidden = true;
  }

  printRetailerSelect.addEventListener("change", () => {
    printRetailer = printRetailerSelect.value;
    renderPrintSheet();
  });
  previewToggle.addEventListener("click", () => {
    printSheet.hidden = !printSheet.hidden;
    previewToggle.setAttribute("aria-expanded", String(!printSheet.hidden));
    previewToggle.textContent = printSheet.hidden ? "Preview checklist" : "Hide checklist preview";
  });
  page.querySelector("[data-list-print-button]").addEventListener("click", () => {
    if (printData) window.print();
  });
  // Ctrl+P uses the same current selection and carries no stale hidden estimates.
  window.addEventListener("beforeprint", renderPrintSheet);
  function updateNames() {
    list.querySelectorAll("[data-item-name]").forEach((node) => {
      const info = names.get(node.dataset.itemName);
      const saved = state[source].find((item) => item.slug === node.dataset.itemName);
      node.textContent = info ? info.name + (info.available ? "" : " — unavailable") : saved?.product?.name || node.dataset.itemName;
      if (saved?.unresolved || (info && !info.available)) {
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
          invalidatePrint("Correct quantities to whole numbers from 1 to 99 before printing.");
          updateTransfer();
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
      const budgetText = budgetDescription(retailer.budget_assessment);
      if (budgetText) {
        const budgetResult = element("div", undefined, "budget-assessment");
        budgetResult.dataset.budgetAssessment = retailer.budget_assessment.status;
        budgetResult.append(element("strong", budgetText), element("p", "Item-price budget: " + money(data.budget) + ". Delivery and checkout charges are excluded."));
        card.append(budgetResult);
      }
      const details = element("details");
      details.append(element("summary", "Item breakdown"));
      const breakdown = element("ul", undefined, "basket-breakdown");
      retailer.lines.forEach((line) => {
        const row = element("li");
        row.append(element("strong", names.get(line.slug)?.name || line.slug));
        row.append(element("span", `${line.quantity} pack(s) · ${statusLabels[line.status] || line.status}`));
        if (line.line_total !== null) {
          row.append(element("span", money(line.unit_price) + " each · " + money(line.line_total) + " total"));
          row.append(element("span", line.standard_unit_price?.display || "Unit price unavailable", "standard-unit-price"));
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
    invalidatePrint("Estimates are not ready. Load valid estimates before printing a shopping checklist.");
    if (rebuild) renderItems();
    updateTransfer();
    empty.hidden = state[source].length > 0;
    content.hidden = state[source].length === 0;
    estimates.replaceChildren();
    estimates.removeAttribute("aria-busy");
    if (!state[source].length) {
      pickedUp.clear();
      invalidatePrint("Your shopping list is empty. Add products before printing a checklist.");
      message.textContent = "";
      return;
    }
    if (list.querySelector("[aria-invalid='true']")) {
      message.textContent = "Enter a whole quantity from 1 to 99 to update estimates.";
      return;
    }
    message.textContent = "Updating estimates from the local catalog…";
    estimates.setAttribute("aria-busy", "true");
    controller = new AbortController();
    const query = new URLSearchParams({source});
    if (budgets[source] !== null) query.set("budget", budgets[source]);
    state[source].forEach((item) => {
      query.append("item", item.slug + ":" + item.quantity);
      if (item.unresolved) query.append("unresolved", item.slug);
    });
    try {
      const response = await fetch(page.dataset.estimateUrl + "?" + query, {signal: controller.signal, cache: "no-store"});
      if (!response.ok) throw new Error("Estimate request failed");
      const data = await response.json();
      if (requestRevision !== revision) return;
      let metadataChanged = false;
      data.items.forEach((item) => {
        const saved = state[source].find((entry) => entry.slug === item.slug);
        if (item.product && saved && !saved.unresolved) {
          const product = transfer.cleanProduct(item.product);
          if (JSON.stringify(saved.product) !== JSON.stringify(product)) {
            saved.product = product;
            metadataChanged = true;
          }
        }
        if (!item.available && saved?.product) {
          item.name = saved.product.name;
          item.size = saved.product.size;
        }
      });
      if (metadataChanged) save();
      data.items.forEach((item) => names.set(item.slug, item));
      updateNames();
      renderEstimates(data);
      preparePrint(data);
      updateTransfer();
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
  updateTransfer = transfer.mount({page, source, read: () => state[source].map(transfer.cleanEntry),
    hasInvalidQuantities: () => Boolean(list.querySelector("[aria-invalid='true']")),
    commit: (entries) => {
      state[source] = entries;
      pickedUp.clear();
      const persisted = save();
      updateCounts();
      refresh(true);
      return persisted;
    }});
  refresh(true);
})();
