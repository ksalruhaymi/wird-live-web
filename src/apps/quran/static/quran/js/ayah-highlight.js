// static/quran/js/ayah-highlight.js

(function () {
  if (window.__ayahHighlightInitialized) return;
  window.__ayahHighlightInitialized = true;

  let currentHoverKey = null;

  function getInteractiveTarget(element) {
    if (!element || typeof element.closest !== "function") return null;
    return element.closest(".ayah-box");
  }

  function buildKey(target) {
    if (!target) return null;

    const page = target.dataset.page || "";
    const surah = target.dataset.surah || "";
    const ayah = target.dataset.ayah || "";

    if (!page || !surah || !ayah) return null;
    return `${page}|${surah}|${ayah}`;
  }

  function sameGroup(a, b) {
    const ta = getInteractiveTarget(a);
    const tb = getInteractiveTarget(b);
    if (!ta || !tb) return false;
    return buildKey(ta) === buildKey(tb);
  }

  function getPageWrapperFromBox(box) {
    if (!box) return null;
    return box.parentElement ? box.parentElement.parentElement : null;
  }

  function getOrCreateHoverLayer(pageWrapper) {
    if (!pageWrapper) return null;

    let layer = pageWrapper.querySelector(".ayah-hover-unified-layer");
    if (layer) return layer;

    layer = document.createElement("div");
    layer.className = "ayah-hover-unified-layer";
    pageWrapper.appendChild(layer);

    return layer;
  }

  function clearHoverLayer(pageWrapper) {
    if (!pageWrapper) return;
    const layer = pageWrapper.querySelector(".ayah-hover-unified-layer");
    if (layer) {
      layer.innerHTML = "";
    }
  }

  function clearAllHoverLayers() {
    document.querySelectorAll(".ayah-hover-unified-layer").forEach((layer) => {
      layer.innerHTML = "";
    });
    currentHoverKey = null;
  }

  function getMatchingPolygons(box) {
    if (!box) return [];

    const pageWrapper = getPageWrapperFromBox(box);
    if (!pageWrapper) return [];

    const svg = pageWrapper.querySelector("svg");
    if (!svg) return [];

    const surah = box.dataset.surah;
    const ayah = box.dataset.ayah;

    if (!surah || !ayah) return [];

    return Array.from(
      svg.querySelectorAll(
        `.ayah-polygon[data-surah="${surah}"][data-ayah="${ayah}"]`
      )
    );
  }

  function toRects(nodes) {
    return nodes
      .map((node) => ({
        x: parseFloat(node.getAttribute("x") || "0"),
        y: parseFloat(node.getAttribute("y") || "0"),
        width: parseFloat(node.getAttribute("width") || "0"),
        height: parseFloat(node.getAttribute("height") || "0"),
      }))
      .filter((r) => r.width > 0 && r.height > 0);
  }

  function nearlyEqual(a, b, eps = 0.15) {
    return Math.abs(a - b) <= eps;
  }

  function rectContains(a, b, eps = 0.15) {
    return (
      a.x <= b.x + eps &&
      a.y <= b.y + eps &&
      a.x + a.width >= b.x + b.width - eps &&
      a.y + a.height >= b.y + b.height - eps
    );
  }

  function uniqueRects(rects) {
    const result = [];

    rects.forEach((rect) => {
      const found = result.some((r) =>
        nearlyEqual(r.x, rect.x) &&
        nearlyEqual(r.y, rect.y) &&
        nearlyEqual(r.width, rect.width) &&
        nearlyEqual(r.height, rect.height)
      );

      if (!found) {
        result.push(rect);
      }
    });

    return result;
  }

  function removeContainedRects(rects) {
    return rects.filter((rect, i) => {
      return !rects.some((other, j) => {
        if (i === j) return false;
        if ((other.width * other.height) + 0.01 < (rect.width * rect.height)) return false;
        return rectContains(other, rect);
      });
    });
  }

  function mergeRectsByRow(rects) {
    const rowToleranceY = 0.35;
    const rowToleranceH = 0.35;
    const mergeGap = 0.20;

    const rows = [];

    rects
      .slice()
      .sort((a, b) => a.y - b.y || a.x - b.x)
      .forEach((rect) => {
        let row = rows.find((r) =>
          Math.abs(r.y - rect.y) <= rowToleranceY &&
          Math.abs(r.height - rect.height) <= rowToleranceH
        );

        if (!row) {
          row = {
            y: rect.y,
            height: rect.height,
            ranges: [],
          };
          rows.push(row);
        }

        row.ranges.push([rect.x, rect.x + rect.width]);
      });

    const merged = [];

    rows.forEach((row) => {
      row.ranges.sort((a, b) => a[0] - b[0]);

      const compact = [];
      row.ranges.forEach((range) => {
        if (!compact.length) {
          compact.push(range);
          return;
        }

        const last = compact[compact.length - 1];
        if (range[0] <= last[1] + mergeGap) {
          last[1] = Math.max(last[1], range[1]);
        } else {
          compact.push(range);
        }
      });

      compact.forEach(([start, end]) => {
        merged.push({
          x: start,
          y: row.y,
          width: Math.max(0, end - start),
          height: row.height,
        });
      });
    });

    return merged;
  }

  function renderUnifiedHover(box) {
    const pageWrapper = getPageWrapperFromBox(box);
    if (!pageWrapper) return;

    clearHoverLayer(pageWrapper);

    const polygons = getMatchingPolygons(box);
    if (!polygons.length) return;

    const rects = mergeRectsByRow(removeContainedRects(uniqueRects(toRects(polygons))));
    if (!rects.length) return;

    const layer = getOrCreateHoverLayer(pageWrapper);
    if (!layer) return;

    const area = document.getElementById("mushafArea");
    const thematicEnabled = area && area.classList.contains("quran-thematic-mode");
    const thematicBg = box.style.getPropertyValue("--quran-topic-bg");
    const thematicShadow = box.style.getPropertyValue("--quran-topic-shadow");
    const fragment = document.createDocumentFragment();

    rects.forEach((rect) => {
      const piece = document.createElement("div");
      piece.className = "ayah-hover-piece";
      if (thematicEnabled && thematicBg) {
        piece.classList.add("quran-thematic-hover");
        piece.style.background = thematicBg;
        if (thematicShadow) {
          piece.style.filter = `drop-shadow(0 0 6px ${thematicShadow})`;
        }
      }
      piece.style.left = `${rect.x}%`;
      piece.style.top = `${rect.y}%`;
      piece.style.width = `${rect.width}%`;
      piece.style.height = `${rect.height}%`;
      fragment.appendChild(piece);
    });

    layer.appendChild(fragment);
    currentHoverKey = buildKey(box);
  }

  function reapplyActiveHighlight() {
    const current = window.currentAyahItem;
    if (!current || current.surah == null || current.ayah == null) return;

    document.querySelectorAll(".ayah-polygon").forEach((r) => {
      r.classList.remove("ayah-active");
    });

    const activeRects = document.querySelectorAll(
      `.ayah-polygon[data-surah="${current.surah}"][data-ayah="${current.ayah}"]`
    );

    activeRects.forEach((r) => r.classList.add("ayah-active"));
  }

  document.addEventListener("mouseover", (event) => {
    const target = getInteractiveTarget(event.target);
    if (!target) return;

    if (sameGroup(target, event.relatedTarget)) return;

    renderUnifiedHover(target);
  });

  document.addEventListener("mouseout", (event) => {
    const target = getInteractiveTarget(event.target);
    if (!target) return;

    if (sameGroup(target, event.relatedTarget)) return;

    clearAllHoverLayers();
  });

  document.addEventListener("click", (event) => {
    const target = getInteractiveTarget(event.target);
    if (!target) {
      clearAllHoverLayers();
    }
  });

  window.addEventListener("scroll", clearAllHoverLayers);

  document.addEventListener("ayah-play", (e) => {
    const detail = e.detail || {};
    const surah = detail.surah;
    const ayah = detail.ayah;

    document.querySelectorAll(".ayah-polygon").forEach((r) => {
      r.classList.remove("ayah-active");
    });

    if (surah == null || ayah == null) return;

    const activeRects = document.querySelectorAll(
      `.ayah-polygon[data-surah="${surah}"][data-ayah="${ayah}"]`
    );

    activeRects.forEach((r) => r.classList.add("ayah-active"));
  });

  document.addEventListener("quran-page-flipped", reapplyActiveHighlight);
  document.addEventListener("quran-positions-rendered", reapplyActiveHighlight);

  window.addEventListener("resize", () => {
    setTimeout(reapplyActiveHighlight, 60);
  });
})();
