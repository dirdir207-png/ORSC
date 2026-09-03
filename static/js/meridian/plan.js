/* Plan workspace: summary-first view model rendering, the shared-rule
   inspector, and the funding-rule editor whose only write path is an
   approval-gated proposal. */

import { MeridianApiError, meridianFetch, meridianPropose } from "./api.js";
import { formatCurrency } from "./format.js";

let controller = null;

/* Latest plan payload + selected rule, kept so delegated interactions (row
   click → inspector, edit schedule) can reach the data without re-fetching. */
let currentPlan = null;
let currentRulesById = new Map();

const TYPE_LABELS = {
  bill: "Bill",
  goal: "Goal",
  reserve: "Reserve",
  buffer: "Buffer",
  debt: "Debt",
};

function money(value, currency = "USD") {
  return value === null || value === undefined ? "—" : formatCurrency(value, currency);
}

/* Whole-dollar figure used for the prominent atlas-style sums. */
function moneyWhole(value, currency = "USD") {
  if (value === null || value === undefined) {
    return "—";
  }
  return new Intl.NumberFormat("en-US", {
    style: "currency",
    currency,
    maximumFractionDigits: 0,
  }).format(value);
}

function isMobileViewport() {
  return window.matchMedia("(max-width: 900px)").matches;
}

function formatShortDate(value) {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, { month: "short", day: "numeric" });
}

function formatLongDate(value) {
  if (!value) {
    return "—";
  }
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) {
    return value;
  }
  return parsed.toLocaleDateString(undefined, { month: "long", day: "numeric" });
}

/* ---------- Command + coverage ---------- */

function renderSummary(root, plan) {
  // Machine-readable headline (kept for assistive tech + tests).
  root.querySelector("[data-plan-headline]").textContent = plan.summary.headline;
}

function renderCoverage(root, plan) {
  const ratio = Math.max(0, Math.min(1, plan.summary.coverage_ratio || 0));
  const percent = Math.round(ratio * 100);

  const month = new Date().toLocaleDateString(undefined, { month: "long" });
  root.querySelector("[data-coverage-label]").textContent = `${month} coverage`;

  // Coverage orbit (donut ring) with an accessible numeric alternative.
  const R = 52;
  const circumference = 2 * Math.PI * R;
  const fill = root.querySelector("[data-coverage-fill]");
  fill.style.strokeDasharray = `${circumference}`;
  fill.style.strokeDashoffset = `${circumference * (1 - ratio)}`;
  root.querySelector("[data-coverage-text]").textContent = `${percent}%`;

  const orbit = root.querySelector("[data-coverage-orbit]");
  if (orbit) {
    const funded = moneyWhole(plan.summary.total_funded);
    const target = moneyWhole(plan.summary.total_target);
    orbit.setAttribute(
      "aria-label",
      `${percent}% funded — ${funded} of ${target} total funded`
    );
  }

  root.querySelector("[data-coverage-detail]").textContent =
    `${moneyWhole(plan.summary.total_funded)} of ${moneyWhole(plan.summary.total_target)} funded`;
  root.querySelector("[data-coverage-projection]").textContent =
    coverageProjection(plan);

  root.querySelector("[data-plan-total]").textContent = money(plan.summary.total_target);
  root.querySelector("[data-plan-funded]").textContent = money(plan.summary.total_funded);
  root.querySelector("[data-plan-unfunded]").textContent = money(plan.summary.unfunded);
  root.querySelector("[data-plan-next-due]").textContent = formatShortDate(plan.summary.next_due);

  const shortfall = root.querySelector("[data-plan-shortfall]");
  const first = plan.summary.first_shortfall;
  if (first) {
    shortfall.hidden = false;
    shortfall.textContent = `Shortfall: ${formatShortDate(first.date)} — ${money(first.amount)} (${first.cause})`;
  } else {
    shortfall.hidden = true;
    shortfall.textContent = "";
  }
}

function coverageProjection(plan) {
  const unfunded = plan.summary.unfunded || 0;
  if (unfunded <= 0) {
    return "Fully funded.";
  }
  const events = plan.timeline?.events || [];
  if (!events.length) {
    return "No projected funding yet.";
  }
  let accumulated = 0;
  for (const event of events) {
    accumulated += event.amount || 0;
    if (accumulated >= unfunded) {
      return `Projected complete by ${formatShortDate(event.date)}`;
    }
  }
  return "Not fully funded in the next 30 days.";
}

/* ---------- Next paycheck ---------- */

function nextPaycheck(plan) {
  const events = plan.timeline?.events || [];
  if (!events.length) {
    return null;
  }
  const sorted = [...events].sort((a, b) => (a.date < b.date ? -1 : a.date > b.date ? 1 : 0));
  const date = sorted[0].date;
  const amount = sorted
    .filter((event) => event.date === date)
    .reduce((sum, event) => sum + (event.amount || 0), 0);
  return { date, amount };
}

function renderFundingCard(root, plan, activeRuleCount) {
  const next = nextPaycheck(plan);
  root.querySelector("[data-next-paycheck-date]").textContent = next
    ? formatLongDate(next.date)
    : "—";
  root.querySelector("[data-next-paycheck-amount]").textContent = next
    ? moneyWhole(next.amount)
    : "—";

  const available =
    plan.allocation?.segments?.find((segment) => segment.label === "Available")?.amount ||
    0;
  const caption = root.querySelector("[data-funding-caption]");
  if (next) {
    caption.textContent =
      `${activeRuleCount} rule${activeRuleCount === 1 ? "" : "s"} allocate ${moneyWhole(next.amount)}; ` +
      `${moneyWhole(Math.max(0, available))} remains flexible.`;
  } else {
    caption.textContent = "No funding scheduled yet.";
  }
}

/* ---------- Allocation + timeline ---------- */

const SEGMENT_CLASSES = {
  "Committed to commitments": "is-committed",
  "Unfunded commitments": "is-unfunded",
  "Available": "is-available",
};

function renderAllocation(root, plan) {
  const bar = root.querySelector("[data-allocation-bar]");
  const legend = root.querySelector("[data-allocation-legend]");
  bar.replaceChildren();
  legend.replaceChildren();

  const cash = plan.allocation.cash_total || 0;
  for (const segment of plan.allocation.segments) {
    if (cash > 0 && segment.amount > 0) {
      const slice = document.createElement("span");
      slice.className = SEGMENT_CLASSES[segment.label] || "";
      slice.style.width = `${(segment.amount / cash) * 100}%`;
      bar.appendChild(slice);
    }
    const item = document.createElement("li");
    item.className = "m-allocation-legend-item";
    const swatch = document.createElement("span");
    swatch.className = `swatch ${SEGMENT_CLASSES[segment.label] || ""}`;
    item.appendChild(swatch);
    item.appendChild(
      document.createTextNode(`${segment.label}: ${money(segment.amount)}`)
    );
    legend.appendChild(item);
  }
}

function renderTimeline(root, plan) {
  const list = root.querySelector("[data-timeline]");
  const empty = root.querySelector("[data-timeline-empty]");
  list.replaceChildren();
  const events = plan.timeline.events || [];
  empty.hidden = events.length > 0;
  for (const event of events.slice(0, 12)) {
    const row = document.createElement("li");
    const label = document.createElement("span");
    label.textContent = `${formatShortDate(event.date)} · ${event.commitment}`;
    const amount = document.createElement("span");
    amount.className = "m-timeline-amount";
    amount.textContent = money(event.amount);
    row.append(label, amount);
    list.appendChild(row);
  }
}

/* ---------- Commitment table ---------- */

function nextDateForCommitment(plan, commitment) {
  const events = (plan.timeline?.events || []).filter(
    (event) => event.commitment_id === commitment.id
  );
  if (events.length) {
    return formatShortDate(
      events.reduce((earliest, event) =>
        event.date < earliest.date ? event : earliest
      ).date
    );
  }
  if (commitment.due_date) {
    return formatShortDate(commitment.due_date);
  }
  if (commitment.target_date) {
    return formatShortDate(commitment.target_date);
  }
  return "—";
}

function renderCommitments(root, plan, template) {
  const list = root.querySelector("[data-commitment-list]");
  const empty = root.querySelector("[data-commitments-empty]");
  // Keep the head row; remove previously rendered body rows.
  list.querySelectorAll("[data-commitment-card]").forEach((node) => node.remove());
  const commitments = plan.commitments || [];
  empty.hidden = commitments.length > 0;

  for (const commitment of commitments) {
    const row = document.createElement("div");
    row.className = "m-plan-table-row";
    row.setAttribute("role", "row");
    row.dataset.commitmentCard = String(commitment.id);
    row.tabIndex = 0;
    row.setAttribute("aria-label", `View ${commitment.name} rule`);
    row.addEventListener("keydown", (event) => {
      if (event.target !== row) {
        return;
      }
      if (event.key === "Enter" || event.key === " ") {
        event.preventDefault();
        selectedCommitment(commitment);
      }
    });

    const nameCell = document.createElement("div");
    nameCell.className = "m-plan-table-cell m-plan-cell-commitment";
    nameCell.setAttribute("role", "cell");

    const nameWrap = document.createElement("div");
    nameWrap.className = "m-plan-cell-name";
    const name = document.createElement("span");
    name.className = "m-commitment-name";
    name.textContent = commitment.name;
    const type = document.createElement("span");
    type.className = "m-commitment-type";
    type.textContent = TYPE_LABELS[commitment.type] || commitment.type;
    nameWrap.append(name, type);

    const facts = document.createElement("p");
    facts.className = "m-commitment-facts";
    const factsParts = [`${moneyWhole(commitment.funded)} of ${moneyWhole(commitment.target)}`];
    if (commitment.backing) {
      factsParts.push(`backed by ${commitment.backing.name}`);
    }
    if (commitment.due_date) {
      factsParts.push(`due ${formatShortDate(commitment.due_date)}`);
    }
    facts.textContent = factsParts.join(" · ");
    nameCell.append(nameWrap, facts);

    const fundedCell = document.createElement("div");
    fundedCell.className = "m-plan-table-cell m-plan-cell-funded";
    fundedCell.setAttribute("role", "cell");
    fundedCell.textContent = moneyWhole(commitment.funded);

    const nextCell = document.createElement("div");
    nextCell.className = "m-plan-table-cell m-plan-cell-next";
    nextCell.setAttribute("role", "cell");
    nextCell.textContent = nextDateForCommitment(plan, commitment);

    const actionCell = document.createElement("div");
    actionCell.className = "m-plan-table-cell m-plan-cell-action";
    actionCell.setAttribute("role", "cell");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "m-button m-button--quiet m-button--small";
    button.textContent = "Edit funding";
    button.addEventListener("click", (event) => {
      event.stopPropagation();
      openEditor(root, commitment, template);
    });
    actionCell.appendChild(button);

    // Live Crew bills: offer an approval-gated write-back proposal.
    if (commitment.crew_bill_id) {
      const crew = document.createElement("button");
      crew.type = "button";
      crew.className = "m-button m-button--quiet m-button--small";
      crew.textContent = "Save to Crew";
      crew.addEventListener("click", (event) => {
        event.stopPropagation();
        openCrewBillEditor(root, commitment, template);
      });
      actionCell.appendChild(crew);
    }

    row.append(nameCell, fundedCell, nextCell, actionCell);
    list.appendChild(row);
  }

  const footer = root.querySelector("[data-plan-next-funding]");
  const nextFunding =
    plan.summary.next_due ||
    (plan.timeline?.events?.length ? plan.timeline.events[0].date : null);
  if (nextFunding) {
    footer.hidden = false;
    footer.textContent = `Next funding ${formatShortDate(nextFunding)}`;
  } else {
    footer.hidden = true;
    footer.textContent = "";
  }
}

function renderDocumentDiscrepancies(root, plan) {
  const section = root.querySelector("[data-document-discrepancies]");
  const list = root.querySelector("[data-document-discrepancy-list]");
  const document_discrepancies = plan.document_discrepancies || [];
  section.hidden = document_discrepancies.length === 0;
  list.replaceChildren();
  for (const discrepancy of document_discrepancies) {
    const item = document.createElement("li");
    item.className = "m-commitment-card";
    const message = document.createElement("p");
    message.textContent = discrepancy.message;
    const approval = document.createElement("p");
    approval.className = "m-state-line";
    approval.textContent = discrepancy.requires_approval
      ? "Any change requires approval."
      : "Review only.";
    item.append(message, approval);
    list.append(item);
  }
}

/* ---------- Shared-rule inspector (desktop rail / mobile sheet) ---------- */

const inspectorState = { open: false };

function buildInspectorPanel() {
  const panel = document.createElement("section");
  panel.className = "m-inspector-inner m-plan-inspector";
  panel.dataset.planInspector = "";
  panel.innerHTML = `
    <div class="m-inspector-head">
      <span class="m-section-label">Selected rule</span>
      <button type="button" class="m-icon-button" data-plan-inspector-close data-sheet-initial-focus aria-label="Close rule details">
        <svg width="20" height="20" viewBox="0 0 24 24" fill="none" aria-hidden="true" focusable="false">
          <path d="M6 6l12 12M18 6L6 18" stroke="currentColor" stroke-width="2" stroke-linecap="round"/>
        </svg>
      </button>
    </div>
    <div class="m-inspector-scroll">
      <h2 class="m-inspector-title" data-plan-inspector-title tabindex="-1">Select a commitment</h2>
      <dl class="m-facts">
        <div class="m-fact" data-fact="rule-method"><dt>Method</dt><dd data-plan-rule-method>—</dd></div>
        <div class="m-fact" data-fact="rule-target"><dt>Target</dt><dd data-plan-rule-target>—</dd></div>
        <div class="m-fact" data-fact="rule-current"><dt>Current</dt><dd data-plan-rule-current>—</dd></div>
      </dl>
      <section class="m-inspector-section" aria-label="Rule guidance">
        <h3>Guidance</h3>
        <p class="m-state-line" data-plan-rule-note>Select a commitment to see its funding rule.</p>
      </section>
      <button type="button" class="m-button" data-plan-edit-schedule>Edit schedule</button>
    </div>`;
  return panel;
}

function ensureInspectorPanel() {
  const rail = document.querySelector("[data-inspector-rail]");
  if (!rail) {
    return null;
  }
  let panel = rail.querySelector("[data-plan-inspector]");
  if (!panel) {
    panel = buildInspectorPanel();
    panel.addEventListener("click", (event) => {
      if (event.target.closest("[data-plan-inspector-close]")) {
        closePlanInspector();
        return;
      }
      if (event.target.closest("[data-plan-edit-schedule]")) {
        openScheduleEditor();
      }
    });
    rail.appendChild(panel);
  }
  return { rail, panel };
}

function ruleMethodText(rule) {
  if (!rule) {
    return "No funding rule yet";
  }
  switch (rule.kind) {
    case "percent_of_paycheck":
      return `${rule.percent || 0}% of pay`;
    case "fixed_per_paycheck":
      return `${money(rule.amount)} per paycheck`;
    case "calendar":
      return `${money(rule.amount)} on a calendar cadence`;
    case "even_by_due_date":
      return "Even by due date";
    default:
      return "Manual";
  }
}

function guidanceNote(commitment, rule) {
  if (!rule) {
    return "No funding rule yet. Add one to fund this commitment.";
  }
  if (commitment.unfunded <= 0) {
    return "Fully funded. Meridian can repurpose the surplus.";
  }
  if (commitment.projected_30d > 0) {
    const months = Math.max(1, Math.ceil(commitment.unfunded / commitment.projected_30d));
    const arrives = new Date();
    arrives.setMonth(arrives.getMonth() + months);
    const label = arrives.toLocaleDateString(undefined, { month: "long", year: "numeric" });
    return `At this pace, the target arrives ${label}. Meridian can propose a faster schedule.`;
  }
  return "Underfunded. Add a funding rule to reach the target.";
}

function populateInspector(panel, commitment) {
  const rule = currentRulesById.get(String(commitment.id))?.[0] || null;
  const title = panel.querySelector("[data-plan-inspector-title]");
  title.textContent = commitment.name;
  panel.querySelector("[data-plan-rule-method]").textContent = ruleMethodText(rule);
  panel.querySelector("[data-plan-rule-target]").textContent = moneyWhole(commitment.target);
  panel.querySelector("[data-plan-rule-current]").textContent = moneyWhole(commitment.funded);
  panel.querySelector("[data-plan-rule-note]").textContent = guidanceNote(commitment, rule);
}

function openPlanInspector(commitment) {
  const ctx = ensureInspectorPanel();
  if (!ctx || !commitment) {
    return;
  }
  ctx.rail.setAttribute("data-plan-mode", "");
  populateInspector(ctx.panel, commitment);
  if (!inspectorState.open) {
    inspectorState.open = true;
    window.MeridianShell.openSheet(ctx.rail, { modal: isMobileViewport() });
  }
}

function closePlanInspector() {
  const rail = document.querySelector("[data-inspector-rail]");
  if (rail) {
    rail.removeAttribute("data-plan-mode");
  }
  if (inspectorState.open) {
    inspectorState.open = false;
    window.MeridianShell.closeSheet();
  }
}

function openScheduleEditor() {
  // "Edit schedule" behaves like the row's Edit funding control.
  if (isMobileViewport()) {
    closePlanInspector();
  }
  const root = document.querySelector("[data-plan-root]");
  const template = root.closest("main").querySelector("[data-funding-editor-template]");
  const card = root.querySelector(`[data-commitment-card="${currentInspectorCommitmentId}"]`);
  const commitment = currentPlan?.commitments?.find(
    (item) => item.id === currentInspectorCommitmentId
  );
  if (card && commitment) {
    openEditor(root, commitment, template);
    card.scrollIntoView({ block: "center" });
    card.querySelector("[data-funding-editor] input, [data-funding-editor] select")?.focus();
  }
}

let currentInspectorCommitmentId = null;

function selectedCommitment(commitment) {
  if (!commitment) {
    return;
  }
  currentInspectorCommitmentId = commitment.id;
  openPlanInspector(commitment);
}

/* ---------- Funding-rule editor ---------- */

function describeRule(kind, amount, percent) {
  switch (kind) {
    case "fixed_per_paycheck":
      return `Moves ${money(amount)} from available cash on each paycheck.`;
    case "percent_of_paycheck":
      return `Moves ${percent || 0}% of each paycheck.`;
    case "calendar":
      return `Moves ${money(amount)} on a repeating calendar cadence.`;
    case "even_by_due_date":
      return `Splits the remaining amount evenly between now and the due date.`;
    default:
      return "";
  }
}

function openEditor(root, commitment, template) {
  root.querySelectorAll("[data-funding-editor]").forEach((node) => node.remove());
  const editor = template.content.firstElementChild.cloneNode(true);
  editor.dataset.commitmentId = String(commitment.id);
  const preview = editor.querySelector("[data-editor-preview]");

  const kindSelect = editor.querySelector('select[name="kind"]');
  const amountInput = editor.querySelector('input[name="amount"]');
  const percentInput = editor.querySelector('input[name="percent"]');

  function syncFields() {
    const kind = kindSelect.value;
    editor.querySelector('[data-editor-field="amount"]').hidden = kind === "percent_of_paycheck";
    editor.querySelector('[data-editor-field="percent"]').hidden = kind !== "percent_of_paycheck";
    preview.textContent = describeRule(
      kind,
      amountInput.value ? Number(amountInput.value) : null,
      percentInput.value
    );
  }

  kindSelect.addEventListener("change", syncFields);
  amountInput.addEventListener("input", syncFields);
  percentInput.addEventListener("input", syncFields);
  editor.querySelector("[data-editor-cancel]").addEventListener("click", () => editor.remove());

  editor.addEventListener("submit", async (event) => {
    event.preventDefault();
    const note = editor.querySelector("[data-editor-note]");
    const rule = { kind: kindSelect.value };
    if (kindSelect.value === "percent_of_paycheck") {
      if (percentInput.value) {
        rule.percent = Number(percentInput.value);
      }
    } else if (amountInput.value) {
      rule.amount = Number(amountInput.value);
    }
    note.hidden = true;
    try {
      await meridianPropose("/api/meridian/funding-rules/propose", {
        commitment_id: commitment.id,
        rule,
      });
      note.hidden = false;
      note.textContent = "Proposal created — approve it in Pending Actions.";
      note.dataset.state = "ok";
    } catch (error) {
      note.hidden = false;
      note.dataset.state = "error";
      note.textContent =
        error instanceof MeridianApiError
          ? `${error.message} ${error.recoveryAction}`
          : "The proposal could not be created.";
    }
  });

  syncFields();
  root.querySelector(`[data-commitment-card="${commitment.id}"]`).appendChild(editor);
  return editor;
}

/* ---------- Live Crew bill write-back (approval-gated) ---------- */

function openCrewBillEditor(root, commitment, template) {
  root.querySelectorAll("[data-funding-editor]").forEach((node) => node.remove());
  const editor = template.content.firstElementChild.cloneNode(true);
  editor.dataset.commitmentId = String(commitment.id);
  const preview = editor.querySelector("[data-editor-preview]");
  const kindSelect = editor.querySelector('select[name="kind"]');
  const amountInput = editor.querySelector('input[name="amount"]');
  const percentInput = editor.querySelector('input[name="percent"]');
  const note = editor.querySelector("[data-editor-note]");
  const submit = editor.querySelector('button[type="submit"]');

  // Re-purpose: Create a Crew bill write-back proposal.
  kindSelect.hidden = true;
  percentInput.closest('[data-editor-field="percent"]').hidden = true;
  amountInput.value = "";
  amountInput.setAttribute("placeholder", `New amount ($) for ${commitment.name}`);
  preview.textContent = `Approve to push a ${commitment.name} amount change to Crew.`;
  submit.textContent = "Propose to Crew";

  editor.querySelector("[data-editor-cancel]").addEventListener("click", () => editor.remove());

  editor.addEventListener("submit", async (event) => {
    event.preventDefault();
    note.hidden = true;
    const amount = Number(amountInput.value);
    if (!Number.isFinite(amount) || amount <= 0) {
      note.hidden = false;
      note.dataset.state = "error";
      note.textContent = "Enter a valid amount.";
      return;
    }
    try {
      await meridianPropose("/api/meridian/crew/bills", {
        billId: commitment.crew_bill_id,
        name: commitment.name,
        amount: Math.round(amount * 100), // dollars -> cents (Crew contract)
        frequency: "MONTHLY",
        frequencyInterval: 1,
        anchorDate: new Date().toISOString().slice(0, 10),
      });
      note.hidden = false;
      note.textContent = "Crew write-back proposed — approve it in Pending Actions.";
      note.dataset.state = "ok";
    } catch (error) {
      note.hidden = false;
      note.dataset.state = "error";
      note.textContent =
        error instanceof MeridianApiError
          ? `${error.message} ${error.recoveryAction}`
          : "The Crew write-back could not be proposed.";
    }
  });

  root.querySelector(`[data-commitment-card="${commitment.id}"]`).appendChild(editor);
  amountInput.focus();
  return editor;
}

/* ---------- New autopilot rule (approval-gated) ---------- */

function openAutopilotRuleEditor() {
  const root = document.querySelector("[data-plan-root]");
  if (!root || typeof window.MeridianShell === "undefined") return;

  const sheet = document.createElement("section");
  sheet.className = "m-sheet m-funding-editor m-autopilot-rule-editor";
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-label", "New autopilot rule");
  sheet.hidden = true;
  sheet.innerHTML = `
    <form class="m-funding-editor" data-autopilot-rule-form>
      <h3 class="m-editor-title">New autopilot rule</h3>
      <label class="m-field">
        <span class="m-field-label">Rule name</span>
        <input class="m-input" name="rule-name" type="text" required maxlength="80" placeholder="e.g. Round up spare change">
      </label>
      <p class="m-editor-preview">Creates a Crew autopilot rule; approve to push it to Crew.</p>
      <div class="m-editor-actions">
        <button type="submit" class="m-button">Propose to Crew</button>
        <button type="button" class="m-button m-button--quiet" data-autopilot-rule-cancel>Cancel</button>
      </div>
      <p class="m-editor-note" data-autopilot-rule-note hidden></p>
    </form>
  `;

  const note = sheet.querySelector("[data-autopilot-rule-note]");
  sheet.querySelector("[data-autopilot-rule-cancel]").addEventListener("click", () => {
    if (window.MeridianShell.closeSheet) window.MeridianShell.closeSheet();
  });
  sheet.querySelector("form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const name = sheet.querySelector('input[name="rule-name"]').value.trim();
    note.hidden = true;
    if (!name) {
      note.hidden = false; note.dataset.state = "error"; note.textContent = "Enter a rule name.";
      return;
    }
    try {
      await meridianPropose("/api/meridian/crew/rules", { name });
      note.hidden = false; note.dataset.state = "ok";
      note.textContent = "Autopilot rule proposed — approve it in Pending Actions.";
    } catch (error) {
      note.hidden = false; note.dataset.state = "error";
      note.textContent = error instanceof MeridianApiError
        ? `${error.message} ${error.recoveryAction}`
        : "The rule could not be proposed.";
    }
  });

  document.body.appendChild(sheet);
  window.MeridianShell.openSheet(sheet, { modal: true });
}

/* ---------- Load + wiring ---------- */

function indexRules(rules) {
  const map = new Map();
  for (const rule of rules || []) {
    const key = String(rule.commitment_id);
    if (!map.has(key)) {
      map.set(key, []);
    }
    map.get(key).push(rule);
  }
  return map;
}

async function loadPlan() {
  const root = document.querySelector("[data-plan-root]");
  if (!root) {
    return;
  }
  if (controller) {
    controller.abort();
  }
  controller = new AbortController();
  const errorBox = root.querySelector("[data-plan-error]");
  errorBox.hidden = true;
  root.setAttribute("aria-busy", "true");
  try {
    const [planRes, rulesRes] = await Promise.allSettled([
      meridianFetch("/api/meridian/plan", { signal: controller.signal }),
      meridianFetch("/api/meridian/funding-rules", { signal: controller.signal }),
    ]);
    if (planRes.status === "rejected") {
      throw planRes.reason;
    }
    const plan = planRes.value;
    const rules =
      rulesRes.status === "fulfilled" ? rulesRes.value.funding_rules || [] : [];

    currentPlan = plan;
    currentRulesById = indexRules(rules);
    const template = root
      .closest("main")
      .querySelector("[data-funding-editor-template]");

    renderSummary(root, plan);
    renderCoverage(root, plan);
    renderFundingCard(root, plan, rules.length);
    renderAllocation(root, plan);
    renderTimeline(root, plan);
    renderCommitments(root, plan, template);
    renderDocumentDiscrepancies(root, plan);

    // Desktop shows the rail by default; mobile only on demand. Prefer a
    // commitment with a funding rule and a real target (e.g. a goal/reserve).
    if (!isMobileViewport() && plan.commitments?.length) {
      const withRule =
        plan.commitments.find(
          (item) => currentRulesById.has(String(item.id)) && item.target > 0
        ) ||
        plan.commitments.find((item) => currentRulesById.has(String(item.id))) ||
        plan.commitments[0];
      selectedCommitment(withRule);
    }
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    errorBox.textContent =
      error instanceof MeridianApiError
        ? `${error.message} ${error.recoveryAction}`
        : "The plan could not be loaded.";
    errorBox.hidden = false;
  } finally {
    root.removeAttribute("aria-busy");
  }
}

window.MeridianPlan = { loadPlan };

document.addEventListener("meridian:workspacechange", (event) => {
  if (event.detail.workspace === "plan") {
    loadPlan();
  } else {
    closePlanInspector();
  }
});

document.addEventListener("click", (event) => {
  const newButton = event.target.closest("[data-plan-new-commitment]");
  if (newButton && typeof window.advisorSetOpen === "function") {
    window.advisorSetOpen(true);
    return;
  }
  const ruleButton = event.target.closest("[data-plan-new-rule]");
  if (ruleButton) {
    event.preventDefault();
    openAutopilotRuleEditor();
    return;
  }
  const root = document.querySelector("[data-plan-root]");
  if (!root) {
    return;
  }
  if (event.target.closest("button, a, input, select, textarea, .m-funding-editor")) {
    return;
  }
  const row = event.target.closest("[data-commitment-card]");
  if (row && currentPlan) {
    const id = Number(row.dataset.commitmentCard);
    const commitment = currentPlan.commitments.find((item) => item.id === id);
    selectedCommitment(commitment);
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    if (window.MeridianShell && window.MeridianShell.getWorkspace() === "plan") {
      loadPlan();
    }
  });
} else if (window.MeridianShell && window.MeridianShell.getWorkspace() === "plan") {
  loadPlan();
}
