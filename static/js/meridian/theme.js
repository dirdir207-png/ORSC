/* Meridian visual priming — theme control and brand treatment.
   Dark mode is designed independently; never derive from legacy palettes. */

(function() {
  "use strict";

  var ROOT = document.documentElement;
  var STORAGE_KEY = "meridian-theme";
  var TOGGLE_SELECTOR = "[data-theme-toggle]";

  function getPreferredTheme() {
    try {
      var stored = localStorage.getItem(STORAGE_KEY);
      if (stored === "light" || stored === "dark") return stored;
    } catch (_) { /* localStorage unavailable */ }
    return window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  }

  function applyTheme(theme) {
    if (theme === "dark") {
      ROOT.classList.add("m-theme-dark");
      ROOT.classList.remove("m-theme-light");
    } else {
      ROOT.classList.add("m-theme-light");
      ROOT.classList.remove("m-theme-dark");
    }
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) { /* ignore */ }
  }

  function toggleTheme() {
    var current = ROOT.classList.contains("m-theme-dark") ? "dark" : "light";
    applyTheme(current === "dark" ? "light" : "dark");
  }

  /* Apply immediately on first paint to prevent flash */
  applyTheme(getPreferredTheme());

  /* Expose global API */
  window.MeridianTheme = {
    getTheme: getPreferredTheme,
    setTheme: applyTheme,
    toggle: toggleTheme
  };

  /* Bind toggle controls */
  document.addEventListener("click", function(event) {
    var toggle = event.target.closest(TOGGLE_SELECTOR);
    if (toggle) {
      event.preventDefault();
      toggleTheme();
    }
  });
})();