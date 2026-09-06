// Classification corrections are owner-initiated POSTs (not financial mutations
// requiring a proposal), so they use plain fetch — meridianFetch only permits
// GET + a small proposal allowlist.
async function postCategory(path, body) {
  const response = await fetch(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) {
    let message = "The correction could not be saved.";
    try {
      const payload = await response.json();
      if (payload && payload.error && payload.error.message) {
        message = payload.error.message;
      }
    } catch {
      /* non-JSON error body */
    }
    throw new Error(message);
  }
}

async function correct(row, category, kind, createRule) {
  await postCategory(
    `/api/meridian/transactions/${row.dataset.transactionId}/classification`,
    { category, kind, create_rule: createRule },
  );
  window.MeridianActivity.loadActivity({ cursor: null });
}

// Inline category editor (replaces a native window.prompt, which is unreliable
// and janky). Opens a small input over the Correct button; Save posts the
// correction, Cancel dismisses it. An optional `onSave` callback (batch) can
// route the category elsewhere.
function openInlineCategoryEditor(row, onSave) {
  const container = row;
  const existing = row.querySelector("[data-review-editor]");
  if (existing) {
    existing.remove();
    return;
  }
  const editor = document.createElement("div");
  editor.className = "m-review-editor";
  editor.dataset.reviewEditor = "";
  const input = document.createElement("input");
  input.className = "m-review-editor-input";
  input.type = "text";
  input.placeholder = "Category name";
  input.setAttribute("aria-label", "Correct category");
  const category = row.dataset.classificationCategory || "";
  input.value = category === "Uncategorized" ? "" : category;
  const save = document.createElement("button");
  save.type = "button";
  save.className = "m-button m-button--small m-review-editor-save";
  save.textContent = "Save";
  const cancel = document.createElement("button");
  cancel.type = "button";
  cancel.className = "m-button m-button--quiet m-button--small";
  cancel.textContent = "Cancel";

  function closeEditor() {
    editor.remove();
  }
  cancel.addEventListener("click", closeEditor);
  input.addEventListener("keydown", (e) => {
    if (e.key === "Enter") {
      e.preventDefault();
      save.click();
    }
    if (e.key === "Escape") {
      closeEditor();
    }
  });
  save.addEventListener("click", async () => {
    const value = input.value.trim();
    if (!value) {
      input.focus();
      return;
    }
    save.disabled = true;
    try {
      if (onSave) {
        await onSave(value);
      } else {
        await correct(row, value, row.dataset.kind || "spend", true);
      }
    } catch (error) {
      save.disabled = false;
      input.value = error.message || "Could not save";
      input.focus();
    }
  });

  editor.append(input, save, cancel);
  container.insertBefore(editor, container.firstChild);
  input.focus();
}

document.addEventListener("click", async (event) => {
  const row = event.target.closest("[data-transaction-row]");
  if (event.target.closest("[data-review-approve]") && row) {
    event.stopPropagation();
    const classification = row.dataset.classificationCategory || "Uncategorized";
    await correct(row, classification, row.dataset.kind || "spend", false);
    return;
  }
  if (event.target.closest("[data-review-correct]") && row) {
    event.stopPropagation();
    openInlineCategoryEditor(row);
    return;
  }
  if (event.target.closest("[data-batch-review]")) {
    const selected = [...document.querySelectorAll("[data-review-select]:checked")]
      .map((item) => Number(item.closest("[data-transaction-row]").dataset.transactionId));
    if (!selected.length) {
      return;
    }
    const first = document.querySelector(
      `[data-transaction-row][data-transaction-id="${selected[0]}"]`,
    );
    if (first) {
      openInlineCategoryEditor(first, async (category) => {
        await postCategory("/api/meridian/classifications/batch", {
          transaction_ids: selected,
          category,
          kind: "spend",
        });
        window.MeridianActivity.loadActivity({ cursor: null });
      });
    }
  }
});

document.addEventListener("change", (event) => {
  if (!event.target.matches("[data-review-select]")) {
    return;
  }
  const batch = document.querySelector("[data-batch-review]");
  batch.hidden = document.querySelector("[data-review-select]:checked") === null;
});
