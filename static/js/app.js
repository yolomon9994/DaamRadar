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

let historyController;
document.querySelectorAll(".history-button").forEach((button) => {
  button.addEventListener("click", async () => {
    if (historyController) historyController.abort();
    historyController = new AbortController();
    const output = document.getElementById("history-output");
    output.textContent = "Loading recorded prices…";
    output.setAttribute("aria-busy", "true");
    try {
      const response = await fetch(button.dataset.historyUrl, {headers: {Accept: "application/json"}, signal: historyController.signal});
      if (!response.ok) throw new Error("History unavailable");
      const data = await response.json();
      output.replaceChildren();
      const heading = document.createElement("h3");
      heading.textContent = `${button.dataset.retailer} · recorded observations`;
      output.append(heading);
      if (!data.results.length) {
        output.append(document.createTextNode("No observations have been recorded yet."));
        return;
      }
      const list = document.createElement("ul");
      list.className = "history-list";
      data.results.forEach((record) => {
        const item = document.createElement("li");
        const date = new Date(record.checked_at).toLocaleString("en-PK", {timeZone: "Asia/Karachi"});
        item.textContent = `${date} PKT — Rs. ${Number(record.price).toLocaleString("en-PK")} ${record.is_demo ? "(demo)" : ""}`;
        list.append(item);
      });
      output.append(list);
      if (data.next) {
        const next = document.createElement("a");
        next.href = data.next;
        next.textContent = "Older observations (JSON) →";
        output.append(next);
      }
    } catch (error) {
      if (error.name !== "AbortError") output.textContent = "We couldn’t load price history. Please select the retailer to try again.";
    } finally {
      output.removeAttribute("aria-busy");
    }
  });
});
