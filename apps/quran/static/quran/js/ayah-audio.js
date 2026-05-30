(function () {
  if (window.__ayahAudioMiniPlayerInitialized) return;
  window.__ayahAudioMiniPlayerInitialized = true;

  document.addEventListener("DOMContentLoaded", () => {
    const $ = (id) => document.getElementById(id);

    const audioEl = $("ayahAudio");
    const playBtn = $("miniPlayBtn");
    const stopBtn = $("miniStopBtn");
    const progressFill = $("miniProgressFill");
    const progressBar = $("miniProgressBar");
    const volumeSlider = $("miniVolume");
    const wordContent = $("wordContent");

    if (!audioEl || !playBtn || !stopBtn) return;

    const items = (window.QURAN_AUDIO_ITEMS || [])
      .map((o) => ({
        surah: Number(o.surah),
        ayah: o.ayah === null || typeof o.ayah === "undefined" ? null : Number(o.ayah),
        page: Number(o.page),
        audio: o.audio,
      }))
      .filter(
        (i) =>
          i.surah > 0 &&
          i.page > 0 &&
          i.ayah !== null &&
          i.ayah >= 1 &&
          !!i.audio
      )
      .sort(
        (a, b) =>
          a.page - b.page ||
          a.surah - b.surah ||
          (a.ayah - b.ayah)
      );

    if (!items.length) return;

    // Expose live reference so changeQariFolder can update audio URLs without a page reload
    window.__quranAudioItemsRef = items;

    const map = new Map();
    items.forEach((it, i) => {
      const key = `${it.surah}:${it.ayah}`;
      map.set(key, i);
    });

    const wordMeaningsCache = new Map();

    let current = -1;
    let pendingAyahAfterFlip = null;
    let pendingFlipCheckTimer = null;
    let pendingFlipForceTimer = null;
    let pendingFlipResumeTimer = null;
    let wordMeaningsRequestToken = 0;
    let progress50SentForKey = null;
    let hoveredWordMeaningsKey = "";

    function getAyahHoverTarget(element) {
      if (!element || typeof element.closest !== "function") return null;
      return element.closest(".ayah-box");
    }

    function isSameAyahHoverGroup(target, relatedTarget) {
      const relatedAyah = getAyahHoverTarget(relatedTarget);
      if (!target || !relatedAyah) return false;
      return (
        String(target.dataset.surah || "") === String(relatedAyah.dataset.surah || "") &&
        String(target.dataset.ayah || "") === String(relatedAyah.dataset.ayah || "")
      );
    }

    function isArabicWordMeaningsAllowed() {
      return (
        window.QURAN_ARABIC_FEATURES_ENABLED === true ||
        window.HIFZ_ARABIC_FEATURES_ENABLED === true
      );
    }

    function isWordMeaningsPanelEnabled() {
      if (!isArabicWordMeaningsAllowed()) return false;

      const toggle = $("toggleWordPanel");
      const panel = $("wordPanel");
      return !!(
        wordContent &&
        (!toggle || toggle.checked) &&
        (!panel || !panel.classList.contains("hidden"))
      );
    }

    function getCurrentAudioItem() {
      if (current === -1) return null;
      return items[current] || null;
    }

    function getCurrentAudioKey(it) {
      if (!it) return "";
      return `${it.surah}:${it.ayah}:${it.audio || ""}`;
    }

    function normalizeAudioUrl(url) {
  let value = String(url || "").trim();

  if (!value) {
    return value;
  }

  value = value.replace("https://wird.mehttps://wird.me", "https://wird.me");
  value = value.replace("http://wird.mehttp://wird.me", "https://wird.me");
  value = value.replace("http://wird.mehttps://wird.me", "https://wird.me");
  value = value.replace("https://wird.mehttp://wird.me", "https://wird.me");

  if (value.startsWith("/media/audio/")) {
    return "https://wird.me" + value;
  }

  return value;
}

function replaceQariInAudioUrl(url, newQari) {
  const cleanQari = String(newQari || "").trim();
  let value = normalizeAudioUrl(url);

  if (!value || !cleanQari) {
    return value;
  }

  value = value.replace(
    /(\/media\/audio\/[^/]+\/)([^/]+)(\/)/,
    "$1" + cleanQari + "$3"
  );

  return normalizeAudioUrl(value);
}

    function applyQariToAudioItems(newQari) {
      const cleanQari = String(newQari || "").trim();

      if (!cleanQari) {
        return;
      }

      items.forEach((item) => {
        if (!item || !item.audio) return;
        item.audio = replaceQariInAudioUrl(item.audio, cleanQari);
      });

      if (Array.isArray(window.QURAN_AUDIO_ITEMS)) {
        window.QURAN_AUDIO_ITEMS.forEach((item) => {
          if (!item || !item.audio) return;
          item.audio = replaceQariInAudioUrl(item.audio, cleanQari);
        });
      }

      if (window.currentAyahItem && window.currentAyahItem.audio) {
        window.currentAyahItem.audio = replaceQariInAudioUrl(
          window.currentAyahItem.audio,
          cleanQari
        );
      }
    }

    function reloadCurrentAudioForQari(newQari, options = {}) {
      const cleanQari = String(newQari || "").trim();

      if (!cleanQari) {
        return false;
      }

      applyQariToAudioItems(cleanQari);

      window.CURRENT_QARI_FOLDER = cleanQari;
      window.CURRENT_QARI_CODE = cleanQari;

      const it = getCurrentAudioItem();

      if (!it || !it.audio) {
        return false;
      }

      const wasPlaying = options.forcePlay === true || !audioEl.paused;
      const currentTime = Number.isFinite(audioEl.currentTime) ? audioEl.currentTime : 0;
      const nextSrc = replaceQariInAudioUrl(it.audio, cleanQari);

      it.audio = nextSrc;

      window.currentAyahItem = {
        surah: it.surah,
        ayah: it.ayah,
        page: it.page,
        audio: nextSrc,
      };

      progress50SentForKey = null;

      audioEl.pause();
      audioEl.removeAttribute("src");
      audioEl.load();
      audioEl.src = nextSrc;
      audioEl.load();

      const startPlayback = function () {
        try {
          if (currentTime > 0 && Number.isFinite(audioEl.duration) && currentTime < audioEl.duration) {
            audioEl.currentTime = currentTime;
          }
        } catch (err) {}

        if (wasPlaying) {
          audioEl.play().catch((err) => {
            console.error("Audio play failed after qari change:", nextSrc, err);
          });
        }
      };

      if (audioEl.readyState >= 1) {
        startPlayback();
      } else {
        audioEl.addEventListener("loadedmetadata", startPlayback, { once: true });
      }

      return true;
    }

    window.reloadCurrentAyahAudioForQari = reloadCurrentAudioForQari;

    function trackAudioEvent(type, extra = {}) {
      if (window.__WirdAudioGlobalTrackerActive) return;
      const it = getCurrentAudioItem();
      if (!it) return;
      if (!window.WirdAnalytics || typeof window.WirdAnalytics.track !== "function") return;

      window.WirdAnalytics.track(type, {
        source: window.location.pathname.indexOf("/hifz/") === 0 ? "hifz" : "quran",
        mushaf: window.CURRENT_MUSHAF_KEY || window.QURAN_MUSHAF_KEY || window.CURRENT_MUSHAF || "",
        qari: window.CURRENT_QARI_FOLDER || window.CURRENT_QARI_CODE || "",
        reader: window.CURRENT_QARI_FOLDER || window.CURRENT_QARI_CODE || "",
        surah: it.surah,
        ayah: it.ayah,
        page: it.page,
        audio: it.audio || "",
        current_time: Math.round(audioEl.currentTime || 0),
        duration: Math.round(audioEl.duration || 0),
        percent: audioEl.duration ? Math.round((audioEl.currentTime / audioEl.duration) * 100) : 0,
        ...extra,
      });
    }

    function clearPendingFlipTimers() {
      if (pendingFlipCheckTimer) {
        clearTimeout(pendingFlipCheckTimer);
        pendingFlipCheckTimer = null;
      }

      if (pendingFlipForceTimer) {
        clearTimeout(pendingFlipForceTimer);
        pendingFlipForceTimer = null;
      }

      if (pendingFlipResumeTimer) {
        clearTimeout(pendingFlipResumeTimer);
        pendingFlipResumeTimer = null;
      }
    }

    function setPendingAyahAfterFlip(item) {
      pendingAyahAfterFlip = item || null;
    }

    function resumePendingAyahAfterPageFlip() {
      if (!pendingAyahAfterFlip) return;

      const target = pendingAyahAfterFlip;
      const key = `${target.surah}:${target.ayah}`;

      if (!map.has(key)) {
        pendingAyahAfterFlip = null;
        return;
      }

      const idx = map.get(key);
      pendingAyahAfterFlip = null;
      clearPendingFlipTimers();
      play(idx);
    }

    window.resumePendingAyahAfterPageFlip = resumePendingAyahAfterPageFlip;

    function clearActiveHighlight() {
      document
        .querySelectorAll(".ayah-polygon")
        .forEach((r) => r.classList.remove("ayah-active"));
    }

    function setDefaultWordMeaningsState() {
      if (!wordContent) return;
      wordContent.innerHTML = `
        <div class="text-gray-400 text-center py-4">
          ${window.TRANSLATIONS.wordMeaningsHint}
        </div>
      `;
    }

    function setLoadingWordMeaningsState() {
      if (!wordContent) return;
      wordContent.innerHTML = `
        <div class="text-gray-400 text-center py-4">
          ${window.TRANSLATIONS.wordMeaningsHint}
        </div>
      `;
    }

    function setErrorWordMeaningsState() {
      if (!wordContent) return;
      wordContent.innerHTML = `
        <div class="text-red-500 text-center py-4">
          ${window.TRANSLATIONS.errorWordMeanings}
        </div>
      `;
    }

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function renderWordMeanings(data, surah, ayah) {
      if (!wordContent) return;

      const items = Array.isArray(data?.items) ? data.items : [];

      if (!items.length) {
        wordContent.innerHTML = `
          <div class="space-y-2">
            <div class="text-xs font-bold text-emerald-700">
              ${window.TRANSLATIONS.surah} ${surah} · ${window.TRANSLATIONS.ayah} ${ayah}
            </div>
            <div class="text-sm text-gray-500 text-center py-3">
              ${window.TRANSLATIONS.noWordMeanings}
            </div>
          </div>
        `;
        return;
      }

      const html = items
        .map((item) => {
          const word = escapeHtml(item.word || item.word_plain || "");
          const meaning = escapeHtml(item.meaning || "");
          return `
            <div class="rounded-lg bg-gray-50 px-3 py-2">
              <div class="text-sm leading-6">
                <span class="font-semibold text-emerald-600">${word}</span>
                <span class="text-gray-400 mx-1">:</span>
                <span class="text-gray-800">${meaning}</span>
              </div>
            </div>
          `;
        })
        .join("");

      wordContent.innerHTML = `
        <div class="space-y-2">
          <div class="text-xs font-bold text-emerald-700">
            ${window.TRANSLATIONS.surah} ${surah} · ${window.TRANSLATIONS.ayah} ${ayah}
          </div>
          <div class="space-y-2">
            ${html}
          </div>
        </div>
      `;
    }

    async function loadWordMeaningsForAyah(surah, ayah) {
      if (!isArabicWordMeaningsAllowed() || !wordContent || !surah || !ayah) return;

      const baseUrl = window.QURAN_WORD_MEANINGS_URL;

      if (!baseUrl) {
        setErrorWordMeaningsState();
        return;
      }

      const cacheKey = `${surah}:${ayah}`;
      const requestToken = ++wordMeaningsRequestToken;

      if (wordMeaningsCache.has(cacheKey)) {
        renderWordMeanings(wordMeaningsCache.get(cacheKey), surah, ayah);
        return;
      }

      setLoadingWordMeaningsState();

      try {
        const url = new URL(baseUrl, window.location.origin);
        url.searchParams.set("surah", surah);
        url.searchParams.set("ayah", ayah);

        const response = await fetch(url.toString(), {
          headers: {
            "X-Requested-With": "XMLHttpRequest",
          },
        });

        const data = await response.json();

        if (!response.ok || !data.success) {
          throw new Error(data?.error || `HTTP ${response.status}`);
        }

        wordMeaningsCache.set(cacheKey, data);

        if (requestToken !== wordMeaningsRequestToken) return;

        renderWordMeanings(data, surah, ayah);
      } catch (error) {
        if (requestToken !== wordMeaningsRequestToken) return;
        setErrorWordMeaningsState();
        console.error("Word meanings load failed:", { surah, ayah, error });
      }
    }

    function updateCurrentAyahWordMeanings(it) {
      if (!isArabicWordMeaningsAllowed()) return;

      if (!it) {
        setDefaultWordMeaningsState();
        return;
      }

      loadWordMeaningsForAyah(it.surah, it.ayah);
    }

    function initWordMeaningsHover() {
      document.addEventListener("mouseover", function (event) {
        if (!isWordMeaningsPanelEnabled()) return;

        const target = getAyahHoverTarget(event.target);
        if (!target || isSameAyahHoverGroup(target, event.relatedTarget)) return;

        const surah = target.dataset.surah;
        const ayah = target.dataset.ayah;
        const key = `${surah || ""}:${ayah || ""}`;
        if (!surah || !ayah || key === hoveredWordMeaningsKey) return;

        hoveredWordMeaningsKey = key;
        loadWordMeaningsForAyah(surah, ayah);
      }, true);
    }

    function stop() {
      clearPendingFlipTimers();
      audioEl.pause();
      audioEl.currentTime = 0;
      if (progressFill) progressFill.style.width = "0%";
      clearActiveHighlight();
      current = -1;
      pendingAyahAfterFlip = null;
      window.currentAyahItem = null;
      wordMeaningsRequestToken += 1;

      document.dispatchEvent(
        new CustomEvent("ayah-play", {
          detail: { surah: null, ayah: null },
        })
      );
    }

    function notifyAyahPlay(i) {
      const it = items[i];
      if (!it) return;

      document.dispatchEvent(
        new CustomEvent("ayah-play", {
          detail: {
            surah: it.surah,
            ayah: it.ayah,
          },
        })
      );
    }

    function play(i) {
      if (!items[i]) {
        stop();
        return;
      }

      current = i;
      const it = items[i];

      audioEl.src = it.audio;
      progress50SentForKey = null;

      window.currentAyahItem = {
        surah: it.surah,
        ayah: it.ayah,
        page: it.page,
        audio: it.audio,
      };

      notifyAyahPlay(i);
      updateCurrentAyahWordMeanings(it);

      audioEl.play().catch((err) => {
        console.error("Audio play failed:", it.audio, err);
      });
    }

    if (isArabicWordMeaningsAllowed()) {
      initWordMeaningsHover();
    }

    function playFromPage(page) {
      const i = items.findIndex((x) => x.page === page);
      if (i !== -1) play(i);
    }

    function getRightPage() {
      if (typeof window.getRightLeftLogicalPages !== "function") return null;
      const p = window.getRightLeftLogicalPages();
      if (!p) return null;
      return Math.min(p.right || 9999, p.left || 9999);
    }

    function isCurrentAyahVisible() {
      if (current === -1) return false;
      const page = items[current]?.page;
      if (!page) return false;
      return typeof window.isLogicalPageVisible === "function"
        ? window.isLogicalPageVisible(page)
        : false;
    }

    playBtn.addEventListener("click", () => {
      const page = getRightPage();

      if (current === -1 || !isCurrentAyahVisible()) {
        return page ? playFromPage(page) : play(0);
      }

      audioEl.paused ? audioEl.play() : audioEl.pause();
    });

    stopBtn.addEventListener("click", stop);

    audioEl.addEventListener("play", () => {
      trackAudioEvent("audio_play");
    });

    audioEl.addEventListener("pause", () => {
      if (audioEl.ended || current === -1 || !audioEl.currentTime) return;
      trackAudioEvent("audio_pause");
    });

    audioEl.addEventListener("ended", () => {
      trackAudioEvent("audio_complete", {
        current_time: Math.round(audioEl.duration || audioEl.currentTime || 0),
        percent: 100,
      });

      const next = current + 1;

      if (!items[next]) {
        stop();
        return;
      }

      const nextItem = items[next];
      const nextPage = nextItem.page;

      const isNextVisible =
        typeof window.isLogicalPageVisible === "function"
          ? window.isLogicalPageVisible(nextPage)
          : false;

      if (isNextVisible) {
        play(next);
        return;
      }

      setPendingAyahAfterFlip(nextItem);
      clearPendingFlipTimers();

      if (typeof window.goToLogicalPage === "function") {
        window.goToLogicalPage(nextPage);
      }

      pendingFlipCheckTimer = setTimeout(() => {
        if (!pendingAyahAfterFlip) return;

        const nowVisible =
          typeof window.isLogicalPageVisible === "function"
            ? window.isLogicalPageVisible(nextPage)
            : false;

        if (nowVisible) {
          resumePendingAyahAfterPageFlip();
        }
      }, 900);

      pendingFlipForceTimer = setTimeout(() => {
        if (!pendingAyahAfterFlip) return;

        const stillHidden =
          typeof window.isLogicalPageVisible === "function"
            ? !window.isLogicalPageVisible(nextPage)
            : true;

        if (stillHidden && typeof window.forceGoToLogicalPage === "function") {
          window.forceGoToLogicalPage(nextPage);
        }
      }, 1300);

      pendingFlipResumeTimer = setTimeout(() => {
        if (!pendingAyahAfterFlip) return;

        const nowVisible =
          typeof window.isLogicalPageVisible === "function"
            ? window.isLogicalPageVisible(nextPage)
            : false;

        if (nowVisible) {
          resumePendingAyahAfterPageFlip();
          return;
        }

        const key = `${nextItem.surah}:${nextItem.ayah}`;
        if (map.has(key)) {
          pendingAyahAfterFlip = null;
          clearPendingFlipTimers();
          play(map.get(key));
        }
      }, 2100);
    });

    audioEl.addEventListener("timeupdate", () => {
      if (!audioEl.duration) return;

      const percent = (audioEl.currentTime / audioEl.duration) * 100;

      if (progressFill) {
        progressFill.style.width = percent + "%";
      }

      const it = getCurrentAudioItem();
      const key = getCurrentAudioKey(it);
      if (key && percent >= 50 && progress50SentForKey !== key) {
        progress50SentForKey = key;
        trackAudioEvent("audio_progress_50", { percent: Math.round(percent) });
      }
    });

    progressBar?.addEventListener("click", (e) => {
      if (!audioEl.duration) return;
      const rect = progressBar.getBoundingClientRect();
      const percent = (e.clientX - rect.left) / rect.width;
      audioEl.currentTime = percent * audioEl.duration;
    });

    volumeSlider?.addEventListener("input", (e) => {
      audioEl.volume = +e.target.value;
    });

    audioEl.volume = +volumeSlider?.value || 1;

    document.addEventListener("click", function (event) {
      const qariButton = event.target.closest("[data-qari-code], [data-folder]");
      if (!qariButton) return;

      const newQari = qariButton.dataset.qariCode || qariButton.dataset.folder || "";
      if (!newQari) return;

      setTimeout(function () {
        reloadCurrentAudioForQari(newQari);
      }, 0);
    }, true);

    window.playAyahByKey = function (surah, ayah) {
      const key = `${+surah}:${+ayah}`;
      if (!map.has(key)) return;
      const idx = map.get(key);
      play(idx);
    };

    if (isArabicWordMeaningsAllowed()) {
      setDefaultWordMeaningsState();
    }
  });
})();