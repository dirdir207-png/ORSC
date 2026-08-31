import { MeridianApiError, formatTimestamp, meridianFetch } from "./api.js";

const root = document.querySelector("[data-connections-root]");
const inspector = document.querySelector("[data-connection-inspector]");
let lastOpener = null;

function element(tag, className, text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function connectionRow(connection) {
  const button = element("button", "m-connection-row-settings");
  button.type = "button";
  button.dataset.connectionId = connection.public_id;
  button.setAttribute("aria-pressed", "false");
  button.setAttribute("aria-label", `Open ${connection.display_name} connection details`);

  const identity = element("span", "m-connection-identity");
  identity.append(
    element("strong", "", connection.display_name),
    element("small", "", connection.uses.join(", "))
  );
  const state = element("span", "m-connection-state", connection.state);
  state.dataset.state = connection.state;
  const freshness = element(
    "span",
    "m-connection-freshness",
    connection.freshness ? formatTimestamp(connection.freshness) : "Not updated yet"
  );
  const use = element("span", "m-connection-use", connection.uses.join(", "));
  button.append(identity, state, freshness, use, element("span", "m-row-chevron", "›"));
  button.addEventListener("click", () => openInspector(connection, button));
  return button;
}

function render(payload) {
  const ledger = root.querySelector("[data-connection-ledger]");
  ledger.replaceChildren();
  for (const group of payload.groups || []) {
    const section = element("section", "m-connection-group");
    section.dataset.connectionGroup = group.kind;
    section.append(element("h2", "m-section-label", group.label));
    const list = element("div", "m-connection-list");
    if (!group.connections.length) {
      list.append(element("p", "m-settings-empty", `No ${group.label.toLowerCase()} sources connected.`));
    }
    for (const connection of group.connections) list.append(connectionRow(connection));
    section.append(list);
    ledger.append(section);
  }
}

function openInspector(connection, opener) {
  lastOpener = opener;
  root.querySelectorAll("[data-connection-id]").forEach((row) => {
    row.setAttribute("aria-pressed", row === opener ? "true" : "false");
  });
  inspector.querySelector("[data-detail-name]").textContent = connection.display_name;
  inspector.querySelector("[data-detail-state]").textContent =
    `${connection.state} · ${connection.freshness ? formatTimestamp(connection.freshness) : "freshness unavailable"}`;
  inspector.querySelector("[data-detail-uses]").textContent = connection.uses.join(", ");
  if (window.matchMedia("(max-width: 900px)").matches) {
    inspector.setAttribute("role", "dialog");
    inspector.setAttribute("aria-modal", "true");
    document.querySelector("[data-settings-shell] > .m-nav")?.setAttribute("inert", "");
    document.querySelector("[data-topbar]")?.setAttribute("inert", "");
    document.querySelector("[data-settings-shell] > main")?.setAttribute("inert", "");
  }
  inspector.hidden = false;
  inspector.querySelector("[data-close-connection]").focus();
}

function closeInspector() {
  inspector.hidden = true;
  inspector.removeAttribute("role");
  inspector.removeAttribute("aria-modal");
  document.querySelector("[data-settings-shell] > .m-nav")?.removeAttribute("inert");
  document.querySelector("[data-topbar]")?.removeAttribute("inert");
  document.querySelector("[data-settings-shell] > main")?.removeAttribute("inert");
  root.querySelectorAll("[data-connection-id]").forEach((row) => {
    row.setAttribute("aria-pressed", "false");
  });
  if (lastOpener) lastOpener.focus();
}

async function load() {
  if (!root) return;
  root.setAttribute("aria-busy", "true");
  const errorBox = root.querySelector("[data-connections-error]");
  errorBox.hidden = true;
  try {
    render(await meridianFetch("/api/meridian/settings/connections"));
  } catch (error) {
    const detail = error instanceof MeridianApiError
      ? `${error.message} ${error.recoveryAction}`
      : "Connections could not be loaded.";
    errorBox.textContent = detail;
    errorBox.hidden = false;
  } finally {
    root.removeAttribute("aria-busy");
  }
}

document.querySelector("[data-close-connection]")?.addEventListener("click", closeInspector);
document.addEventListener("keydown", (event) => {
  if (event.key === "Escape" && !inspector.hidden) closeInspector();
});

window.MeridianConnections = { load };
load();
