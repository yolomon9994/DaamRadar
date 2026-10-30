"use strict";

// Expire locally, without polling. Monotonic elapsed time prevents a backwards
// clock adjustment from extending a snapshot's lifetime.
window.DaamRadarSnapshot = (() => {
  function create(onExpire) {
    let timer, wallDeadline = null, elapsedDeadline = null;
    function clear() {
      clearTimeout(timer);
      wallDeadline = elapsedDeadline = null;
    }
    function expire() {
      if (wallDeadline === null) return;
      clear();
      onExpire();
    }
    function check() {
      if (wallDeadline === null) return;
      const remaining = Math.min(wallDeadline - Date.now(), elapsedDeadline - performance.now());
      if (remaining < 0) { expire(); return; }
      clearTimeout(timer);
      timer = setTimeout(check, Math.min(300001, remaining + 1));
    }
    function arm(data, started = performance.now()) {
      clear();
      const asOf = Date.parse(data.as_of || data.evaluated_at || data.estimated_at);
      const expires = Date.parse(data.expires_at);
      const lifetime = Math.min(300000, expires - asOf);
      if (!Number.isFinite(asOf) || !Number.isFinite(expires) || lifetime < 0) { onExpire(); return false; }
      wallDeadline = expires;
      elapsedDeadline = started + lifetime;
      check();
      return wallDeadline !== null;
    }
    window.addEventListener("focus", check);
    document.addEventListener("visibilitychange", check);
    window.addEventListener("pageshow", check);
    window.addEventListener("pagehide", expire);
    return Object.freeze({arm, clear, check});
  }
  return Object.freeze({create});
})();

document.querySelectorAll("[data-observation-snapshot]").forEach((root) => {
  const guard = window.DaamRadarSnapshot.create(() => {
    root.classList.add("snapshot-expired");
    root.querySelector("[data-snapshot-status]").textContent = "Snapshot expired. Reload to review current local eligibility. Product names and saved-list controls remain available.";
    root.querySelectorAll(".price-summary, .offer-list, .detail-price, .comparison-table-wrap, .pack-ranking-note, .pack-table-wrap, .source-totals, .source-grid, .offer-filter-note").forEach((node) => {
      if (node.contains(document.activeElement)) root.querySelector("[data-snapshot-reload]").focus();
      node.hidden = true;
    });
  });
  guard.arm({as_of: root.dataset.snapshotAsOf, expires_at: root.dataset.snapshotExpires}, 0);
  window.addEventListener("beforeprint", guard.check);
});
