(function () {
  function getResumeTargetFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var surah = params.get("surah");
      var ayah = params.get("ayah");

      if (!surah || !ayah) return null;

      return {
        surah: String(surah),
        ayah: String(ayah),
      };
    } catch (err) {
      return null;
    }
  }

  function getResumePageFromUrl() {
    try {
      var params = new URLSearchParams(window.location.search);
      var page = parseInt(params.get("resume_page") || "0", 10);
      return page > 0 ? page : null;
    } catch (err) {
      return null;
    }
  }

  function findPageIndex(pageNumber) {
    if (!Array.isArray(window.QURAN_PAGE_MAP)) return -1;
    return window.QURAN_PAGE_MAP.indexOf(pageNumber);
  }

  function goToPage(pageNumber) {
    if (!pageNumber) return;

    try {
      if (typeof flipBook === "undefined") return;

      var index = findPageIndex(pageNumber);
      if (index < 0) return;

      flipBook.flip(index);
    } catch (err) {
      console.error("goToPage error:", err);
    }
  }

  function findAyahElement(page, surah, ayah) {
    return document.querySelector(
      `.ayah-layer[data-page="${page}"] [data-surah="${surah}"][data-ayah="${ayah}"]`
    );
  }

  function highlightAyah(el) {
    if (!el) return;

    el.classList.add("resume-ayah-target");

    setTimeout(function () {
      el.classList.remove("resume-ayah-target");
    }, 2500);
  }

  function resumeToAyah() {
    var target = getResumeTargetFromUrl();
    var page = getResumePageFromUrl();

    if (!target) return;

    if (page) {
      goToPage(page);
    }

    var attempts = 0;

    var timer = setInterval(function () {
      attempts++;

      var el = findAyahElement(page, target.surah, target.ayah);

      if (el) {
        highlightAyah(el);
        clearInterval(timer);
      }

      if (attempts > 40) {
        clearInterval(timer);
      }
    }, 250);
  }

  document.addEventListener("DOMContentLoaded", resumeToAyah);
  document.addEventListener("quran-page-flipped", resumeToAyah);
})();