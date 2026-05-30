(function () {
  if (window.__hifzHideAyahsInitialized) return;
  window.__hifzHideAyahsInitialized = true;

  let selectedKey = null;
  let activeAudioKey = null;

  function getArea() {
    return document.getElementById("mushafArea");
  }

  function getAyahKeyFromElement(el) {
    if (!el) return null;

    const box = el.closest(".ayah-box");
    if (!box) return null;

    const page = box.dataset.page || "";
    const surah = box.dataset.surah || "";
    const ayah = box.dataset.ayah || "";

    if (!page || !surah || !ayah) return null;
    return `${page}|${surah}|${ayah}`;
  }

  function getBoxFromElement(el) {
    if (!el || typeof el.closest !== "function") return null;
    return el.closest(".ayah-box");
  }

  function getOrCreateMaskLayer(pageWrapper) {
    if (!pageWrapper) return null;

    let layer = pageWrapper.querySelector(".hifz-mask-layer");
    if (layer) return layer;

    layer = document.createElement("div");
    layer.className = "hifz-mask-layer";
    pageWrapper.appendChild(layer);

    return layer;
  }

  function clearMaskLayer(pageWrapper) {
    if (!pageWrapper) return;
    const layer = pageWrapper.querySelector(".hifz-mask-layer");
    if (layer) {
      layer.innerHTML = "";
    }
  }

  function buildRectsForPage(pageNumber) {
    const svg = document.querySelector(`.ayah-svg[data-page="${pageNumber}"]`);
    if (!svg) return new Map();

    const groups = new Map();

    svg.querySelectorAll(".ayah-polygon").forEach((node) => {
      const surah = node.getAttribute("data-surah") || "";
      const ayah = node.getAttribute("data-ayah") || "";
      const page = node.getAttribute("data-page") || String(pageNumber);

      if (!surah || !ayah || !page) return;

      const key = `${page}|${surah}|${ayah}`;
      if (!groups.has(key)) {
        groups.set(key, []);
      }

      groups.get(key).push({
        x: parseFloat(node.getAttribute("x") || "0"),
        y: parseFloat(node.getAttribute("y") || "0"),
        width: parseFloat(node.getAttribute("width") || "0"),
        height: parseFloat(node.getAttribute("height") || "0"),
      });
    });

    return groups;
  }

  function refreshMaskPiecesByKey(key) {
    if (!key) return;

    document
      .querySelectorAll(`.hifz-mask-piece[data-key="${CSS.escape(key)}"]`)
      .forEach((piece) => {
        const isSelected = selectedKey === key;
        const isAudioActive = activeAudioKey === key;

        piece.classList.toggle("is-revealed", isSelected || isAudioActive);

        if (piece.classList.contains("is-revealed")) {
          piece.classList.remove("is-hover");
        }
      });
  }

  function renderMasksForPage(pageNumber) {
    const layerHost = document.querySelector(`.ayah-layer[data-page="${pageNumber}"]`);
    if (!layerHost) return;

    const pageWrapper = layerHost.parentElement;
    if (!pageWrapper) return;

    clearMaskLayer(pageWrapper);

    const maskLayer = getOrCreateMaskLayer(pageWrapper);
    if (!maskLayer) return;

    const groups = buildRectsForPage(pageNumber);
    const fragment = document.createDocumentFragment();

    groups.forEach((rects, key) => {
      rects.forEach((rect) => {
        const piece = document.createElement("div");
        piece.className = "hifz-mask-piece";
        piece.dataset.key = key;
        piece.style.left = `${rect.x}%`;
        piece.style.top = `${rect.y}%`;
        piece.style.width = `${rect.width}%`;
        piece.style.height = `${rect.height}%`;

        const isSelected = selectedKey === key;
        const isAudioActive = activeAudioKey === key;

        if (isSelected || isAudioActive) {
          piece.classList.add("is-revealed");
        }

        fragment.appendChild(piece);
      });
    });

    maskLayer.appendChild(fragment);
  }

  function renderAllMasks() {
    document.querySelectorAll(".ayah-layer[data-page]").forEach((layer) => {
      const pageNumber = layer.getAttribute("data-page");
      if (pageNumber) {
        renderMasksForPage(pageNumber);
      }
    });
  }

  function setHoverState(key, isHover) {
    if (!key) return;

    document
      .querySelectorAll(`.hifz-mask-piece[data-key="${CSS.escape(key)}"]`)
      .forEach((node) => {
        const isSelected = selectedKey === key;
        const isAudioActive = activeAudioKey === key;
        node.classList.toggle("is-hover", isHover && !isSelected && !isAudioActive);
      });
  }

  function selectOnlyReveal(key) {
    const prevKey = selectedKey;
    selectedKey = key || null;

    if (prevKey) {
      refreshMaskPiecesByKey(prevKey);
    }

    if (selectedKey) {
      refreshMaskPiecesByKey(selectedKey);
    }
  }

  function clearSelectedReveal() {
    const prevKey = selectedKey;
    selectedKey = null;

    if (prevKey) {
      refreshMaskPiecesByKey(prevKey);
    }
  }

  function getCurrentAudioKey() {
    const item = window.currentAyahItem;
    if (!item) return null;

    const page = item.page || item.page_number || "";
    const surah = item.surah || item.surah_number || "";
    const ayah = item.ayah || item.ayah_number || "";

    if (!page || !surah || !ayah) return null;
    return `${page}|${surah}|${ayah}`;
  }

  function syncActiveAudioReveal() {
    const nextKey = getCurrentAudioKey();
    if (nextKey === activeAudioKey) return;

    const prevKey = activeAudioKey;
    activeAudioKey = nextKey;

    if (prevKey) {
      refreshMaskPiecesByKey(prevKey);
    }

    if (activeAudioKey) {
      refreshMaskPiecesByKey(activeAudioKey);
    }
  }

  function syncHideModeState() {
    const area = getArea();
    if (!area) return;
    let enabled = true;
    try {
      const saved = localStorage.getItem("hifz_hide_ayahs_enabled");
      if (saved === "0" || saved === "false" || saved === "off") {
        enabled = false;
      }
    } catch (err) {}
    area.classList.toggle("hifz-hide-mode", enabled);
    area.dataset.hifzHideMode = enabled ? "always" : "off";
  }

  window.hifzSelectAyahRevealByKey = function (key) {
    selectOnlyReveal(key);
  };

  window.hifzClearAyahReveal = function () {
    clearSelectedReveal();
  };

  document.addEventListener("DOMContentLoaded", function () {
    syncHideModeState();
    syncActiveAudioReveal();
    renderAllMasks();
  });

  document.addEventListener("quran-positions-rendered", function (event) {
    syncHideModeState();
    syncActiveAudioReveal();

    const page = event.detail && event.detail.page;
    if (page) {
      renderMasksForPage(page);
    } else {
      renderAllMasks();
    }
  });

  document.addEventListener("quran-page-flipped", function () {
    syncHideModeState();

    requestAnimationFrame(() => {
      syncActiveAudioReveal();
      renderAllMasks();
    });
  });

  document.addEventListener("mouseover", function (event) {
    const box = getBoxFromElement(event.target);
    if (!box) return;

    const key = getAyahKeyFromElement(box);
    setHoverState(key, true);
  });

  document.addEventListener("mouseout", function (event) {
    const box = getBoxFromElement(event.target);
    if (!box) return;

    const key = getAyahKeyFromElement(box);
    setHoverState(key, false);
  });

  const audio = document.getElementById("ayahAudio");

  if (audio) {
    audio.addEventListener("play", syncActiveAudioReveal);
    audio.addEventListener("playing", syncActiveAudioReveal);
    audio.addEventListener("pause", syncActiveAudioReveal);
    audio.addEventListener("ended", syncActiveAudioReveal);
    audio.addEventListener("timeupdate", syncActiveAudioReveal);
  }

  if (typeof window.setCurrentAyahItem === "function") {
    const originalSetCurrentAyahItem = window.setCurrentAyahItem;
    window.setCurrentAyahItem = function () {
      const result = originalSetCurrentAyahItem.apply(this, arguments);
      syncActiveAudioReveal();
      return result;
    };
  }

  setInterval(syncActiveAudioReveal, 150);
})();