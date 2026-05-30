function getShortTafsirPopover() {
  return document.getElementById("shortTafsirPopover");
}

function getShortTafsirLoading() {
  return document.getElementById("shortTafsirLoading");
}

function getShortTafsirError() {
  return document.getElementById("shortTafsirError");
}

function getShortTafsirAyahText() {
  return document.getElementById("shortTafsirAyahText");
}

function getShortTafsirText() {
  return document.getElementById("shortTafsirText");
}

function setShortTafsirLoadingState(isLoading) {
  const loading = getShortTafsirLoading();
  const error = getShortTafsirError();
  const ayahText = getShortTafsirAyahText();
  const tafsirText = getShortTafsirText();

  if (loading) {
    loading.classList.toggle("hidden", !isLoading);
  }

  if (error) {
    error.classList.add("hidden");
    error.textContent = "";
  }

  if (ayahText) {
    ayahText.classList.add("hidden");
    ayahText.textContent = "";
  }

  if (tafsirText) {
    tafsirText.textContent = "";
  }
}

function showShortTafsirError(message) {
  const loading = getShortTafsirLoading();
  const error = getShortTafsirError();
  const ayahText = getShortTafsirAyahText();
  const tafsirText = getShortTafsirText();

  if (loading) {
    loading.classList.add("hidden");
  }

  if (ayahText) {
    ayahText.classList.add("hidden");
    ayahText.textContent = "";
  }

  if (tafsirText) {
    tafsirText.textContent = "";
  }

  if (error) {
    error.textContent = message || "Failed to load.";
    error.classList.remove("hidden");
  }
}

function renderShortTafsir(data) {
  const loading = getShortTafsirLoading();
  const error = getShortTafsirError();
  const ayahText = getShortTafsirAyahText();
  const tafsirText = getShortTafsirText();

  if (loading) {
    loading.classList.add("hidden");
  }

  if (error) {
    error.classList.add("hidden");
    error.textContent = "";
  }

  if (ayahText) {
    if (data.ayah_text) {
      ayahText.textContent = data.ayah_text;
      ayahText.classList.remove("hidden");
    } else {
      ayahText.classList.add("hidden");
      ayahText.textContent = "";
    }
  }

  if (tafsirText) {
    tafsirText.textContent = data.tafsir_text || "";
  }
}

function positionShortTafsirPopover() {
  const popover = getShortTafsirPopover();
  if (!popover) return;

  const margin = 12;
  const ayahCenterOffsetY = 26;

  let top = window.innerHeight / 2;
  let left = window.innerWidth / 2;

  const ayahRect = window.__LAST_AYAH_TARGET_RECT__;
  if (ayahRect) {
    left = ayahRect.left + ayahRect.width / 2;
    top = ayahRect.top + ayahRect.height / 2 + ayahCenterOffsetY;
  } else if (window.__LAST_AYAH_CLICK_EVENT__) {
    left = window.__LAST_AYAH_CLICK_EVENT__.clientX;
    top = window.__LAST_AYAH_CLICK_EVENT__.clientY + ayahCenterOffsetY;
  }

  popover.style.visibility = "hidden";
  popover.classList.remove("hidden");

  const popRect = popover.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  left -= popRect.width / 2;
  top -= popRect.height / 2;

  left = Math.max(margin, Math.min(left, vw - popRect.width - margin));
  top = Math.max(margin, Math.min(top, vh - popRect.height - margin));

  popover.style.left = `${left}px`;
  popover.style.top = `${top}px`;
  popover.style.visibility = "visible";
}

function openShortTafsirPopoverBox() {
  const popover = getShortTafsirPopover();
  if (!popover) return;

  popover.classList.remove("hidden");
  positionShortTafsirPopover();
}

function closeShortTafsirPopover() {
  const popover = getShortTafsirPopover();
  if (!popover) return;

  popover.classList.add("hidden");
}

window.openShortTafsirPopover = async function (surah, ayah) {
  if (!surah || !ayah) return;

  const meta = document.getElementById("shortTafsirMeta");
  if (meta) {
    meta.textContent = `السعدي • سورة ${surah} • آية ${ayah}`;
  }

  setShortTafsirLoadingState(true);
  openShortTafsirPopoverBox();

  try {
    const url = new URL(window.QURAN_SHORT_TAFSIR_URL, window.location.origin);
    url.searchParams.set("surah", surah);
    url.searchParams.set("ayah", ayah);

    const response = await fetch(url.toString(), {
      headers: {
        "X-Requested-With": "XMLHttpRequest"
      }
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      showShortTafsirError(data.error || "Failed to load.");
      positionShortTafsirPopover();
      return;
    }

    renderShortTafsir(data);
    positionShortTafsirPopover();
  } catch (error) {
    console.error(error);
    showShortTafsirError("Failed to load.");
    positionShortTafsirPopover();
  }
};

document.addEventListener("click", function (event) {
  const popover = getShortTafsirPopover();
  const ayahMenu = document.getElementById("ayahMenu");

  if (!popover || popover.classList.contains("hidden")) return;

  const clickedInsidePopover = popover.contains(event.target);
  const clickedInsideAyahMenu = ayahMenu ? ayahMenu.contains(event.target) : false;

  if (!clickedInsidePopover && !clickedInsideAyahMenu) {
    closeShortTafsirPopover();
  }
});

window.addEventListener("resize", function () {
  const popover = getShortTafsirPopover();
  if (popover && !popover.classList.contains("hidden")) {
    positionShortTafsirPopover();
  }
});

window.addEventListener("scroll", function () {
  const popover = getShortTafsirPopover();
  if (popover && !popover.classList.contains("hidden")) {
    positionShortTafsirPopover();
  }
}, true);

window.closeShortTafsirPopover = closeShortTafsirPopover;