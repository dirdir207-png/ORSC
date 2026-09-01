/* Today workspace: one dominant, honest safe-to-spend area with its inputs.
   The forecast chart is drawn from the data — never a hardcoded path — so its
   scales are truthful and its labels are direct. */

import { MeridianApiError, freshnessText, meridianFetch } from "./api.js";
import { formatCurrency } from "./format.js";

let controller = null;

/* Maximum number of upcoming money moments surfaced on the command center.
   Anything beyond this is routed to the Plan workspace for deeper review. */
const UPCOMING_LIMIT = 4;

/* The atlas forecast: semantic horizon keys in their fixed order. */
const HORIZON_ORDER = ["today", "payday", "rent", "insurance", "next_payday"];
const HORIZON_LABELS = {
  today: "Today",
  payday: "Payday",
  rent: "Rent",
  insurance: "Insurance",
  next_payday: "Next payday",
};

/* Chart geometry shared by SVG coordinates and label placement. */
const FORECAST_VIEWBOX = { w: 500, h: 120, top: 18, bottom: 100 };

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

/* Editorial command-header date: prefer the data's as-of date, else today. */
function editorialDate(value) {
  const parsed = value ? new Date(value) : new Date();
  if (Number.isNaN(parsed.getTime())) {
    return "Today";
  }
  return new Intl.DateTimeFormat(undefined, {
    weekday: "long",
    month: "long",
    day: "numeric",
  })
    .format(parsed)
    .toUpperCase();
}

/* Turn a coverage_horizons map into an ordered series of {label, value, norm}
   points. Numeric keys ("7d", "30d") scale horizontally by their day offset;
   semantic keys (today/payday/...) spread evenly in their fixed order. */
function forecastSeries(coverage) {
  if (!coverage) {
    return [];
  }
  const entries = Object.entries(coverage).filter(
    ([, value]) => typeof value === "number" && Number.isFinite(value),
  );
  if (!entries.length) {
    return [];
  }
  const numeric = entries.every(([key]) => /^\d+d$/i.test(key));
  if (numeric) {
    const items = entries
      .map(([key, value]) => ({ key, value, offset: parseInt(key, 10) }))
      .sort((a, b) => a.offset - b.offset);
    const maxOffset = items[items.length - 1].offset || 1;
    return items.map((item) => ({
      label: item.key,
      value: item.value,
      norm: item.offset / maxOffset,
    }));
  }
  const items = entries
    .map(([key, value]) => ({ key: String(key).toLowerCase(), value }))
    .filter((item) => HORIZON_ORDER.indexOf(item.key) >= 0)
    .sort((a, b) => HORIZON_ORDER.indexOf(a.key) - HORIZON_ORDER.indexOf(b.key));
  const n = items.length;
  return items.map((item, index) => ({
    label: HORIZON_LABELS[item.key] || item.key,
    value: item.value,
    norm: n > 1 ? index / (n - 1) : 0,
  }));
}

function renderForecast(root, forecast) {
  const graphic = root.querySelector("[data-forecast]");
  const labelWrap = root.querySelector("[data-forecast-labels]");
  const floor = root.querySelector("[data-forecast-floor]");
  const shade = root.querySelector("[data-forecast-shade]");
  const line = root.querySelector("[data-forecast-line]");
  const labels = Array.from(root.querySelectorAll("[data-forecast-label]"));
  if (!graphic || !line || !shade) {
    return;
  }
  const available = !!(forecast && forecast.available === true);
  graphic.hidden = !available;
  if (labelWrap) {
    labelWrap.hidden = !available;
  }

  if (!available) {
    line.setAttribute("points", "");
    shade.setAttribute("d", "");
    graphic.setAttribute("aria-label", "Projected balance unavailable");
    return;
  }

  const series = forecastSeries(forecast.coverage_horizons);
  if (!series.length) {
    line.setAttribute("points", "");
    shade.setAttribute("d", "");
    graphic.setAttribute("aria-label", "Projected balance unavailable");
    return;
  }

  const { w, h, top, bottom } = FORECAST_VIEWBOX;
  const innerPad = 14;

  /* Truthful y-scale: include the drawn points plus the forecast low point and
     opening cash so the line is never clipped or exaggerated. */
  const scaleValues = series.map((point) => point.value);
  if (typeof forecast.low_point === "number") {
    scaleValues.push(forecast.low_point);
  }
  if (typeof forecast.starting_cash === "number") {
    scaleValues.push(forecast.starting_cash);
  }
  const dataMin = Math.min(...scaleValues);
  const dataMax = Math.max(...scaleValues);
  const span = dataMax - dataMin || 1;
  const topY = top + 8;
  const baseY = bottom - 4;
  const x = (norm) => innerPad + norm * (w - innerPad * 2);
  const y = (value) => baseY - ((value - dataMin) / span) * (baseY - topY);

  const points = series.map((point) => ({ x: x(point.norm), y: y(point.value) }));

  line.setAttribute(
    "points",
    points.map((p) => `${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" "),
  );
  const first = points[0];
  const last = points[points.length - 1];
  shade.setAttribute(
    "d",
    `M${first.x.toFixed(1)},${baseY.toFixed(1)} L${first.x.toFixed(1)},${first.y.toFixed(1)} ` +
      points.slice(1).map((p) => `L${p.x.toFixed(1)},${p.y.toFixed(1)}`).join(" ") +
      ` L${last.x.toFixed(1)},${baseY.toFixed(1)} Z`,
  );
  floor.setAttribute("x1", String(innerPad));
  floor.setAttribute("x2", String(w - innerPad));
  floor.setAttribute("y1", String(baseY));
  floor.setAttribute("y2", String(baseY));

  labels.forEach((span, index) => {
    const point = points[index];
    if (point) {
      span.hidden = false;
      span.style.left = `${((point.x / w) * 100).toFixed(2)}%`;
      span.textContent = series[index].label;
      span.dataset.align =
        index === 0 ? "start" : index === points.length - 1 ? "end" : "center";
    } else {
      span.hidden = true;
    }
  });

  const currency = forecast.currency || "USD";
  const detail = series
    .map((point) => `${point.label} ${formatCurrency(point.value, currency)}`)
    .join(", ");
  graphic.setAttribute(
    "aria-label",
    `Projected balance forecast over the next payday: ${detail}.`,
  );
}

function renderOptionalText(root, selector, value, fallback) {
  const node = root.querySelector(selector);
  if (node) {
    node.textContent = value || fallback;
  }
}

function renderEvidenceLinks(container, evidence) {
  if (!container) {
    return;
  }
  const items = Array.isArray(evidence) ? evidence.filter(Boolean) : [];
  container.textContent = "";
  if (!items.length) {
    container.hidden = true;
    return;
  }
  for (const entry of items) {
    const link = document.createElement("a");
    link.className = "m-evidence-link";
    link.href = entry.href || `/api/meridian/evidence/${entry.id}/content`;
    link.textContent = entry.span || entry.label || "evidence";
    container.appendChild(link);
  }
  container.hidden = false;
}

function render(root, payload) {
  const forecast = payload.forecast || {};

  const today = root.querySelector("[data-today-date]");
  if (today) {
    today.textContent = editorialDate(forecast.as_of);
  }

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

  renderForecast(root, forecast);

  const list = root.querySelector("[data-today-inputs]");
  list.textContent = "";
  const inputs = sts.inputs || {};
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
  const visibleEvents = events.slice(0, UPCOMING_LIMIT);
  for (const event of visibleEvents) {
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
  if (events.length > UPCOMING_LIMIT) {
    const more = document.createElement("li");
    more.className = "m-input-row m-input-row--more";
    const link = document.createElement("a");
    link.className = "m-evidence-link";
    link.href = "/meridian?workspace=plan";
    link.textContent = `Review ${events.length - UPCOMING_LIMIT} more in Plan`;
    more.appendChild(link);
    upcomingList.appendChild(more);
  }

  const comingIn = payload.total_cash || {};
  renderOptionalText(root, "[data-coming-in]", currencyEntry(comingIn), "—");
  renderOptionalText(
    root,
    "[data-committed]",
    currencyEntry(inputs.known_obligations),
    "—",
  );
  renderOptionalText(
    root,
    "[data-runway]",
    forecast.runway_days !== null && forecast.runway_days !== undefined
      ? `${forecast.runway_days} days`
      : null,
    "—",
  );
  renderOptionalText(
    root,
    "[data-runway-note]",
    forecast.confidence !== null && forecast.confidence !== undefined
      ? `${Math.round(forecast.confidence * 100)}% confidence`
      : null,
    "Confidence unavailable",
  );

  const beacon = payload.beacon || {};
  renderOptionalText(root, "[data-beacon-title]", beacon.title, "Your plan is steady");
  renderOptionalText(
    root,
    "[data-beacon-summary]",
    beacon.summary,
    "No urgent changes have been detected.",
  );
  renderOptionalText(
    root,
    "[data-beacon-detail]",
    beacon.detail,
    "Meridian will surface material changes here with their evidence.",
  );
  renderEvidenceLinks(root.querySelector("[data-beacon-evidence]"), beacon.evidence);

  const brief = payload.brief || {};
  renderOptionalText(root, "[data-brief-title]", brief.title, "A useful connection");
  renderOptionalText(
    root,
    "[data-brief-summary]",
    brief.summary,
    "Nothing needs your attention right now.",
  );
  renderEvidenceLinks(root.querySelector("[data-brief-evidence]"), brief.evidence);

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
  const advisorOpener = event.target.closest("[data-open-advisor]");
  if (advisorOpener && typeof window.advisorSetOpen === "function") {
    window.advisorSetOpen(true);
  }

  const beaconOpener = event.target.closest("[data-open-beacon]");
  if (beaconOpener) {
    const card = beaconOpener.closest("[data-beacon-evidence]") || beaconOpener.closest(".m-beacon-card");
    const evidenceBox = card && card.querySelector("[data-beacon-evidence]");
    if (evidenceBox && evidenceBox.children.length > 0) {
      evidenceBox.hidden = false;
      beaconOpener.setAttribute("aria-expanded", "true");
    } else if (window.MeridianShell && typeof window.MeridianShell.setWorkspace === "function") {
      window.MeridianShell.setWorkspace("activity", { focus: true });
    }
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
