// نمط قراءة التفسير — مستقل عن نمط قراءة المصحف

(function () {
  if (window.__tafsirReadingModeInitialized) return;
  window.__tafsirReadingModeInitialized = true;

  var LS_KEY = "tafsir_reading_mode";

  function dispatch(active) {
    try {
      window.dispatchEvent(
        new CustomEvent("tafsir-reading-mode-change", { detail: { active: !!active } })
      );
    } catch (e) {}
  }

  document.addEventListener("DOMContentLoaded", function () {
    var area = document.getElementById("tafsirArea");
    var btn = document.getElementById("tafsirReadingModeToggle");

    var sidebar = document.getElementById("sidebarMenuWrapper");
    var recitation = document.getElementById("recitationPanelWrapper");
    var center = document.getElementById("centerColumn");
    var navbar = document.getElementById("mainNavbar");
    var footer = document.querySelector(".public-footer");

    if (!area || !btn) return;

    var switchTrack = btn.querySelector("[data-switch-track]");
    var switchKnob = btn.querySelector("[data-switch-knob]");

    function styleSwitch(isOn) {
      if (!switchTrack || !switchKnob) return;

      if (isOn) {
        switchTrack.classList.remove("bg-gray-300");
        switchTrack.classList.add("bg-emerald-500");

        switchKnob.classList.remove("right-0.5");
        switchKnob.classList.add("left-0.5");

        btn.classList.remove("text-gray-700");
        btn.classList.add("text-emerald-700");
      } else {
        switchTrack.classList.remove("bg-emerald-500");
        switchTrack.classList.add("bg-gray-300");

        switchKnob.classList.remove("left-0.5");
        switchKnob.classList.add("right-0.5");

        btn.classList.add("text-gray-700");
        btn.classList.remove("text-emerald-700");
      }
    }

    function updateState(isOn) {
      if (isOn) {
        area.classList.add("tafsir-reading-mode");

        if (sidebar) sidebar.classList.add("hidden");
        if (recitation) recitation.classList.add("hidden");
        if (navbar) navbar.classList.add("hidden");
        if (footer) footer.classList.add("hidden");

        if (center) {
          center.classList.remove("lg:col-span-8");
          center.classList.add("lg:col-span-12");
        }
      } else {
        area.classList.remove("tafsir-reading-mode");

        if (sidebar) sidebar.classList.remove("hidden");
        if (recitation) recitation.classList.remove("hidden");
        if (navbar) navbar.classList.remove("hidden");
        if (footer) footer.classList.remove("hidden");

        if (center) {
          center.classList.remove("lg:col-span-12");
          center.classList.add("lg:col-span-8");
        }
      }

      styleSwitch(isOn);

      if (typeof tafsirFlip !== "undefined" && tafsirFlip) {
        try {
          tafsirFlip.update();
        } catch (e) {
          console.warn("tafsirFlip update failed:", e);
        }
      }

      dispatch(isOn);

      try {
        localStorage.setItem(LS_KEY, isOn ? "on" : "off");
      } catch (err) {}
    }

    var savedInit;
    try {
      savedInit = localStorage.getItem(LS_KEY);
    } catch (e) {
      savedInit = null;
    }
    if (savedInit === "on" || savedInit === "off") {
      updateState(savedInit === "on");
    } else {
      updateState(area.classList.contains("tafsir-reading-mode"));
    }

    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      var isOn = !area.classList.contains("tafsir-reading-mode");
      updateState(isOn);
    });

    window.setTafsirReadingMode = function (on) {
      updateState(!!on);
    };

    var classObserver = new MutationObserver(function () {
      var isOn = area.classList.contains("tafsir-reading-mode");
      var stored = null;
      try {
        stored = localStorage.getItem(LS_KEY);
      } catch (err) {}
      if ((isOn && stored !== "on") || (!isOn && stored !== "off")) {
        try {
          localStorage.setItem(LS_KEY, isOn ? "on" : "off");
        } catch (e) {}
      }
    });
    classObserver.observe(area, { attributes: true, attributeFilter: ["class"] });
  });
})();
