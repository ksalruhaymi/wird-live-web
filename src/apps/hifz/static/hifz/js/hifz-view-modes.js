// apps/hifz/static/hifz/js/hifz-view-modes.js

(function () {
  const body = document.body;
  const mushafArea = document.getElementById("mushafArea");
  const floatingControls = document.getElementById("hifzFloatingControls");

  if (!mushafArea) return;

  function isRealMushafFullscreen() {
    return document.fullscreenElement === mushafArea;
  }

  function syncFloatingControls() {
    if (!floatingControls) return;

    const isFullscreen = isRealMushafFullscreen();
    floatingControls.classList.toggle("hidden", !isFullscreen);
  }

  function syncBodyFullscreenState() {
    body.classList.toggle("mushaf-fullscreen-active", isRealMushafFullscreen());
  }

  function syncReadingMode() {
    try {
      const saved = localStorage.getItem("quran_reading_mode");
      mushafArea.classList.toggle("reading-mode", saved === "on");
    } catch (err) {}
  }

  window.setHifzReadingMode = function (enabled) {
    mushafArea.classList.toggle("reading-mode", !!enabled);

    try {
      localStorage.setItem("quran_reading_mode", enabled ? "on" : "off");
    } catch (err) {}
  };

  window.setHifzNormalMode = function () {
    mushafArea.classList.remove("reading-mode");

    try {
      localStorage.setItem("quran_reading_mode", "off");
    } catch (err) {}

    syncBodyFullscreenState();
    syncFloatingControls();
  };

  function syncAllModes() {
    syncBodyFullscreenState();
    syncFloatingControls();
    syncReadingMode();
  }

  document.addEventListener("fullscreenchange", function () {
    syncBodyFullscreenState();
    syncFloatingControls();
  });

  document.addEventListener("hifz-fullscreen-change", function () {
    syncBodyFullscreenState();
    syncFloatingControls();
  });

  window.addEventListener("load", function () {
    syncAllModes();
  });
})();