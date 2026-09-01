/* Activity workspace: a stable, date-grouped ledger with cursor pagination. */

import { MeridianApiError, meridianFetch } from "./api.js";
import { dayKey, dayLabel, formatCurrency } from "./format.js";

const state = {
  cursor: null,
  accountId: null,
  category: "",
  mode: "timeline",
  controller: null,
  accountsLoaded: false,
};

/* Show an explicit sign so income reads "+$" and spend reads "−$", matching the
   atlas. formatCurrency keeps the locale grouping; we only add the sign. */
function signedAmount(amount, currency) {
  const sign = amount < 0 ? "\u2212" : "+";
  return `${sign}${formatCurrency(Math.abs(amount), currency)}`;
}

function buildRow(transaction) {
  const row = document.createElement("div");
  row.className = "m-transaction-row";
  row.dataset.transactionRow = "";
  row.dataset.transactionId = String(transaction.id);
  row.dataset.kind = transaction.amount < 0 ? "spend" : "income";
  row.dataset.classificationCategory = transaction.classification?.category || "";
  row.setAttribute("role", "button");
  row.setAttribute("tabindex", "0");
  row.setAttribute(
    "aria-label",
    `${transaction.merchant || transaction.description}, ${formatCurrency(
      transaction.amount,
      transaction.currency
    )}. Open details.`
  );

  const left = document.createElement("span");
  left.className = "m-row-text";
  const title = document.createElement("span");
  title.className = "m-row-title";
  title.setAttribute("data-row-description", "");
  title.textContent =
    transaction.merchant || transaction.description || `Transaction ${transaction.id}`;
  const sub = document.createElement("span");
  sub.className = "m-row-sub";
  sub.textContent =
    transaction.merchant && transaction.description
      ? transaction.description
      : (transaction.provider || "");
  left.append(title, sub);

  const category = document.createElement("span");
  category.className = "m-row-category";
  category.setAttribute("data-row-category", "");
  category.textContent =
    transaction.classification?.category || "Unassigned";

  const amount = document.createElement("span");
  amount.className = `m-row-amount ${
    transaction.amount < 0 ? "is-spend" : "is-income"
  }`;
  amount.textContent = signedAmount(transaction.amount, transaction.currency);

  row.append(left, category, amount);
  if (state.mode === "review") {
    const confidence = document.createElement("span");
    confidence.className = "m-chip";
    confidence.dataset.confidenceLabel = "";
    confidence.textContent = `${Math.round((transaction.classification?.confidence || 0) * 100)}% confidence`;
    const select = document.createElement("input");
    select.type = "checkbox";
    select.dataset.reviewSelect = "";
    select.setAttribute("aria-label", `Select ${title.textContent} for batch review`);
    const approve = document.createElement("button");
    approve.type = "button";
    approve.className = "m-button";
    approve.dataset.reviewApprove = "";
    approve.textContent = "Approve";
    const correct = document.createElement("button");
    correct.type = "button";
    correct.className = "m-button";
    correct.dataset.reviewCorrect = "";
    correct.textContent = "Correct";
    const actions = document.createElement("span");
    actions.className = "m-row-review-actions";
    actions.append(confidence, select, approve, correct);
    row.append(actions);
  }
  return row;
}

function groupFor(ledger, isoTimestamp) {
  const key = dayKey(isoTimestamp);
  let group = ledger.querySelector(`[data-day-group][data-day-key="${key}"]`);
  if (!group) {
    group = document.createElement("section");
    group.className = "m-day-group";
    group.dataset.dayGroup = "";
    group.dataset.dayKey = key;
    const heading = document.createElement("h2");
    heading.className = "m-day-heading";
    heading.textContent = dayLabel(isoTimestamp);
    const list = document.createElement("div");
    list.className = "m-day-rows";
    group.append(heading, list);

    // Insert newest day first.
    const existing = [...ledger.querySelectorAll("[data-day-group]")];
    const anchor = existing.find((candidate) => candidate.dataset.dayKey < key);
    if (anchor) {
      ledger.insertBefore(group, anchor);
    } else {
      ledger.appendChild(group);
    }
  }
  return group.querySelector(".m-day-rows");
}

function setChip(root, freshness) {
  const chip = root.querySelector("[data-freshness]");
  chip.dataset.state = freshness ? (freshness.status || "unavailable") : "unavailable";
  const labels = { fresh: "Fresh", stale: "Stale", unavailable: "Not connected" };
  chip.textContent = labels[chip.dataset.state] || chip.dataset.state;
}

/* Collect the distinct classification categories seen so far into the filter
   select, preserving the current selection. */
function populateCategories(root, transactions) {
  const select = root.querySelector("[data-category-filter]");
  if (!select) {
    return;
  }
  const known = new Set(
    [...select.options].map((option) => option.value).filter(Boolean)
  );
  for (const transaction of transactions || []) {
    const category = transaction.classification?.category;
    if (category && !known.has(category)) {
      known.add(category);
      const option = document.createElement("option");
      option.value = category;
      option.textContent = category;
      select.appendChild(option);
    }
  }
}

/* Client-side category filter. Timeline rows carry data-classification-category;
   day groups that end up with no matching row are collapsed. Pattern cards are
   never filtered (category is a timeline notion). */
function applyCategoryFilter(root) {
  const category = state.category;
  const groups = root.querySelectorAll("[data-day-group]");
  let visibleRows = 0;
  let hasPattern = false;
  for (const group of groups) {
    if (group.hasAttribute("data-pattern-card")) {
      group.hidden = false;
      hasPattern = true;
      continue;
    }
    const rows = group.querySelectorAll("[data-transaction-row]");
    let visible = 0;
    for (const row of rows) {
      const rowCategory = row.dataset.classificationCategory || "";
      const show = !category || rowCategory === category;
      row.hidden = !show;
      if (show) {
        visible += 1;
      }
    }
    group.hidden = visible === 0;
    visibleRows += visible;
  }
  const empty = root.querySelector("[data-activity-empty]");
  if (empty) {
    empty.hidden = visibleRows > 0 || hasPattern;
  }
}

function renderPage(root, payload, { append }) {
  const ledger = root.querySelector("[data-ledger]");
  const empty = root.querySelector("[data-activity-empty]");
  const loadMore = root.querySelector("[data-load-more]");
  const errorBox = root.querySelector("[data-activity-error]");

  errorBox.hidden = true;
  if (!append) {
    ledger.replaceChildren();
  }

  const transactions = payload.transactions || [];
  if (state.mode === "patterns") {
    for (const pattern of payload.patterns || []) {
      const card = document.createElement("article");
      card.className = "m-day-group";
      card.dataset.patternCard = pattern.kind;
      const heading = document.createElement("h2");
      heading.className = "m-day-heading";
      heading.textContent = pattern.title;
      const evidence = document.createElement("p");
      evidence.textContent = `Evidence: ${(pattern.evidence_ids || []).join(", ")}`;
      card.append(heading, evidence);
      ledger.appendChild(card);
    }
  }
  for (const transaction of transactions) {
    groupFor(ledger, transaction.occurred_at).appendChild(buildRow(transaction));
  }

  empty.hidden = ledger.children.length > 0;
  state.cursor = payload.next_cursor || null;
  loadMore.hidden = !state.cursor;
  setChip(root, payload.data_freshness);
  populateCategories(root, transactions);
  applyCategoryFilter(root);
}

async function populateAccounts(select) {
  if (state.accountsLoaded) {
    return;
  }
  state.accountsLoaded = true;
  try {
    const payload = await meridianFetch("/api/meridian/accounts");
    for (const account of payload.accounts || []) {
      const option = document.createElement("option");
      option.value = String(account.id);
      option.textContent = account.name;
      select.appendChild(option);
    }
  } catch {
    /* The All-accounts view remains usable without the filter options. */
  }
}

async function loadActivity(options = {}) {
  const root = document.querySelector("[data-activity-root]");
  if (!root) {
    return;
  }
  const append = Boolean(options.cursor) && options.cursor === state.cursor;

  if (state.controller) {
    state.controller.abort();
  }
  state.controller = new AbortController();

  const params = new URLSearchParams();
  const limit = options.limit || 50;
  params.set("limit", String(limit));
  const cursor = options.cursor !== undefined ? options.cursor : null;
  if (cursor && append) {
    params.set("cursor", cursor);
  }
  const accountId =
    options.accountId !== undefined ? options.accountId : state.accountId;
  if (accountId) {
    params.set("account_id", String(accountId));
  }
  params.set("mode", state.mode);

  root.setAttribute("aria-busy", "true");
  try {
    const payload = await meridianFetch(`/api/meridian/activity?${params}`, {
      signal: state.controller.signal,
    });
    renderPage(root, payload, { append: append && cursor !== null });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    const ledgerEmpty =
      root.querySelector("[data-ledger] [data-transaction-row]") === null;
    if (ledgerEmpty || !(error instanceof MeridianApiError)) {
      const detail =
        error instanceof MeridianApiError
          ? `${error.message} ${error.recoveryAction}`
          : "Something went wrong while loading Activity.";
      const errorBox = root.querySelector("[data-activity-error]");
      errorBox.textContent = detail;
      errorBox.hidden = false;
    }
  } finally {
    root.removeAttribute("aria-busy");
  }
}

window.MeridianActivity = { loadActivity };

document.addEventListener("click", (event) => {
  const modeButton = event.target.closest("[data-activity-mode]");
  if (!modeButton) {
    return;
  }
  state.mode = modeButton.dataset.activityMode;
  document.querySelectorAll("[data-activity-mode]").forEach((button) => {
    button.setAttribute("aria-pressed", String(button === modeButton));
  });
  loadActivity({ cursor: null });
});

document.addEventListener("click", (event) => {
  if (!event.target.closest("[data-load-more]")) {
    return;
  }
  event.preventDefault();
  if (state.cursor) {
    loadActivity({ cursor: state.cursor });
  }
});

document.addEventListener("change", (event) => {
  const select = event.target.closest("[data-account-filter]");
  if (!select) {
    return;
  }
  const value = select.value ? Number(select.value) : null;
  state.accountId = value;
  loadActivity({ accountId: value, cursor: null });
});

document.addEventListener("change", (event) => {
  const select = event.target.closest("[data-category-filter]");
  if (!select) {
    return;
  }
  state.category = select.value || "";
  const root = document.querySelector("[data-activity-root]");
  if (root) {
    applyCategoryFilter(root);
  }
});

document.addEventListener("click", (event) => {
  const toggle = event.target.closest("[data-filter-toggle]");
  if (!toggle) {
    return;
  }
  const panel = document.querySelector("[data-filter-panel]");
  const expanded = toggle.getAttribute("aria-expanded") === "true";
  toggle.setAttribute("aria-expanded", String(!expanded));
  if (panel) {
    panel.hidden = expanded;
  }
});

document.addEventListener("meridian:workspacechange", (event) => {
  if (event.detail.workspace === "activity") {
    loadActivity();
    const select = document.querySelector("[data-account-filter]");
    if (select) {
      populateAccounts(select);
    }
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    if (window.MeridianShell && window.MeridianShell.getWorkspace() === "activity") {
      loadActivity();
      const select = document.querySelector("[data-account-filter]");
      if (select) {
        populateAccounts(select);
      }
    }
  });
} else if (
  window.MeridianShell &&
  window.MeridianShell.getWorkspace() === "activity"
) {
  loadActivity();
  const select = document.querySelector("[data-account-filter]");
  if (select) {
    populateAccounts(select);
  }
}
