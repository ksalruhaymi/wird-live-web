(function () {
  if (window.__hifzRepeatAudioInitialized) return;
  window.__hifzRepeatAudioInitialized = true;

  function getSettings() {
    return window.HIFZ_REPEAT_SETTINGS || {
      quickRepeat: 0,
      repeatCount: 5
    };
  }

  function getTargetRepeat() {
    const settings = getSettings();
    return Number(settings.quickRepeat || 0);
  }

  function reHighlightCurrentAyah() {
    const item = window.currentAyahItem;
    if (!item) return;

    if (typeof window.highlightCurrentAyah === "function") {
      try {
        window.highlightCurrentAyah(Number(item.surah), Number(item.ayah));
      } catch (e) {}
    }
  }

  document.addEventListener("DOMContentLoaded", function () {
    const audio = document.getElementById("ayahAudio");
    if (!audio) return;

    let replayCount = 0;
    let replaying = false;
    let lastAudioSrc = "";

    function resetRepeatState() {
      replayCount = 0;
      replaying = false;
      lastAudioSrc = audio.currentSrc || audio.src || "";
    }

    audio.addEventListener("play", function () {
      const currentSrc = audio.currentSrc || audio.src || "";

      if (!replaying && currentSrc !== lastAudioSrc) {
        replayCount = 0;
        lastAudioSrc = currentSrc;
      }
    });

    audio.addEventListener(
      "ended",
      function (e) {
        const item = window.currentAyahItem;
        const target = getTargetRepeat();

        if (!window.HIFZ_MODE || !item || target <= 1) {
          resetRepeatState();
          return;
        }

        const neededReplays = target - 1;

        if (replayCount < neededReplays) {
          replayCount += 1;
          replaying = true;

          if (typeof e.stopImmediatePropagation === "function") {
            e.stopImmediatePropagation();
          }

          reHighlightCurrentAyah();

          setTimeout(function () {
            audio.currentTime = 0;
            audio.play().catch(() => {
              replaying = false;
            });
          }, 120);

          return;
        }

        resetRepeatState();
      },
      true
    );

    audio.addEventListener("pause", function () {
      if (!audio.ended && !replaying) {
        replayCount = 0;
      }
    });
  });
})();