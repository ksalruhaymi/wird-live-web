(function () {
  const controls = document.getElementById("hifzFloatingControls");
  const playPauseBtn = document.getElementById("hifzFloatPlayPauseBtn");
  const playPauseIcon = document.getElementById("hifzFloatPlayPauseIcon");
  const stopBtn = document.getElementById("hifzFloatStopBtn");
  const volumeRange = document.getElementById("hifzFloatVolumeRange");

  const toolbarRepeatBtn = document.getElementById("hifzToolbarRepeatCountBtn");
  const toolbarRepeatText = document.getElementById("hifzToolbarRepeatCountText");

  const repeatCountBtn = document.getElementById("hifzZoomRepeatCountBtn");
  const repeatCountText = document.getElementById("hifzZoomRepeatCountText");

  const mushafArea = document.getElementById("mushafArea");

  const miniPlayBtn = document.getElementById("miniPlayBtn");
  const miniStopBtn = document.getElementById("miniStopBtn");
  const miniVolume = document.getElementById("miniVolume");
  const audio = document.getElementById("ayahAudio");

  if (!controls || !mushafArea) return;

  const STORAGE_KEY = "hifz_repeat_settings";

  function isZoomModeActive() {
    return document.fullscreenElement === mushafArea;
  }

  function syncFloatingControls() {
    controls.classList.toggle("hidden", !isZoomModeActive());
  }

  function syncPlayPauseIcon() {
    if (!playPauseIcon || !audio) return;

    playPauseIcon.classList.remove("bi-play-fill", "bi-pause-fill");

    if (audio.paused || audio.ended) {
      playPauseIcon.classList.add("bi-play-fill");
    } else {
      playPauseIcon.classList.add("bi-pause-fill");
    }
  }

  function syncVolumeSlider() {
    if (!volumeRange) return;

    if (miniVolume) {
      volumeRange.value = miniVolume.value;
      return;
    }

    if (audio) {
      volumeRange.value = String(audio.volume ?? 1);
    }
  }

  function readRepeatSettings() {
    try {
      const raw = localStorage.getItem(STORAGE_KEY);
      if (!raw) {
        return { quickRepeat: 0, repeatCount: 0 };
      }

      const parsed = JSON.parse(raw);
      const value = Math.max(0, Math.min(10, Number(parsed.quickRepeat ?? parsed.repeatCount ?? 0) || 0));

      return {
        quickRepeat: value,
        repeatCount: value
      };
    } catch (err) {
      return { quickRepeat: 0, repeatCount: 0 };
    }
  }

  function getRepeatSettings() {
    if (!window.HIFZ_REPEAT_SETTINGS) {
      window.HIFZ_REPEAT_SETTINGS = readRepeatSettings();
    }
    return window.HIFZ_REPEAT_SETTINGS;
  }

  function getCurrentRepeatCount() {
    const settings = getRepeatSettings();
    const count = parseInt(settings.quickRepeat ?? settings.repeatCount ?? 0, 10);
    return Number.isNaN(count) || count < 0 ? 0 : count;
  }

  function emitRepeatCountChange(normalized) {
    document.dispatchEvent(
      new CustomEvent("hifz-repeat-count-change", {
        detail: { count: normalized }
      })
    );
  }

  function setCurrentRepeatCount(count, shouldEmit = true) {
    const normalized = Math.max(0, Math.min(10, Number(count) || 0));
    const settings = getRepeatSettings();

    settings.quickRepeat = normalized;
    settings.repeatCount = normalized;

    try {
      localStorage.setItem(
        STORAGE_KEY,
        JSON.stringify({
          quickRepeat: normalized,
          repeatCount: normalized
        })
      );
    } catch (err) {}

    syncRepeatCount();

    if (shouldEmit) {
      emitRepeatCountChange(normalized);
    }
  }

  window.setRepeatCount = function (count) {
    setCurrentRepeatCount(count, true);
  };

  function syncRepeatCount() {
    const value = `${getCurrentRepeatCount()}`;

    if (repeatCountText) {
      repeatCountText.textContent = value;
    }

    if (toolbarRepeatText) {
      toolbarRepeatText.textContent = value;
    }
  }

  function triggerMiniPlay() {
    if (miniPlayBtn) {
      miniPlayBtn.click();
      return true;
    }
    return false;
  }

  function triggerMiniStop() {
    if (miniStopBtn) {
      miniStopBtn.click();
      return true;
    }
    return false;
  }

  function syncMiniVolumeFromFloating(value) {
    if (miniVolume) {
      miniVolume.value = String(value);
      miniVolume.dispatchEvent(new Event("input", { bubbles: true }));
      miniVolume.dispatchEvent(new Event("change", { bubbles: true }));
    }

    if (audio) {
      const volume = Math.max(0, Math.min(1, parseFloat(value || "1")));
      audio.volume = volume;
      audio.muted = volume === 0;
    }

    try {
      localStorage.setItem("hifz_audio_volume", String(value));
    } catch (err) {}
  }

  function handleRepeatCountClick(e) {
    e.stopPropagation();

    const current = getCurrentRepeatCount();
    const next = current >= 10 ? 0 : current + 1;

    setCurrentRepeatCount(next, true);
  }

  if (playPauseBtn) {
    playPauseBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      triggerMiniPlay();

      setTimeout(function () {
        syncPlayPauseIcon();
        syncVolumeSlider();
      }, 0);
    });
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", function (e) {
      e.stopPropagation();
      triggerMiniStop();

      setTimeout(function () {
        syncPlayPauseIcon();
        syncVolumeSlider();
      }, 0);
    });
  }

  if (repeatCountBtn) {
    repeatCountBtn.addEventListener("click", handleRepeatCountClick);
  }

  if (toolbarRepeatBtn) {
    toolbarRepeatBtn.addEventListener("click", handleRepeatCountClick);
  }

  if (volumeRange) {
    volumeRange.addEventListener("input", function (e) {
      e.stopPropagation();
      syncMiniVolumeFromFloating(volumeRange.value);
    });

    volumeRange.addEventListener("change", function (e) {
      e.stopPropagation();
      syncMiniVolumeFromFloating(volumeRange.value);
    });
  }

  if (miniVolume) {
    miniVolume.addEventListener("input", syncVolumeSlider);
    miniVolume.addEventListener("change", syncVolumeSlider);
  }

  if (audio) {
    audio.addEventListener("play", syncPlayPauseIcon);
    audio.addEventListener("pause", syncPlayPauseIcon);
    audio.addEventListener("ended", syncPlayPauseIcon);
    audio.addEventListener("volumechange", syncVolumeSlider);
    audio.addEventListener("loadedmetadata", syncVolumeSlider);
    audio.addEventListener("canplay", syncVolumeSlider);
  }

  document.addEventListener("fullscreenchange", function () {
    syncFloatingControls();
    syncPlayPauseIcon();
    syncVolumeSlider();
    syncRepeatCount();
  });

  document.addEventListener("hifz-fullscreen-change", function () {
    syncFloatingControls();
    syncPlayPauseIcon();
    syncVolumeSlider();
    syncRepeatCount();
  });

  document.addEventListener("hifz-repeat-count-change", function (e) {
    const count =
      e.detail && typeof e.detail.count !== "undefined"
        ? Number(e.detail.count)
        : getCurrentRepeatCount();

    setCurrentRepeatCount(count, false);
  });

  window.addEventListener("load", function () {
    getRepeatSettings();
    syncFloatingControls();
    syncPlayPauseIcon();
    syncVolumeSlider();
    syncRepeatCount();
  });
})();