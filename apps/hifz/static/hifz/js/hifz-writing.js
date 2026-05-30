(function () {
  if (!window.HIFZ_MODE) return;
  if (window.__hifzWritingInitialized) return;
  window.__hifzWritingInitialized = true;

  let hifzWritingPad = null;
  let hifzWritingPadKey = null;
  let hifzWritingAllVisible = false;
  const hifzAllWritingPads = new Map();
  const HIFZ_WRITING_STORAGE_PREFIX = "hifz_writing_practice_";
  const HIFZ_WRITING_FONT_SIZE_SUFFIX = "__font_size";

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
  function isWritingTechniqueActive() {
    const area = document.getElementById("mushafArea");
    if (area && area.dataset.hifzWritingMode === "on") {
      return true;
    }

    try {
      return localStorage.getItem("hifz_technique_mode") === "writing";
    } catch (err) {
      return false;
    }
  }

  function getSortedAyahAnchors(ayahData) {
    if (!ayahData) return [];

    return Array.from(document.querySelectorAll(
      `.ayah-polygon[data-page="${CSS.escape(String(ayahData.page || ""))}"][data-surah="${CSS.escape(String(ayahData.surah || ""))}"][data-ayah="${CSS.escape(String(ayahData.ayah || ""))}"]`
    )).filter(function (item) {
      const rect = item.getBoundingClientRect();
      return rect.width > 2 && rect.height > 2;
    }).sort(function (a, b) {
      const ar = a.getBoundingClientRect();
      const br = b.getBoundingClientRect();
      if (Math.abs(ar.top - br.top) > 6) return ar.top - br.top;
      return br.left - ar.left;
    });
  }

  function getWritingSegmentIndex(anchor, ayahData) {
    if (!anchor || !ayahData) return 0;

    const anchors = getSortedAyahAnchors(ayahData);
    const index = anchors.indexOf(anchor);
    if (index >= 0) return index;

    const anchorRect = anchor.getBoundingClientRect && anchor.getBoundingClientRect();
    if (!anchorRect) return 0;

    let bestIndex = 0;
    let bestScore = Number.POSITIVE_INFINITY;
    const anchorCenterX = anchorRect.left + anchorRect.width / 2;
    const anchorCenterY = anchorRect.top + anchorRect.height / 2;

    anchors.forEach(function (item, itemIndex) {
      const rect = item.getBoundingClientRect();
      const centerX = rect.left + rect.width / 2;
      const centerY = rect.top + rect.height / 2;
      const score = Math.abs(centerX - anchorCenterX) + Math.abs(centerY - anchorCenterY);
      if (score < bestScore) {
        bestScore = score;
        bestIndex = itemIndex;
      }
    });

    return bestIndex;
  }

  function getWritingStorageKey(ayahData, anchor) {
    const key = buildAyahKey(ayahData);
    if (!key) return "";
    return `${HIFZ_WRITING_STORAGE_PREFIX}${key}|line:${getWritingSegmentIndex(anchor, ayahData)}`;
  }

  function getLegacyWritingStorageKey(ayahData) {
    const key = buildAyahKey(ayahData);
    return key ? `${HIFZ_WRITING_STORAGE_PREFIX}${key}` : "";
  }

  function readWritingValue(storageKey, ayahData, anchor) {
    try {
      const saved = localStorage.getItem(storageKey);
      if (saved !== null) return saved;

      if (getWritingSegmentIndex(anchor, ayahData) === 0) {
        return localStorage.getItem(getLegacyWritingStorageKey(ayahData)) || "";
      }
    } catch (err) {}

    return "";
  }

  function getWritingFontSizeStorageKey(storageKey) {
    return storageKey ? `${storageKey}${HIFZ_WRITING_FONT_SIZE_SUFFIX}` : "";
  }

  function readStoredWritingFontSize(storageKey) {
    try {
      const value = parseFloat(localStorage.getItem(getWritingFontSizeStorageKey(storageKey)) || "");
      return Number.isNaN(value) || value <= 0 ? null : value;
    } catch (err) {
      return null;
    }
  }

  function storeWritingFontSize(storageKey, fontSize) {
    if (!storageKey || !fontSize) return;
    try {
      localStorage.setItem(getWritingFontSizeStorageKey(storageKey), String(fontSize));
    } catch (err) {}
  }

  function removeWritingPad() {
    if (!hifzWritingPad) return;
    hifzWritingPad.remove();
    hifzWritingPad = null;
    hifzWritingPadKey = null;
  }

  function getAyahAnchor(element) {
    if (!element) return null;
    return element.classList && element.classList.contains("ayah-polygon")
      ? element
      : element.querySelector(".ayah-polygon") || element;
  }

  function getWritingPadHost(anchor, ayahData) {
    if (!anchor) return null;

    const layer = anchor.closest && anchor.closest(".ayah-layer");
    if (layer && layer.parentElement) return layer.parentElement;

    const page = (ayahData && ayahData.page) || anchor.dataset.page || "";
    if (page) {
      const pageLayer = document.querySelector(`.ayah-layer[data-page="${CSS.escape(String(page))}"]`);
      if (pageLayer && pageLayer.parentElement) return pageLayer.parentElement;
    }

    const pageContent = anchor.closest && anchor.closest(".page-content");
    if (pageContent) {
      return pageContent.querySelector(".mushaf-page-img")?.parentElement || pageContent;
    }

    return null;
  }

  function positionWritingPad(element, ayahData) {
    if (!hifzWritingPad || !element) return;

    const anchor = getAyahAnchor(element);
    positionWritingPadElement(hifzWritingPad, anchor, ayahData);
  }

  function showWritingPadForElement(element, ayahData) {
    if (!element || !ayahData || !isWritingTechniqueActive()) {
      removeWritingPad();
      return;
    }

    const anchor = getAyahAnchor(element);
    if (!anchor) return;
    const anchorAyahData = buildAyahDataFromElement(anchor) || ayahData;
    const storageKey = getWritingStorageKey(anchorAyahData, anchor);
    if (!storageKey) return;

    if (!hifzWritingPad) {
      hifzWritingPad = createWritingPadElement("hifz-writing-pad", "الكتابة فوق الآية");
      hifzWritingPad.id = "hifzWritingPad";
      hifzWritingPad.addEventListener("input", function () {
        if (!hifzWritingPadKey) return;
        try {
          localStorage.setItem(hifzWritingPadKey, hifzWritingPad.value);
        } catch (err) {}
        removeDisplayedWritingPadForKey(hifzWritingPadKey);
      });
    }

    if (hifzWritingPadKey !== storageKey) {
      hifzWritingPadKey = storageKey;
      hifzWritingPad.value = readWritingValue(storageKey, anchorAyahData, anchor);
    }

    removeDisplayedWritingPadForKey(storageKey);
    positionWritingPad(element, anchorAyahData);
    hifzWritingPad.classList.remove("hidden");
    requestAnimationFrame(function () {
      if (hifzWritingPad) {
        hifzWritingPad.focus({ preventScroll: true });
      }
    });
  }


  function createWritingPadElement(className, label) {
    const pad = document.createElement("textarea");
    pad.className = className;
    pad.dir = "rtl";
    pad.rows = 1;
    pad.spellcheck = false;
    pad.autocomplete = "off";
    pad.placeholder = "";
    pad.setAttribute("aria-label", label);
    pad.addEventListener("click", function (event) {
      event.stopPropagation();
    });
    pad.addEventListener("pointerdown", function (event) {
      event.stopPropagation();
    });
    pad.addEventListener("keydown", function (event) {
      if (event.key !== "Enter") return;
      event.preventDefault();
      focusSiblingWritingPad(pad, event.shiftKey ? -1 : 1);
    });
    return pad;
  }

  function getWritingPadFontSizeFromRect(rect) {
    const height = Math.max(rect.height || 0, 1);
    return Math.max(8, Math.min(38, height * 0.73));
  }

  function getWritingPadFontSize(rect, storageKey) {
    const storedSize = readStoredWritingFontSize(storageKey);
    return storedSize || getWritingPadFontSizeFromRect(rect);
  }

  function positionWritingPadElement(pad, anchor, ayahData) {
    if (!pad || !anchor || typeof anchor.getBoundingClientRect !== "function") return;

    const host = getWritingPadHost(anchor, ayahData);
    if (!host || typeof host.getBoundingClientRect !== "function") return;

    if (pad.parentElement !== host) {
      host.appendChild(pad);
    }

    const rect = anchor.getBoundingClientRect();
    const hostRect = host.getBoundingClientRect();

    pad.style.left = `${Math.max(0, rect.left - hostRect.left)}px`;
    pad.style.top = `${Math.max(0, rect.top - hostRect.top)}px`;
    pad.style.width = `${Math.max(1, Math.min(hostRect.width, rect.width))}px`;
    pad.style.height = `${Math.max(1, rect.height)}px`;
    const storageKey = pad.dataset.storageKey || (pad === hifzWritingPad ? hifzWritingPadKey : "");
    const fontSize = getWritingPadFontSize(rect, storageKey);
    pad.style.setProperty("--hifz-writing-font-size", `${fontSize}px`);

    if (pad === hifzWritingPad) {
      storeWritingFontSize(storageKey, fontSize);
    }
  }

  function focusSiblingWritingPad(currentPad, direction) {
    const pads = Array.from(document.querySelectorAll("textarea.hifz-writing-pad:not(.hifz-writing-pad-all)"))
      .filter(function (pad) {
        return pad.offsetParent !== null;
      })
      .sort(function (a, b) {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        if (Math.abs(ar.top - br.top) > 8) return ar.top - br.top;
        return br.left - ar.left;
      });

    const index = pads.indexOf(currentPad);
    if (index === -1) return;

    const nextPad = pads[index + direction];
    if (!nextPad) return;

    nextPad.focus({ preventScroll: true });
    const len = nextPad.value.length;
    try {
      nextPad.setSelectionRange(len, len);
    } catch (err) {}
  }

  function getAllWritingAnchors() {
    return Array.from(document.querySelectorAll(".ayah-polygon"))
      .filter(function (anchor) {
        if (!anchor.dataset || !anchor.dataset.page || !anchor.dataset.surah || !anchor.dataset.ayah) return false;
        const rect = anchor.getBoundingClientRect();
        return rect.width > 3 && rect.height > 3;
      })
      .sort(function (a, b) {
        const ar = a.getBoundingClientRect();
        const br = b.getBoundingClientRect();
        if (Math.abs(ar.top - br.top) > 8) return ar.top - br.top;
        return br.left - ar.left;
      });
  }

  function renderAllWritingPads() {
    if (!hifzWritingAllVisible || !isWritingTechniqueActive()) return;

    const seen = new Set();
    getAllWritingAnchors().forEach(function (anchor) {
      const ayahData = buildAyahDataFromElement(anchor);
      const storageKey = getWritingStorageKey(ayahData, anchor);
      if (!storageKey || seen.has(storageKey)) return;

      const value = readWritingValue(storageKey, ayahData, anchor);
      if (!value) return;

      const activePadVisible = hifzWritingPad &&
        hifzWritingPadKey === storageKey &&
        !hifzWritingPad.classList.contains("hidden") &&
        hifzWritingPad.offsetParent !== null;

      if (activePadVisible) {
        removeDisplayedWritingPadForKey(storageKey);
        return;
      }

      seen.add(storageKey);

      let pad = hifzAllWritingPads.get(storageKey);
      if (!pad) {
        pad = createWritingPadElement("hifz-writing-pad hifz-writing-pad-all", "عرض الكتابة فوق الآية");
        pad.id = "";
        pad.readOnly = true;
        pad.tabIndex = -1;
        pad.dataset.storageKey = storageKey;
        hifzAllWritingPads.set(storageKey, pad);
      }

      pad.value = value;
      pad.dataset.page = String(ayahData.page || "");
      pad.dataset.surah = String(ayahData.surah || "");
      pad.dataset.ayah = String(ayahData.ayah || "");
      positionWritingPadElement(pad, anchor, ayahData);
      pad.classList.remove("hidden");
    });

    hifzAllWritingPads.forEach(function (pad, key) {
      if (!seen.has(key)) {
        pad.remove();
        hifzAllWritingPads.delete(key);
      }
    });
  }

  function removeAllWritingPads() {
    hifzAllWritingPads.forEach(function (pad) {
      pad.remove();
    });
    hifzAllWritingPads.clear();
  }

  function removeDisplayedWritingPadForKey(storageKey) {
    if (!storageKey) return;

    const pad = hifzAllWritingPads.get(storageKey);
    if (!pad) return;

    pad.remove();
    hifzAllWritingPads.delete(storageKey);
  }

  function setAllWritingVisible(enabled) {
    hifzWritingAllVisible = !!enabled;
    const button = document.getElementById("hifzWritingShowAllBtn");
    if (button) {
      button.classList.toggle("is-active", hifzWritingAllVisible);
      button.setAttribute("aria-pressed", hifzWritingAllVisible ? "true" : "false");
      button.setAttribute("title", hifzWritingAllVisible ? "إخفاء الكتابة من الكل" : "إظهار الكتابة للكل");
      button.setAttribute("aria-label", hifzWritingAllVisible ? "إخفاء الكتابة من الكل" : "إظهار الكتابة للكل");
      button.innerHTML = hifzWritingAllVisible ? '<i class="bi bi-eye-slash-fill"></i>' : '<i class="bi bi-eye-fill"></i>';
    }

    if (hifzWritingAllVisible) {
      renderAllWritingPads();
    } else {
      removeAllWritingPads();
    }
  }

  function clearAllWritingPractice() {
    try {
      for (let i = localStorage.length - 1; i >= 0; i -= 1) {
        const key = localStorage.key(i);
      if (key && key.startsWith(HIFZ_WRITING_STORAGE_PREFIX)) {
        localStorage.removeItem(key);
      }
      }
    } catch (err) {}

    if (hifzWritingPad) hifzWritingPad.value = "";
    removeAllWritingPads();
  }

  function syncWritingToolsBarVisibility() {
    const bar = document.getElementById("hifzWritingToolsBar");
    if (!bar) return;

    const enabled = isWritingTechniqueActive();
    bar.classList.toggle("hidden", !enabled);
    bar.setAttribute("aria-hidden", enabled ? "false" : "true");
  }

  function initWritingToolsBar() {
    syncWritingToolsBarVisibility();
    const clearBtn = document.getElementById("hifzWritingClearAllBtn");
    const showAllBtn = document.getElementById("hifzWritingShowAllBtn");

    if (clearBtn && !clearBtn.dataset.hifzBound) {
      clearBtn.dataset.hifzBound = "1";
      clearBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        clearAllWritingPractice();
      });
    }

    if (showAllBtn && !showAllBtn.dataset.hifzBound) {
      showAllBtn.dataset.hifzBound = "1";
      showAllBtn.addEventListener("click", function (event) {
        event.preventDefault();
        event.stopPropagation();
        setAllWritingVisible(!hifzWritingAllVisible);
      });
    }
  }


  window.HifzWriting = {
    isActive: isWritingTechniqueActive,
    showForElement: showWritingPadForElement,
    removeActive: removeWritingPad,
    renderAll: renderAllWritingPads,
    setAllVisible: setAllWritingVisible,
    isAllVisible: function () { return hifzWritingAllVisible; },
    syncToolsBarVisibility: syncWritingToolsBarVisibility,
    initToolsBar: initWritingToolsBar,
    clearAll: clearAllWritingPractice,
  };

  initWritingToolsBar();

  document.addEventListener("quran-page-flipped", function () {
    setTimeout(renderAllWritingPads, 120);
  });

  document.addEventListener("hifz-technique-changed", function (event) {
    const mode = event.detail && event.detail.mode;
    syncWritingToolsBarVisibility();

    if (mode === "writing") {
      initWritingToolsBar();
      if (hifzWritingAllVisible) {
        renderAllWritingPads();
      }
      return;
    }

    setAllWritingVisible(false);
    removeWritingPad();
  });

  document.addEventListener("fullscreenchange", function () {
    setTimeout(renderAllWritingPads, 160);
  });

  window.addEventListener("resize", function () {
    setTimeout(renderAllWritingPads, 120);
  });
})();
