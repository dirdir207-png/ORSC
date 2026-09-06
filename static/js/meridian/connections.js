import { MeridianApiError, formatTimestamp, meridianFetch } from "./api.js";

const root = document.querySelector("[data-connections-root]");
const inspector = document.querySelector("[data-connection-inspector]");
let lastOpener = null;

// Providers the owner can add from the "Add connection" button. Each maps to a
// kind the authorize endpoint accepts; iCloud is IMAP/env-gated and is not a
// chooser option (it is configured out-of-band).
const ADDABLE_PROVIDERS = [
  {
    kind: "gmail",
    name: "Gmail",
    detail: "Bills, statements, and receipts from your inbox.",
  },
  {
    kind: "calendar",
    name: "Google Calendar",
    detail: "Payday, due-date, travel, and event timing.",
  },
];

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

/* ---------- Add connection (owner-initiated OAuth) ---------- */

// Authorize is a POST (creates a pending OAuth handoff), so it must use plain
// fetch, not meridianFetch (which only permits GET + proposal endpoints).
async function startAuthorization(kind) {
  const response = await fetch(
    `/api/meridian/settings/connections/${kind}/authorize`,
    { method: "POST", headers: { Accept: "application/json" } }
  );
  let payload = null;
  try {
    payload = await response.json();
  } catch {
    payload = null;
  }
  if (!response.ok || !payload || !payload.authorization_url) {
    const detail = payload && payload.error ? payload.error : {};
    throw new MeridianApiError({
      code: detail.code || "connection_unavailable",
      message: detail.message || "The connection could not be started.",
      recoveryAction: detail.recovery_action || "Try again in a moment.",
      status: response.status,
    });
  }
  return payload.authorization_url;
}

function openAddConnection() {
  const rootNode = document.querySelector("[data-connections-root]");
  if (!rootNode) return;

  const sheet = document.createElement("section");
  sheet.className = "m-sheet m-connection-chooser";
  sheet.setAttribute("role", "dialog");
  sheet.setAttribute("aria-modal", "true");
  sheet.setAttribute("aria-label", "Add a connection");
  const opener = document.activeElement instanceof HTMLElement ? document.activeElement : null;
  sheet.hidden = true;
  sheet.innerHTML = `
    <div class="m-connection-chooser-card">
      <h3 class="m-editor-title">Add a connection</h3>
      <p class="m-editor-preview">Choose a source to keep Meridian's picture current. Meridian only reads it.</p>
      <div class="m-connection-chooser-list"></div>
      <div class="m-editor-actions">
        <button type="button" class="m-button m-button--quiet" data-add-connection-cancel>Cancel</button>
      </div>
      <p class="m-editor-note" data-add-connection-note hidden></p>
    </div>
  `;

  const list = sheet.querySelector(".m-connection-chooser-list");
  for (const provider of ADDABLE_PROVIDERS) {
    const button = element("button", "m-connection-chooser-item");
    button.type = "button";
    button.dataset.providerKind = provider.kind;
    button.dataset.providerName = provider.name;
    button.append(
      element("strong", "", provider.name),
      element("small", "", provider.detail)
    );
    button.addEventListener("click", async () => {
      const note = sheet.querySelector("[data-add-connection-note]");
      note.hidden = true;
      button.setAttribute("aria-busy", "true");
      button.disabled = true;
      try {
        const authorizationUrl = await startAuthorization(provider.kind);
        window.location.assign(authorizationUrl);
      } catch (error) {
        const detail = error instanceof MeridianApiError
          ? `${error.message} ${error.recoveryAction}`
          : "The connection could not be started. Try again shortly.";
        note.hidden = false;
        note.dataset.state = "error";
        note.textContent = detail;
      } finally {
        button.removeAttribute("aria-busy");
        button.disabled = false;
      }
    });
    list.append(button);
  }

  function closeSheet() {
    sheet.hidden = true;
    sheet.removeAttribute("role");
    sheet.removeAttribute("aria-modal");
    sheet.removeEventListener("keydown", onKeyDown);
    sheet.remove();
    if (opener && typeof opener.focus === "function") opener.focus();
  }

  function onKeyDown(event) {
    if (event.key === "Escape") {
      event.stopPropagation();
      closeSheet();
    }
  }

  sheet.querySelector("[data-add-connection-cancel]").addEventListener("click", closeSheet);
  sheet.addEventListener("keydown", onKeyDown);

  document.body.append(sheet);
  sheet.hidden = false;
  sheet.querySelector(".m-connection-chooser-item")?.focus();
}

document.querySelector("[data-add-connection]")?.addEventListener("click", openAddConnection);

window.MeridianConnections = { load };
load();
