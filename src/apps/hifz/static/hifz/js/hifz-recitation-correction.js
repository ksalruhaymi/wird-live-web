document.addEventListener("DOMContentLoaded", function () {
  const correctionBar = document.getElementById("recitationCorrectionBar");
  const startBtn = document.getElementById("startRecitationRecordingBtn");
  const stopBtn = document.getElementById("stopRecitationRecordingBtn");

  const barAyahText = document.getElementById("recitationBarAyahText");
  const resultAyahText = document.getElementById("recitationResultAyahText");
  const expectedTextBox = document.getElementById("recitationExpectedText");
  const recognizedTextBox = document.getElementById("recitationRecognizedText");
  const analysisBox = document.getElementById("recitationAnalysisResult");
  const i18nEl = document.getElementById("hifzRecitationI18n");
  const recitationI18n = {
    noResult: (i18nEl && i18nEl.dataset.noResult) || "",
  };

  let mediaRecorder = null;
  let audioChunks = [];
  let currentAyah = null;
  let currentStream = null;

  function getCsrfToken() {
    const cookieValue = document.cookie
      .split("; ")
      .find((row) => row.startsWith("csrftoken="));
    return cookieValue ? decodeURIComponent(cookieValue.split("=")[1]) : "";
  }

  function stopTracks() {
    if (currentStream) {
      currentStream.getTracks().forEach((track) => track.stop());
      currentStream = null;
    }
  }

  function showCorrectionBar() {
    if (!correctionBar) return;
    correctionBar.classList.remove("hidden");
  }

  function hideCorrectionBar() {
    if (!correctionBar) return;
    correctionBar.classList.add("hidden");
  }

  function clearResults() {
    if (expectedTextBox) expectedTextBox.textContent = "";
    if (recognizedTextBox) {
      recognizedTextBox.textContent = recitationI18n.noResult;
    }
    if (analysisBox) {
      analysisBox.innerHTML = "";
    }
  }

  function setSelectedAyahText(text) {
    const value = text && text.trim() ? text.trim() : "";

    if (barAyahText) {
      barAyahText.textContent = value;
    }

    if (resultAyahText) {
      resultAyahText.textContent = value;
    }
  }

  function renderAnalysis(comparison) {
    if (!analysisBox) return;

    if (!comparison) {
      analysisBox.innerHTML = '<span class="text-gray-400">No analysis</span>';
      return;
    }

    if (comparison.is_correct) {
      analysisBox.innerHTML =
        '<div class="rounded-xl border border-emerald-200 bg-emerald-50 p-3 text-emerald-700 font-semibold">تلاوة صحيحة ✅</div>';
      return;
    }

    if (!comparison.errors || !comparison.errors.length) {
      analysisBox.innerHTML =
        '<div class="rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-700 font-semibold">النتيجة غير واضحة</div>';
      return;
    }

    const firstError = comparison.errors[0];

    if (
      firstError.type === "delete" &&
      firstError.expected &&
      (!firstError.actual || firstError.actual === "")
    ) {
      analysisBox.innerHTML = `
        <div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">
          <div class="font-semibold mb-2">لم يتم التعرف على التلاوة</div>
          <div class="text-sm">تأكد من وضوح الصوت وعدم إيقاف التسجيل بسرعة.</div>
        </div>
      `;
      return;
    }

    const rows = comparison.errors.map((error) => {
      let message = "";

      if (error.type === "replace") {
        message = `خطأ في القراءة: "${error.expected || "-"}" ← "${error.actual || "-"}"`;
      } else if (error.type === "delete") {
        message = `لم تقرأ: "${error.expected || "-"}"`;
      } else if (error.type === "insert") {
        message = `قرأت زيادة: "${error.actual || "-"}"`;
      } else {
        message = `يوجد اختلاف بين المتوقع والمسموع`;
      }

      return `
        <div class="mb-2 rounded-xl border border-amber-200 bg-amber-50 p-3 text-amber-800">
          ${message}
        </div>
      `;
    });

    analysisBox.innerHTML = rows.join("");
  }

  function resolveAyahFromElement(element) {
    if (!element) return null;

    const surahNumber =
      element.dataset.surah ||
      element.dataset.surahNumber ||
      element.getAttribute("data-surah") ||
      "";

    const ayahNumber =
      element.dataset.ayah ||
      element.dataset.ayahNumber ||
      element.getAttribute("data-ayah") ||
      "";

    const page =
      element.dataset.page ||
      element.dataset.pageNumber ||
      element.getAttribute("data-page") ||
      "";

    if (!surahNumber || !ayahNumber) return null;

    return {
      surahNumber,
      ayahNumber,
      page,
      text: "",
    };
  }

  function resolveCurrentAyah() {
    if (
      window.currentAyahItem &&
      (window.currentAyahItem.surah || window.currentAyahItem.surah_number || window.currentAyahItem.surahNumber) &&
      (window.currentAyahItem.ayah || window.currentAyahItem.ayah_number || window.currentAyahItem.ayahNumber)
    ) {
      return {
        surahNumber:
          window.currentAyahItem.surah ??
          window.currentAyahItem.surah_number ??
          window.currentAyahItem.surahNumber ??
          "",
        ayahNumber:
          window.currentAyahItem.ayah ??
          window.currentAyahItem.ayah_number ??
          window.currentAyahItem.ayahNumber ??
          "",
        page:
          window.currentAyahItem.page ??
          window.currentAyahItem.page_number ??
          window.currentAyahItem.pageNumber ??
          "",
        text:
          window.currentAyahItem.text ??
          window.currentAyahItem.ayah_text ??
          "",
      };
    }

    return null;
  }

  async function loadAyahText(surahNumber, ayahNumber) {
    try {
      const response = await fetch(
        `/hifz/api/ayah-text/?surah_number=${encodeURIComponent(surahNumber)}&ayah_number=${encodeURIComponent(ayahNumber)}`
      );

      const rawText = await response.text();
      let data = null;

      try {
        data = JSON.parse(rawText);
      } catch (error) {
        return "";
      }

      if (!response.ok) {
        return "";
      }

      return data.text || "";
    } catch (error) {
      console.error("Failed to load ayah text:", error);
      return "";
    }
  }

  async function activateRecitationCorrectionForAyah(ayahData) {
    if (!ayahData || !ayahData.surahNumber || !ayahData.ayahNumber) {
      currentAyah = null;
      hideCorrectionBar();
      setSelectedAyahText("");
      clearResults();
      return;
    }

    currentAyah = {
      surahNumber: ayahData.surahNumber,
      ayahNumber: ayahData.ayahNumber,
      page: ayahData.page || "",
      text: ayahData.text || "",
    };

    showCorrectionBar();
    clearResults();

    const ayahText =
      currentAyah.text && currentAyah.text.trim()
        ? currentAyah.text.trim()
        : await loadAyahText(currentAyah.surahNumber, currentAyah.ayahNumber);

    currentAyah.text = ayahText || "";
    setSelectedAyahText(currentAyah.text || `سورة ${currentAyah.surahNumber} - آية ${currentAyah.ayahNumber}`);
  }

  async function sendAudioToServer(audioBlob) {
    if (!currentAyah || !currentAyah.surahNumber || !currentAyah.ayahNumber) {
      if (analysisBox) {
        analysisBox.innerHTML =
          '<div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700 font-semibold">اختر آية أولًا</div>';
      }
      return;
    }

    const formData = new FormData();
    formData.append("audio", audioBlob, "recitation.webm");
    formData.append("surah_number", currentAyah.surahNumber);
    formData.append("ayah_number", currentAyah.ayahNumber);
    const hifzQariSelect = document.getElementById("hifzQariSelect");
    const selectedQari = hifzQariSelect ? (hifzQariSelect.value || "").trim() : "";
    const selectedMushaf = (window.QURAN_MUSHAF_KEY || "hafs").trim();
    formData.append("qari", selectedQari || "alhudhaify");
    formData.append("mushaf", selectedMushaf || "hafs");

    try {
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
      } catch (parseError) {
        if (analysisBox) {
          analysisBox.innerHTML = `
            <div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">
              السيرفر أعاد استجابة غير مفهومة
            </div>
          `;
        }
        console.error("Non-JSON response:", rawText);
        return;
      }

      if (!response.ok) {
        if (analysisBox) {
          analysisBox.innerHTML = `
            <div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">
              ${data.error || "Request failed"}
            </div>
          `;
        }
        return;
      }

      if (expectedTextBox) {
        expectedTextBox.textContent = data.expected_text || "";
      }

      if (recognizedTextBox) {
        recognizedTextBox.textContent = data.recognized_text || "";
      }

      renderAnalysis(data.comparison);
      if (window.WirdAnalytics && typeof window.WirdAnalytics.track === "function") {
        window.WirdAnalytics.track("recitation_correction", {
          surah: currentAyah.surahNumber,
          ayah: currentAyah.ayahNumber,
          score: data.score || 0,
          is_correct: !!data.is_correct,
        });
      }
    } catch (error) {
      if (analysisBox) {
        analysisBox.innerHTML = `
          <div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700">
            Network or server error
          </div>
        `;
      }
      console.error("Recitation correction request failed:", error);
    }
  }

  async function startRecording() {
    try {
      if (!currentAyah || !currentAyah.surahNumber || !currentAyah.ayahNumber) {
        if (analysisBox) {
          analysisBox.innerHTML =
            '<div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700 font-semibold">اختر آية أولًا</div>';
        }
        return;
      }

      if (analysisBox) {
        analysisBox.innerHTML =
          '<div class="rounded-xl border border-sky-200 bg-sky-50 p-3 text-sky-700 font-semibold">جاري التسجيل...</div>';
      }

      audioChunks = [];
      currentStream = await navigator.mediaDevices.getUserMedia({ audio: true });
      mediaRecorder = new MediaRecorder(currentStream);

      mediaRecorder.ondataavailable = function (event) {
        if (event.data && event.data.size > 0) {
          audioChunks.push(event.data);
        }
      };

      mediaRecorder.onstop = async function () {
        const audioBlob = new Blob(audioChunks, { type: "audio/webm" });
        stopTracks();
        await sendAudioToServer(audioBlob);
        document.dispatchEvent(new CustomEvent("hifz-recitation-stop"));
      };

      mediaRecorder.start();
    } catch (error) {
      stopTracks();

      if (analysisBox) {
        analysisBox.innerHTML =
          '<div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700 font-semibold">فشل الوصول إلى الميكروفون</div>';
      }

      console.error("Microphone access failed:", error);
    }
  }

  function stopRecording() {
    if (mediaRecorder && mediaRecorder.state !== "inactive") {
      mediaRecorder.stop();
      return;
    }

    stopTracks();
  }

  document.addEventListener("click", async function (event) {
    const target = event.target.closest("[data-surah][data-ayah]");

    if (!target) return;

    const ayahData = resolveAyahFromElement(target);

    if (!ayahData) return;

    await activateRecitationCorrectionForAyah(ayahData);
  });

  window.addEventListener("hifz-ayah-selected", async function (event) {
    const detail = event.detail || {};

    await activateRecitationCorrectionForAyah({
      surahNumber: detail.surahNumber || detail.surah || "",
      ayahNumber: detail.ayahNumber || detail.ayah || "",
      page: detail.page || detail.pageNumber || "",
      text: detail.text || "",
    });
  });

  window.addEventListener("hifz-open-recitation-correction", async function () {
    const ayahData = resolveCurrentAyah();

    if (!ayahData) {
      if (analysisBox) {
        analysisBox.innerHTML =
          '<div class="rounded-xl border border-red-200 bg-red-50 p-3 text-red-700 font-semibold">اختر آية أولًا ثم ابدأ التصحيح</div>';
      }
      hideCorrectionBar();
      return;
    }

    await activateRecitationCorrectionForAyah(ayahData);
  });

  if (startBtn) {
    startBtn.addEventListener("click", startRecording);
  }

  if (stopBtn) {
    stopBtn.addEventListener("click", stopRecording);
  }
});