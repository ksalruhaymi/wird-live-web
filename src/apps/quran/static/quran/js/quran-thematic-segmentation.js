(function () {
  if (window.__quranThematicSegmentationInitialized) return;
  window.__quranThematicSegmentationInitialized = true;

  const STORAGE_KEY = "quran_thematic_segment_enabled";
  let hoveredAyahKey = "";

  function isArabicEnabled() {
    return window.QURAN_ARABIC_FEATURES_ENABLED === true;
  }

  function $(id) {
    return document.getElementById(id);
  }

  function getArea() {
    return $("mushafArea");
  }

  function readThematicData() {
    const el = $("quranThematicAyahsData");
    if (!el) return {};

    try {
      const data = JSON.parse(el.textContent || "{}");
      return data && typeof data === "object" ? data : {};
    } catch (err) {
      return {};
    }
  }

  const thematicMap = readThematicData();

  function normalizeHex(hex) {
    const value = String(hex || "").trim();
    if (/^#[0-9a-fA-F]{6}$/.test(value)) return value;
    if (/^#[0-9a-fA-F]{3}$/.test(value)) {
      return "#" + value.slice(1).split("").map((ch) => ch + ch).join("");
    }
    return "#f59e0b";
  }

  function hexToRgba(hex, alpha) {
    const normalized = normalizeHex(hex).replace("#", "");
    const r = parseInt(normalized.slice(0, 2), 16);
    const g = parseInt(normalized.slice(2, 4), 16);
    const b = parseInt(normalized.slice(4, 6), 16);
    return `rgba(${r}, ${g}, ${b}, ${alpha})`;
  }

  function escapeHtml(value) {
    return String(value || "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;")
      .replace(/'/g, "&#39;");
  }

  function getAyahKeyFromParts(surah, ayah) {
    if (!surah || !ayah) return "";
    return `${surah}:${ayah}`;
  }

  function getAyahKeyFromNode(node) {
    if (!node) return "";
    const surah = node.dataset ? node.dataset.surah : node.getAttribute("data-surah");
    const ayah = node.dataset ? node.dataset.ayah : node.getAttribute("data-ayah");
    return getAyahKeyFromParts(surah, ayah);
  }

  function getThematicItem(surah, ayah) {
    return thematicMap[getAyahKeyFromParts(surah, ayah)] || null;
  }

  function applyThematicToNode(node) {
    const item = thematicMap[getAyahKeyFromNode(node)];

    if (!item) {
      node.removeAttribute("data-quran-thematic-topic");
      node.removeAttribute("data-quran-thematic-title");
      node.style.removeProperty("--quran-topic-color");
      node.style.removeProperty("--quran-topic-bg");
      node.style.removeProperty("--quran-topic-border");
      node.style.removeProperty("--quran-topic-fill");
      node.style.removeProperty("--quran-topic-shadow");
      return;
    }

    const color = normalizeHex(item.color_hex);
    node.setAttribute("data-quran-thematic-topic", String(item.topic_id || ""));
    node.setAttribute("data-quran-thematic-title", item.topic_ar || "");
    node.style.setProperty("--quran-topic-color", color);
    node.style.setProperty("--quran-topic-bg", hexToRgba(color, 0.18));
    node.style.setProperty("--quran-topic-border", hexToRgba(color, 0.55));
    node.style.setProperty("--quran-topic-fill", hexToRgba(color, 0.24));
    node.style.setProperty("--quran-topic-shadow", hexToRgba(color, 0.36));
  }

  function applyThematicColors() {
    document.querySelectorAll(".ayah-box, .ayah-polygon").forEach(applyThematicToNode);
  }

  function renderEmptyPanel() {
    const content = $("quranThematicContent");
    const swatch = $("quranThematicSwatch");
    if (swatch) swatch.style.backgroundColor = "#d1d5db";
    if (!content) return;
    content.innerHTML = `
      <div class="text-gray-400 text-center py-3">
        اختر آية لعرض موضوعها.
      </div>
    `;
  }

  function renderThematicPanel(item) {
    const content = $("quranThematicContent");
    const swatch = $("quranThematicSwatch");
    if (!content) return;

    if (!item) {
      renderEmptyPanel();
      return;
    }

    const color = normalizeHex(item.color_hex);
    if (swatch) swatch.style.backgroundColor = color;

    content.innerHTML = `
      <div class="rounded-lg px-3 py-2" style="background:${hexToRgba(color, 0.10)};border:1px solid ${hexToRgba(color, 0.28)}">
        <div class="text-sm font-bold text-gray-900">${escapeHtml(item.topic_ar)}</div>
        <div class="mt-1 text-xs leading-5 text-gray-700">${escapeHtml(item.topic_text || "")}</div>
      </div>
    `;
  }

  function updatePanelForAyah(surah, ayah) {
    if (!isEnabled()) return;
    renderThematicPanel(getThematicItem(surah, ayah));
  }

  function isEnabled() {
    const area = getArea();
    return !!(area && area.classList.contains("quran-thematic-mode"));
  }

  function setEnabled(enabled) {
    if (!isArabicEnabled()) {
      enabled = false;
    }

    const area = getArea();
    const panel = $("quranThematicPanel");
    const checkbox = $("quranThematicToggle");
    const label = $("quranThematicToggleLabel");

    if (area) {
      area.classList.toggle("quran-thematic-mode", !!enabled);
      area.dataset.quranThematicMode = enabled ? "on" : "off";
    }
    if (panel) panel.classList.toggle("hidden", !enabled);
    if (checkbox) checkbox.checked = !!enabled;
    if (label) {
      label.textContent = enabled
        ? (window.TRANSLATIONS && window.TRANSLATIONS.hideThematicSegmentation) || "إخفاء التقسيم الموضوعي"
        : (window.TRANSLATIONS && window.TRANSLATIONS.showThematicSegmentation) || "إظهار التقسيم الموضوعي";
    }

    renderEmptyPanel();

    try {
      localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0");
    } catch (err) {}
  }

  function getSavedEnabled() {
    if (!isArabicEnabled()) return false;

    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      if (saved === null) return false;
      return saved === "1" || saved === "true" || saved === "on";
    } catch (err) {
      return false;
    }
  }

  function getTarget(eventTarget) {
    if (!eventTarget || typeof eventTarget.closest !== "function") return null;
    return eventTarget.closest(".ayah-box") || eventTarget.closest(".ayah-polygon");
  }

  function bindControls() {
    const checkbox = $("quranThematicToggle");
    if (checkbox) {
      checkbox.disabled = !isArabicEnabled();
      checkbox.addEventListener("change", function () {
        if (!isArabicEnabled()) {
          this.checked = false;
          setEnabled(false);
          return;
        }
        setEnabled(this.checked);
      });
    }

    document.addEventListener("mouseover", function (event) {
      if (!isEnabled()) return;
      const target = getTarget(event.target);
      if (!target) return;

      const surah = target.dataset.surah || target.getAttribute("data-surah");
      const ayah = target.dataset.ayah || target.getAttribute("data-ayah");
      const key = getAyahKeyFromParts(surah, ayah);
      if (!key || key === hoveredAyahKey) return;

      hoveredAyahKey = key;
      updatePanelForAyah(surah, ayah);
    }, true);

    document.addEventListener("ayah-play", function (event) {
      if (!isEnabled()) return;

      const detail = event.detail || {};
      const surah = detail.surah;
      const ayah = detail.ayah;
      const key = getAyahKeyFromParts(surah, ayah);

      if (!key) {
        hoveredAyahKey = "";
        renderEmptyPanel();
        return;
      }

      hoveredAyahKey = key;
      updatePanelForAyah(surah, ayah);
    });
  }

  document.addEventListener("DOMContentLoaded", function () {
    applyThematicColors();
    bindControls();
    setEnabled(getSavedEnabled());
  });

  document.addEventListener("quran-positions-rendered", function () {
    applyThematicColors();
  });

  document.addEventListener("quran-page-flipped", function () {
    requestAnimationFrame(applyThematicColors);
  });
})();