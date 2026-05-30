(function () {
  if (window.__hifzThematicSegmentationInitialized) return;
  window.__hifzThematicSegmentationInitialized = true;

  const STORAGE_KEY = "hifz_thematic_segment_enabled";

  function getArea() {
    return document.getElementById("mushafArea");
  }

  function readThematicData() {
    const el = document.getElementById("hifzThematicAyahsData");
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

  function getAyahKey(node) {
    if (!node) return "";

    const surah = node.dataset ? node.dataset.surah : node.getAttribute("data-surah");
    const ayah = node.dataset ? node.dataset.ayah : node.getAttribute("data-ayah");

    if (!surah || !ayah) return "";
    return `${surah}:${ayah}`;
  }

  function applyThematicToNode(node) {
    const key = getAyahKey(node);
    const item = key ? thematicMap[key] : null;

    if (!item) {
      node.removeAttribute("data-thematic-topic");
      node.removeAttribute("data-thematic-title");
      node.style.removeProperty("--hifz-topic-color");
      node.style.removeProperty("--hifz-topic-bg");
      node.style.removeProperty("--hifz-topic-border");
      node.style.removeProperty("--hifz-topic-fill");
      return;
    }

    const color = normalizeHex(item.color_hex);
    const title = item.topic_ar || item.topic_id || "";

    node.setAttribute("data-thematic-topic", String(item.topic_id || ""));
    node.setAttribute("data-thematic-title", title);
    node.style.setProperty("--hifz-topic-color", color);
    node.style.setProperty("--hifz-topic-bg", hexToRgba(color, 0.20));
    node.style.setProperty("--hifz-topic-border", hexToRgba(color, 0.55));
    node.style.setProperty("--hifz-topic-fill", hexToRgba(color, 0.28));
  }

  function applyThematicColors() {
    document.querySelectorAll(".ayah-box, .ayah-polygon").forEach(applyThematicToNode);
  }

  function setSegmentEnabled(enabled) {
    const area = getArea();
    if (area) {
      area.classList.toggle("hifz-segment-mode", !!enabled);
      area.dataset.hifzSegmentMode = enabled ? "on" : "off";
    }

    document.querySelectorAll("#toggleSegment, #hifzMobileSegmentToggle").forEach((input) => {
      input.checked = !!enabled;
    });

    const mobileBtn = document.getElementById("hifzMobileSegmentBtn");
    if (mobileBtn) {
      mobileBtn.classList.toggle("is-active", !!enabled);
      mobileBtn.setAttribute("aria-pressed", enabled ? "true" : "false");
    }

    try {
      localStorage.setItem(STORAGE_KEY, enabled ? "1" : "0");
    } catch (err) {}
  }

  function getSavedSegmentEnabled() {
    try {
      const saved = localStorage.getItem(STORAGE_KEY);
      return saved === "1" || saved === "true" || saved === "on";
    } catch (err) {
      return false;
    }
  }

  function bindControls() {
    const checkbox = document.getElementById("toggleSegment");
    if (checkbox) {
      checkbox.addEventListener("change", function () {
        setSegmentEnabled(this.checked);
      });
    }

  }

  document.addEventListener("DOMContentLoaded", function () {
    applyThematicColors();
    bindControls();
    setSegmentEnabled(getSavedSegmentEnabled());
  });

  document.addEventListener("quran-positions-rendered", function () {
    applyThematicColors();
    setSegmentEnabled(getArea() && getArea().classList.contains("hifz-segment-mode"));
  });

  document.addEventListener("quran-page-flipped", function () {
    requestAnimationFrame(applyThematicColors);
  });

  window.hifzRefreshThematicSegmentation = function () {
    applyThematicColors();
    setSegmentEnabled(getArea() && getArea().classList.contains("hifz-segment-mode"));
  };
})();
