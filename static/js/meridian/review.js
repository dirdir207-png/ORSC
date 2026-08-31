import { meridianFetch } from "./api.js";

async function correct(row, category, kind, createRule) {
  await meridianFetch(`/api/meridian/transactions/${row.dataset.transactionId}/classification`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ category, kind, create_rule: createRule }),
  });
  window.MeridianActivity.loadActivity({ cursor: null });
}

document.addEventListener("click", async (event) => {
  const row = event.target.closest("[data-transaction-row]");
  if (event.target.closest("[data-review-approve]") && row) {
    event.stopPropagation();
    const classification = row.dataset.classificationCategory || "Uncategorized";
    await correct(row, classification, row.dataset.kind || "spend", false);
    return;
  }
  if (event.target.closest("[data-review-correct]") && row) {
    event.stopPropagation();
    const category = window.prompt("Correct category");
    if (category) {
      await correct(row, category, row.dataset.kind || "spend", true);
    }
    return;
  }
  if (event.target.closest("[data-batch-review]")) {
    const selected = [...document.querySelectorAll("[data-review-select]:checked")]
      .map((item) => Number(item.closest("[data-transaction-row]").dataset.transactionId));
    const category = selected.length ? window.prompt("Category for selected transactions") : null;
    if (category) {
      await meridianFetch("/api/meridian/classifications/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ transaction_ids: selected, category, kind: "spend" }),
      });
      window.MeridianActivity.loadActivity({ cursor: null });
    }
  }
});

document.addEventListener("change", (event) => {
  if (!event.target.matches("[data-review-select]")) {
    return;
  }
  const batch = document.querySelector("[data-batch-review]");
  batch.hidden = document.querySelector("[data-review-select]:checked") === null;
});
