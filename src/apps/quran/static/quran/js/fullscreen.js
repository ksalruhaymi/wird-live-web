// static/quran/js/fullscreen.js

function toggleMushafFullscreen() {
  const area = document.getElementById("mushafArea");
  const btn = document.getElementById("mushafFullscreenBtn");
  const icon = document.getElementById("mushafFullscreenIcon");
  const textSpan = btn ? btn.querySelector("span") : null;

  if (!area) return;

  if (!document.fullscreenElement) {
    // Enter fullscreen for mushaf
    area.requestFullscreen().then(() => {
      area.classList.add("mushaf-fullscreen");

      if (icon) icon.className = "bi bi-fullscreen-exit text-xs";
      if (textSpan) textSpan.textContent = "تصغير";

      if (typeof applyFullscreenMushafSizeStable === "function") applyFullscreenMushafSizeStable();
      requestAnimationFrame(() => {
        if (typeof flipBook !== "undefined" && flipBook) flipBook.update();
      });
    }).catch((err) => {
      console.error("Failed to enter mushaf fullscreen:", err);
    });
  } else {
    // Exit fullscreen
    document.exitFullscreen().then(() => {
      area.classList.remove("mushaf-fullscreen");

      if (icon) icon.className = "bi bi-arrows-fullscreen text-xs";
      if (textSpan) textSpan.textContent = "تكبير";

      if (typeof applyFullscreenMushafSizeStable === "function") applyFullscreenMushafSizeStable();
      requestAnimationFrame(() => {
        if (typeof flipBook !== "undefined" && flipBook) flipBook.update();
      });
    }).catch((err) => {
      console.error("Failed to exit mushaf fullscreen:", err);
    });
  }
}

function toggleTafsirFullscreen() {
  const area = document.getElementById("tafsirArea");
  const btn = document.getElementById("tafsirFullscreenBtn");
  const icon = document.getElementById("tafsirFullscreenIcon");
  const textSpan = btn ? btn.querySelector("span") : null;

  if (!area) return;

  if (!document.fullscreenElement) {
    // Enter fullscreen for tafsir
    area.requestFullscreen().then(() => {
      area.classList.add("tafsir-fullscreen");

      if (icon) icon.className = "bi bi-fullscreen-exit text-xs";
      if (textSpan) textSpan.textContent = "تصغير";

      requestAnimationFrame(() => {
        if (typeof resizeTafsirBookToViewport === "function") resizeTafsirBookToViewport();
        else if (typeof tafsirFlip !== "undefined" && tafsirFlip) tafsirFlip.update();
      });
    }).catch((err) => {
      console.error("Failed to enter tafsir fullscreen:", err);
    });
  } else {
    // Exit fullscreen
    document.exitFullscreen().then(() => {
      area.classList.remove("tafsir-fullscreen");

      if (icon) icon.className = "bi bi-arrows-fullscreen text-xs";
      if (textSpan) textSpan.textContent = "تكبير";

      requestAnimationFrame(() => {
        if (typeof resizeTafsirBookToViewport === "function") resizeTafsirBookToViewport();
        else if (typeof tafsirFlip !== "undefined" && tafsirFlip) tafsirFlip.update();
      });
    }).catch((err) => {
      console.error("Failed to exit tafsir fullscreen:", err);
    });
  }
}

// Keep state in sync when user presses ESC, etc.
document.addEventListener("fullscreenchange", () => {
  const isFull = !!document.fullscreenElement;

  const mushafArea = document.getElementById("mushafArea");
  const tafsirArea = document.getElementById("tafsirArea");

  const mushafBtn = document.getElementById("mushafFullscreenBtn");
  const mushafIcon = document.getElementById("mushafFullscreenIcon");
  const mushafText = mushafBtn ? mushafBtn.querySelector("span") : null;

  const tafsirBtn = document.getElementById("tafsirFullscreenBtn");
  const tafsirIcon = document.getElementById("tafsirFullscreenIcon");
  const tafsirText = tafsirBtn ? tafsirBtn.querySelector("span") : null;

  // Mushaf state
  if (mushafArea) {
    if (isFull && document.fullscreenElement === mushafArea) {
      mushafArea.classList.add("mushaf-fullscreen");
      if (mushafIcon) mushafIcon.className = "bi bi-fullscreen-exit text-xs";
      if (mushafText) mushafText.textContent = "تصغير";
    } else {
      mushafArea.classList.remove("mushaf-fullscreen");
      if (mushafIcon) mushafIcon.className = "bi bi-arrows-fullscreen text-xs";
      if (mushafText) mushafText.textContent = "تكبير";
    }
  }

  // Tafsir state
  if (tafsirArea) {
    if (isFull && document.fullscreenElement === tafsirArea) {
      tafsirArea.classList.add("tafsir-fullscreen");
      if (tafsirIcon) tafsirIcon.className = "bi bi-fullscreen-exit text-xs";
      if (tafsirText) tafsirText.textContent = "تصغير";
    } else {
      tafsirArea.classList.remove("tafsir-fullscreen");
      if (tafsirIcon) tafsirIcon.className = "bi bi-arrows-fullscreen text-xs";
      if (tafsirText) tafsirText.textContent = "تكبير";
    }
  }

  if (typeof applyFullscreenMushafSizeStable === "function") applyFullscreenMushafSizeStable();
  requestAnimationFrame(() => {
    if (typeof flipBook !== "undefined" && flipBook) flipBook.update();
    if (typeof resizeTafsirBookToViewport === "function") resizeTafsirBookToViewport();
    else if (typeof tafsirFlip !== "undefined" && tafsirFlip) tafsirFlip.update();
  });
});

