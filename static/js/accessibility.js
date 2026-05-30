(function () {
  "use strict";

  var STORAGE_KEY = "alhafaz_a11y";
  var LEGACY_KEY = "wird_a11y";
  var FONT_STEPS  = ["sm", "base", "lg", "xl", "xxl"];
  var FONT_SIZES  = ["90%", "100%", "112%", "125%", "140%"];
  var FONT_LABELS = { sm: "90%", base: "100%", lg: "112%", xl: "125%", xxl: "140%" };

  var defaults = {
    fontStep: 1,
    highContrast: false,
    darkMode: false,
    readingMode: false,
  };

  function load() {
    try {
      var raw = localStorage.getItem(STORAGE_KEY) || localStorage.getItem(LEGACY_KEY);
      if (!raw) return Object.assign({}, defaults);
      return Object.assign({}, defaults, JSON.parse(raw));
    } catch (_) {
      return Object.assign({}, defaults);
    }
  }

  function save(state) {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (_) {}
  }

  function applyFont(step) {
    document.documentElement.style.fontSize = FONT_SIZES[step] || "100%";
  }

  function normalizeState(state) {
    if (state.darkMode && state.readingMode) {
      state.readingMode = false;
    }
    return state;
  }

  function applyState(state) {
    state = normalizeState(state);
    applyFont(state.fontStep);

    var html = document.documentElement;
    var body = document.body;
    var readingOn = !!state.readingMode && !state.darkMode;

    html.classList.toggle("a11y-dark", !!state.darkMode);
    html.classList.toggle("a11y-reading", readingOn);
    body.classList.toggle("a11y-high-contrast", !!state.highContrast);
    body.classList.toggle("a11y-reading", readingOn);

    return state;
  }

  function syncToggles(state) {
    var hc = document.getElementById("a11yHighContrast");
    var dm = document.getElementById("a11yDarkMode");
    var rm = document.getElementById("a11yReadingMode");
    if (hc) hc.checked = !!state.highContrast;
    if (dm) dm.checked = !!state.darkMode;
    if (rm) rm.checked = !!state.readingMode;
    var fv = document.getElementById("a11yFontVal");
    if (fv) fv.textContent = FONT_LABELS[FONT_STEPS[state.fontStep]];
  }

  function buildPanel(state) {
    var lang = document.documentElement.lang || "en";
    var isRtl = ["ar", "ur", "fa"].indexOf(lang) !== -1;

    var labels = {
      title: isRtl ? "إمكانية الوصول" : "Accessibility",
      fontSize: isRtl ? "حجم الخط" : "Font Size",
      highContrast: isRtl ? "تباين عالٍ" : "High Contrast",
      darkMode: isRtl ? "الوضع الليلي" : "Dark Mode",
      readingMode: isRtl ? "وضع القراءة" : "Reading Mode",
      reset: isRtl ? "إعادة الإعدادات" : "Reset Settings",
    };

    var panel = document.createElement("div");
    panel.id = "a11yPanel";
    panel.setAttribute("role", "dialog");
    panel.setAttribute("aria-label", labels.title);

    panel.innerHTML = [
      '<div class="a11y-header">',
        '<span class="a11y-header-title">',
          '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor" width="18" height="18">',
            '<path d="M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4zm-1 5h2l1 5 3-2 1 1.7-3 2 1.5 5.3H15l-1.5-5-1.5 5h-1.5L12 14l-3 2L7.7 14.3l3-2L9 9z"/>',
          "</svg>",
          labels.title,
        "</span>",
        '<button class="a11y-close-btn" id="a11yCloseBtn" aria-label="Close">&#10005;</button>',
      "</div>",
      '<div class="a11y-body">',
        '<div class="a11y-font-row">',
          '<span class="a11y-font-label">' + labels.fontSize + '</span>',
          '<div class="a11y-font-controls">',
            '<button class="a11y-font-btn" id="a11yFontDec" aria-label="Decrease">A-</button>',
            '<span class="a11y-font-value" id="a11yFontVal">' + FONT_LABELS[FONT_STEPS[state.fontStep]] + "</span>",
            '<button class="a11y-font-btn" id="a11yFontInc" aria-label="Increase">A+</button>',
          "</div>",
        "</div>",

        buildToggleRow("a11yHighContrast", "bi bi-circle-half", labels.highContrast, state.highContrast),
        buildToggleRow("a11yDarkMode", "bi bi-moon-fill", labels.darkMode, state.darkMode),
        buildToggleRow("a11yReadingMode", "bi bi-book-half", labels.readingMode, state.readingMode),

        '<div class="a11y-reset-row">',
          '<button class="a11y-reset-btn" id="a11yResetBtn">',
            '<i class="bi bi-arrow-counterclockwise"></i> ' + labels.reset,
          "</button>",
        "</div>",
      "</div>",
    ].join("");

    return panel;
  }

  function buildToggleRow(id, icon, label, checked) {
    return [
      '<label class="a11y-toggle-row" for="' + id + '">',
        '<span class="a11y-toggle-label">',
          '<i class="' + icon + '"></i>',
          label,
        "</span>",
        '<span class="a11y-switch">',
          '<input type="checkbox" id="' + id + '"' + (checked ? " checked" : "") + ">",
          '<span class="a11y-switch-track"></span>',
          '<span class="a11y-switch-thumb"></span>',
        "</span>",
      "</label>",
    ].join("");
  }

  function buildTrigger() {
    var btn = document.createElement("button");
    btn.id = "a11yTrigger";
    btn.setAttribute("aria-label", "Accessibility settings");
    btn.setAttribute("aria-haspopup", "true");
    btn.setAttribute("aria-expanded", "false");
    btn.innerHTML = [
      '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 24 24" fill="currentColor">',
        '<path d="M12 2a2 2 0 1 1 0 4 2 2 0 0 1 0-4z"/>',
        '<path fill-rule="evenodd" d="M7.5 7h9l-1 5 2.5 8h-2l-2-6.5-2 6.5h-2l-2-6.5L6 20H4l2.5-8-1-5z" clip-rule="evenodd"/>',
      "</svg>",
    ].join("");
    return btn;
  }

  document.addEventListener("DOMContentLoaded", function () {
    var state = applyState(load());

    var trigger = buildTrigger();
    var panel = buildPanel(state);
    document.body.appendChild(trigger);
    document.body.appendChild(panel);

    function openPanel() {
      panel.classList.add("a11y-open");
      trigger.setAttribute("aria-expanded", "true");
    }

    function closePanel() {
      panel.classList.remove("a11y-open");
      trigger.setAttribute("aria-expanded", "false");
    }

    trigger.addEventListener("click", function (e) {
      e.stopPropagation();
      if (panel.classList.contains("a11y-open")) {
        closePanel();
      } else {
        openPanel();
      }
    });

    document.getElementById("a11yCloseBtn").addEventListener("click", closePanel);

    document.addEventListener("click", function (e) {
      if (!panel.contains(e.target) && e.target !== trigger) {
        closePanel();
      }
    });

    document.getElementById("a11yFontInc").addEventListener("click", function () {
      if (state.fontStep < FONT_STEPS.length - 1) {
        state.fontStep++;
        applyFont(state.fontStep);
        document.getElementById("a11yFontVal").textContent = FONT_LABELS[FONT_STEPS[state.fontStep]];
        save(state);
      }
    });

    document.getElementById("a11yFontDec").addEventListener("click", function () {
      if (state.fontStep > 0) {
        state.fontStep--;
        applyFont(state.fontStep);
        document.getElementById("a11yFontVal").textContent = FONT_LABELS[FONT_STEPS[state.fontStep]];
        save(state);
      }
    });

    document.getElementById("a11yHighContrast").addEventListener("change", function () {
      state.highContrast = this.checked;
      state = applyState(state);
      save(state);
    });

    document.getElementById("a11yDarkMode").addEventListener("change", function () {
      state.darkMode = this.checked;
      if (state.darkMode) {
        state.readingMode = false;
      }
      state = applyState(state);
      syncToggles(state);
      save(state);
    });

    document.getElementById("a11yReadingMode").addEventListener("change", function () {
      state.readingMode = this.checked;
      if (state.readingMode) {
        state.darkMode = false;
      }
      state = applyState(state);
      syncToggles(state);
      save(state);
    });

    document.getElementById("a11yResetBtn").addEventListener("click", function () {
      state = applyState(Object.assign({}, defaults));
      syncToggles(state);
      save(state);
    });
  });
})();
