// apps/quran/static/quran/js/quran-page.js

let flipBook = null;
let fullscreenSizeRaf1 = null;
let fullscreenSizeRaf2 = null;

function getMushafDimensions() {
  return window.MUSHAF_DIMENSIONS || {};
}

// ─── القيم الاحتياطية — مصدرها mushaf_config.py ─────────────────────────────
// إذا أردت تغيير أي قيمة، غيّرها في mushaf_config.py فقط،
// ثم انعكاسها يصل هنا عبر window.MUSHAF_* المُحقن من الـ template.
// هذه الأرقام هي نسخة احتياطية للحالات التي يُحمَّل فيها هذا الملف
// قبل أن يُنفَّذ الـ script الـ inline في الـ template.
// !! لا تعدّل الأرقام هنا — عدّلها في mushaf_config.py !!
const _CFG_PAGE_WIDTH   = 430;   // MUSHAF_DIMENSIONS["normal"]["page_width"]
const _CFG_PAGE_HEIGHT  = 660;   // MUSHAF_DIMENSIONS["normal"]["page_height"]
const _CFG_MIN_WIDTH    = 350;   // MUSHAF_DIMENSIONS["normal"]["min_width"]
const _CFG_MAX_WIDTH    = 1000;  // MUSHAF_DIMENSIONS["normal"]["max_width"]
const _CFG_MIN_HEIGHT   = 400;   // MUSHAF_DIMENSIONS["normal"]["min_height"]
const _CFG_MAX_HEIGHT   = 1200;  // MUSHAF_DIMENSIONS["normal"]["max_height"]
const _CFG_FS_WIDTH_VW  = 100;   // MUSHAF_DIMENSIONS["fullscreen"]["width_vw"]
const _CFG_FS_H_RATIO   = 1.30;  // MUSHAF_DIMENSIONS["fullscreen"]["height_ratio"]
const _CFG_FS_MAX_W_VW  = 100;   // MUSHAF_DIMENSIONS["fullscreen"]["max_width_vw"]
const _CFG_FS_MAX_H_VH  = 100;   // MUSHAF_DIMENSIONS["fullscreen"]["max_height_vh"]
// ─────────────────────────────────────────────────────────────────────────────

function getNormalMushafConfig() {
  const dims = getMushafDimensions();

  return {
    pageWidth:  Number(dims.pageWidth  || window.MUSHAF_PAGE_WIDTH  || _CFG_PAGE_WIDTH),
    pageHeight: Number(dims.pageHeight || window.MUSHAF_PAGE_HEIGHT || _CFG_PAGE_HEIGHT),
    minWidth:   Number(dims.minWidth   || window.MUSHAF_MIN_WIDTH   || _CFG_MIN_WIDTH),
    maxWidth:   Number(dims.maxWidth   || window.MUSHAF_MAX_WIDTH   || _CFG_MAX_WIDTH),
    minHeight:  Number(dims.minHeight  || window.MUSHAF_MIN_HEIGHT  || _CFG_MIN_HEIGHT),
    maxHeight:  Number(dims.maxHeight  || window.MUSHAF_MAX_HEIGHT  || _CFG_MAX_HEIGHT),
  };
}

/** حفظ: دائماً portrait (صفحة واحدة) — مكتبة page-flip تختار landscape عندما عرض الحاوية ≥ 2×minWidth */
const HIFZ_PAGE_FLIP_FORCE_PORTRAIT_MIN = 5600;

function getPageFlipStretchDimensions() {
  const cfg = getNormalMushafConfig();
  if (!window.HIFZ_MODE) {
    return cfg;
  }
  /** مواجهة صفحتين: نفس منطق القرآن العام (عرض كافٍ ⇒ landscape) */
  if (window.HIFZ_MUSHAF_SPREAD === "double") {
    return cfg;
  }
  const minW = Math.max(cfg.minWidth, HIFZ_PAGE_FLIP_FORCE_PORTRAIT_MIN);
  return {
    ...cfg,
    minWidth: minW,
    maxWidth: Math.max(cfg.maxWidth, minW),
  };
}

function getFullscreenMushafConfig() {
  const dims = getMushafDimensions();
  const fullscreen = dims.fullscreen || {};

  return {
    widthVW:    Number(fullscreen.widthVW    || window.MUSHAF_FULLSCREEN_WIDTH_VW      || _CFG_FS_WIDTH_VW),
    heightRatio:Number(fullscreen.heightRatio|| window.MUSHAF_FULLSCREEN_HEIGHT_RATIO  || _CFG_FS_H_RATIO),
    maxWidthVW: Number(fullscreen.maxWidthVW || window.MUSHAF_FULLSCREEN_MAX_WIDTH_VW  || _CFG_FS_MAX_W_VW),
    maxHeightVH:Number(fullscreen.maxHeightVH|| window.MUSHAF_FULLSCREEN_MAX_HEIGHT_VH || _CFG_FS_MAX_H_VH),
  };
}

function isPortraitMode() {
  if (!flipBook || typeof flipBook.getOrientation !== "function") {
    return false;
  }

  return flipBook.getOrientation() === "portrait";
}

function getCurrentPageMapIndex() {
  if (!flipBook || !Array.isArray(window.QURAN_PAGE_MAP)) {
    return 0;
  }

  if (typeof flipBook.getCurrentPageIndex !== "function") {
    return 0;
  }

  return flipBook.getCurrentPageIndex();
}

function syncFlipBookOrientationUI() {
  const container = document.getElementById("mushafFlipBook");
  if (!container) return;

  const portrait = isPortraitMode();

  container.classList.toggle("is-portrait", portrait);
  container.classList.toggle("is-landscape", !portrait);

  Promise.resolve(ensurePositionsAroundCurrentSpread()).finally(() => {
    reapplyCurrentAyahHighlight();
    applySavedAyahHighlight();
  });
}

const CLICK_MARGIN = 0.20;

let CURRENT_TAFSIR_PAGE = null;
let CURRENT_AYAH_CONTEXT = null;
window.__LAST_AYAH_CLICK_EVENT__ = null;
window.__LAST_AYAH_TARGET_RECT__ = null;

const PAGE_POSITIONS_CACHE = new Map();
const PAGE_POSITIONS_PENDING = new Map();

function getRightLeftLogicalPages() {
  if (!flipBook || !Array.isArray(window.QURAN_PAGE_MAP)) {
    return { right: null, left: null };
  }

  const idx = getCurrentPageMapIndex();

  if (isPortraitMode()) {
    return {
      right: window.QURAN_PAGE_MAP[idx] || null,
      left: null
    };
  }

  return {
    right: window.QURAN_PAGE_MAP[idx] || null,
    left: window.QURAN_PAGE_MAP[idx + 1] || null
  };
}

window.getRightLeftLogicalPages = getRightLeftLogicalPages;

function updateTafsirSide() {
  const overlay = document.getElementById("tafsirOverlay");
  if (!overlay) return;

  overlay.classList.remove("left-0", "right-0");

  const { right, left } = getRightLeftLogicalPages();

  if (CURRENT_TAFSIR_PAGE && left && CURRENT_TAFSIR_PAGE === left) {
    overlay.classList.add("right-0");
  } else {
    overlay.classList.add("left-0");
  }
}

function getCurrentMushafKey() {
  return window.QURAN_MUSHAF_KEY || window.CURRENT_MUSHAF_KEY || "hafs";
}

function getCurrentQariFromUrl() {
  try {
    const params = new URLSearchParams(window.location.search);
    return params.get("qari") || "";
  } catch (err) {
    return "";
  }
}

/** عنوان المتصفح لصفحة المصحف — حفظ القرآن يستخدم /hifz/ وليس /quran/ */
function buildMushafPageBrowserUrl(logicalPage) {
  const mushafKey = getCurrentMushafKey();
  const path = window.HIFZ_MODE
    ? `/hifz/${mushafKey}/page/${logicalPage}/`
    : `/quran/${mushafKey}/page/${logicalPage}/`;

  return new URL(path, window.location.origin);
}

function getPositionsUrl(pageNumber) {
  const template = window.QURAN_POSITIONS_URL_TEMPLATE || "";
  if (!template) return "";

  const url = new URL(
    template.replace("999999", String(pageNumber)),
    window.location.origin
  );

  const mushafKey = getCurrentMushafKey();
  url.searchParams.set("mushaf", mushafKey);

  return url.toString();
}

function clearPageOverlays(pageNumber) {
  const svg = document.querySelector(`.ayah-svg[data-page="${pageNumber}"]`);
  const layer = document.querySelector(`.ayah-layer[data-page="${pageNumber}"]`);

  if (svg) {
    svg.innerHTML = "";
  }

  if (layer) {
    layer.innerHTML = "";
  }
}

function createPolygonRect(position, rect) {
  const node = document.createElementNS("http://www.w3.org/2000/svg", "rect");
  node.setAttribute("class", "ayah-polygon");
  node.setAttribute("data-surah", position.surah_number);
  node.setAttribute("data-page", position.page_number);

  if (position.ayah_number !== null && position.ayah_number !== undefined) {
    node.setAttribute("data-ayah", position.ayah_number);
  } else {
    node.setAttribute("data-ayah", "");
  }

  node.setAttribute("x", rect.x);
  node.setAttribute("y", rect.y);
  node.setAttribute("width", rect.width);
  node.setAttribute("height", rect.height);

  return node;
}

function createAyahBox(position, rect) {
  const node = document.createElement("div");
  node.className = "ayah-box";
  node.dataset.surah = String(position.surah_number);
  node.dataset.page = String(position.page_number);

  if (position.ayah_number !== null && position.ayah_number !== undefined) {
    node.dataset.ayah = String(position.ayah_number);
  } else {
    node.dataset.ayah = "";
  }

  node.style.position = "absolute";
  node.style.left = `${rect.x}%`;
  node.style.top = `${rect.y}%`;
  node.style.width = `${rect.width}%`;
  node.style.height = `${rect.height}%`;
  node.style.cursor = "pointer";

  return node;
}

function getRectsForPosition(position) {
  if (Array.isArray(position.polygon) && position.polygon.length) {
    return position.polygon.filter((rect) => (
      rect &&
      rect.x !== null &&
      rect.y !== null &&
      rect.width !== null &&
      rect.height !== null
    ));
  }

  if (
    position.x !== null &&
    position.y !== null &&
    position.width !== null &&
    position.height !== null
  ) {
    return [
      {
        x: position.x,
        y: position.y,
        width: position.width,
        height: position.height
      }
    ];
  }

  return [];
}

function reapplyCurrentAyahHighlight() {
  const current = window.currentAyahItem;
  if (!current || current.surah == null || current.ayah == null) return;

  document.dispatchEvent(
    new CustomEvent("ayah-play", {
      detail: {
        surah: current.surah,
        ayah: current.ayah
      }
    })
  );
}

function renderPagePositions(pageNumber, positions) {
  const svg = document.querySelector(`.ayah-svg[data-page="${pageNumber}"]`);
  const layer = document.querySelector(`.ayah-layer[data-page="${pageNumber}"]`);

  if (!svg || !layer) return;

  clearPageOverlays(pageNumber);

  const svgFragment = document.createDocumentFragment();
  const layerFragment = document.createDocumentFragment();

  positions.forEach((position) => {
    const rects = getRectsForPosition(position);
    if (!rects.length) return;

    rects.forEach((rect) => {
      svgFragment.appendChild(createPolygonRect(position, rect));
      layerFragment.appendChild(createAyahBox(position, rect));
    });
  });

  svg.appendChild(svgFragment);
  layer.appendChild(layerFragment);

  reapplyCurrentAyahHighlight();
  applySavedAyahHighlight();

  document.dispatchEvent(
    new CustomEvent("quran-positions-rendered", {
      detail: { page: pageNumber }
    })
  );
}

async function fetchPagePositions(pageNumber) {
  if (!pageNumber) return [];

  if (PAGE_POSITIONS_CACHE.has(pageNumber)) {
    return PAGE_POSITIONS_CACHE.get(pageNumber);
  }

  if (PAGE_POSITIONS_PENDING.has(pageNumber)) {
    return PAGE_POSITIONS_PENDING.get(pageNumber);
  }

  const url = getPositionsUrl(pageNumber);
  if (!url) return [];

  const request = fetch(url, {
    headers: {
      "X-Requested-With": "XMLHttpRequest"
    }
  })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Failed to load positions for page ${pageNumber}`);
      }
      return response.json();
    })
    .then((data) => {
      const normalized = Array.isArray(data.positions) ? data.positions : data;
      PAGE_POSITIONS_CACHE.set(pageNumber, Array.isArray(normalized) ? normalized : []);
      PAGE_POSITIONS_PENDING.delete(pageNumber);
      return PAGE_POSITIONS_CACHE.get(pageNumber);
    })
    .catch((error) => {
      PAGE_POSITIONS_PENDING.delete(pageNumber);
      console.error(error);
      return [];
    });

  PAGE_POSITIONS_PENDING.set(pageNumber, request);
  return request;
}

async function ensurePagePositions(pageNumber) {
  if (!pageNumber) return;
  const positions = await fetchPagePositions(pageNumber);
  renderPagePositions(pageNumber, positions);
}

function preloadPagePositions(pageNumber) {
  if (!pageNumber) return Promise.resolve();
  return fetchPagePositions(pageNumber).catch((error) => {
    console.error(error);
  });
}

function ensurePositionsAroundCurrentSpread() {
  const { right, left } = getRightLeftLogicalPages();
  const tasks = [];

  if (right) {
    tasks.push(ensurePagePositions(right));
  }

  if (left) {
    tasks.push(ensurePagePositions(left));
  }

  const preloadTargets = [];

  if (isPortraitMode()) {
    if (right) {
      preloadTargets.push(right + 1, right - 1);
    }
  } else {
    if (right) {
      preloadTargets.push(right + 1);
    }

    if (left) {
      preloadTargets.push(left - 1);
    }
  }

  preloadTargets
    .filter(Boolean)
    .forEach((pageNumber) => {
      tasks.push(preloadPagePositions(pageNumber));
    });

  return Promise.all(tasks);
}

function isMushafFullscreen() {
  const mushafArea = document.getElementById("mushafArea");
  return !!(mushafArea && mushafArea.classList.contains("mushaf-fullscreen"));
}

function applyFullscreenMushafSizeStable() {
  applyFullscreenMushafSize();

  if (fullscreenSizeRaf1) {
    cancelAnimationFrame(fullscreenSizeRaf1);
  }

  if (fullscreenSizeRaf2) {
    cancelAnimationFrame(fullscreenSizeRaf2);
  }

  fullscreenSizeRaf1 = requestAnimationFrame(() => {
    applyFullscreenMushafSize();

    fullscreenSizeRaf2 = requestAnimationFrame(() => {
      applyFullscreenMushafSize();
    });
  });
}

function initMushafFlipBook() {
  const container = document.getElementById("mushafFlipBook");
  if (!container) return;

  if (!window.St || !window.St.PageFlip) {
    return;
  }

  const startIndex = typeof window.QURAN_START_PAGE_INDEX === "number"
    ? window.QURAN_START_PAGE_INDEX
    : 0;

  const normalCfg = getPageFlipStretchDimensions();

  const hifzForceDoubleSpread =
  window.HIFZ_MODE && window.HIFZ_MUSHAF_SPREAD === "double";

flipBook = new St.PageFlip(container, {
  width: normalCfg.pageWidth,
  height: normalCfg.pageHeight,
  size: "stretch",
  minWidth: normalCfg.minWidth,
  maxWidth: normalCfg.maxWidth,
  minHeight: normalCfg.minHeight,
  maxHeight: normalCfg.maxHeight,
  maxShadowOpacity: 0.35,
  showCover: false,
  mobileScrollSupport: false,
  useMouseEvents: false,
  flippingTime: 800,
  startPage: startIndex,
  direction: "rtl",

  // In Hifz double-page mode, force landscape spread.
  // In single-page mode, keep portrait behavior.
  usePortrait: !hifzForceDoubleSpread,

  autoSize: true
});

  const pages = container.querySelectorAll(".page");
  flipBook.loadFromHTML(pages);
  applyFullscreenMushafSizeStable();

  syncFlipBookOrientationUI();

  let mushafRevealed = false;
  function revealMushaf() {
    if (!mushafRevealed) {
      mushafRevealed = true;
      const spinner = document.getElementById("mushafLoadingSpinner");
      const flipContainer = document.getElementById("mushafFlipContainer");
      if (spinner) spinner.remove();
      if (flipContainer) flipContainer.classList.remove("hidden");
      container.classList.add("mushaf-ready");
    }
  }

  flipBook.on("changeOrientation", function () {
    syncFlipBookOrientationUI();
    revealMushaf();

    if (isMushafFullscreen()) {
      applyFullscreenMushafSizeStable();
    }
  });

  requestAnimationFrame(function () {
    requestAnimationFrame(function () {
      revealMushaf();
    });
  });

  const { right } = getRightLeftLogicalPages();
  CURRENT_TAFSIR_PAGE = right || 1;
  updateTafsirSide();

  ensurePositionsAroundCurrentSpread().finally(() => {
    reapplyCurrentAyahHighlight();
    applySavedAyahHighlight();
  });

  flipBook.on("flip", function (e) {
    try {
      const pageIndex = e.data;

      if (!Array.isArray(window.QURAN_PAGE_MAP)) {
        return;
      }

      const visiblePages = isPortraitMode()
        ? [window.QURAN_PAGE_MAP[pageIndex] || null].filter(Boolean)
        : [
            window.QURAN_PAGE_MAP[pageIndex] || null,
            window.QURAN_PAGE_MAP[pageIndex + 1] || null
          ].filter(Boolean);

      const logicalPage = visiblePages[0];
      if (!logicalPage) {
        return;
      }

      try {
        const url = buildMushafPageBrowserUrl(logicalPage);

        const qari = getCurrentQariFromUrl();
        if (qari) {
          url.searchParams.set("qari", qari);
        }

        window.history.replaceState({}, "", url.toString());
      } catch (err) {
        console.error("Flip URL update error:", err);
      }

      if (window.WirdAnalytics && typeof window.WirdAnalytics.track === "function") {
        window.WirdAnalytics.track("page_flip", {
          page_number: logicalPage
        });
      }

      CURRENT_TAFSIR_PAGE = logicalPage;
      updateTafsirSide();
      syncFlipBookOrientationUI();

      Promise.resolve(ensurePositionsAroundCurrentSpread())
        .finally(() => {
          document.dispatchEvent(
            new CustomEvent("quran-page-flipped", {
              detail: { page: logicalPage }
            })
          );

          reapplyCurrentAyahHighlight();
          applySavedAyahHighlight();

          setTimeout(() => {
            if (typeof window.resumePendingAyahAfterPageFlip === "function") {
              window.resumePendingAyahAfterPageFlip();
            }
          }, 120);

          if (typeof window.goToExactPage === "function") {
            window.goToExactPage(logicalPage);
          }
        });
    } catch (err) {
      console.error("Flip handler error:", err);
    }
  });

  container.addEventListener("click", function (e) {
    if (!flipBook) return;

    if (e.target.closest(".ayah-box") || e.target.closest(".ayah-polygon")) {
      return;
    }

    const mushafArea = document.getElementById("mushafArea");

    /** حفظ + تكبير + وجه واحد: التقليب من شريط 20px حول عمود المحتوى (البياض) كما المنطقتان في الوجهين، بدون نسبة كبيرة من العرض. */
    const hifzSingleFullscreen =
      window.HIFZ_MODE &&
      mushafArea &&
      mushafArea.classList.contains("mushaf-fullscreen") &&
      mushafArea.dataset.hifzSpread === "single";

    if (hifzSingleFullscreen) {
      const EDGE_CLICK_PX = 20;
      const cx = e.clientX;
      const cy = e.clientY;

      let padHost = null;
      try {
        const topEl =
          typeof document.elementFromPoint === "function"
            ? document.elementFromPoint(cx, cy)
            : null;
        padHost = topEl ? topEl.closest(".page-content > div") : null;

        if (padHost && !container.contains(padHost)) {
          padHost = null;
        }
      } catch (err) {
        padHost = null;
      }

      if (padHost) {
        const pr = padHost.getBoundingClientRect();
        const xRel = cx - pr.left;
        const leftStripe = xRel >= 0 && xRel <= EDGE_CLICK_PX;
        const rightStripe = xRel >= pr.width - EDGE_CLICK_PX && xRel <= pr.width;

        if (leftStripe) {
          flipPrev();
          return;
        }

        if (rightStripe) {
          flipNext();
          return;
        }
      }

      return;
    }

    const rect = container.getBoundingClientRect();
    const clickX = e.clientX - rect.left;
    const width = rect.width;
    const edgeZone = width * (isPortraitMode() ? 0.08 : 0.05);

    if (clickX <= edgeZone) {
      flipPrev();
      return;
    }

    if (clickX >= width - edgeZone) {
      flipNext();
      return;
    }
  });

  window.addEventListener("resize", function () {
    setTimeout(() => {
      if (!flipBook) return;

      if (isMushafFullscreen()) {
        applyFullscreenMushafSize();
        return;
      }

      flipBook.update();
      syncFlipBookOrientationUI();
    }, 80);
  });
}

function loadTafsirForLogicalPage(page) {
  const overlay = document.getElementById("tafsirOverlay");
  if (!overlay) return;

  if (typeof CURRENT_TAFSIR_KEY === "undefined" || !CURRENT_TAFSIR_KEY) {
    return;
  }

  const url = new URL(window.location.href);
  url.searchParams.set("page", page);
  url.searchParams.set("mushaf", getCurrentMushafKey());

  const qari = getCurrentQariFromUrl();
  if (qari) {
    url.searchParams.set("qari", qari);
  } else {
    url.searchParams.delete("qari");
  }

  url.searchParams.set("tafsir", CURRENT_TAFSIR_KEY);
  url.searchParams.set("mode", "tafsir");

  fetch(url.toString(), {
    headers: { "X-Requested-With": "XMLHttpRequest" }
  })
    .then((res) => res.text())
    .then((html) => {
      overlay.innerHTML = html;
      CURRENT_TAFSIR_PAGE = page;
      updateTafsirSide();
    })
    .catch((err) => {
      console.error("Failed to load tafsir for page", page, err);
    });
}

function getCurrentLogicalIndex() {
  if (!flipBook || typeof flipBook.getCurrentPageIndex !== "function") {
    return 0;
  }

  return flipBook.getCurrentPageIndex();
}

function getVisibleLogicalPages() {
  if (!Array.isArray(window.QURAN_PAGE_MAP) || !window.QURAN_PAGE_MAP.length) {
    return [];
  }

  const idx = getCurrentPageMapIndex();

  if (isPortraitMode()) {
    return [window.QURAN_PAGE_MAP[idx]].filter(Boolean);
  }

  return [
    window.QURAN_PAGE_MAP[idx] || null,
    window.QURAN_PAGE_MAP[idx + 1] || null,
  ].filter(Boolean);
}

function isLogicalPageVisible(pageNumber) {
  return getVisibleLogicalPages().includes(pageNumber);
}

function flipTowardLogicalPage(pageNumber) {
  if (!flipBook || !Array.isArray(window.QURAN_PAGE_MAP)) return false;

  const targetIdx = window.QURAN_PAGE_MAP.indexOf(pageNumber);
  if (targetIdx === -1) return false;

  if (isLogicalPageVisible(pageNumber)) {
    return true;
  }

  const visiblePages = getVisibleLogicalPages();
  if (!visiblePages.length) {
    try {
      flipBook.flip(targetIdx);
    } catch (err) {
      console.error("flipTowardLogicalPage direct flip error:", err);
    }
    return false;
  }

  const maxVisible = Math.max(...visiblePages);
  const minVisible = Math.min(...visiblePages);

  try {
    if (pageNumber > maxVisible) {
      flipBook.flipPrev();
      return false;
    }

    if (pageNumber < minVisible) {
      flipBook.flipNext();
      return false;
    }

    flipBook.flip(targetIdx);
  } catch (err) {
    console.error("flipTowardLogicalPage error:", err);
  }

  return false;
}

function goToLogicalPage(pageNumber) {
  return flipTowardLogicalPage(pageNumber);
}

function forceGoToLogicalPage(pageNumber) {
  if (!flipBook || !Array.isArray(window.QURAN_PAGE_MAP)) return false;

  const targetIdx = window.QURAN_PAGE_MAP.indexOf(pageNumber);
  if (targetIdx === -1) return false;

  if (isLogicalPageVisible(pageNumber)) {
    return true;
  }

  try {
    flipBook.flip(targetIdx);
  } catch (err) {
    console.error("forceGoToLogicalPage direct flip error:", err);
  }

  return false;
}

window.isLogicalPageVisible = isLogicalPageVisible;
window.goToLogicalPage = goToLogicalPage;
window.forceGoToLogicalPage = forceGoToLogicalPage;

function flipNext() {
  if (!flipBook) return;
  flipBook.flipNext();
}

function flipPrev() {
  if (!flipBook) return;
  flipBook.flipPrev();
}

window.initMushafFlipBook = initMushafFlipBook;
window.flipPrev = flipPrev;
window.flipNext = flipNext;
window.refreshVisibleAyahPositions = ensurePositionsAroundCurrentSpread;

function getAyahTarget(el) {
  if (!el) return null;
  return el.closest(".ayah-box") || el.closest(".ayah-polygon");
}

function getSavedAyah() {
  const saved = localStorage.getItem("quran_saved_ayah");
  if (!saved) return null;

  try {
    const data = JSON.parse(saved);
    if (!data || !data.surah || !data.ayah) return null;
    return data;
  } catch (error) {
    console.error("Invalid saved ayah data:", error);
    return null;
  }
}

function isCurrentAyahSaved() {
  const saved = getSavedAyah();
  if (!saved || !CURRENT_AYAH_CONTEXT) return false;

  return (
    Number(saved.surah) === Number(CURRENT_AYAH_CONTEXT.surah) &&
    Number(saved.ayah) === Number(CURRENT_AYAH_CONTEXT.ayah)
  );
}

function updateAyahBookmarkIcon() {
  const icon = document.getElementById("ayahBookmarkIcon");
  const text = document.getElementById("ayahBookmarkText");

  if (!icon || !text) return;

  if (isCurrentAyahSaved()) {
    icon.classList.remove("bi-heart");
    icon.classList.add("bi-heart-fill");
    icon.style.color = "#dc2626";
    text.textContent = window.TRANSLATIONS?.cancelStop || "إزالة موضع القراءة";
  } else {
    icon.classList.remove("bi-heart-fill");
    icon.classList.add("bi-heart");
    icon.style.color = "#dc2626";
    text.textContent = window.TRANSLATIONS?.saveStop || "حفظ موضع القراءة";
  }
}

function updateToolbarBookmark() {
  const btn = document.getElementById("toolbarBookmarkBtn");
  if (!btn) return;

  const saved = getSavedAyah();

  if (saved) {
    btn.classList.remove("hidden");
    btn.classList.add("flex");
  } else {
    btn.classList.add("hidden");
    btn.classList.remove("flex");
  }
}

function showAyahMenu(event, target) {
  window.__LAST_AYAH_CLICK_EVENT__ = event;
  window.__LAST_AYAH_TARGET_RECT__ = target ? target.getBoundingClientRect() : null;

  const menu = document.getElementById("ayahMenu");
  if (!menu || !target) return;

  const surah = parseInt(target.dataset.surah || "0", 10);
  const ayah = target.dataset.ayah ? parseInt(target.dataset.ayah, 10) : null;
  const page = parseInt(target.dataset.page || "0", 10);
  const audio = target.dataset.audio || "";
  const polyId = target.dataset.polyId || "";

  CURRENT_AYAH_CONTEXT = { surah, ayah, page, audio, polyId };
  updateAyahBookmarkIcon();

  const isSmallScreen = window.matchMedia("(max-width: 640px)").matches;
  let clickX = event.clientX;
  let clickY = event.clientY;

  if (isSmallScreen) {
    const ayahRect = target.getBoundingClientRect();
    clickX = ayahRect.left + ayahRect.width / 2;
    clickY = ayahRect.top + ayahRect.height / 2;
  }

  menu.style.left = clickX + "px";
  menu.style.top = clickY + "px";
  menu.classList.remove("hidden");
}

function hideAyahMenu() {
  const menu = document.getElementById("ayahMenu");
  if (!menu) return;
  menu.classList.add("hidden");
}

function initAyahContextMenu() {
  const container = document.getElementById("mushafFlipBook");
  if (!container) return;

  container.addEventListener("click", function (e) {
    const target = getAyahTarget(e.target);
    if (!target) {
      return;
    }

    e.stopPropagation();
    e.preventDefault();
    showAyahMenu(e, target);
  });

  document.addEventListener("click", function (e) {
    const menu = document.getElementById("ayahMenu");
    if (!menu) return;

    const insideMenu = e.target.closest("#ayahMenu");
    const insideAyah = getAyahTarget(e.target);

    if (!insideMenu && !insideAyah) {
      hideAyahMenu();
    }
  });

  window.addEventListener("scroll", function () {
    hideAyahMenu();
  });
}

function ayahMenuPlay() {
  if (!CURRENT_AYAH_CONTEXT) return;

  if (typeof window.playAyahByKey === "function") {
    window.playAyahByKey(
      CURRENT_AYAH_CONTEXT.surah,
      CURRENT_AYAH_CONTEXT.ayah
    );
  }

  hideAyahMenu();
}

function ayahMenuWords() {
  if (!CURRENT_AYAH_CONTEXT) return;

  const arabicWordMeaningsOn =
    window.QURAN_ARABIC_FEATURES_ENABLED === true ||
    window.HIFZ_ARABIC_FEATURES_ENABLED === true;
  if (!arabicWordMeaningsOn) return;

  if (typeof window.openWordMeaningsPopover === "function") {
    window.openWordMeaningsPopover(
      CURRENT_AYAH_CONTEXT.surah,
      CURRENT_AYAH_CONTEXT.ayah
    );
  }

  hideAyahMenu();
}

function ayahMenuTafsir() {
  if (!CURRENT_AYAH_CONTEXT) return;

  if (typeof window.openShortTafsirPopover === "function") {
    window.openShortTafsirPopover(
      CURRENT_AYAH_CONTEXT.surah,
      CURRENT_AYAH_CONTEXT.ayah
    );
  }

  hideAyahMenu();
}

function clearSavedAyahHighlight() {
  document.querySelectorAll(".ayah-saved").forEach(function (el) {
    el.classList.remove("ayah-saved");
  });
}

function applySavedAyahHighlight() {
  const data = getSavedAyah();
  if (!data) return;

  clearSavedAyahHighlight();

  const activeRects = document.querySelectorAll(
    `.ayah-polygon[data-surah="${data.surah}"][data-ayah="${data.ayah}"]`
  );

  activeRects.forEach(function (el) {
    el.classList.add("ayah-saved");
  });
}

function ayahMenuBookmark() {
  if (!CURRENT_AYAH_CONTEXT) return;

  const isSaved = isCurrentAyahSaved();

  if (isSaved) {
    localStorage.removeItem("quran_saved_ayah");
    clearSavedAyahHighlight();
  } else {
    const data = {
      surah: CURRENT_AYAH_CONTEXT.surah,
      ayah: CURRENT_AYAH_CONTEXT.ayah,
      page: CURRENT_AYAH_CONTEXT.page || null
    };

    localStorage.setItem("quran_saved_ayah", JSON.stringify(data));
    applySavedAyahHighlight();
  }

  updateAyahBookmarkIcon();
  updateToolbarBookmark();
  hideAyahMenu();
}

function goToSavedAyah() {
  const saved = getSavedAyah();
  if (!saved) return;

  const focusSavedAyah = () => {
    const el = document.querySelector(
      `.ayah-polygon[data-surah="${saved.surah}"][data-ayah="${saved.ayah}"]`
    );

    if (!el) return false;

    applySavedAyahHighlight();
    hideAyahMenu();

    return true;
  };

  if (saved.page && typeof window.forceGoToLogicalPage === "function") {
    const alreadyVisible = window.forceGoToLogicalPage(saved.page);

    if (alreadyVisible) {
      setTimeout(focusSavedAyah, 80);
      return;
    }

    let tries = 0;
    const maxTries = 20;

    const timer = setInterval(() => {
      tries += 1;

      if (window.isLogicalPageVisible && window.isLogicalPageVisible(saved.page)) {
        clearInterval(timer);
        setTimeout(focusSavedAyah, 120);
        return;
      }

      if (tries >= maxTries) {
        clearInterval(timer);
      }
    }, 120);

    return;
  }

  setTimeout(focusSavedAyah, 120);
}
window.ayahMenuPlay = ayahMenuPlay;
window.ayahMenuWords = ayahMenuWords;
window.ayahMenuTafsir = ayahMenuTafsir;
window.ayahMenuBookmark = ayahMenuBookmark;
window.goToSavedAyah = goToSavedAyah;

document.addEventListener("DOMContentLoaded", function () {
  initAyahContextMenu();
  applySavedAyahHighlight();
  updateToolbarBookmark();
});

function getResumeTargetFromUrl() {
  const params = new URLSearchParams(window.location.search);

  const surah = params.get("surah");
  const ayah = params.get("ayah");

  if (!surah || !ayah) {
    return null;
  }

  return {
    surah: String(surah),
    ayah: String(ayah),
  };
}

function findAyahElement(target) {
  if (!target) return null;

  const selectors = [
    `[data-surah="${target.surah}"][data-ayah="${target.ayah}"]`,
    `[data-surah-number="${target.surah}"][data-ayah-number="${target.ayah}"]`,
    `[data-sura="${target.surah}"][data-aya="${target.ayah}"]`,
    `#ayah-${target.surah}-${target.ayah}`,
  ];

  for (const selector of selectors) {
    const element = document.querySelector(selector);
    if (element) {
      return element;
    }
  }

  return null;
}

function scrollToAyahElement(element) {
  if (!element) return;

  element.scrollIntoView({
    behavior: "smooth",
    block: "center",
    inline: "center",
  });

  element.classList.add("resume-ayah-target");

  setTimeout(() => {
    element.classList.remove("resume-ayah-target");
  }, 2500);
}

function tryResumeToAyahFromUrl() {
  const target = getResumeTargetFromUrl();
  if (!target) return;

  let attempts = 0;
  const maxAttempts = 30;

  const timer = setInterval(() => {
    attempts += 1;

    const ayahElement = findAyahElement(target);

    if (ayahElement) {
      clearInterval(timer);
      scrollToAyahElement(ayahElement);
      return;
    }

    if (attempts >= maxAttempts) {
      clearInterval(timer);
    }
  }, 300);
}

document.addEventListener("DOMContentLoaded", function () {
  tryResumeToAyahFromUrl();
});

document.addEventListener("quran-page-flipped", function () {
  tryResumeToAyahFromUrl();
});

function applyFullscreenMushafSize() {
  const mushafArea = document.getElementById("mushafArea");
  const zoomWrapper = document.getElementById("mushafZoomWrapper");
  const flipContainer = document.getElementById("mushafFlipContainer");
  const flipBookEl = document.getElementById("mushafFlipBook");

  if (!mushafArea || !zoomWrapper || !flipContainer || !flipBookEl) return;

  const isFullscreen = mushafArea.classList.contains("mushaf-fullscreen");

  const targets = [zoomWrapper, flipContainer];

  if (!isFullscreen) {
    targets.forEach((el) => {
      el.style.width = "";
      el.style.height = "";
      el.style.maxWidth = "";
      el.style.maxHeight = "";
      el.style.margin = "";
    });

    flipBookEl.style.width = "";
    flipBookEl.style.maxWidth = "";
    flipBookEl.style.maxHeight = "";
    flipBookEl.style.height = "";
    flipBookEl.style.margin = "";

    return;
  }

  const fullscreenCfg = getFullscreenMushafConfig();

  /**
   * التكبير: تصغير منطقة عرض المصحف نسبة للشاشة (بدون تشويه الصورة — نفس المنطق لقرآن/حفظ).
   * قيمة أصغر ⇒ مصحف أصغر داخل الشاشة ⇒ تظهر صفحة المصحف في الصورة كاملة أكثر (هوامش، زخرفة، رقم).
   */
  const FULLSCREEN_MUSHAF_FIT_FACTOR = 0.86;
  const vhAvail = 100 * FULLSCREEN_MUSHAF_FIT_FACTOR;

  const hifzDoubleSpread =
  window.HIFZ_MODE && window.HIFZ_MUSHAF_SPREAD === "double";

  const spreadRatio = hifzDoubleSpread
    ? fullscreenCfg.heightRatio * 2
    : fullscreenCfg.heightRatio;

  const targetWidth = `min(${fullscreenCfg.widthVW}vw, calc(${vhAvail}vh * ${spreadRatio}))`;
  const targetMaxWidth = `${fullscreenCfg.maxWidthVW}vw`;
  const targetMaxHeight = `${fullscreenCfg.maxHeightVH * FULLSCREEN_MUSHAF_FIT_FACTOR}vh`;

  targets.forEach((el) => {
    el.style.width = targetWidth;
    el.style.maxWidth = targetMaxWidth;
    el.style.maxHeight = targetMaxHeight;
    el.style.height = "auto";
    el.style.margin = "0 auto";
  });

  flipBookEl.style.width = "100%";
  flipBookEl.style.maxWidth = "100%";
  flipBookEl.style.maxHeight = "100%";
  flipBookEl.style.height = "auto";
  flipBookEl.style.margin = "0 auto";
}
// ===== VOLUME SLIDER FILL =====
(function () {
  function updateVolumeFill(el) {
    var min = parseFloat(el.min) || 0;
    var max = parseFloat(el.max) || 1;
    var val = parseFloat(el.value) || 0;
    var pct = ((val - min) / (max - min)) * 100;
    el.style.setProperty("--fill", pct + "%");
  }

  function initVolumeSliders() {
    document.querySelectorAll(".mushaf-volume-range").forEach(function (el) {
      updateVolumeFill(el);
    });
  }

  document.addEventListener("input", function (e) {
    if (e.target && e.target.classList.contains("mushaf-volume-range")) {
      updateVolumeFill(e.target);
    }
  });

  document.addEventListener("DOMContentLoaded", initVolumeSliders);
  // Also run after htmx swaps in case panels are loaded dynamically
  document.addEventListener("htmx:afterSwap", initVolumeSliders);
})();
