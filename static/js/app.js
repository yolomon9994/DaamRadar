"use strict";

// Forms remain regular GET requests, usable without JavaScript.
document.querySelectorAll("form[role='search']").forEach((form) => {
  form.addEventListener("submit", () => {
    const button = form.querySelector("button");
    button.textContent = "Finding matches…";
    button.setAttribute("aria-busy", "true");
  });
});
window.addEventListener("pageshow", () => {
  document.querySelectorAll("form[role='search'] button[aria-busy]").forEach((button) => {
    button.textContent = "Compare prices ↗";
    button.removeAttribute("aria-busy");
  });
});

// Optional local-catalog suggestions. Ordinary GET search remains the fallback.
document.querySelectorAll("[data-search-widget]").forEach((widget) => {
  const form = widget.querySelector("form[data-suggestions-url]");
  const input = form?.querySelector("input[name='q']");
  const list = widget.querySelector("[role='listbox']");
  const status = widget.querySelector("[data-suggestion-status]");
  if (!form || !input || !list || !status || !window.fetch || !window.AbortController) return;
  const endpoint = new URL(form.dataset.suggestionsUrl, location.origin);
  if (endpoint.origin !== location.origin) return;
  let revision = 0, timer, controller, selected = -1, options = [];
  input.setAttribute("role", "combobox");
  input.setAttribute("aria-autocomplete", "list");
  input.setAttribute("aria-controls", list.id);
  input.setAttribute("aria-expanded", "false");
  const close = () => {
    revision += 1;
    clearTimeout(timer);
    controller?.abort();
    list.replaceChildren();
    list.hidden = true;
    options = [];
    selected = -1;
    status.textContent = "";
    input.setAttribute("aria-expanded", "false");
    input.removeAttribute("aria-activedescendant");
  };
  const activate = (index) => {
    selected = index;
    options.forEach((option, i) => option.setAttribute("aria-selected", String(index === i)));
    input.setAttribute("aria-activedescendant", options[index].id);
    options[index].scrollIntoView({block: "nearest"});
  };
  const schedule = () => {
    close();
    if (input.value.trim().length < 2 || document.activeElement !== input) return;
    const current = revision;
    timer = setTimeout(async () => {
      controller = new AbortController();
      const params = new URLSearchParams(new FormData(form));
      params.set("q", input.value.trim().slice(0, 150));
      try {
        const response = await fetch(endpoint.pathname + "?" + params.toString(), {
          signal: controller.signal, headers: {Accept: "application/json"}, cache: "no-store",
        });
        if (!response.ok) throw new Error("Suggestions unavailable");
        const data = await response.json();
        if (revision !== current || document.activeElement !== input) return;
        if (!Array.isArray(data.results)) throw new Error("Invalid suggestions");
        for (const item of data.results.slice(0, 6)) {
          if (typeof item.name !== "string" || typeof item.size !== "string" || typeof item.url !== "string") continue;
          const target = new URL(item.url, location.origin);
          if (target.origin !== location.origin || !target.pathname.startsWith("/products/")) continue;
          const option = document.createElement("li");
          option.id = list.id + "-" + options.length;
          option.setAttribute("role", "option");
          option.setAttribute("aria-selected", "false");
          const name = document.createElement("span");
          name.textContent = item.name;
          const size = document.createElement("small");
          size.textContent = item.size;
          option.append(name, size);
          option.addEventListener("pointerdown", (event) => event.preventDefault());
          option.addEventListener("click", () => { close(); location.assign(target.href); });
          options.push(option);
          list.append(option);
        }
        list.hidden = options.length === 0;
        input.setAttribute("aria-expanded", String(!list.hidden));
        status.textContent = options.length ? `${options.length} suggestions. Use arrow keys and Enter to open a product, or submit your search.` : "No suggestions. Press Enter to search.";
      } catch (error) {
        if (revision !== current || error.name === "AbortError") return;
        close();
        status.textContent = "Suggestions unavailable. Press Enter to search.";
      }
    }, 200);
  };
  input.addEventListener("input", schedule);
  input.addEventListener("focus", schedule);
  input.addEventListener("blur", close);
  input.addEventListener("keydown", (event) => {
    if (event.key === "Escape") { event.preventDefault(); close(); return; }
    if (!options.length) return;
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      const next = selected < 0 ? (event.key === "ArrowDown" ? 0 : options.length - 1)
        : (selected + (event.key === "ArrowDown" ? 1 : -1) + options.length) % options.length;
      activate(next);
    } else if (event.key === "Enter" && selected >= 0) {
      event.preventDefault();
      options[selected].click();
    }
  });
  form.addEventListener("submit", close);
  window.addEventListener("pagehide", close);
});

// The SVG and table are server-rendered; JS only enhances series selection.
document.querySelectorAll("[data-price-history]").forEach((section) => {
  const toggles = [...section.querySelectorAll("[data-history-toggle]")];
  const selectionNote = section.querySelector("[data-history-selection-note]");
  const pointOutput = section.querySelector("[data-history-point-output]");
  toggles.forEach((toggle) => {
    const series = document.getElementById(toggle.dataset.historyToggle);
    if (!series || !section.contains(series)) return;
    toggle.hidden = false;
    const update = () => {
      series.style.display = toggle.checked ? "" : "none";
      series.setAttribute("aria-hidden", String(!toggle.checked));
      if (selectionNote) selectionNote.hidden = toggles.some((item) => !item.hidden && item.checked);
      if (pointOutput) pointOutput.textContent = "Focus or hover over a point to inspect its observation.";
    };
    toggle.addEventListener("change", update);
    update();
  });
  section.querySelectorAll("[data-history-point]").forEach((point) => {
    const describe = () => {
      if (pointOutput) pointOutput.textContent = point.getAttribute("aria-label");
    };
    point.addEventListener("focus", describe);
    point.addEventListener("pointerenter", describe);
  });
});
