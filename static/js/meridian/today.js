/* Today workspace: one dominant, honest safe-to-spend area with its inputs. */

import { MeridianApiError, freshnessText, meridianFetch } from "./api.js";
import { formatCurrency } from "./format.js";

let controller = null;

function currencyEntry(entry) {
  if (!entry) {
    return "Unavailable";
  }
  if (entry.amount !== null && entry.amount !== undefined) {
    return formatCurrency(entry.amount, entry.currency);
  }
  const currencies = Object.keys(entry.by_currency || {});
  if (!currencies.length) {
    return "Unavailable";
  }
  return currencies
    .map((code) => formatCurrency(entry.by_currency[code], code))
    .join(" + ");
}

function renderFreshness(chip, freshness) {
  const view = freshnessText(freshness);
  chip.dataset.state = view.state;
  chip.textContent = view.label;
}

function humanDate(value) {
  if (!value) {
    return null;
  }
  const parsed = new Date(`${value}T12:00:00`);
  if (Number.isNaN(parsed.getTime())) {
    return null;
  }
  return new Intl.DateTimeFormat(undefined, { month: "long", day: "numeric" }).format(parsed);
}

function renderOptionalText(root, selector, value, fallback) {
  const node = root.querySelector(selector);
  if (node) {
    node.textContent = value || fallback;
  }
}

function render(root, payload) {
  const figure = root.querySelector("[data-sts-figure]");
  const note = root.querySelector("[data-sts-note]");
  const sts = payload.safe_to_spend || {};
  if (sts.amount !== null && sts.amount !== undefined) {
    figure.textContent = formatCurrency(sts.amount, sts.currency);
    note.hidden = true;
  } else {
    figure.textContent = "—";
    note.hidden = false;
    note.textContent =
      sts.status === "unavailable"
        ? "Safe to spend is unavailable"
        : "Safe to spend is being calculated";
  }

  const throughDate = humanDate(sts.through_date);
  root.querySelector("[data-sts-label]").textContent = throughDate
    ? `Safe to spend until ${throughDate}`
    : "Safe to spend until next payday";

  const change = root.querySelector("[data-sts-change]");
  if (sts.change_since_yesterday !== null && sts.change_since_yesterday !== undefined) {
    const prefix = sts.change_since_yesterday >= 0 ? "+" : "";
    change.textContent = `${prefix}${formatCurrency(sts.change_since_yesterday, sts.currency)} since yesterday`;
    change.dataset.state = sts.change_since_yesterday >= 0 ? "positive" : "negative";
    change.hidden = false;
  } else {
    change.hidden = true;
    change.textContent = "";
  }

  const forecast = payload.forecast || {};
  const forecastGraphic = root.querySelector("[data-forecast]");
  forecastGraphic.hidden = forecast.available !== true;
  root.querySelector("[data-forecast-labels]").hidden = forecast.available !== true;
  forecastGraphic.setAttribute(
    "aria-label",
    forecast.available === true
      ? "Projected balance remains above the safety floor through the next payday"
      : "Projected balance unavailable"
  );

  const list = root.querySelector("[data-today-inputs]");
  list.textContent = "";
  const inputs = (sts.inputs || {});
  const rows = [];
  if (inputs.available_cash) {
    rows.push(["Available cash", currencyEntry(inputs.available_cash)]);
  }
  if (inputs.known_obligations !== null && inputs.known_obligations !== undefined) {
    rows.push([
      "Known obligations",
      typeof inputs.known_obligations === "object" && inputs.known_obligations !== null
        ? currencyEntry(inputs.known_obligations)
        : String(inputs.known_obligations),
    ]);
  }
  for (const [label, value] of rows) {
    const item = document.createElement("li");
    item.className = "m-input-row";
    item.setAttribute("data-input", "");
    const labelNode = document.createElement("span");
    labelNode.className = "m-input-label";
    labelNode.textContent = label;
    const valueNode = document.createElement("span");
    valueNode.className = "m-input-value";
    valueNode.textContent = value;
    item.append(labelNode, valueNode);
    list.appendChild(item);
  }

  const reason = root.querySelector("[data-today-reason]");
  if (inputs.reason) {
    reason.hidden = false;
    reason.textContent = inputs.reason;
  } else {
    reason.hidden = true;
    reason.textContent = "";
  }

  const upcomingEmpty = root.querySelector("[data-upcoming-empty]");
  const upcomingList = root.querySelector("[data-upcoming-list]");
  const events = Array.isArray(payload.upcoming_events) ? payload.upcoming_events : [];
  upcomingList.replaceChildren();
  upcomingEmpty.hidden = events.length > 0;
  for (const event of events) {
    const row = document.createElement("li");
    row.className = "m-input-row";
    const label = document.createElement("span");
    label.className = "m-input-label";
    label.textContent = event.label || "Event";
    const value = document.createElement("span");
    value.className = "m-input-value";
    value.textContent = [event.date, event.amount].filter(Boolean).join(" · ");
    row.append(label, value);
    upcomingList.appendChild(row);
  }

  const comingIn = payload.total_cash || {};
  renderOptionalText(root, "[data-coming-in]", currencyEntry(comingIn), "—");
  renderOptionalText(
    root,
    "[data-committed]",
    currencyEntry(inputs.known_obligations),
    "—"
  );
  renderOptionalText(
    root,
    "[data-runway]",
    forecast.runway_days !== null && forecast.runway_days !== undefined
      ? `${forecast.runway_days} days`
      : null,
    "—"
  );
  renderOptionalText(
    root,
    "[data-runway-note]",
    forecast.confidence !== null && forecast.confidence !== undefined
      ? `${Math.round(forecast.confidence * 100)}% confidence`
      : null,
    "Confidence unavailable"
  );

  const beacon = payload.beacon || {};
  renderOptionalText(root, "[data-beacon-title]", beacon.title, "Your plan is steady");
  renderOptionalText(
    root,
    "[data-beacon-summary]",
    beacon.summary,
    "No urgent changes have been detected."
  );
  renderOptionalText(
    root,
    "[data-beacon-detail]",
    beacon.detail,
    "Meridian will surface material changes here with their evidence."
  );

  const brief = payload.brief || {};
  renderOptionalText(root, "[data-brief-title]", brief.title, "A useful connection");
  renderOptionalText(
    root,
    "[data-brief-summary]",
    brief.summary,
    "Nothing needs your attention right now."
  );

  renderFreshness(root.querySelector("[data-freshness]"), payload.data_freshness);
}

async function loadToday() {
  const root = document.querySelector("[data-today-root]");
  if (!root) {
    return;
  }
  if (controller) {
    controller.abort();
  }
  controller = new AbortController();
  const errorBox = root.querySelector("[data-today-error]");
  errorBox.hidden = true;
  root.setAttribute("aria-busy", "true");
  try {
    const payload = await meridianFetch("/api/meridian/today", {
      signal: controller.signal,
    });
    render(root, payload);
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      return;
    }
    const detail =
      error instanceof MeridianApiError
        ? `${error.message} ${error.recoveryAction}`
        : "Something went wrong while loading Today.";
    errorBox.textContent = detail;
    errorBox.hidden = false;
  } finally {
    if (controller && !controller.signal.aborted) {
      root.removeAttribute("aria-busy");
    }
  }
}

window.MeridianToday = { loadToday };

document.addEventListener("click", (event) => {
  const opener = event.target.closest("[data-open-advisor]");
  if (opener && typeof window.advisorSetOpen === "function") {
    window.advisorSetOpen(true);
  }
});

document.addEventListener("meridian:workspacechange", (event) => {
  if (event.detail.workspace === "today") {
    loadToday();
  }
});

if (document.readyState === "loading") {
  document.addEventListener("DOMContentLoaded", () => {
    if (window.MeridianShell && window.MeridianShell.getWorkspace() === "today") {
      loadToday();
    }
  });
} else if (window.MeridianShell && window.MeridianShell.getWorkspace() === "today") {
  loadToday();
}
