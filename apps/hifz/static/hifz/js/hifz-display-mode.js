(function () {
  // Display Mode Buttons
  const normalBtn = document.getElementById("displayModeNormal");
  const zoomBtn = document.getElementById("displayModeZoom");
  const readingBtn = document.getElementById("displayModeReading");
  const mushafArea = document.getElementById("mushafArea");

  if (!normalBtn || !zoomBtn || !readingBtn || !mushafArea) return;

  // Buttons List
  const buttons = [normalBtn, zoomBtn, readingBtn];

  // Zoom State
  function isZoomMode() {
    return document.fullscreenElement === mushafArea;
  }

  // Reading State
  function isReadingMode() {
    return mushafArea.classList.contains("reading-mode");
  }

  // Active Button State
  function setActiveButton(activeBtn) {
    buttons.forEach(function (btn) {
      btn.classList.remove("active");
    });

    if (activeBtn) {
      activeBtn.classList.add("active");
    }
  }

  // Sync Button State
  function syncButtons() {
    if (isReadingMode()) {
      setActiveButton(readingBtn);
      return;
    }

    if (isZoomMode()) {
      setActiveButton(zoomBtn);
      return;
    }

    setActiveButton(normalBtn);
  }

  // Normal Mode
  function setNormalMode() {
    mushafArea.classList.remove("reading-mode");

    try {
      localStorage.setItem("quran_reading_mode", "off");
    } catch (err) {}

    if (
      document.fullscreenElement === mushafArea &&
      typeof window.toggleMushafFullscreen === "function"
    ) {
      window.toggleMushafFullscreen();
    }

    syncButtons();
  }

  // Zoom Mode
  function setZoomMode() {
    mushafArea.classList.remove("reading-mode");

    try {
      localStorage.setItem("quran_reading_mode", "off");
    } catch (err) {}

    if (
      document.fullscreenElement !== mushafArea &&
      typeof window.toggleMushafFullscreen === "function"
    ) {
      window.toggleMushafFullscreen();
    }

    syncButtons();
  }

  // Reading Mode
  function setReadingMode() {
    mushafArea.classList.add("reading-mode");

    try {
      localStorage.setItem("quran_reading_mode", "on");
    } catch (err) {}

    if (
      document.fullscreenElement === mushafArea &&
      typeof window.toggleMushafFullscreen === "function"
    ) {
      window.toggleMushafFullscreen();
    }

    syncButtons();
  }

  // Normal Button Click
  normalBtn.addEventListener("click", function () {
    setNormalMode();
  });

  // Zoom Button Click
  zoomBtn.addEventListener("click", function () {
    setZoomMode();
  });

  // Reading Button Click
  readingBtn.addEventListener("click", function () {
    setReadingMode();
  });

  // Fullscreen State Sync
  document.addEventListener("fullscreenchange", syncButtons);
  document.addEventListener("hifz-fullscreen-change", syncButtons);

  // Init
  window.addEventListener("load", syncButtons);
  syncButtons();
})();