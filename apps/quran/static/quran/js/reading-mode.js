// static/quran/js/reading-mode.js

(function () {
  if (window.__readingModeInitialized) return;
  window.__readingModeInitialized = true;

  document.addEventListener("DOMContentLoaded", function () {
    const area = document.getElementById("mushafArea");
    const btn = document.getElementById("readingModeToggle");

    const sidebar = document.getElementById("sidebarMenuWrapper");
    const recitation = document.getElementById("recitationPanelWrapper");
    const center = document.getElementById("centerColumn");
    const navbar = document.getElementById("mainNavbar"); // optional if you added this id in base.html
    const footer = document.querySelector(".public-footer");
    const exitReadBtn = document.getElementById("exitReadingModeBtn");
    const quranBadgeChip = document.getElementById("quranBadgeChip");
    const tafsirBtn = document.getElementById("openTafsirModeBtn");
    const mushafField = document.getElementById("quranMushafField");
    const qariField = document.getElementById("quranQariField");
    const fihrisField = document.getElementById("quranFihrisField");

    if (!area || !btn) return;

    const switchTrack = btn.querySelector("[data-switch-track]");
    const switchKnob = btn.querySelector("[data-switch-knob]");

    const LS_KEY = "quran_reading_mode";

    function syncExitButtonVisibility() {
      if (!exitReadBtn || !area) return;
      const isOn = area.classList.contains("reading-mode");
      exitReadBtn.classList.toggle("hidden", !isOn);
    }

    function syncToolbarOrder(isOn) {
      if (exitReadBtn) exitReadBtn.style.order = isOn ? "1" : "";
      if (quranBadgeChip) quranBadgeChip.style.order = isOn ? "2" : "";
      if (tafsirBtn) tafsirBtn.style.order = isOn ? "3" : "";
      if (mushafField) mushafField.style.order = isOn ? "4" : "";
      if (qariField) qariField.style.order = isOn ? "5" : "";
      if (fihrisField) fihrisField.style.order = isOn ? "6" : "";
    }

    function styleSwitch(isOn) {
      if (!switchTrack || !switchKnob) return;

      if (isOn) {
        // track green
        switchTrack.classList.remove("bg-gray-300");
        switchTrack.classList.add("bg-emerald-500");

        // knob moves to left INSIDE the track
        switchKnob.classList.remove("right-0.5");
        switchKnob.classList.add("left-0.5");

        // text color
        btn.classList.remove("text-gray-700");
        btn.classList.add("text-emerald-700");
      } else {
        // track gray
        switchTrack.classList.remove("bg-emerald-500");
        switchTrack.classList.add("bg-gray-300");

        // knob back to right
        switchKnob.classList.remove("left-0.5");
        switchKnob.classList.add("right-0.5");

        // text color
        btn.classList.add("text-gray-700");
        btn.classList.remove("text-emerald-700");
      }
    }

    function updateState(isOn) {
      if (isOn) {
        area.classList.add("reading-mode");

        if (sidebar) sidebar.classList.add("hidden");
        if (recitation) recitation.classList.add("hidden");
        if (navbar) navbar.classList.add("hidden");
        if (footer) footer.classList.add("hidden");

        if (center) {
          center.classList.remove("lg:col-span-8");
          center.classList.add("lg:col-span-12");
        }
        if (exitReadBtn) exitReadBtn.classList.remove("hidden");
      } else {
        area.classList.remove("reading-mode");

        if (sidebar) sidebar.classList.remove("hidden");
        if (recitation) recitation.classList.remove("hidden");
        if (navbar) navbar.classList.remove("hidden");
        if (footer) footer.classList.remove("hidden");

        if (center) {
          center.classList.remove("lg:col-span-12");
          center.classList.add("lg:col-span-8");
        }
        if (exitReadBtn) exitReadBtn.classList.add("hidden");
      }

      styleSwitch(isOn);

      if (typeof flipBook !== "undefined" && flipBook) {
        try {
          flipBook.update();
        } catch (e) {
          console.warn("flipBook update failed:", e);
        }
      }

      syncExitButtonVisibility();
      syncToolbarOrder(isOn);

    }

    // Keep localStorage in sync when another script/class toggles reading-mode (SPA-like flows).
    const syncFromClass = () => {
      const isOn = area.classList.contains("reading-mode");
      let stored = null;
      try {
        stored = localStorage.getItem(LS_KEY);
      } catch (e) {
        stored = null;
      }
      if ((isOn && stored !== "on") || (!isOn && stored !== "off")) {
        try {
          localStorage.setItem(LS_KEY, isOn ? "on" : "off");
        } catch (e) {}
      }
      styleSwitch(isOn);
      syncExitButtonVisibility();
      syncToolbarOrder(isOn);
    };

    // Initial state from localStorage (only if markup does not contradict).
    try {
      const saved = localStorage.getItem(LS_KEY);
      if (saved === "on" || saved === "off") {
        updateState(saved === "on");
      } else {
        updateState(area.classList.contains("reading-mode"));
      }
    } catch (e) {
      updateState(area.classList.contains("reading-mode"));
    }

    syncFromClass();

    const classObserver = new MutationObserver(syncFromClass);
    classObserver.observe(area, { attributes: true, attributeFilter: ["class"] });

    // Toggle on click
    btn.addEventListener("click", function (e) {
      e.stopPropagation();
      const isOn = !area.classList.contains("reading-mode");
      updateState(isOn);
      localStorage.setItem(LS_KEY, isOn ? "on" : "off");
    });

    // Keep visibility correct even if another script changes reading-mode class.
    if (exitReadBtn) {
      const observer = new MutationObserver(function () {
        const isOn = area.classList.contains("reading-mode");
        syncExitButtonVisibility();
        syncToolbarOrder(isOn);
      });
      observer.observe(area, { attributes: true, attributeFilter: ["class"] });
      syncExitButtonVisibility();
      syncToolbarOrder(area.classList.contains("reading-mode"));
    }

  });
})();