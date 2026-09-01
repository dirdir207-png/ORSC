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

  function reflect(theme) {
    // Drive the CSS data-theme attribute (tokens.css dark and light blocks) and
    // keep the legacy class names as a compatibility hook for older selectors.
    ROOT.dataset.theme = theme;
    if (theme === "dark") {
      ROOT.classList.add("m-theme-dark");
      ROOT.classList.remove("m-theme-light");
    } else {
      ROOT.classList.add("m-theme-light");
      ROOT.classList.remove("m-theme-dark");
    }
  }

  function syncToggles() {
    var dark = ROOT.dataset.theme === "dark";
    document.querySelectorAll(TOGGLE_SELECTOR).forEach(function(toggle) {
      toggle.setAttribute("aria-pressed", dark ? "true" : "false");
      var label = toggle.querySelector("[data-theme-label]");
      if (label) {
        label.textContent = dark ? "Light" : "Dark";
      }
    });
  }

  function applyTheme(theme) {
    reflect(theme);
    try { localStorage.setItem(STORAGE_KEY, theme); } catch (_) { /* ignore */ }
    syncToggles();
  }

  function toggleTheme() {
    var current = ROOT.dataset.theme === "dark" ? "dark" : "light";
    applyTheme(current === "dark" ? "light" : "dark");
  }

  /* Apply immediately on first paint to prevent flash. The inline head script
     already set data-theme before the stylesheets; reconcile so the toggle's
     aria-pressed reflects the active theme even if the toggle rendered late. */
  reflect(getPreferredTheme());

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

  /* Reconcile toggle state and follow system preference when the user has not
     explicitly chosen a theme. */
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    var onChange = function(event) {
      var stored = null;
      try { stored = localStorage.getItem(STORAGE_KEY); } catch (_) {}
      if (stored !== "light" && stored !== "dark") {
        reflect(event.matches ? "dark" : "light");
        syncToggles();
      }
    };
    if (mq.addEventListener) {
      mq.addEventListener("change", onChange);
    } else if (mq.addListener) {
      mq.addListener(onChange);
    }
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", syncToggles);
  } else {
    syncToggles();
  }
})();