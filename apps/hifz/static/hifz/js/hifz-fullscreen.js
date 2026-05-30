// apps/hifz/static/hifz/js/hifz-fullscreen.js

function enterMushafFullscreen() {
  const area = document.getElementById("mushafArea");
  if (!area) return;

  if (!document.fullscreenElement) {
    area
      .requestFullscreen()
      .then(() => {
        area.classList.add("mushaf-fullscreen");
        if (typeof applyFullscreenMushafSizeStable === "function") {
          applyFullscreenMushafSizeStable();
        }
        requestAnimationFrame(() => {
          if (typeof flipBook !== "undefined" && flipBook) {
            flipBook.update();
          }
        });
      })
      .catch((err) => {
        console.error("Failed to enter mushaf fullscreen:", err);
      });
  }
}

function exitMushafFullscreen() {
  const area = document.getElementById("mushafArea");
  if (!area) return;

  if (document.fullscreenElement === area) {
    document
      .exitFullscreen()
      .then(() => {
        area.classList.remove("mushaf-fullscreen");
        if (typeof applyFullscreenMushafSizeStable === "function") {
          applyFullscreenMushafSizeStable();
        }
        requestAnimationFrame(() => {
          if (typeof flipBook !== "undefined" && flipBook) {
            flipBook.update();
          }
        });
      })
      .catch((err) => {
        console.error("Failed to exit mushaf fullscreen:", err);
      });
  }
}

function toggleMushafFullscreen() {
  const area = document.getElementById("mushafArea");
  if (!area) return;

  if (document.fullscreenElement === area) {
    exitMushafFullscreen();
    return;
  }

  enterMushafFullscreen();
}

function enforceFullscreenSizeSequence() {
  requestAnimationFrame(() => {
    requestAnimationFrame(() => {
      try {
        if (typeof applyFullscreenMushafSizeStable === "function") {
          applyFullscreenMushafSizeStable();
        } else if (typeof applyFullscreenMushafSize === "function") {
          applyFullscreenMushafSize();
        }
        if (typeof flipBook !== "undefined" && flipBook) {
          flipBook.update();
        }
      } catch (e) {
        console.warn("Fullscreen size enforcement failed:", e);
      }
    });
  });
}

document.addEventListener("fullscreenchange", function () {
  const mushafArea = document.getElementById("mushafArea");
  if (!mushafArea) return;

  const isFull = document.fullscreenElement === mushafArea;

  mushafArea.classList.toggle("mushaf-fullscreen", isFull);
  document.body.classList.toggle("mushaf-fullscreen-active", isFull);

  document.dispatchEvent(new Event("hifz-fullscreen-change"));
  enforceFullscreenSizeSequence();
});

window.enterMushafFullscreen = enterMushafFullscreen;
window.exitMushafFullscreen = exitMushafFullscreen;
window.toggleMushafFullscreen = toggleMushafFullscreen;

// إعادة قياس page-flip عند تغيّر ارتفاع الشاشة الفعلية (شريط العنوان في الجوال، إلخ)
(function scheduleHifzFlipViewportSync() {
  if (!window.HIFZ_MODE) return;

  var t;

  function bump() {
    if (typeof flipBook === "undefined" || !flipBook) return;
    try {
      flipBook.update();
    } catch (e) {}
  }

  function scheduleBump() {
    clearTimeout(t);
    t = setTimeout(bump, 60);
  }

  window.addEventListener("orientationchange", scheduleBump);
  if (window.visualViewport) {
    window.visualViewport.addEventListener("resize", scheduleBump);
  }
})();

// وجه واحد + تكبير: نقرة على الهامش الأسود خارج #mushafFlipBook لكن ضمن المنطقة (مثل بعد padding-inline)، لأن الاستماع على الكتاب لا يلتقطها.
(function initHifzFullscreenSingleSpreadMarginFlip() {
  var EDGE_CLICK_PX = 20;

  function onAreaClick(e) {
    if (!window.HIFZ_MODE) return;
    var area = document.getElementById("mushafArea");
    if (
      !area ||
      document.fullscreenElement !== area ||
      !area.classList.contains("mushaf-fullscreen")
    ) {
      return;
    }
    if (area.dataset.hifzSpread !== "single") return;
    if (
      e.target.closest &&
      (e.target.closest("[data-no-flip='true']") ||
        e.target.closest("#hifzFloatingControls") ||
        e.target.closest("#hifzFloatingControlsSafeZone") ||
        e.target.closest("#hifzAyahPlayBtn") ||
        e.target.closest(".ayah-box") ||
        e.target.closest(".ayah-polygon"))
    ) {
      return;
    }
    var book = document.getElementById("mushafFlipBook");
    if (!book || book.contains(e.target)) return;

    var ar = area.getBoundingClientRect();
    var br = book.getBoundingClientRect();
    var px = e.clientX;
    var py = e.clientY;

    if (
      px < ar.left ||
      px > ar.right ||
      py < ar.top ||
      py > ar.bottom
    ) {
      return;
    }

    var inBandY = py >= br.top && py <= br.bottom;
    var leftStripe = px >= br.left - EDGE_CLICK_PX && px < br.left;
    var rightStripe = px > br.right && px <= br.right + EDGE_CLICK_PX;

    if (!inBandY || !(leftStripe || rightStripe)) return;

    if (typeof window.flipPrev !== "function" || typeof window.flipNext !== "function") return;

    e.preventDefault();
    e.stopPropagation();

    if (leftStripe) {
      window.flipPrev();
    } else {
      window.flipNext();
    }
  }

  document.addEventListener("click", onAreaClick, false);
})();