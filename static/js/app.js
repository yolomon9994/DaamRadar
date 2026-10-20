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
