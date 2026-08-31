import { meridianFetch } from "./api.js";
import { formatCurrency } from "./format.js";

const root = document.querySelector("[data-accounts]");

function textNode(tag, className, text) {
  const node = document.createElement(tag);
  node.className = className;
  node.textContent = text;
  return node;
}

function accountRow(account) {
  const row = document.createElement("article");
  row.className = "m-account-row";
  row.dataset.accountRow = "";
  const identity = document.createElement("div");
  identity.className = "m-account-identity";
  const name = textNode("h3", "m-account-name", account.name);
  name.dataset.accountName = "";
  const detail = textNode("p", "m-account-source", `${account.account_type} · ${account.provider}`);
  detail.dataset.accountSource = "";
  identity.append(name, detail);
  row.append(identity, textNode("strong", "m-account-balance", formatCurrency(account.balance, account.currency)));
  return row;
}

function renderGroups(groups) {
  const target = root.querySelector("[data-accounts-groups]");
  target.replaceChildren();
  for (const group of groups) {
    const section = document.createElement("section");
    section.className = "m-account-section";
    section.dataset.accountsGroup = group.role;
    section.append(textNode("h2", "m-section-label", group.label));
    const list = document.createElement("div");
    list.className = "m-account-list";
    for (const account of group.accounts) list.append(accountRow(account));
    section.append(list);
    target.append(section);
  }
  if (!groups.length) target.append(textNode("p", "m-empty-note", "No accounts are connected yet."));
}

function renderReimbursements(items) {
  const section = root.querySelector("[data-reimbursements]");
  section.hidden = !items.length;
  const list = root.querySelector("[data-reimbursement-list]");
  list.replaceChildren();
  for (const item of items) {
    list.append(accountRow({ ...item, account_type: "expected", balance: item.amount }));
  }
}

function renderConnections(items) {
  const list = root.querySelector("[data-connections-list]");
  list.replaceChildren();
  if (!items.length) {
    list.append(textNode("p", "m-empty-note", "No provider connections are configured."));
    return;
  }
  for (const item of items) {
    const row = document.createElement("article");
    row.className = "m-connection-row";
    row.append(textNode("strong", "m-account-name", item.provider));
    const status = textNode("span", "m-chip", item.status);
    status.dataset.state = item.status === "healthy" ? "fresh" : "stale";
    row.append(status);
    list.append(row);
  }
}

async function loadAccounts() {
  if (!root) return;
  root.setAttribute("aria-busy", "true");
  const error = root.querySelector("[data-accounts-error]");
  error.hidden = true;
  try {
    const payload = await meridianFetch("/api/meridian/accounts");
    renderGroups(payload.groups || []);
    renderReimbursements(payload.reimbursements || []);
    renderConnections(payload.connections || []);
    const freshness = root.querySelector("[data-accounts-freshness]");
    freshness.dataset.state = payload.data_freshness?.status || "unavailable";
    freshness.textContent = `Data ${payload.data_freshness?.status || "unavailable"}`;
  } catch (failure) {
    error.textContent = `${failure.message} ${failure.recoveryAction || ""}`.trim();
    error.hidden = false;
  } finally {
    root.setAttribute("aria-busy", "false");
  }
}

loadAccounts();
