// static/quran/js/mode.js



//Mushaf Modal

function toggleMushafMenu() {
  const modal = document.getElementById("mushafModal");
  if (!modal) return;

  const isHidden = modal.classList.contains("hidden");

  if (isHidden) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  } else {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

document.addEventListener("DOMContentLoaded", function () {
  // Modal close logic (existing)
  const mushafModal = document.getElementById("mushafModal");
  if (mushafModal) {
    mushafModal.addEventListener("click", function (e) {
      if (e.target === mushafModal) {
        toggleMushafMenu();
      }
    });
  }

  // View mode logic (tilawa / tafsir)
  const tilawaBtn = document.getElementById("modeTilawaBtn");
  const tafsirBtn = document.getElementById("modeTafsirBtn");
  const flipContainer = document.getElementById("mushafFlipContainer");
  const tafsirPanel = document.getElementById("tafsirCenterPanel");

  function updateButtons(mode) {
    if (!tilawaBtn || !tafsirBtn) return;

    if (mode === "tafsir") {
      tafsirBtn.classList.add("bg-gray-900", "text-white");
      tafsirBtn.classList.remove("bg-white", "text-gray-700");

      tilawaBtn.classList.add("bg-white", "text-gray-700");
      tilawaBtn.classList.remove("bg-gray-900", "text-white");
    } else {
      tilawaBtn.classList.add("bg-gray-900", "text-white");
      tilawaBtn.classList.remove("bg-white", "text-gray-700");

      tafsirBtn.classList.add("bg-white", "text-gray-700");
      tafsirBtn.classList.remove("bg-gray-900", "text-white");
    }
  }

  function setMode(mode) {
    if (!flipContainer || !tafsirPanel) return;

    if (mode === "tafsir") {
      flipContainer.classList.add("hidden");
      tafsirPanel.classList.remove("hidden");
    } else {
      tafsirPanel.classList.add("hidden");
      flipContainer.classList.remove("hidden");
    }

    updateButtons(mode);
    window.currentMushafMode = mode;
  }

  // Expose global for other scripts (tafsir loader)
  window.setMushafMode = function (mode) {
    setMode(mode === "tafsir" ? "tafsir" : "tilawa");
  };

  if (tilawaBtn) {
    tilawaBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setMode("tilawa");
    });
  }

  if (tafsirBtn) {
    tafsirBtn.addEventListener("click", function (e) {
      e.preventDefault();
      setMode("tafsir");
    });
  }

  // Default mode
  setMode("tilawa");
});




//Surah Modal
let surahGridWrapperInitialHeight = null;
let activeQuranIndexTab = "surahs";

function toggleMenu() {
  const modal = document.getElementById("surahModal");
  if (!modal) return;

  const isHidden = modal.classList.contains("hidden");

  if (isHidden) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");

    const input = document.getElementById("surahSearch");
    if (input) {
      input.value = "";
    }
    filterSurahs("");
    setQuranIndexTab(activeQuranIndexTab);

    const wrapper = document.getElementById("surahGridWrapper");
    if (wrapper && surahGridWrapperInitialHeight === null) {
      requestAnimationFrame(() => {
        surahGridWrapperInitialHeight = wrapper.offsetHeight;
        wrapper.style.minHeight = surahGridWrapperInitialHeight + "px";
      });
    }

    const input2 = document.getElementById("surahSearch");
    if (input2) {
      setTimeout(() => input2.focus(), 50);
    }
  } else {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

function filterSurahs(query) {
  const q = (query || "").trim().toLowerCase();
  const activePanel = document.querySelector('[data-index-panel="' + activeQuranIndexTab + '"]');
  const panels = activePanel
    ? [activePanel]
    : Array.from(document.querySelectorAll("[data-index-panel]"));

  panels.forEach((panel) => {
    const items = panel.querySelectorAll("[data-index-name]");

    items.forEach((item) => {
      const name = (item.getAttribute("data-index-name") || "").toLowerCase();
      if (!q || name.includes(q)) {
        item.classList.remove("hidden");
      } else {
        item.classList.add("hidden");
      }
    });
  });
}

function setQuranIndexTab(tabName) {
  const nextTab = tabName === "juzs" ? "juzs" : "surahs";
  activeQuranIndexTab = nextTab;

  document.querySelectorAll("[data-index-panel]").forEach((panel) => {
    if (panel.getAttribute("data-index-panel") === nextTab) {
      panel.classList.remove("hidden");
    } else {
      panel.classList.add("hidden");
    }
  });

  document.querySelectorAll("[data-index-tab]").forEach((tab) => {
    const isActive = tab.getAttribute("data-index-tab") === nextTab;
    tab.classList.toggle("bg-white", isActive);
    tab.classList.toggle("text-emerald-700", isActive);
    tab.classList.toggle("shadow-sm", isActive);
    tab.classList.toggle("text-gray-600", !isActive);
  });

  const input = document.getElementById("surahSearch");
  filterSurahs(input ? input.value : "");
}

document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("surahSearch");
  if (input) {
    input.addEventListener("input", function (e) {
      filterSurahs(e.target.value);
    });
  }

  document.querySelectorAll("[data-index-tab]").forEach((tab) => {
    tab.addEventListener("click", function () {
      setQuranIndexTab(tab.getAttribute("data-index-tab"));
    });
  });

  setQuranIndexTab(activeQuranIndexTab);

  const modal = document.getElementById("surahModal");
  if (modal) {
    modal.addEventListener("click", function (e) {
      if (e.target === modal) {
        toggleMenu();
      }
    });
  }

  document.addEventListener("click", function (e) {
    const qariBtn = e.target.closest("#qurraGrid .quran-qari-opt");
    if (!qariBtn) return;
    if (typeof toggleQurraModal === "function") {
      toggleQurraModal();
    }
  });
});





//Quraa Modal

function toggleTafsirModal() {
  const modal = document.getElementById("tafsirModal");
  if (!modal) return;

  if (modal.classList.contains("hidden")) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
  } else {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

function closeTafsirOutside(event) {
  const modal = document.getElementById("tafsirModal");
  if (!modal) return;
  // Close when clicking on dark background only
  if (event.target === modal) {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

function selectTafsir(slug) {
  const url = new URL(window.location.href);
  url.searchParams.set('tafsir', slug);
  // Keep other params like page, mushaf, qari
  window.location.href = url.toString();
}
///////////////////////////////////////////////////////////

let qurraGridWrapperInitialHeight = null;

function toggleQurraModal() {
  const modal = document.getElementById("qurraModal");
  if (!modal) return;

  const isHidden = modal.classList.contains("hidden");

  if (isHidden) {
    modal.classList.remove("hidden");
    modal.classList.add("flex");

    // تنظيف حقل البحث
    const input = document.getElementById("qurraSearch");
    if (input) {
      input.value = "";
    }
    filterQurra("");

    // تثبيت ارتفاع اللفّاف مرة واحدة (مثل surahGridWrapper)
    const wrapper = document.getElementById("qurraGridWrapper");
    if (wrapper && qurraGridWrapperInitialHeight === null) {
      requestAnimationFrame(() => {
        qurraGridWrapperInitialHeight = wrapper.offsetHeight;
        wrapper.style.minHeight = qurraGridWrapperInitialHeight + "px";
      });
    }

    // فوكس على حقل البحث
    const input2 = document.getElementById("qurraSearch");
    if (input2) {
      setTimeout(() => input2.focus(), 50);
    }
  } else {
    modal.classList.add("hidden");
    modal.classList.remove("flex");
  }
}

function filterQurra(query) {
  const grid = document.getElementById("qurraGrid");
  if (!grid) return;

  const q = (query || "").trim().toLowerCase();
  const items = grid.querySelectorAll("[data-qari-name]");

  items.forEach((item) => {
    const name = (item.getAttribute("data-qari-name") || "").toLowerCase();
    if (!q || name.includes(q)) {
      item.classList.remove("hidden");
    } else {
      item.classList.add("hidden");
    }
  });
}

document.addEventListener("DOMContentLoaded", function () {
  const input = document.getElementById("qurraSearch");
  if (input) {
    input.addEventListener("input", function (e) {
      filterQurra(e.target.value);
    });
  }

  const modal = document.getElementById("qurraModal");
  if (modal) {
    // إغلاق عند الضغط على الخلفية
    modal.addEventListener("click", function (e) {
      if (e.target === modal) {
        toggleQurraModal();
      }
    });
  }
});
