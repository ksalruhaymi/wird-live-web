(function () {
  if (window.__wirdAudioListenTrackerInitialized) return;
  window.__wirdAudioListenTrackerInitialized = true;
  window.__WirdAudioGlobalTrackerActive = true;

  function cleanPath(value) {
    if (!value) return "";
    try {
      return new URL(value, window.location.origin).pathname;
    } catch (e) {
      return String(value).split("?")[0];
    }
  }

  function sameAudio(a, b) {
    const pa = cleanPath(a);
    const pb = cleanPath(b);
    return !!pa && !!pb && pa === pb;
  }

  function getCurrentItem(audio) {
    const current = window.currentAyahItem || null;
    const src = audio.currentSrc || audio.src || "";

    if (current && (!current.audio || sameAudio(current.audio, src))) {
      return current;
    }

    const items = Array.isArray(window.QURAN_AUDIO_ITEMS) ? window.QURAN_AUDIO_ITEMS : [];
    const matched = items.find(function (item) {
      return item && item.audio && sameAudio(item.audio, src);
    });

    if (matched) return matched;

    const path = cleanPath(src);
    const match = path.match(/\/media\/audio\/([^/]+)\/([^/]+)\/(\d{3})\/(\d{3})(\d{3})\.mp3$/);
    if (!match) return null;

    return {
      mushaf: match[1] || "",
      qari: match[2] || "",
      reader: match[2] || "",
      surah: Number(match[3]),
      ayah: Number(match[5]),
      page: window.RIGHT_PAGE || window.LEFT_PAGE || window.QURAN_DEFAULT_PAGE || null,
      audio: path
    };
  }

  function getAudioKey(audio, item) {
    const src = cleanPath(audio.currentSrc || audio.src || "");
    if (!item) return src;
    return [item.surah || "", item.ayah || "", src].join(":");
  }

  function track(audio, type, extra) {
    if (!window.WirdAnalytics || typeof window.WirdAnalytics.track !== "function") return;

    const item = getCurrentItem(audio);
    const src = cleanPath(audio.currentSrc || audio.src || "");
    const duration = Math.round(audio.duration || 0);
    const currentTime = Math.round(audio.currentTime || 0);
    const percent = duration ? Math.round((audio.currentTime / audio.duration) * 100) : 0;

    window.WirdAnalytics.track(type, Object.assign({
      source: window.location.pathname.indexOf("/hifz/") === 0 ? "hifz" : "quran",
      mushaf: (item && item.mushaf) || window.CURRENT_MUSHAF_KEY || window.QURAN_MUSHAF_KEY || window.CURRENT_MUSHAF || "",
      qari: (item && (item.qari || item.reader)) || window.CURRENT_QARI_FOLDER || window.CURRENT_QARI_CODE || "",
      reader: (item && (item.reader || item.qari)) || window.CURRENT_QARI_FOLDER || window.CURRENT_QARI_CODE || "",
      surah: item && item.surah ? Number(item.surah) : null,
      ayah: item && item.ayah ? Number(item.ayah) : null,
      page: item && item.page ? Number(item.page) : (window.RIGHT_PAGE || window.LEFT_PAGE || window.QURAN_DEFAULT_PAGE || null),
      audio: src,
      current_time: currentTime,
      duration: duration,
      percent: percent
    }, extra || {}));
  }

  function init() {
    const audio = document.getElementById("ayahAudio");
    if (!audio || audio.dataset.wirdAudioListenTracker === "1") return;
    audio.dataset.wirdAudioListenTracker = "1";

    let progress50Key = "";
    let completeKey = "";

    audio.addEventListener("play", function () {
      const item = getCurrentItem(audio);
      const key = getAudioKey(audio, item);
      progress50Key = "";
      completeKey = "";
      track(audio, "audio_play", { audio_key: key });
    }, true);

    audio.addEventListener("pause", function () {
      if (audio.ended || !audio.currentTime) return;
      track(audio, "audio_pause");
    }, true);

    audio.addEventListener("timeupdate", function () {
      if (!audio.duration) return;
      const item = getCurrentItem(audio);
      const key = getAudioKey(audio, item);
      const percent = (audio.currentTime / audio.duration) * 100;
      if (key && percent >= 50 && progress50Key !== key) {
        progress50Key = key;
        track(audio, "audio_progress_50", { percent: Math.round(percent), audio_key: key });
      }
    }, true);

    audio.addEventListener("ended", function () {
      const item = getCurrentItem(audio);
      const key = getAudioKey(audio, item);
      if (key && completeKey === key) return;
      completeKey = key;
      track(audio, "audio_complete", {
        current_time: Math.round(audio.duration || audio.currentTime || 0),
        duration: Math.round(audio.duration || audio.currentTime || 0),
        percent: 100,
        audio_key: key
      });
    }, true);
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", init);
  } else {
    init();
  }
})();
