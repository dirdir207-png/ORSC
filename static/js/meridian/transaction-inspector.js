/* Transaction inspector controller.
   Opens the details panel from Activity rows or a ?transaction= deep link,
   keeps the selection in the URL without disturbing Activity filters, and
   restores focus to the originating row on close. */

import { MeridianApiError, freshnessText, meridianFetch } from "./api.js";
import { formatCurrency } from "./format.js";

const state = { openId: null, opener: null, accounts: null };

function isMobileViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function signedAmount(amount, currency) {
  const sign = amount < 0 ? "\u2212" : "+";
  return `${sign}${formatCurrency(Math.abs(amount), currency)}`;
}

/* Keep the mobile selected-transaction summary in sync with the open detail so
   closing the sheet still shows which transaction was last selected. */
function updateSelectedSummary(transaction) {
  const summary = document.querySelector("[data-selected-summary]");
  if (!summary) {
    return;
  }
  const title =
    transaction.merchant || transaction.description || `Transaction ${transaction.id}`;
  summary.hidden = false;
  summary.dataset.selectedId = String(transaction.id);
  const nodes = {
    "[data-selected-summary-title]": title,
    "[data-selected-summary-category]": transaction.classification?.category || "Unassigned",
    "[data-selected-summary-amount]": signedAmount(transaction.amount, transaction.currency),
  };
  for (const [selector, text] of Object.entries(nodes)) {
    const node = summary.querySelector(selector);
    if (node) {
      node.textContent = text;
    }
  }
}

async function accountName(accountId) {
  if (state.accounts === null) {
    try {
      const payload = await meridianFetch("/api/meridian/accounts");
      state.accounts = new Map(
        (payload.accounts || []).map((account) => [account.id, account.name])
      );
    } catch {
      state.accounts = new Map();
    }
  }
  return state.accounts.get(accountId) || `Account ${accountId}`;
}

function setText(selector, value) {
  const node = document.querySelector(`[data-inspector-body] ${selector}`);
  if (node) {
    node.textContent = value;
  }
}

function setFact(key, value) {
  const row = document.querySelector(`[data-fact="${key}"] dd`);
  if (row) {
    row.textContent = value;
  }
}

function formatFullDate(value) {
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value || "";
  }
  return parsed.toLocaleString(undefined, {
    weekday: "short",
    year: "numeric",
    month: "long",
    day: "numeric",
    hour: "numeric",
    minute: "2-digit",
  });
}

function renderEvidence(evidence) {
  const target = document.querySelector("[data-evidence-list]");
  if (!target) return;
  target.replaceChildren();
  if (!evidence.length) {
    const empty = document.createElement("p");
    empty.className = "m-state-line";
    empty.textContent = "No linked documents";
    target.append(empty);
    setText("[data-retention-state]", "");
    return;
  }
  for (const item of evidence) {
    const link = document.createElement("a");
    link.href = item.content_url;
    link.target = "_blank";
    link.rel = "noopener";
    link.textContent = `${item.title || "Financial document"} · ${item.provenance}`;
    link.dataset.confidence = item.confidence ?? "unavailable";
    target.append(link);
  }
  const expiry = evidence.find((item) => item.expires_at)?.expires_at;
  setText(
    "[data-retention-state]",
    expiry ? `Retained until ${expiry}` : "No expiry scheduled"
  );
}

function render(transaction, freshness, evidence = []) {
  const title =
    transaction.merchant || transaction.description || `Transaction ${transaction.id}`;
  setText("[data-inspector-title]", title);
  setText("[data-inspector-provider]", transaction.provider || "");

  setFact("merchant", transaction.merchant || "—");
  setFact("description", transaction.description || "—");
  setFact(
    "amount",
    formatCurrency(transaction.amount, transaction.currency)
  );
  setFact("date", formatFullDate(transaction.occurred_at));
  setFact("status", (transaction.status || "unknown").toLowerCase());
  const classification = transaction.classification || {};
  setText("[data-category-state]", classification.category || "Unassigned");
  setText(
    "[data-confidence-state]",
    classification.confidence === null || classification.confidence === undefined
      ? "Confidence unavailable"
      : `${Math.round(classification.confidence * 100)}% confidence`
  );
  setText(
    "[data-classification-evidence]",
    classification.evidence || "No classification evidence"
  );
  renderEvidence(evidence);
  updateSelectedSummary(transaction);

  const chip = document.querySelector("[data-inspector-rail] [data-freshness]");
  const view = freshnessText(freshness);
  chip.dataset.state = view.state;
  chip.textContent = view.label;

  void accountName(transaction.account_id).then((name) => {
    if (state.openId === transaction.id) {
      setFact("account", name);
    }
  });
}

function setUrlTransaction(id) {
  const url = new URL(window.location.href);
  if (id === null) {
    url.searchParams.delete("transaction");
  } else {
    url.searchParams.set("transaction", String(id));
  }
  window.history.replaceState(
    { meridianTransaction: id },
    "",
    url
  );
}

async function open(id, options = {}) {
  const panel = document.querySelector("[data-inspector-rail]");
  if (!panel) {
    return;
  }
  state.openId = id;
  state.opener =
    options.opener instanceof HTMLElement ? options.opener : document.activeElement;

  window.MeridianShell.openSheet(panel, { modal: isMobileViewport() });
  panel.setAttribute("data-advisor-context", "transaction");
  panel.setAttribute("data-object-id", String(id));
  setUrlTransaction(id);

  try {
    const payload = await meridianFetch(`/api/meridian/transactions/${id}`);
    if (state.openId !== id) {
      return;
    }
    render(payload.transaction, payload.data_freshness, payload.evidence || []);
  } catch (error) {
    if (state.openId !== id) {
      return;
    }
    const detail =
      error instanceof MeridianApiError
        ? `${error.message} ${error.recoveryAction}`
        : "This transaction could not be loaded.";
    setText("[data-inspector-title]", "Unavailable");
    setText("[data-recurrence-state]", "");
    setFact("description", detail);
  }
}

function close() {
  const panel = document.querySelector("[data-inspector-rail]");
  if (!panel || state.openId === null) {
    return null;
  }
  state.openId = null;
  panel.removeAttribute("data-advisor-context");
  panel.removeAttribute("data-object-id");
  window.MeridianShell.closeSheet();
  setUrlTransaction(null);
  return state.opener;
}

window.MeridianTransactionInspector = { open, close };

document.addEventListener("click", (event) => {
  const row = event.target.closest("[data-transaction-row]");
  if (row) {
    open(Number(row.dataset.transactionId), { opener: row });
    return;
  }
  if (event.target.closest("[data-selected-summary-open]")) {
    const summary = document.querySelector("[data-selected-summary]");
    const id = summary && summary.dataset.selectedId;
    if (id) {
      open(Number(id));
    }
    return;
  }
  if (event.target.closest("[data-inspector-close]")) {
    close();
  }
});

document.addEventListener("keydown", (event) => {
  const row = event.target.closest("[data-transaction-row]");
  if (!row || (event.key !== "Enter" && event.key !== " ")) {
    return;
  }
  event.preventDefault();
  open(Number(row.dataset.transactionId), { opener: row });
});

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && state.openId !== null) {
    close();
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    const requested = new URLSearchParams(window.location.search).get("transaction");
    if (requested && window.MeridianShell.getWorkspace() === "activity") {
      open(Number(requested), { opener: null });
    }
  });
} else {
  const requested = new URLSearchParams(window.location.search).get("transaction");
  if (requested && window.MeridianShell.getWorkspace() === "activity") {
    open(Number(requested), { opener: null });
  }
}
