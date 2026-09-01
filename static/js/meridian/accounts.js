import { meridianFetch } from "./api.js";
import { formatCurrency } from "./format.js";

const root = document.querySelector("[data-accounts]");

/* ---------- Inline icon system (line set, stroke = currentColor) ---------- */

const ROLE_ICONS = {
  cash: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><path d="M3 10.5 12 4l9 6.5M5 10v7h14v-7M9.5 17v-4h5v4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  savings: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><path d="M5 9.5h.5V7.5a1 1 0 0 1 1-1h4.5a1 1 0 0 1 .4.09A5.5 5.5 0 0 1 20 12v2.5a1 1 0 0 1-1 1h-1.3a5 5 0 0 1-4.3 3h-4.2a1 1 0 0 1-.4-.09L5 14.5a1 1 0 0 1-.5-.87V9.5Z" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/><path d="M17 11h.01" stroke="currentColor" stroke-width="2.4" stroke-linecap="round"/></svg>`,
  investments: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><path d="M4 19V5M4 19h16M7 15l3-4 2.5 2 3.5-5" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  liabilities: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><rect x="3" y="6" width="18" height="13" rx="2" stroke="currentColor" stroke-width="1.7"/><path d="M3 10h18M6.5 14.5h4" stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>`,
  reimbursements: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><path d="M12 4v10M8 10l4 4 4-4M5 19h14" stroke="currentColor" stroke-width="1.7" stroke-linecap="round" stroke-linejoin="round"/></svg>`,
  other: `<svg viewBox="0 0 24 24" fill="none" focusable="false" aria-hidden="true"><circle cx="12" cy="12" r="8.5" stroke="currentColor" stroke-width="1.7"/><path d="M9 9.5h.01M15 9.5h.01" stroke="currentColor" stroke-width="2.2" stroke-linecap="round"/></svg>`,
};

function roleIcon(role) {
  return ROLE_ICONS[role] || ROLE_ICONS.other;
}

/* ---------- Formatting helpers ---------- */

function textNode(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function prettyType(accountType) {
  const map = {
    checking: "Chequing",
    cash: "Chequing",
    depository: "Chequing",
    wallet: "Chequing",
    savings: "High-Savings",
    money_market: "High-Savings",
    reserve: "High-Savings",
    credit: "Credit",
    credit_card: "Credit",
    loan: "Credit",
    mortgage: "Credit",
    liability: "Credit",
    investment: "Investment",
    brokerage: "Investment",
    retirement: "Investment",
    asset: "Investment",
    reimbursement: "Reimbursement",
    receivable: "Reimbursement",
  };
  const key = String(accountType || "").trim().toLowerCase().replace(/-/g, "_").replace(/ /g, "_");
  return map[key] || (accountType ? accountType.charAt(0).toUpperCase() + accountType.slice(1) : "Account");
}

function relativeAge(isoTimestamp) {
  if (!isoTimestamp) return "never synced";
  const parsed = new Date(isoTimestamp);
  if (Number.isNaN(parsed.getTime())) return "recently synced";
  const diffMs = Date.now() - parsed.getTime();
  if (diffMs < 0) return "just now";
  const mins = Math.round(diffMs / 60000);
  if (mins < 1) return "just now";
  if (mins < 60) return `${mins}m ago`;
  const hours = Math.round(mins / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.round(hours / 24);
  if (days < 30) return `${days}d ago`;
  return days < 365 ? `${Math.round(days / 30)}mo ago` : `${Math.round(days / 365)}y ago`;
}

function providerList(accounts, role) {
  const names = [
    ...new Set(accounts
      .filter((a) => role === undefined || a.role === role)
      .map((a) => a.provider)
      .filter(Boolean)),
  ];
  if (!names.length) return "No sources";
  if (names.length === 1) return names[0].charAt(0).toUpperCase() + names[0].slice(1);
  return names.slice(0, -1).map((n) => n.charAt(0).toUpperCase() + n.slice(1)).join(", ")
    + `, and ${names[names.length - 1].charAt(0).toUpperCase() + names[names.length - 1].slice(1)}`;
}

/* ---------- Account identity rows (provider-neutral) ---------- */

function accountRow(account, role) {
  const row = document.createElement("article");
  row.className = "m-account-row";
  row.dataset.accountRow = "";

  const icon = document.createElement("span");
  icon.className = "m-account-icon";
  icon.dataset.accountIcon = role;
  icon.innerHTML = roleIcon(role);
  icon.setAttribute("aria-hidden", "true");

  const identity = document.createElement("div");
  identity.className = "m-account-identity";
  const name = textNode("h3", "m-account-name", account.name);
  name.dataset.accountName = "";
  const source = textNode(
    "p",
    "m-account-source",
    `${prettyType(account.account_type)} · ${relativeAge(account.synced_at)}`
  );
  source.dataset.accountSource = "";
  identity.append(name, source);
  row.append(icon, identity, textNode("strong", "m-account-balance", formatCurrency(account.balance, account.currency)));
  return row;
}

function renderGroups(groups) {
  const target = root.querySelector("[data-accounts-groups]");
  target.replaceChildren();

  // Provider-neutral grouping by financial role (never provider-led).
  const roles = [...new Set(groups.map((g) => g.role))];
  for (const role of roles) {
    const groupAccounts = groups.filter((g) => g.role === role).flatMap((g) => g.accounts);
    const group = groups.find((g) => g.role === role);
    const section = document.createElement("section");
    section.className = "m-account-group";
    section.dataset.accountsGroup = role;

    if (groupAccounts.length > 1 || roles.length > 1) {
      const heading = textNode("h2", "m-section-label", group.label);
      heading.dataset.accountsGroupLabel = role;
      section.append(heading);
    }

    const list = document.createElement("div");
    list.className = "m-account-list";
    for (const account of groupAccounts) list.append(accountRow(account, role));
    section.append(list);
    target.append(section);
  }
  if (!roles.length) target.append(textNode("p", "m-empty-note", "No accounts are connected yet."));
}

/* ---------- Net-position summary ---------- */

function summarize(groups) {
  const all = groups.flatMap((g) => g.accounts.map((a) => ({ ...a, role: g.role })));
  const liquidRoles = new Set(["cash", "savings", "investments"]);
  const liquid = all.filter((a) => liquidRoles.has(a.role));
  const liabilities = all.filter((a) => a.role === "liabilities");

  const available = liquid.reduce((sum, a) => sum + (Number(a.balance) || 0), 0);
  const liabilityTotal = liabilities.reduce((sum, a) => sum + Math.abs(Number(a.balance) || 0), 0);

  return {
    available,
    liabilities: liabilityTotal,
    availableNote: `Across ${providerList(all)} · synced ${relativeAge(liquid.length ? liquid[0].synced_at : null)}`,
    liabilitiesNote: liabilities.length
      ? `${liabilities.length} ${liabilities.length === 1 ? "card" : "cards"} · ${
          providerList(all.filter((a) => a.role === "liabilities"))
        }`
      : "No outstanding balances",
  };
}

function renderSummary(summary) {
  const available = root.querySelector("[data-available-cash]");
  const liabilities = root.querySelector("[data-liabilities]");
  const availableNote = root.querySelector("[data-available-note]");
  const liabilitiesNote = root.querySelector("[data-liabilities-note]");
  if (available) available.textContent = formatCurrency(summary.available, "USD");
  if (liabilities) liabilities.textContent = formatCurrency(summary.liabilities, "USD");
  if (availableNote) availableNote.textContent = summary.availableNote;
  if (liabilitiesNote) liabilitiesNote.textContent = summary.liabilitiesNote;
}

/* ---------- Reimbursements ---------- */

function renderReimbursements(items) {
  const section = root.querySelector("[data-reimbursements]");
  section.hidden = !items.length;
  const list = root.querySelector("[data-reimbursement-list]");
  list.replaceChildren();
  for (const item of items) {
    list.append(accountRow({ ...item, account_type: "reimbursement", balance: item.amount }, "reimbursements"));
  }
}

/* ---------- Connection-health rail ---------- */

function renderConnections(items) {
  const list = root.querySelector("[data-connections-list]");
  const status = root.querySelector("[data-connection-status]");
  const freshness = root.querySelector("[data-accounts-freshness]");
  list.replaceChildren();
  if (!items.length) {
    list.append(textNode("p", "m-empty-note", "No provider connections are configured."));
    if (status) status.textContent = "No connected sources";
    if (freshness) {
      freshness.dataset.state = "unavailable";
      freshness.textContent = "No sources";
    }
    return;
  }
  for (const item of items) {
    const row = document.createElement("article");
    row.className = "m-connection-row";
    row.dataset.connectionRow = "";
    const provider = textNode("strong", "m-account-name", item.provider.charAt(0).toUpperCase() + item.provider.slice(1));
    provider.dataset.connectionProvider = "";
    const detail = textNode(
      "span",
      "m-connection-age",
      item.status === "healthy" ? relativeAge(item.last_successful_at) : item.status
    );
    detail.dataset.connectionAge = "";
    row.append(provider, detail);
    list.append(row);
  }
  const healthy = items.every((item) => item.status === "healthy");
  if (status) status.textContent = healthy ? "All sources current" : "Sources need attention";
  if (freshness) {
    freshness.dataset.state = healthy ? "fresh" : "stale";
    freshness.textContent = healthy ? "Current" : "Stale";
  }
}

/* ---------- Boot ---------- */

async function loadAccounts() {
  if (!root) return;
  root.setAttribute("aria-busy", "true");
  const error = root.querySelector("[data-accounts-error]");
  error.hidden = true;
  try {
    const payload = await meridianFetch("/api/meridian/accounts");
    const groups = payload.groups || [];
    renderGroups(groups);
    renderSummary(summarize(groups));
    renderReimbursements(payload.reimbursements || []);
    renderConnections(payload.connections || []);
  } catch (failure) {
    error.textContent = `${failure.message} ${failure.recoveryAction || ""}`.trim();
    error.hidden = false;
  } finally {
    root.setAttribute("aria-busy", "false");
  }
}

loadAccounts();

/* ---------- Refresh now (live-data trigger) ---------- */

document.addEventListener("click", async (event) => {
  const button = event.target.closest("[data-connections-refresh]");
  if (!button || !root) return;
  event.preventDefault();
  button.setAttribute("aria-busy", "true");
  button.disabled = true;
  const previousLabel = button.textContent;
  button.textContent = "Refreshing…";
  try {
    const result = await meridianFetch("/api/meridian/sync");
    if (result && result.success) {
      button.textContent = "Updated";
      await loadAccounts();
      window.setTimeout(() => { button.textContent = "Refresh now"; }, 1500);
    } else {
      button.textContent = "Retry";
    }
  } catch (_) {
    button.textContent = "Retry";
  } finally {
    button.removeAttribute("aria-busy");
    button.disabled = false;
  }
});
