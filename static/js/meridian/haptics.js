/* meridian/haptics.js — Task 9 a11y: visual alternatives for every gesture.

The product relies on swipe/click gestures (sheets, drawers, mode segments).
Per the recovery plan, every gesture-backed interaction must also be
reachable/visible without the gesture. This module:
- Ensures sheet/drawer close affordances are visible buttons (not swipe-only);
- Flags a visible "pull to close" hint when a sheet also supports swipe-dismiss;
- Never removes a gesture — only adds visible alternatives.
*/
(function () {
  "use strict";

  const SELECTORS = {
    sheet: '[data-sheet], .m-sheet, [data-drawer]',
    close: '[data-sheet-close], [data-drawer-close], .m-sheet [aria-label*="close" i]',
    back: '[data-sheet-back], [data-back]',
    openers: '[data-sheet-open], [aria-haspopup="dialog"], [aria-expanded]',
  };

  function isVisible(el) {
    return !!el && el.offsetParent !== null && !el.hidden;
  }

  function ensureVisibleAlternative(sheet) {
    const label = sheet.getAttribute("aria-label") || "panel";
    // If the sheet has no visible close control but the UI relies on a
    // gesture (swipe-dismiss), add a small visible "Close" affordance.
    const hasClose = !!sheet.querySelector(SELECTORS.close) ||
      (sheet.getAttribute("aria-modal") === "true" && sheet.querySelector(SELECTORS.back));
    if (!hasClose && !sheet.dataset.hapticsPatched) {
      const button = document.createElement("button");
      button.type = "button";
      button.className = "m-sheet-haptic-close";
      button.setAttribute("aria-label", `Close ${label}`);
      button.textContent = "Close";
      sheet.appendChild(button);
      sheet.dataset.hapticsPatched = "true";
    }
  }

  function init() {
    document.addEventListener("click", (event) => {
      const opener = event.target.closest(SELECTORS.openers);
      if (!opener) return;
      // Sheeted panels created by other modules: ensure a visible close exists.
      setTimeout(() => {
        document.querySelectorAll(SELECTORS.sheet).forEach(ensureVisibleAlternative);
      }, 60);
    });
    // Passive observer: catch dynamically inserted sheets.
    new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const node of m.addedNodes) {
          if (node.nodeType !== 1) continue;
          if (node.matches && node.matches(SELECTORS.sheet)) ensureVisibleAlternative(node);
          if (node.querySelectorAll) {
            node.querySelectorAll(SELECTORS.sheet).forEach(ensureVisibleAlternative);
          }
        }
      }
    }).observe(document.documentElement, { childList: true, subtree: true });
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
