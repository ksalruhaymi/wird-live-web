function isArabicWordMeaningsAllowed() {
  return (
    window.QURAN_ARABIC_FEATURES_ENABLED === true ||
    window.HIFZ_ARABIC_FEATURES_ENABLED === true
  );
}

function getWordMeaningsPopover() {
  return document.getElementById("wordMeaningsPopover");
}

function getWordMeaningsList() {
  return document.getElementById("wordMeaningsList");
}

function getWordMeaningsError() {
  return document.getElementById("wordMeaningsError");
}

function getWordMeaningsLoading() {
  return document.getElementById("wordMeaningsLoading");
}

function setWordMeaningsLoadingState(isLoading) {
  const loading = getWordMeaningsLoading();
  const error = getWordMeaningsError();
  const list = getWordMeaningsList();

  if (loading) {
    loading.classList.toggle("hidden", !isLoading);
  }

  if (error) {
    error.classList.add("hidden");
    error.textContent = "";
  }

  if (list) {
    list.innerHTML = "";
  }
}

function showWordMeaningsError(message) {
  const loading = getWordMeaningsLoading();
  const error = getWordMeaningsError();
  const list = getWordMeaningsList();

  if (loading) {
    loading.classList.add("hidden");
  }

  if (list) {
    list.innerHTML = "";
  }

  if (error) {
    error.textContent = message || "Failed to load.";
    error.classList.remove("hidden");
  }
}

function renderWordMeaningsItems(items) {
  const loading = getWordMeaningsLoading();
  const error = getWordMeaningsError();
  const list = getWordMeaningsList();

  if (loading) {
    loading.classList.add("hidden");
  }

  if (error) {
    error.classList.add("hidden");
    error.textContent = "";
  }

  if (!list) return;

  list.innerHTML = "";

  if (!items || !items.length) {
    list.innerHTML = `
      <div class="text-sm text-gray-500 text-center py-4">
        ${window.TRANSLATIONS.noWordMeanings}
      </div>
    `;
    return;
  }

  items.forEach(function (item) {
    const box = document.createElement("div");
    box.className = "rounded-lg bg-gray-50 px-2 py-2";

    const line = document.createElement("div");
    line.className = "text-sm text-gray-800 leading-6";

    line.innerHTML = `
            <span class="font-semibold text-emerald-600">${item.word}</span>
            <span class="text-gray-400 mx-1">:</span>
            <span class="text-black">${item.meaning}</span>
            `;

    box.appendChild(line);
        list.appendChild(box);
    });
    }

function positionWordMeaningsPopover() {
  const popover = getWordMeaningsPopover();
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
    const evt = window.__LAST_AYAH_CLICK_EVENT__;
    left = evt.clientX;
    top = evt.clientY + ayahCenterOffsetY;
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

function openWordMeaningsPopover() {
  const popover = getWordMeaningsPopover();
  if (!popover) return;

  popover.classList.remove("hidden");
  positionWordMeaningsPopover();
}

function closeWordMeaningsPopover() {
  const popover = getWordMeaningsPopover();
  if (!popover) return;

  popover.classList.add("hidden");
}

window.openWordMeaningsPopover = async function (surah, ayah) {
  if (!isArabicWordMeaningsAllowed()) return;
  if (!surah || !ayah) return;

  const meta = document.getElementById("wordMeaningsMeta");
  if (meta) {
    meta.textContent = `سورة ${surah} - آية ${ayah}`;
  }

  setWordMeaningsLoadingState(true);
  openWordMeaningsPopover();

  try {
    const url = new URL(window.QURAN_WORD_MEANINGS_URL, window.location.origin);
    url.searchParams.set("surah", surah);
    url.searchParams.set("ayah", ayah);

    const response = await fetch(url.toString(), {
      headers: {
        "X-Requested-With": "XMLHttpRequest"
      }
    });

    const data = await response.json();

    if (!response.ok || !data.success) {
      showWordMeaningsError(data.error || "Failed to load.");
      positionWordMeaningsPopover();
      return;
    }

    renderWordMeaningsItems(data.items || []);
    positionWordMeaningsPopover();
  } catch (error) {
    console.error(error);
    showWordMeaningsError("Failed to load.");
    positionWordMeaningsPopover();
  }
};

document.addEventListener("click", function (event) {
  const popover = getWordMeaningsPopover();
  const ayahMenu = document.getElementById("ayahMenu");

  if (!popover || popover.classList.contains("hidden")) return;

  const clickedInsidePopover = popover.contains(event.target);
  const clickedInsideAyahMenu = ayahMenu ? ayahMenu.contains(event.target) : false;

  if (!clickedInsidePopover && !clickedInsideAyahMenu) {
    closeWordMeaningsPopover();
  }
});

window.addEventListener("resize", function () {
  const popover = getWordMeaningsPopover();
  if (popover && !popover.classList.contains("hidden")) {
    positionWordMeaningsPopover();
  }
});

window.addEventListener("scroll", function () {
  const popover = getWordMeaningsPopover();
  if (popover && !popover.classList.contains("hidden")) {
    positionWordMeaningsPopover();
  }
}, true);

window.closeWordMeaningsPopover = closeWordMeaningsPopover;