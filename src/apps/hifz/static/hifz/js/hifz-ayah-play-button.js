(function () {
  if (!window.HIFZ_MODE) return;
  if (window.__hifzAyahPlayButtonInitialized) return;
  window.__hifzAyahPlayButtonInitialized = true;

  const hifzAyahPlayBtn = document.getElementById("hifzAyahPlayBtn");
  const hifzAyahReciteBtn = document.getElementById("hifzAyahReciteBtn");
  const hifzAyahReciteIcon = document.getElementById("hifzAyahReciteIcon");
  const audio = document.getElementById("ayahAudio");

  let hifzSelectedAyahElement = null;
  let hifzSelectedAyahData = null;
  let lastSyncedAyahKey = null;

  let recitationMediaRecorder = null;
  let recitationChunks = [];
  let recitationStream = null;
  let isRecitationRecording = false;
  let latestUserRecordingUrl = null;

  function isRecordingTechniqueActive() {
    const area = document.getElementById("mushafArea");
    if (area && area.dataset.hifzRecordingMode === "on") {
      return true;
    }

    try {
      return localStorage.getItem("hifz_technique_mode") === "recording";
    } catch (err) {
      return false;
    }
  }

  function getCsrfToken() {
    const cookieValue = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));

    return cookieValue ? decodeURIComponent(cookieValue.split("=")[1]) : "";
  }

  function setHifzAyahButtonToPlay() {
    if (!hifzAyahPlayBtn) return;
    hifzAyahPlayBtn.innerHTML = '<i class="bi bi-play-fill text-sm leading-none"></i>';
    hifzAyahPlayBtn.setAttribute("aria-label", "Play selected ayah");
    hifzAyahPlayBtn.dataset.state = "play";
  }

  function setHifzAyahButtonToPause() {
    if (!hifzAyahPlayBtn) return;
    hifzAyahPlayBtn.innerHTML = '<i class="bi bi-pause-fill text-sm leading-none"></i>';
    hifzAyahPlayBtn.setAttribute("aria-label", "Pause selected ayah");
    hifzAyahPlayBtn.dataset.state = "pause";
  }

  function setRecitationButtonState(recording) {
    isRecitationRecording = recording;

    if (!hifzAyahReciteIcon) return;

    if (recording) {
      hifzAyahReciteIcon.className = "bi bi-stop-fill text-sm leading-none";
      if (hifzAyahReciteBtn) {
        hifzAyahReciteBtn.setAttribute("aria-label", "Stop recitation recording");
      }
    } else {
      hifzAyahReciteIcon.className = "bi bi-mic-fill text-sm leading-none";
      if (hifzAyahReciteBtn) {
        hifzAyahReciteBtn.setAttribute("aria-label", "Start recitation recording");
      }
    }
  }

  function getAyahTarget(el) {
    if (!el || typeof el.closest !== "function") return null;

    const directTarget = el.closest(".ayah-polygon") || el.closest(".ayah-box");
    if (directTarget) return directTarget;

    const maskPiece = el.closest(".hifz-mask-piece");
    const key = maskPiece && maskPiece.dataset ? maskPiece.dataset.key : "";
    if (!key) return null;

    const parts = key.split("|");
    if (parts.length !== 3) return null;

    const ayahData = {
      page: parseInt(parts[0] || "0", 10),
      surah: parseInt(parts[1] || "0", 10),
      ayah: parseInt(parts[2] || "0", 10),
    };

    const anchors = getSortedAyahAnchors(ayahData);
    if (!anchors.length) return null;

    const pieceRect = maskPiece.getBoundingClientRect();
    const pieceCenterX = pieceRect.left + pieceRect.width / 2;
    const pieceCenterY = pieceRect.top + pieceRect.height / 2;

    let bestAnchor = anchors[0];
    let bestScore = Number.NEGATIVE_INFINITY;

    anchors.forEach(function (anchor) {
      const rect = anchor.getBoundingClientRect();
      const overlapX = Math.max(0, Math.min(rect.right, pieceRect.right) - Math.max(rect.left, pieceRect.left));
      const overlapY = Math.max(0, Math.min(rect.bottom, pieceRect.bottom) - Math.max(rect.top, pieceRect.top));
      const overlapArea = overlapX * overlapY;
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const distance = Math.abs(centerX - pieceCenterX) + Math.abs(centerY - pieceCenterY);
      const score = overlapArea * 1000 - distance;
      if (score > bestScore) {
        bestScore = score;
        bestAnchor = anchor;
      }
    });

    return bestAnchor;
  }

  function buildAyahDataFromElement(element) {
    if (!element) return null;

    const sourceElement =
      element.classList && element.classList.contains("ayah-polygon")
        ? element
        : element.querySelector(".ayah-polygon") || element;

    const surah = parseInt(sourceElement.dataset.surah || element.dataset.surah || "0", 10);
    const ayah = parseInt(sourceElement.dataset.ayah || element.dataset.ayah || "0", 10);
    const page = parseInt(sourceElement.dataset.page || element.dataset.page || "0", 10);
    const audioSrc = sourceElement.dataset.audio || element.dataset.audio || "";
    const polyId = sourceElement.dataset.polyId || element.dataset.polyId || "";

    if (!surah || !ayah) return null;

    return {
      surah,
      ayah,
      page,
      audio: audioSrc,
      polyId,
    };
  }

  function buildAyahKey(ayahData) {
    if (!ayahData) return null;
    if (!ayahData.page || !ayahData.surah || !ayahData.ayah) return null;
    return `${ayahData.page}|${ayahData.surah}|${ayahData.ayah}`;
  }

  function hideHifzAyahReciteButton() {
    if (!hifzAyahReciteBtn) return;
    hifzAyahReciteBtn.classList.add("hidden");
    hifzAyahReciteBtn.classList.remove("flex");
    setRecitationButtonState(false);
  }

  function hideHifzAyahPlayButton() {
    if (!hifzAyahPlayBtn) return;
    hifzAyahPlayBtn.classList.add("hidden");
    hifzAyahPlayBtn.classList.remove("flex");
    setHifzAyahButtonToPlay();
    hideHifzAyahReciteButton();
  }

  function showHifzAyahReciteButtonForElement(element) {
    if (!element || !hifzAyahReciteBtn) return;

    const anchor =
      element.classList && element.classList.contains("ayah-polygon")
        ? element
        : element.querySelector(".ayah-polygon") || element;

    const rect = anchor.getBoundingClientRect();
    window.__LAST_AYAH_TARGET_RECT__ = rect;
    const isSmallScreen = window.matchMedia("(max-width: 768px)").matches;
    const centerX = rect.left + window.scrollX + rect.width / 2;
    const buttonTop = rect.top + window.scrollY + rect.height / 2 - 18;
    let top = buttonTop;
    let left = 0;

    if (isSmallScreen) {
      const btnWidth = hifzAyahReciteBtn.offsetWidth || 18;
      const gap = 14;
      const reciteBtnHeight = hifzAyahReciteBtn.offsetHeight || 18;
      const preferAboveTop = rect.top + window.scrollY - reciteBtnHeight - 16;
      const fallbackBelowTop = rect.bottom + window.scrollY + 14;
      top = preferAboveTop > window.scrollY + 6 ? preferAboveTop : fallbackBelowTop;
      left = centerX + gap / 2;
      left = Math.min(window.scrollX + window.innerWidth - btnWidth - 6, left);
    } else {
      const viewportMid = window.innerWidth / 2;
      const elementCenter = rect.left + rect.width / 2;
      const isRightSide = elementCenter >= viewportMid;
      if (isRightSide) {
        left = rect.right + window.scrollX + 42;
      } else {
        left = rect.left + window.scrollX - 76;
      }
    }

    hifzAyahReciteBtn.style.top = `${top}px`;
    hifzAyahReciteBtn.style.left = `${left}px`;
    hifzAyahReciteBtn.classList.remove("hidden");
    hifzAyahReciteBtn.classList.add("flex");
  }

  function showHifzAyahPlayButtonForElement(element, ayahData, forcePauseState) {
    if (!element || !hifzAyahPlayBtn) return;

    hifzSelectedAyahElement = element;
    hifzSelectedAyahData = ayahData;

    if ((window.HifzWriting && window.HifzWriting.isActive())) {
      hideHifzAyahPlayButton();
      window.HifzWriting.showForElement(element, ayahData);
      return;
    }

    if (window.HifzWriting) window.HifzWriting.removeActive();

    if (!isRecordingTechniqueActive()) {
      hideHifzAyahPlayButton();
      return;
    }

    const anchor =
      element.classList && element.classList.contains("ayah-polygon")
        ? element
        : element.querySelector(".ayah-polygon") || element;

    const rect = anchor.getBoundingClientRect();
    window.__LAST_AYAH_TARGET_RECT__ = rect;
    const isSmallScreen = window.matchMedia("(max-width: 768px)").matches;
    const centerX = rect.left + window.scrollX + rect.width / 2;
    const buttonTop = rect.top + window.scrollY + rect.height / 2 - 18;
    let top = buttonTop;
    let left = 0;

    if (isSmallScreen) {
      const btnWidth = hifzAyahPlayBtn.offsetWidth || 18;
      const gap = 14;
      const playBtnHeight = hifzAyahPlayBtn.offsetHeight || 18;
      const preferAboveTop = rect.top + window.scrollY - playBtnHeight - 16;
      const fallbackBelowTop = rect.bottom + window.scrollY + 14;
      top = preferAboveTop > window.scrollY + 6 ? preferAboveTop : fallbackBelowTop;
      left = centerX - btnWidth - gap / 2;
      left = Math.max(window.scrollX + 6, left);
    } else {
      const viewportMid = window.innerWidth / 2;
      const elementCenter = rect.left + rect.width / 2;
      const isRightSide = elementCenter >= viewportMid;
      if (isRightSide) {
        left = rect.right + window.scrollX + 6;
      } else {
        left = rect.left + window.scrollX - 40;
      }
    }

    hifzAyahPlayBtn.style.top = `${top}px`;
    hifzAyahPlayBtn.style.left = `${left}px`;
    hifzAyahPlayBtn.classList.remove("hidden");
    hifzAyahPlayBtn.classList.add("flex");

    if (forcePauseState) {
      setHifzAyahButtonToPause();
    } else {
      setHifzAyahButtonToPlay();
    }

    showHifzAyahReciteButtonForElement(element);
  }

  function clearAyahHighlight() {
    document.querySelectorAll(".ayah-polygon").forEach((el) => {
      el.classList.remove("ayah-active");
      el.classList.remove("ayah-playing");
      el.classList.remove("ayah-current");
      el.classList.remove("resume-ayah-target");
    });

    document.querySelectorAll(".ayah-box").forEach((el) => {
      el.classList.remove("ayah-active");
      el.classList.remove("ayah-playing");
      el.classList.remove("ayah-current");
      el.classList.remove("resume-ayah-target");
    });

    document.querySelectorAll(".ayah-hover-piece").forEach((el) => {
      el.remove();
    });
  }

  function markSelectedAyah(ayahData) {
    if (!ayahData) return;

    clearAyahHighlight();

    const activePolygons = document.querySelectorAll(
      `.ayah-polygon[data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
    );

    activePolygons.forEach((el) => {
      el.classList.add("ayah-active");
      const box = el.closest(".ayah-box");
      if (box) {
        box.classList.add("ayah-active");
      }
    });

    const activeBoxes = document.querySelectorAll(
      `.ayah-box[data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
    );

    activeBoxes.forEach((el) => {
      el.classList.add("ayah-active");
    });

    const key = buildAyahKey(ayahData);
    if (key && typeof window.hifzSelectAyahRevealByKey === "function") {
      window.hifzSelectAyahRevealByKey(key);
    }

    window.currentAyahItem = ayahData;
  }

  function stopCurrentAudio() {
    if (!audio) return;

    try {
      audio.pause();
      audio.currentTime = 0;
    } catch (err) {}
  }

  function stopRecitationTracks() {
    if (recitationStream) {
      recitationStream.getTracks().forEach((track) => track.stop());
      recitationStream = null;
    }
  }

  function stopRecitationRecordingSilently() {
    if (recitationMediaRecorder && recitationMediaRecorder.state !== "inactive") {
      try {
        recitationMediaRecorder.onstop = null;
        recitationMediaRecorder.stop();
      } catch (err) {}
    }

    stopRecitationTracks();
    recitationMediaRecorder = null;
    recitationChunks = [];
    setRecitationButtonState(false);
  }

  function clearSelectedAyahAndStopAudio() {
    stopCurrentAudio();
    stopRecitationRecordingSilently();
    if (window.HifzWriting) window.HifzWriting.removeActive();
    clearAyahHighlight();

    if (typeof window.hifzClearAyahReveal === "function") {
      window.hifzClearAyahReveal();
    }

    hifzSelectedAyahElement = null;
    hifzSelectedAyahData = null;
    window.currentAyahItem = null;
    lastSyncedAyahKey = null;

    hideHifzAyahPlayButton();
  }

  function isSameAyah(a, b) {
    if (!a || !b) return false;
    return Number(a.surah) === Number(b.surah) && Number(a.ayah) === Number(b.ayah);
  }

  function findElementForAyahData(ayahData) {
    if (!ayahData) return null;

    return (
      document.querySelector(
        `.ayah-box[data-page="${ayahData.page}"][data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
      ) ||
      document.querySelector(
        `.ayah-polygon[data-page="${ayahData.page}"][data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
      ) ||
      document.querySelector(
        `.ayah-box[data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
      ) ||
      document.querySelector(
        `.ayah-polygon[data-surah="${ayahData.surah}"][data-ayah="${ayahData.ayah}"]`
      )
    );
  }

  function syncToCurrentPlayingAyah() {
    if (!audio || audio.paused) return;
    if (!window.currentAyahItem) return;

    const current = window.currentAyahItem;
    const currentKey = buildAyahKey(current);

    if (!currentKey || currentKey === lastSyncedAyahKey) return;

    const targetElement = findElementForAyahData(current);
    if (!targetElement) return;

    markSelectedAyah(current);
    showHifzAyahPlayButtonForElement(targetElement, current, true);

    lastSyncedAyahKey = currentKey;
  }

  function repositionSelectedAyahButton() {
    if (!hifzSelectedAyahData) return;

    const targetElement = findElementForAyahData(hifzSelectedAyahData);
    if (!targetElement) return;

    if ((window.HifzWriting && window.HifzWriting.isActive())) {
      window.HifzWriting.showForElement(targetElement, hifzSelectedAyahData);
      return;
    }

    const shouldShowPause =
      !!audio &&
      !audio.paused &&
      hifzAyahPlayBtn &&
      hifzAyahPlayBtn.dataset.state === "pause";

    showHifzAyahPlayButtonForElement(
      targetElement,
      hifzSelectedAyahData,
      shouldShowPause
    );
  }

  function syncSelectedAyahWithoutStopping() {
    if (!hifzSelectedAyahData) return;

    const targetElement = findElementForAyahData(hifzSelectedAyahData);
    if (!targetElement) return;

    markSelectedAyah(hifzSelectedAyahData);

    const shouldShowPause = !!audio && !audio.paused;

    showHifzAyahPlayButtonForElement(
      targetElement,
      hifzSelectedAyahData,
      shouldShowPause
    );
  }

  async function sendRecitationAudio(audioBlob) {
    if (!window.currentAyahItem) return;

    const formData = new FormData();
    const ext = audioBlob.type.includes("webm") ? "webm" : "bin";
    formData.append("audio", audioBlob, `recitation.${ext}`);
    formData.append("surah_number", window.currentAyahItem.surah);
    formData.append("ayah_number", window.currentAyahItem.ayah);
    const hifzQariSelect = document.getElementById("hifzQariSelect");
    const selectedQari = hifzQariSelect ? (hifzQariSelect.value || "").trim() : "";
    const selectedMushaf = (window.QURAN_MUSHAF_KEY || "hafs").trim();
    formData.append("qari", selectedQari || "alhudhaify");
    formData.append("mushaf", selectedMushaf || "hafs");

    const response = await fetch("/hifz/api/recitation-check/", {
      method: "POST",
      headers: {
        "X-CSRFToken": getCsrfToken(),
      },
      body: formData,
    });

    const rawText = await response.text();
    let data = null;

    try {
      data = JSON.parse(rawText);
    } catch (error) {
      console.error("Non-JSON response:", rawText);
      return;
    }

    const resultAyahText = document.getElementById("recitationResultAyahText");
    const scoreText = document.getElementById("recitationScoreText");
    const analysisBox = document.getElementById("recitationAnalysisResult");
    const expectedTextBox = document.getElementById("recitationExpectedText");
    const recognizedTextBox = document.getElementById("recitationRecognizedText");
    const errorWordsBox = document.getElementById("recitationErrorWords");
    const shaykhCompareAudio = document.getElementById("shaykhCompareAudio");
    const userCompareAudio = document.getElementById("userCompareAudio");
    const playShaykhAudioBtn = document.getElementById("playShaykhAudioBtn");
    const playUserAudioBtn = document.getElementById("playUserAudioBtn");

    if (!response.ok) {
      if (analysisBox) {
        analysisBox.innerHTML = `<span class="text-red-600 font-semibold">${data.error || "Request failed"}</span>`;
      }
      return;
    }

    console.log("Recitation API response:", data);

    function escapeHtml(value) {
      return String(value || "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#39;");
    }

    function renderParts(parts, emptyText) {
      if (!Array.isArray(parts) || !parts.length) {
        return `<span class="text-gray-400">${escapeHtml(emptyText)}</span>`;
      }

      return parts
        .map(function (part) {
          const text = escapeHtml(part.text || "—");
          if (part.status === "correct") {
            return `<span class="rounded-md bg-emerald-50 px-1 py-0.5 text-emerald-700">${text}</span>`;
          }
          return `<span class="rounded-md bg-red-50 px-1 py-0.5 font-semibold text-red-700">${text}</span>`;
        })
        .join(" ");
    }

    function renderFirstError(errors) {
      if (!Array.isArray(errors) || !errors.length) {
        return '<span class="text-emerald-600 font-semibold">لا يوجد خطأ ظاهر في الكلمات.</span>';
      }

      const first = errors[0] || {};
      const expectedWord = escapeHtml(first.expected_word || "—");
      const recognizedWord = escapeHtml(first.recognized_word || "—");
      const tip = escapeHtml(first.tajweed_tip || "");

      return `
        <div class="space-y-1">
          <div><span class="font-semibold text-gray-700">الصحيح:</span> <span class="rounded-md bg-emerald-50 px-1 py-0.5 text-emerald-700">${expectedWord}</span></div>
          <div><span class="font-semibold text-gray-700">المنطوق:</span> <span class="rounded-md bg-red-50 px-1 py-0.5 text-red-700">${recognizedWord}</span></div>
          <div class="text-[11px] leading-5 text-amber-800">${tip}</div>
        </div>
      `;
    }

    if (resultAyahText) {
      resultAyahText.textContent = data.selected_ayah_text || "";
    }

    if (scoreText) {
      scoreText.textContent = `${data.score || 0}%`;
      scoreText.className = `mt-1 text-2xl font-bold ${data.is_correct ? "text-emerald-600" : "text-amber-600"}`;
    }

    if (analysisBox) {
      analysisBox.innerHTML = data.is_correct
        ? '<span class="text-emerald-600 font-semibold">ممتاز ✅ التلاوة متقنة في هذا الموضع.</span>'
        : `<span class="text-red-600 font-semibold">${escapeHtml(data.message || "يوجد موضع يحتاج إعادة")}</span>`;
    }

    if (expectedTextBox) {
      expectedTextBox.innerHTML = renderParts(data.expected_parts, "لا يوجد نص مرجعي");
    }

    if (recognizedTextBox) {
      recognizedTextBox.innerHTML = renderParts(data.recognized_parts, "لم يلتقط النظام قراءة واضحة بعد");
    }

    if (window.WirdAnalytics && typeof window.WirdAnalytics.track === "function") {
      window.WirdAnalytics.track("recitation_correction", {
        surah: window.currentAyahItem.surah,
        ayah: window.currentAyahItem.ayah,
        score: data.score || 0,
        is_correct: !!data.is_correct,
      });
    }

    if (errorWordsBox) {
      errorWordsBox.innerHTML = renderFirstError(data.errors);
    }

    if (shaykhCompareAudio) {
      shaykhCompareAudio.src = data.shaykh_audio_url || "";
      shaykhCompareAudio.load();
    }

    if (userCompareAudio) {
      if (latestUserRecordingUrl) {
        URL.revokeObjectURL(latestUserRecordingUrl);
      }
      latestUserRecordingUrl = URL.createObjectURL(audioBlob);
      userCompareAudio.src = latestUserRecordingUrl;
      userCompareAudio.load();
    }

    function setPlayButtonState(button, playing) {
      if (!button) return;
      const iconClass = playing ? "bi-stop-fill" : "bi-play-fill";
      const label = button.getAttribute("data-label") || button.textContent || "";
      button.innerHTML = `<i class="bi ${iconClass}"></i><span>${label}</span>`;
      button.classList.toggle("is-playing", !!playing);
    }

    if (playShaykhAudioBtn) {
      playShaykhAudioBtn.setAttribute("data-label", playShaykhAudioBtn.textContent.trim());
      playShaykhAudioBtn.classList.add("inline-flex", "items-center", "gap-1.5");
      setPlayButtonState(playShaykhAudioBtn, false);
    }
    if (playUserAudioBtn) {
      playUserAudioBtn.setAttribute("data-label", playUserAudioBtn.textContent.trim());
      playUserAudioBtn.classList.add("inline-flex", "items-center", "gap-1.5");
      setPlayButtonState(playUserAudioBtn, false);
    }

    function resetAudioButtons() {
      setPlayButtonState(playShaykhAudioBtn, false);
      setPlayButtonState(playUserAudioBtn, false);
    }

    if (shaykhCompareAudio) {
      shaykhCompareAudio.onplay = function () {
        setPlayButtonState(playShaykhAudioBtn, true);
      };
      shaykhCompareAudio.onpause = function () {
        setPlayButtonState(playShaykhAudioBtn, false);
      };
      shaykhCompareAudio.onended = function () {
        setPlayButtonState(playShaykhAudioBtn, false);
      };
    }

    if (userCompareAudio) {
      userCompareAudio.onplay = function () {
        setPlayButtonState(playUserAudioBtn, true);
      };
      userCompareAudio.onpause = function () {
        setPlayButtonState(playUserAudioBtn, false);
      };
      userCompareAudio.onended = function () {
        setPlayButtonState(playUserAudioBtn, false);
      };
    }

    if (playShaykhAudioBtn && shaykhCompareAudio) {
      playShaykhAudioBtn.onclick = async function (event) {
        if (event) {
          event.preventDefault();
          event.stopPropagation();
        }
        try {
          if (!shaykhCompareAudio.paused) {
            shaykhCompareAudio.pause();
            shaykhCompareAudio.currentTime = 0;
            setPlayButtonState(playShaykhAudioBtn, false);
            return;
          }

          if (userCompareAudio) {
            userCompareAudio.pause();
            userCompareAudio.currentTime = 0;
          }

          shaykhCompareAudio.currentTime = 0;
          await shaykhCompareAudio.play();
        } catch (error) {
          console.error("Failed to play shaykh audio:", error, shaykhCompareAudio.src);
          resetAudioButtons();
        }
      };
    }

    if (playUserAudioBtn && userCompareAudio) {
      playUserAudioBtn.onclick = async function (event) {
        if (event) {
          event.preventDefault();
          event.stopPropagation();
        }
        try {
          if (!userCompareAudio.paused) {
            userCompareAudio.pause();
            userCompareAudio.currentTime = 0;
            setPlayButtonState(playUserAudioBtn, false);
            return;
          }

          if (shaykhCompareAudio) {
            shaykhCompareAudio.pause();
            shaykhCompareAudio.currentTime = 0;
          }

          userCompareAudio.pause();
          userCompareAudio.currentTime = 0;
          userCompareAudio.muted = false;
          userCompareAudio.volume = 1;
          userCompareAudio.load();

          await userCompareAudio.play();
        } catch (error) {
          console.error("Failed to play user audio:", error);
          console.error("User audio URL:", userCompareAudio.src);
          resetAudioButtons();
        }
      };
    }
}

  async function startRecitationRecording() {
  recitationChunks = [];

  recitationStream = await navigator.mediaDevices.getUserMedia({
    audio: {
      echoCancellation: true,
      noiseSuppression: true,
      autoGainControl: true,
    },
  });

  let mimeType = "";

  if (MediaRecorder.isTypeSupported("audio/webm;codecs=opus")) {
    mimeType = "audio/webm;codecs=opus";
  } else if (MediaRecorder.isTypeSupported("audio/webm")) {
    mimeType = "audio/webm";
  }

  recitationMediaRecorder = mimeType
    ? new MediaRecorder(recitationStream, { mimeType })
    : new MediaRecorder(recitationStream);

  recitationMediaRecorder.ondataavailable = function (event) {
    if (event.data && event.data.size > 0) {
      recitationChunks.push(event.data);
    }
  };

  recitationMediaRecorder.onstop = async function () {
    const finalMimeType =
      recitationMediaRecorder.mimeType || "audio/webm";

    const audioBlob = new Blob(recitationChunks, { type: finalMimeType });

    if (latestUserRecordingUrl) {
      URL.revokeObjectURL(latestUserRecordingUrl);
      latestUserRecordingUrl = null;
    }

    console.log("Recorded blob size:", audioBlob.size, "type:", finalMimeType);

    stopRecitationTracks();
    recitationMediaRecorder = null;
    setRecitationButtonState(false);
    if (window.matchMedia("(max-width: 991px)").matches) {
      hideHifzAyahPlayButton();
    }

    await sendRecitationAudio(audioBlob);
    const selectedAnchor =
      hifzSelectedAyahElement &&
      (hifzSelectedAyahElement.classList.contains("ayah-polygon")
        ? hifzSelectedAyahElement
        : hifzSelectedAyahElement.querySelector(".ayah-polygon") || hifzSelectedAyahElement);
    const selectedRect =
      selectedAnchor && typeof selectedAnchor.getBoundingClientRect === "function"
        ? selectedAnchor.getBoundingClientRect()
        : window.__LAST_AYAH_TARGET_RECT__ || null;
    if (selectedRect) {
      window.__LAST_AYAH_TARGET_RECT__ = selectedRect;
    }
    document.dispatchEvent(new CustomEvent("hifz-recitation-stop", { detail: { rect: selectedRect } }));
  };

  recitationMediaRecorder.start(250);
  setRecitationButtonState(true);
}

  function stopRecitationRecording() {
    if (recitationMediaRecorder && recitationMediaRecorder.state !== "inactive") {
      recitationMediaRecorder.stop();
    } else {
      stopRecitationTracks();
      recitationMediaRecorder = null;
      setRecitationButtonState(false);
    }
  }

  document.addEventListener(
    "click",
    function (event) {
      if (
        event.target.closest("#hifzAyahPlayBtn") ||
        event.target.closest("#hifzAyahReciteBtn")
      ) {
        return;
      }

      const ayah = getAyahTarget(event.target);
      if (!ayah) return;

      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      const ayahData = buildAyahDataFromElement(ayah);
      if (!ayahData) return;

      const wasSameAyah = isSameAyah(hifzSelectedAyahData, ayahData);

      clearSelectedAyahAndStopAudio();

      if (wasSameAyah) {
        return;
      }

      markSelectedAyah(ayahData);
      showHifzAyahPlayButtonForElement(ayah, ayahData, false);
      lastSyncedAyahKey = buildAyahKey(ayahData);
    },
    true
  );

  if (hifzAyahPlayBtn) {
    hifzAyahPlayBtn.addEventListener("click", function (event) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      if (!hifzSelectedAyahData) return;

      const state = hifzAyahPlayBtn.dataset.state || "play";

      if (state === "pause") {
        if (audio && !audio.paused) {
          audio.pause();
        }
        setHifzAyahButtonToPlay();
        return;
      }

      clearAyahHighlight();
      markSelectedAyah(hifzSelectedAyahData);

      if (typeof window.playAyahByKey === "function") {
        window.playAyahByKey(
          hifzSelectedAyahData.surah,
          hifzSelectedAyahData.ayah
        );
        setHifzAyahButtonToPause();
        lastSyncedAyahKey = buildAyahKey(hifzSelectedAyahData);
        return;
      }

      if (audio && audio.paused) {
        audio
          .play()
          .then(function () {
            setHifzAyahButtonToPause();
            lastSyncedAyahKey = buildAyahKey(hifzSelectedAyahData);
          })
          .catch(function () {});
      }
    });
  }

  if (hifzAyahReciteBtn) {
    hifzAyahReciteBtn.addEventListener("click", async function (event) {
      event.preventDefault();
      event.stopPropagation();
      event.stopImmediatePropagation();

      if (!window.currentAyahItem) return;

      if (isRecitationRecording) {
        stopRecitationRecording();
      } else {
        await startRecitationRecording();
      }
    });
  }

  if (audio) {
    audio.addEventListener("play", function () {
      syncToCurrentPlayingAyah();
      setHifzAyahButtonToPause();
    });

    audio.addEventListener("playing", function () {
      syncToCurrentPlayingAyah();
      setHifzAyahButtonToPause();
    });

    audio.addEventListener("pause", function () {
      setHifzAyahButtonToPlay();
    });

    audio.addEventListener("ended", function () {
      setHifzAyahButtonToPlay();
    });

    audio.addEventListener("timeupdate", function () {
      syncToCurrentPlayingAyah();
    });
  }

  if (window.HifzWriting) window.HifzWriting.initToolsBar();

  setInterval(function () {
    syncToCurrentPlayingAyah();
  }, 120);

  document.addEventListener("click", function (event) {
    if (
      event.target.closest("#hifzAyahPlayBtn") ||
      event.target.closest("#hifzAyahReciteBtn") ||
      event.target.closest(".hifz-writing-pad") ||
      event.target.closest("#hifzWritingToolsBar")
    ) {
      return;
    }

    const clickedAyah = getAyahTarget(event.target);
    if (clickedAyah) return;

    clearSelectedAyahAndStopAudio();
  });

  document.addEventListener("quran-page-flipped", function () {
    setTimeout(function () {
      syncSelectedAyahWithoutStopping();
      syncToCurrentPlayingAyah();
      if (window.HifzWriting) window.HifzWriting.renderAll();
    }, 120);
  });

  document.addEventListener("hifz-technique-changed", function (event) {
    const mode = event.detail && event.detail.mode;
    if (window.HifzWriting) window.HifzWriting.syncToolsBarVisibility();
    if (mode === "writing") {
      if (window.HifzWriting) window.HifzWriting.initToolsBar();
      hideHifzAyahPlayButton();
      if (hifzSelectedAyahData) {
        repositionSelectedAyahButton();
      }
      if (window.HifzWriting && window.HifzWriting.isAllVisible()) {
        window.HifzWriting.renderAll();
      }
      return;
    }

    if (window.HifzWriting) window.HifzWriting.setAllVisible(false);
    if (window.HifzWriting) window.HifzWriting.removeActive();

    if (mode === "recording") {
      repositionSelectedAyahButton();
      return;
    }

    hideHifzAyahPlayButton();
    stopRecitationRecordingSilently();
  });

  let scrollLockUntil = 0;

  document.addEventListener("fullscreenchange", function () {
    scrollLockUntil = Date.now() + 600;

    setTimeout(function () {
      syncSelectedAyahWithoutStopping();
      repositionSelectedAyahButton();
      syncToCurrentPlayingAyah();
      if (window.HifzWriting) window.HifzWriting.renderAll();
    }, 160);
  });

  window.addEventListener("resize", function () {
    scrollLockUntil = Date.now() + 400;

    setTimeout(function () {
      syncSelectedAyahWithoutStopping();
      repositionSelectedAyahButton();
      syncToCurrentPlayingAyah();
      if (window.HifzWriting) window.HifzWriting.renderAll();
    }, 120);
  });

  window.addEventListener("scroll", function () {
    if (Date.now() < scrollLockUntil) {
      return;
    }

    if ((window.HifzWriting && window.HifzWriting.isActive()) && hifzSelectedAyahData) {
      repositionSelectedAyahButton();
      return;
    }

    if (audio && !audio.paused) {
      repositionSelectedAyahButton();
      return;
    }

    clearSelectedAyahAndStopAudio();
  });

  setHifzAyahButtonToPlay();
  setRecitationButtonState(false);
})();
