// ─── tafsir-page.js ───────────────────────────────────────────────────────────
// جميع المقاسات تأتي من window.MUSHAF_* المُحقن من الـ template عبر mushaf_config.py
// الأرقام الاحتياطية (|| رقم) هي نسخة طارئة فقط — لا تعدّلها هنا!
// إذا أردت تغيير المقاسات → عدّل mushaf_config.py فقط.
// ─────────────────────────────────────────────────────────────────────────────

let tafsirFlip = null;
let currentTafsirBookId = null;
let tafsirFontSize = 16;

// breakpoint موحّد: أقل من 900px → صفحة واحدة
const TAFSIR_SINGLE_PAGE_BP = 900;
const _tafsirIsMobile = window.innerWidth < TAFSIR_SINGLE_PAGE_BP;

let tafsirWidth  = window.MUSHAF_PAGE_WIDTH  || 430;
let tafsirHeight = window.MUSHAF_PAGE_HEIGHT || 660;

function isSinglePageMode() {
  return window.innerWidth < TAFSIR_SINGLE_PAGE_BP;
}

function getTafsirBookSize() {
  const baseW  = Number(window.MUSHAF_PAGE_WIDTH  || 430);
  const baseH  = Number(window.MUSHAF_PAGE_HEIGHT || 660);
  const maxW   = Number(window.MUSHAF_MAX_WIDTH   || 1000);
  const minW   = Number(window.MUSHAF_MIN_WIDTH   || 350);
  const ratio  = baseW / baseH;
  const single = isSinglePageMode();

  const zoom    = document.getElementById("tafsirZoomWrapper");
  const toolbar = document.querySelector("#tafsirZoomWrapper .flex.flex-nowrap");
  const zoomTop = zoom ? zoom.getBoundingClientRect().top : 128;
  const toolbarH = toolbar ? toolbar.getBoundingClientRect().height : 48;
  const estimatedPageTop = zoomTop + toolbarH;

  const isFullscreen = !!document.fullscreenElement;
  const sideAllowance = single ? 16 : (isFullscreen ? 0 : (window.innerWidth >= 1180 ? 560 : 32));
  const availableWidth  = Math.max(minW, window.innerWidth - sideAllowance);
  const availableHeight = Math.max(360, window.innerHeight - (isFullscreen ? 16 : estimatedPageTop + 18));
  const divisor = single ? 1 : 2;
  const pageWidthFromWidth  = Math.floor(Math.min(maxW / divisor, availableWidth / divisor));
  const pageWidthFromHeight = Math.floor(availableHeight * ratio);
  const widthCap = isFullscreen ? (maxW / divisor) : (baseW - 70);
  const pageWidth = Math.max(300, Math.min(pageWidthFromWidth, pageWidthFromHeight, widthCap));
  const pageHeight = Math.round(pageWidth / ratio);
  return { pageWidth, pageHeight };
}

function syncTafsirFrameHeight() {
  const frame   = document.querySelector("#tafsirZoomWrapper > div");
  const toolbar = document.querySelector("#tafsirZoomWrapper .flex.flex-nowrap");
  if (!frame) return;
  if (isSinglePageMode()) {
    frame.style.height = "auto";
    return;
  }
  const toolbarH = toolbar ? toolbar.getBoundingClientRect().height : 34;
  frame.style.height = Math.ceil(toolbarH + tafsirHeight + 2) + "px";
}

function resizeTafsirBookToViewport() {
  if (!tafsirFlip) return;
  const size = getTafsirBookSize();
  tafsirWidth  = size.pageWidth;
  tafsirHeight = size.pageHeight;
  tafsirFlip.update({ width: tafsirWidth, height: tafsirHeight });
  syncTafsirFrameHeight();
}

const ZOOM_STEP = 50;
const MAX_WIDTH = window.MUSHAF_MAX_WIDTH || 1000;
const MIN_WIDTH = window.MUSHAF_MIN_WIDTH || 350;

document.addEventListener("DOMContentLoaded", () => {
  const flipContainer = document.getElementById("tafsirFlipBook");
  if (!flipContainer || !window.St?.PageFlip) return;

  const single = isSinglePageMode();

  const pages      = flipContainer.querySelectorAll(".page");
  const startPage  = parseInt(window.TAFSIR_DEFAULT_PAGE || "1", 10) || 1;
  const startIndex = window.TAFSIR_PAGE_MAP?.indexOf(startPage) ?? 0;

  const size = getTafsirBookSize();
  tafsirWidth  = size.pageWidth;
  tafsirHeight = size.pageHeight;

  tafsirFlip = new St.PageFlip(flipContainer, {
    width:     tafsirWidth,
    height:    tafsirHeight,
    size:      "fixed",
    minWidth:  window.MUSHAF_MIN_WIDTH  || 350,
    maxWidth:  window.MUSHAF_MAX_WIDTH  || 1000,
    minHeight: window.MUSHAF_MIN_HEIGHT || 400,
    maxHeight: window.MUSHAF_MAX_HEIGHT || 1200,
    maxShadowOpacity: 0.5,
    showCover:            false,
    mobileScrollSupport:  false,
    useMouseEvents:       false,
    flippingTime:         800,
    startPage:            startIndex >= 0 ? startIndex : 0,
    direction:            "rtl",
    usePortrait:          true   // مفعّل دائماً — StPageFlip يقرر بناءً على العرض
  });

  tafsirFlip.loadFromHTML(pages);
  syncTafsirFrameHeight();

  // ─── إزالة الفراغ العلوي على الجوال ─────────────────────────────────────
  // StPageFlip (autoSize=true) يحسب top = blockHeight/2 - pageHeight/2.
  // blockHeight يأتي من .sft__wrapper paddingBottom % × actualWidth.
  // إذا كان actualWidth أكبر من settings.width، ينتج gap.
  // الحل: نصحّح paddingBottom في الـ wrapper ليكون بالنسبة للعرض الفعلي.
  if (single) {
    // StPageFlip يمركز الصفحة عمودياً: top = blockHeight/2 - pageHeight/2
    // نجبر height = tafsirHeight بالضبط → top = 0 → لا فراغ
    flipContainer.style.height = tafsirHeight + "px";
  }

  // ─── منطقتا حافة الكتاب (شاشات كبيرة فقط) ───────────────────────────────
  // تُضاف مباشرةً داخل stf__parent بعد التهيئة مع z-index عالٍ
  if (!single) {
    _addEdgeZones(flipContainer);
  }

  tafsirFlip.on("flip", () => {
    const { right, left } = getPages();
    updateUrl(left || right || 1);
    if (currentTafsirBookId) loadSpread(currentTafsirBookId, right, left);
  });

  // ─── سحب بالإصبع ─────────────────────────────────────────────────────────
  let _tx = 0;
  flipContainer.addEventListener("touchstart", e => { _tx = e.touches[0].clientX; }, { passive: true });
  flipContainer.addEventListener("touchend", e => {
    const dx = e.changedTouches[0].clientX - _tx;
    if (Math.abs(dx) > 40) dx > 0 ? tafsirFlipPrev() : tafsirFlipNext();
  });

  document.querySelectorAll(".tafsir-book-btn").forEach(btn => {
    btn.addEventListener("click", () => {
      currentTafsirBookId = +btn.dataset.bookId || null;
      if (!currentTafsirBookId) return;
      setActive(btn);
      const { right, left } = getPages();
      loadSpread(currentTafsirBookId, right, left);
    });
  });

  window.addEventListener("resize", () => {
    window.requestAnimationFrame(resizeTafsirBookToViewport);
  });

  document.querySelector(".tafsir-book-btn")?.click();
});

// ─── إضافة مناطق نقر الحواف ───────────────────────────────────────────────
function _addEdgeZones(container) {
  [
    { side: "right", action: tafsirFlipNext },
    { side: "left",  action: tafsirFlipPrev }
  ].forEach(({ side, action }) => {
    const zone = document.createElement("div");
    zone.className      = `tafsir-edge-zone tafsir-edge-${side}`;
    zone.setAttribute("aria-hidden", "true");
    zone.addEventListener("click", e => {
      e.stopPropagation();
      action();
    });
    container.appendChild(zone);
  });
}

function getPages() {
  if (!tafsirFlip || !window.TAFSIR_PAGE_MAP) return {};
  const i = tafsirFlip.getCurrentPageIndex();
  return {
    right: window.TAFSIR_PAGE_MAP[i]     || null,
    left:  window.TAFSIR_PAGE_MAP[i + 1] || null
  };
}

function updateUrl(page) {
  try {
    const url = new URL(location.href);
    url.searchParams.set("page", page);
    url.searchParams.set("mode", "tafsir");
    history.replaceState({}, "", url);
  } catch {}
}

function setActive(btn) {
  document.querySelectorAll(".tafsir-book-btn").forEach(b =>
    b.className = btn.className.replace(
      "bg-emerald-600 text-white border-emerald-600",
      "bg-white text-gray-700 border-gray-300"
    )
  );
  btn.classList.remove("bg-white", "text-gray-700", "border-gray-300");
  btn.classList.add("bg-emerald-600", "text-white", "border-emerald-600");
}

function loadSpread(bookId, right, left) {
  if (!window.TAFSIR_API_URL) return;
  const params = new URLSearchParams({ book_id: bookId });
  if (right) params.append("right_page", right);
  if (left)  params.append("left_page",  left);
  fetch(`${window.TAFSIR_API_URL}?${params}`)
    .then(r => r.json())
    .then(data => {
      ["right", "left"].forEach(side => {
        const p = data?.[side]?.page;
        if (!p) return;
        renderSide(data[side], document.getElementById(`tafsirPageContent-${p}`));
      });
    });
}

function renderSide(data, box) {
  if (!box) return;
  box.innerHTML = "";
  if (!data?.items?.length) {
    box.innerHTML = '<p class="text-xs text-gray-400 text-center py-4">لا يوجد تفسير.</p>';
    return;
  }
  data.items.forEach((item, i) => {
    const ayah = document.createElement("p");
    ayah.className  = "text-center text-[14px] md:text-[15px] font-semibold text-emerald-800 mt-2 mb-1";
    ayah.textContent = `﴿ ${item.ayah_text || ""} ﴾`;

    const tafsir = document.createElement("p");
    tafsir.className  = "text-[12px] md:text-[13px] text-gray-800 leading-relaxed text-justify mb-2";
    tafsir.textContent = item.tafsir_text || "";

    box.appendChild(ayah);
    box.appendChild(tafsir);

    if (i < data.items.length - 1) {
      const sep = document.createElement("div");
      sep.className = "flex justify-center my-2";
      sep.innerHTML = '<div class="h-px w-12 bg-gray-200"></div>';
      box.appendChild(sep);
    }
  });
}

function tafsirFlipNext() { tafsirFlip?.flipNext(); }
function tafsirFlipPrev() { tafsirFlip?.flipPrev(); }

function increaseTafsirFont() {
  if (!tafsirFlip) return;
  const baseW = window.MUSHAF_PAGE_WIDTH  || 430;
  const baseH = window.MUSHAF_PAGE_HEIGHT || 660;
  if (tafsirWidth < MAX_WIDTH) {
    tafsirWidth  += ZOOM_STEP;
    tafsirHeight += Math.round(ZOOM_STEP * (baseH / baseW));
  } else {
    tafsirWidth  = baseW;
    tafsirHeight = baseH;
  }
  tafsirFlip.update({ width: tafsirWidth, height: tafsirHeight });
}

window.tafsirFlipNext   = tafsirFlipNext;
window.tafsirFlipPrev   = tafsirFlipPrev;
window.increaseTafsirFont = increaseTafsirFont;
