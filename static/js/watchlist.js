"use strict";

(() => {
  const key = "daamradar.watchlist.v1";
  const page = document.querySelector("[data-watch-page]");
  const control = document.querySelector("[data-watch-control]");
  const host = page || control;
  const source = host?.dataset.source;
  let warning = "";
  let state = {demo: [], live: []};
  let storedWatchValue = null;
  let revision = 0;
  let controller;
  let updateBackup = () => {};
  let unreadableTargets = false;
  const drafts = new Map();
  const validSlug = (value) => typeof value === "string" && /^[-a-zA-Z0-9_]{1,280}$/.test(value);
  function targetPrice(value) {
    if (typeof value !== "string" || !/^\d{1,10}(\.\d{1,2})?$/.test(value.trim())) return null;
    const [whole, fraction = ""] = value.trim().split(".");
    const result = whole.replace(/^0+(?=\d)/, "") + "." + fraction.padEnd(2, "0");
    return /[1-9]/.test(result) ? result : null;
  }
  function load() {
    try {
      warning = "";
      unreadableTargets = false;
      const raw = localStorage.getItem(key);
      storedWatchValue = raw;
      if (raw === null) return {demo: [], live: []};
      const saved = JSON.parse(raw);
      const next = {};
      for (const catalog of ["demo", "live"]) {
        if (!Array.isArray(saved[catalog]) || saved[catalog].length > 50) throw new Error("Invalid watchlist");
        const seen = new Set();
        next[catalog] = saved[catalog].map((item) => {
          if (!item || !validSlug(item.slug) || seen.has(item.slug) || !targetPrice(item.target) ||
              (item.name !== undefined && (typeof item.name !== "string" || item.name.length > 255)) ||
              (item.size !== undefined && (typeof item.size !== "string" || item.size.length > 80))) throw new Error("Invalid target");
          seen.add(item.slug);
          return window.DaamRadarPreferencesBackup.cleanTarget({...item, target: targetPrice(item.target)});
        });
      }
      return next;
    } catch (_) {
      warning = "Saved targets could not be read. This page uses an empty watchlist until you save a target.";
      unreadableTargets = true;
      return {demo: [], live: []};
    }
  }
  function save() {
    try {
      const value = JSON.stringify(state);
      localStorage.setItem(key, value);
      storedWatchValue = value;
      warning = ""; unreadableTargets = false; return true;
    }
    catch (_) { warning = "Browser storage is unavailable or full. Target changes last only on this page."; return false; }
  }
  function counts() {
    updateBackup();
    document.querySelectorAll("[data-watch-total]").forEach((node) => { node.textContent = state.demo.length + state.live.length; });
    document.querySelectorAll("[data-watch-count]").forEach((node) => { node.textContent = state[node.dataset.watchCount].length; });
    document.querySelectorAll("[data-watch-link]").forEach((node) => {
      node.textContent = state[node.dataset.watchSource].some((item) => item.slug === node.dataset.watchSlug) ? "Watching price · edit target" : "Watch price";
    });
  }
  state = load();
  counts();
  if (!host) {
    window.addEventListener("storage", (event) => { if (event.key === key || event.key === null) { state = load(); counts(); } });
    window.addEventListener("pageshow", (event) => {
      if (!event.persisted) return;
      try { if (localStorage.getItem(key) !== storedWatchValue) { state = load(); counts(); } } catch (_) { /* Page-only targets. */ }
    });
    return;
  }
  if (control) control.hidden = false;
  const message = host.querySelector("[data-watch-message]");
  const say = (text) => { message.textContent = [warning, text].filter(Boolean).join(" "); };
  const money = (value) => "Rs. " + Number(value).toLocaleString("en-PK", {minimumFractionDigits: 2, maximumFractionDigits: 2});
  const time = (value) => new Intl.DateTimeFormat("en-PK", {dateStyle: "medium", timeStyle: "short", timeZone: "Asia/Karachi"}).format(new Date(value)) + " PKT";
  const element = (tag, text, className) => {
    const node = document.createElement(tag);
    if (text !== undefined) node.textContent = text;
    if (className) node.className = className;
    return node;
  };
  function selected() { return page ? state[source] : state[source].filter((item) => item.slug === control.dataset.slug); }
  function clearResults(text) {
    host.querySelectorAll("[data-watch-result]").forEach((node) => { node.replaceChildren(element("p", text)); });
  }
  function stopRequest() {
    if (controller) controller.abort();
    snapshot.clear();
    revision += 1;
    host.removeAttribute("aria-busy");
  }
  const snapshot = window.DaamRadarSnapshot.create(() => {
    stopRequest();
    clearResults("Observations may now be stale. Check targets again before using these results.");
    say("Target snapshot expired. Check again to reload eligibility from the local database.");
  });
  function saveTarget(slug, value, name, size) {
    const target = targetPrice(value);
    if (!target) return false;
    const current = state[source].find((item) => item.slug === slug);
    if (!current && state[source].length >= 50) { say("This watchlist has 50 products. Remove one before adding another."); return false; }
    if (current) Object.assign(current, {target, name, size});
    else state[source].push({slug, target, name, size});
    drafts.delete(slug);
    save(); counts(); render(); refresh();
    return true;
  }
  function remove(slug) {
    state[source] = state[source].filter((item) => item.slug !== slug);
    drafts.delete(slug);
    save(); counts(); render(); refresh();
    (host.querySelector("[data-watch-target]") || host.querySelector("a")).focus();
  }
  function bindForm(form, slug, name, size, result) {
    const input = form.querySelector("[data-watch-target]");
    input.addEventListener("input", () => {
      const target = targetPrice(input.value);
      input.setCustomValidity(target ? "" : "Enter a positive PKR amount with at most two decimal places.");
      input.setAttribute("aria-invalid", String(!target));
      drafts.set(slug, input.value);
      updateBackup();
      result.replaceChildren(element("p", "Save this target to check prices."));
      say("Target edited. Save it to check prices.");
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      if (!targetPrice(input.value)) { input.setCustomValidity("Enter a positive PKR amount with at most two decimal places."); input.reportValidity(); return; }
      const row = form.closest(".watch-item");
      saveTarget(slug, input.value, row?.dataset.name || name, row?.dataset.size || size);
    });
    form.querySelector("[data-watch-remove]").addEventListener("click", () => remove(slug));
  }
  function render() {
    if (control) {
      const item = selected()[0];
      const input = control.querySelector("[data-watch-target]");
      input.value = drafts.get(control.dataset.slug) ?? item?.target ?? "";
      input.setCustomValidity("");
      input.removeAttribute("aria-invalid");
      control.querySelector("[data-watch-save]").textContent = item ? "Update target" : "Watch price";
      control.querySelector("[data-watch-remove]").hidden = !item;
      control.querySelector("[data-watch-refresh]").hidden = !item;
      return;
    }
    const entries = selected();
    host.querySelector("[data-watch-empty]").hidden = entries.length > 0;
    host.querySelector("[data-watch-content]").hidden = entries.length === 0;
    const list = host.querySelector("[data-watch-items]");
    list.replaceChildren();
    entries.forEach((item, index) => {
      const row = element("li", undefined, "watch-item"); row.dataset.watchSlug = item.slug;
      const link = element("a", item.name); link.dataset.watchName = "";
      if (!item.unresolved) link.href = "/products/" + encodeURIComponent(item.slug) + "/#watch-price";
      else link.setAttribute("aria-disabled", "true");
      const heading = element("h2"); heading.append(link); row.append(heading, element("p", item.size, "watch-size muted"));
      const form = element("form", undefined, "watch-form");
      const label = element("label", "Target pack price (PKR)"); label.htmlFor = "watch-target-" + index;
      const input = document.createElement("input");
      Object.assign(input, {type: "text", inputMode: "decimal", maxLength: 13, required: true, id: label.htmlFor, value: drafts.get(item.slug) ?? item.target});
      input.dataset.watchTarget = ""; input.setAttribute("aria-label", "Target pack price in PKR for " + item.name); label.append(input);
      const submit = element("button", "Save target", "button-small"); submit.type = "submit"; submit.dataset.watchSave = "";
      const removeButton = element("button", "Remove", "list-action"); removeButton.type = "button"; removeButton.dataset.watchRemove = ""; removeButton.setAttribute("aria-label", "Remove target for " + item.name);
      form.append(label, submit, removeButton);
      const result = element("div"); result.dataset.watchResult = "";
      row.append(form, result); list.append(row);
      bindForm(form, item.slug, item.name, item.size, result);
    });
  }
  function showResult(item) {
    const row = page ? [...host.querySelectorAll(".watch-item")].find((node) => node.dataset.watchSlug === item.slug) : control;
    if (!row) return;
    const result = row.querySelector("[data-watch-result]");
    if (drafts.has(item.slug)) { result.replaceChildren(element("p", "Save this target to check prices.")); return; }
    result.replaceChildren();
    const status = element("p", item.status === "target_met" ? "Observed target met" : item.status === "above_target" ? "Above target" : "Target check unavailable", "watch-status");
    status.dataset.watchStatus = item.status; result.append(status, element("p", item.message));
    if (page) {
      const link = row.querySelector("[data-watch-name]");
      link.textContent = item.name || state[source].find((saved) => saved.slug === item.slug).name + " — unavailable";
      if (item.available) { row.dataset.name = item.name; row.dataset.size = item.size; row.querySelector(".watch-size").textContent = item.size; }
      if (!item.available) { link.removeAttribute("href"); link.setAttribute("aria-disabled", "true"); }
    }
    if (item.observed_price !== null) {
      result.append(element("p", "Lowest eligible observed pack price: " + money(item.observed_price)));
      if (item.standard_unit_price) result.append(element("p", item.standard_unit_price.display, "standard-unit-price"));
    } else if (item.last_observed_at) result.append(element("p", "Most recent stored observation: " + time(item.last_observed_at) + ". Excluded from this target check."));
    if (item.has_unverified_areas) result.append(element("p", "Delivery coverage unverified. Confirm this observation applies to your address.", "basket-warning"));
    if (item.has_mixed_areas) result.append(element("p", "Observations cover different delivery areas. These are individual listings, not a shared-area comparison.", "basket-warning"));
    if (item.offers.length) {
      const offers = element("ul", undefined, "watch-offers");
      item.offers.forEach((offer) => {
        const line = element("li");
        line.append(element("strong", offer.retailer + " · " + money(offer.price) + (offer.meets_target ? " · target met" : " · above target")),
          element("span", "In stock when checked " + time(offer.last_checked)),
          element("span", (offer.delivery_area || "Area unspecified") + (source === "demo" ? " · fictional demo area" : offer.area_is_verified ? " · verified for this observation" : " · unverified coverage")));
        offers.append(line);
      });
      result.append(offers);
    }
  }
  async function refresh() {
    stopRequest();
    const started = performance.now();
    const entries = selected();
    if (!entries.length) { clearResults(""); say(""); return; }
    const requestRevision = revision;
    clearResults("Checking stored prices…"); say("Checking targets against the local catalog…"); host.setAttribute("aria-busy", "true");
    const currentController = new AbortController(); controller = currentController;
    const timeout = setTimeout(() => currentController.abort(), 15000);
    const query = new URLSearchParams({source}); entries.forEach((item) => {
      query.append("item", item.slug + ":" + item.target);
      if (item.unresolved) query.append("unresolved", item.slug);
    });
    try {
      const response = await fetch(host.dataset.checkUrl + "?" + query, {cache: "no-store", signal: currentController.signal});
      if (!response.ok) throw new Error("Target check failed");
      const data = await response.json();
      if (requestRevision !== revision) return;
      if (!snapshot.arm(data, started)) return;
      let metadataChanged = false;
      data.items.forEach((item) => {
        const saved = state[source].find((entry) => entry.slug === item.slug);
        if (!saved || saved.unresolved || !item.product) return;
        const product = window.DaamRadarListTransfer.cleanProduct(item.product);
        if (JSON.stringify(saved.product) !== JSON.stringify(product) || saved.name !== item.name || saved.size !== item.size) {
          Object.assign(saved, {product, name: item.name, size: item.size});
          metadataChanged = true;
        }
      });
      if (metadataChanged) { save(); updateBackup(); }
      data.items.forEach(showResult);
      const checked = data.items.filter((item) => !drafts.has(item.slug));
      say(`${checked.filter((item) => item.status === "target_met").length} of ${checked.length} saved targets met. Checked locally ${time(data.evaluated_at)}. This is a snapshot of stored observations.${drafts.size ? " Save edited targets to check them." : ""}`);
    } catch (error) {
      if (requestRevision !== revision) return;
      clearResults("Target status is unavailable until a check succeeds.");
      say(error.name === "AbortError" ? "The check timed out. Your targets are kept; try Check targets again." : "Targets could not be checked. Your saved targets are kept; check the local server and retry.");
    } finally {
      clearTimeout(timeout);
      if (requestRevision === revision) host.removeAttribute("aria-busy");
    }
  }
  if (control) bindForm(control.querySelector("[data-watch-form]"), control.dataset.slug, control.dataset.name, control.dataset.size, control.querySelector("[data-watch-result]"));
  host.querySelector("[data-watch-refresh]").addEventListener("click", refresh);
  if (page) host.querySelector("[data-watch-clear]").addEventListener("click", () => {
    state[source] = []; drafts.clear(); save(); counts(); render(); refresh(); host.querySelector("a[href]").focus();
  });
  window.addEventListener("storage", (event) => {
    if (event.key !== key && event.key !== null) return;
    state = load(); drafts.clear(); counts(); render(); refresh();
  });
  window.addEventListener("pageshow", (event) => {
    if (!event.persisted) return;
    try { if (localStorage.getItem(key) !== storedWatchValue) { state = load(); drafts.clear(); } } catch (_) { /* Keep page-only targets. */ }
    counts(); render(); refresh();
  });
  if (page) updateBackup = window.DaamRadarPreferencesBackup.mount({page, source,
    read: () => state, hasDrafts: () => drafts.size > 0, unreadable: () => unreadableTargets,
    applied: (next) => {
      state = next;
      try { storedWatchValue = localStorage.getItem(key); } catch (_) { /* Restore already verified storage. */ }
      warning = "";
      unreadableTargets = false;
      drafts.clear();
      counts(); render(); refresh();
    }});
  render(); refresh();
})();
