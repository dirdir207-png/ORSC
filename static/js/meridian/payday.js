import { freshnessText, meridianFetch, meridianPropose } from "./api.js";
import { formatCurrency } from "./format.js";

const root = document.querySelector("[data-payday-root]");
let currentPayload = null;

function humanDate(value) {
  if (!value) return "—";
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric" }).format(parsed);
}

function titleCase(value) {
  return String(value || "").replaceAll("_", " ").replace(/\b\w/g, (letter) => letter.toUpperCase());
}

function render(payload) {
  currentPayload = payload;
  const pattern = payload.pattern;
  root.querySelector("[data-payday-pattern]").textContent = pattern
    ? titleCase(pattern.cadence)
    : "Not recognized";
  root.querySelector("[data-pattern-confidence]").textContent = pattern
    ? `${Math.round(pattern.confidence * 100)}% confidence · ${pattern.evidence_count} deposits`
    : "Add or confirm your payday timing";
  root.querySelector("[data-next-payday]").textContent = humanDate(pattern?.next_date);
  root.querySelector("[data-typical-income]").textContent = pattern
    ? `${formatCurrency(pattern.typical_amount, "USD")} typical income`
    : "Income unavailable";

  const nextRun = payload.next_run;
  root.querySelector("[data-next-run-total]").textContent = nextRun
    ? formatCurrency(nextRun.total, "USD")
    : "—";
  root.querySelector("[data-next-run-date]").textContent = nextRun
    ? `${humanDate(nextRun.date)} · proposal only`
    : "No run projected";

  const freshness = freshnessText(payload.data_freshness);
  const freshnessNode = root.querySelector("[data-payday-freshness]");
  freshnessNode.dataset.state = freshness.state;
  freshnessNode.textContent = freshness.label;

  const commitment = root.querySelector("[data-payday-commitment]");
  commitment.replaceChildren();
  for (const rule of payload.rules || []) {
    const option = document.createElement("option");
    option.value = rule.commitment_id;
    option.dataset.ruleId = rule.id;
    option.dataset.kind = rule.kind;
    option.dataset.amount = rule.amount ?? "";
    option.textContent = rule.commitment;
    commitment.append(option);
  }
  const firstRule = payload.rules?.[0];
  root.querySelector("[data-payday-kind]").value = firstRule?.kind || "fixed_per_paycheck";
  root.querySelector("[data-payday-amount]").value = firstRule?.amount ?? "";

  const contributions = root.querySelector("[data-payday-contributions]");
  contributions.replaceChildren();
  for (const item of nextRun?.contributions || []) {
    const row = document.createElement("div");
    row.className = "m-payday-contribution";
    const name = document.createElement("span");
    name.textContent = item.commitment;
    const amount = document.createElement("strong");
    amount.textContent = formatCurrency(item.amount, "USD");
    row.append(name, amount);
    contributions.append(row);
  }
  if (!nextRun?.contributions?.length) {
    const empty = document.createElement("p");
    empty.className = "m-settings-empty";
    empty.textContent = "No funding contribution is projected yet.";
    contributions.append(empty);
  }
}

async function proposeSchedule() {
  const status = root.querySelector("[data-payday-status]");
  const commitment = root.querySelector("[data-payday-commitment]");
  const selected = commitment.selectedOptions[0];
  if (!selected || !currentPayload) {
    status.textContent = "Choose a commitment before continuing.";
    return;
  }
  const button = root.querySelector("[data-review-schedule]");
  button.disabled = true;
  try {
    await meridianPropose("/api/meridian/funding-rules/propose", {
      commitment_id: Number(selected.value),
      rule_id: selected.dataset.ruleId ? Number(selected.dataset.ruleId) : null,
      rule: {
        kind: root.querySelector("[data-payday-kind]").value,
        amount: Number(root.querySelector("[data-payday-amount]").value),
      },
    });
    status.textContent = "Proposal created for your approval. No money moved.";
  } catch (error) {
    status.textContent = `${error.message} ${error.recoveryAction || ""}`.trim();
  } finally {
    button.disabled = false;
  }
}

async function load() {
  if (!root) return;
  try {
    render(await meridianFetch("/api/meridian/settings/payday"));
  } catch (error) {
    const errorBox = root.querySelector("[data-payday-error]");
    errorBox.textContent = `${error.message} ${error.recoveryAction || ""}`.trim();
    errorBox.hidden = false;
  }
}

root?.querySelector("[data-review-schedule]")?.addEventListener("click", proposeSchedule);
load();
