// static/quran/js/progress-tracker.js

(function () {
  if (window.__quranProgressTrackerInitialized) return;
  window.__quranProgressTrackerInitialized = true;

  const TOTAL_PAGES_FALLBACK = 604;
  const MIN_READING_SECONDS = 120; // الحد الأدنى لاعتبار الصفحة مقروءة

  // DOM references
  let cardEl = null;
  let overallValueEl = null;
  let overallBarEl = null;
  let readingTextEl = null;
  let audioTextEl = null;
  let lastPageTextEl = null;
  let totalListenHoursTextEl = null;
  let khatmaCountTextEl = null;

  // Sync
  let progressUpdateUrl = null;
  let syncTimer = null;
  let isSyncing = false;

  // State
  let totalPages = TOTAL_PAGES_FALLBACK;
  let maxReadPage = 1;
  let maxAudioPage = 1;

  let totalReadAyah = 0;
  let totalListenSeconds = 0;

  let khatmaReadCount = 0;
  let khatmaAudioCount = 0;

  const readPages = new Set();
  const audioPages = new Set();

  let currentPage = null;
  let pageStartTime = null;

  function initFromDOM() {
    cardEl = document.getElementById("quranProgressCard");
    if (!cardEl) return false;

    overallValueEl = document.getElementById("overallProgressValue");
    overallBarEl = document.getElementById("overallProgressBar");
    readingTextEl = document.getElementById("readingProgressText");
    audioTextEl = document.getElementById("audioProgressText");
    lastPageTextEl = document.getElementById("lastPageText");
    totalListenHoursTextEl = document.getElementById("totalListenHoursText");
    khatmaCountTextEl = document.getElementById("khatmaCountText");

    const totalPagesAttr = cardEl.getAttribute("data-total-pages");
    const initialReadPageAttr = cardEl.getAttribute("data-initial-read-page");
    const initialAudioPageAttr = cardEl.getAttribute("data-initial-audio-page");
    const initialReadAyahAttr = cardEl.getAttribute("data-initial-read-ayah");
    const initialListenSecondsAttr = cardEl.getAttribute("data-initial-listen-seconds");
    const initialKhatmaCountAttr = cardEl.getAttribute("data-initial-khatma-count");
    progressUpdateUrl = cardEl.getAttribute("data-update-url") || null;

    totalPages = parseInt(totalPagesAttr || TOTAL_PAGES_FALLBACK, 10) || TOTAL_PAGES_FALLBACK;

    maxReadPage = parseInt(initialReadPageAttr || "1", 10) || 1;
    maxAudioPage = parseInt(initialAudioPageAttr || "1", 10) || 1;

    totalReadAyah = parseInt(initialReadAyahAttr || "0", 10) || 0;
    totalListenSeconds = parseInt(initialListenSecondsAttr || "0", 10) || 0;

    const initialKhatma = parseInt(initialKhatmaCountAttr || "0", 10) || 0;
    khatmaReadCount = initialKhatma;
    khatmaAudioCount = initialKhatma;

    if (maxReadPage > 0) {
      readPages.add(maxReadPage);
    }
    if (maxAudioPage > 0) {
      audioPages.add(maxAudioPage);
    }

    updateProgressCard();
    return true;
  }

  function getOverallPercent() {
    const maxPage = Math.max(maxReadPage, maxAudioPage);
    return Math.round((maxPage / totalPages) * 100);
  }

  function formatListenTime(totalSec) {
    totalSec = parseInt(totalSec || 0, 10);
    if (totalSec < 0) totalSec = 0;

    const hours = Math.floor(totalSec / 3600);
    const rem = totalSec % 3600;
    const minutes = Math.floor(rem / 60);
    const seconds = rem % 60;

    const hh = String(hours).padStart(2, "0");
    const mm = String(minutes).padStart(2, "0");
    const ss = String(seconds).padStart(2, "0");

    return `${hh}:${mm}:${ss}`;
  }

  function getTotalKhatmaCount() {
    return Math.max(khatmaReadCount, khatmaAudioCount);
  }

  function updateProgressCard() {
    const overallPercent = getOverallPercent();

    if (overallValueEl) {
      overallValueEl.textContent = overallPercent + "٪";
    }

    if (overallBarEl) {
      overallBarEl.style.width = overallPercent + "%";
    }

    if (readingTextEl) {
      readingTextEl.textContent = "صفحة " + maxReadPage;
    }

    if (audioTextEl) {
      audioTextEl.textContent = totalReadAyah + " آية";
    }

    if (lastPageTextEl) {
      lastPageTextEl.textContent = "صفحة " + maxReadPage;
    }

    if (totalListenHoursTextEl) {
      totalListenHoursTextEl.textContent = formatListenTime(totalListenSeconds);
    }

    if (khatmaCountTextEl) {
      khatmaCountTextEl.textContent = getTotalKhatmaCount().toString();
    }

    scheduleSync();
  }

  // === Sync with backend ===

  function getCsrfToken() {
    const name = "csrftoken";
    const cookies = document.cookie ? document.cookie.split(";") : [];
    for (let c of cookies) {
      c = c.trim();
      if (c.startsWith(name + "=")) {
        return decodeURIComponent(c.substring(name.length + 1));
      }
    }
    return "";
  }

  function scheduleSync() {
    if (!progressUpdateUrl) return;
    if (syncTimer) return;
    syncTimer = setTimeout(doSync, 5000); // مزامنة بعد 5 ثواني من آخر تحديث
  }

  function doSync() {
    syncTimer = null;
    if (isSyncing) return;
    if (!progressUpdateUrl) return;

    const payload = {
      last_page: maxReadPage,
      read_pages_count: readPages.size,
      max_audio_page: maxAudioPage,
      total_read_ayah: totalReadAyah,
      total_listen_seconds: totalListenSeconds,
      khatma_count: getTotalKhatmaCount(),
      khatma_percent: getOverallPercent(),
    };

    isSyncing = true;

    fetch(progressUpdateUrl, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCsrfToken(),
      },
      body: JSON.stringify(payload),
      credentials: "same-origin",
    })
      .then(() => {
        isSyncing = false;
      })
      .catch(() => {
        isSyncing = false;
      });
  }

  // === Reading behavior tracking ===

  function onLogicalPageChanged(newPage) {
    const now = Date.now();

    if (currentPage != null && pageStartTime != null) {
      const deltaSec = (now - pageStartTime) / 1000;

      if (deltaSec >= MIN_READING_SECONDS) {
        readPages.add(currentPage);

        if (currentPage > maxReadPage) {
          maxReadPage = currentPage;
        }

        if (readPages.size >= totalPages && khatmaReadCount === 0) {
          khatmaReadCount = 1;
        }

        updateProgressCard();
      }
    }

    currentPage = newPage;
    pageStartTime = now;
  }

  function setupPageFlipListener() {
    if (typeof flipBook === "undefined" || !flipBook) return;

    if (typeof getRightLeftLogicalPages === "function") {
      const pages = getRightLeftLogicalPages();
      const logical = pages.left || pages.right;
      if (logical) {
        onLogicalPageChanged(logical);
      }
    }

    flipBook.on("flip", function () {
      if (typeof getRightLeftLogicalPages !== "function") return;
      const pages = getRightLeftLogicalPages();
      const logical = pages.left || pages.right;
      if (logical) {
        onLogicalPageChanged(logical);
      }
    });
  }

  // === Audio tracking (per ayah ended) ===

  function onAyahEnded(page, durationSeconds) {
    if (!page || page < 1) return;

    totalReadAyah += 1;

    if (durationSeconds && durationSeconds > 0) {
      totalListenSeconds += durationSeconds;
    }

    audioPages.add(page);

    if (page > maxAudioPage) {
      maxAudioPage = page;
    }

    if (audioPages.size >= totalPages && khatmaAudioCount === 0) {
      khatmaAudioCount = 1;
    }

    updateProgressCard();
  }

  function setupAudioListener() {
    document.addEventListener("ayah-ended", function (e) {
      const detail = e.detail || {};
      const page = parseInt(detail.page || "0", 10);
      const duration = parseInt(detail.duration || "0", 10);
      onAyahEnded(page, duration);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    if (!initFromDOM()) return;
    setupPageFlipListener();
    setupAudioListener();
  });
})();