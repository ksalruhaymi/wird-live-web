document.addEventListener("click", function (e) {
  const mushafArea = document.getElementById("mushafArea");
  const flipContainer = document.getElementById("mushafFlipBook");

  if (
      e.target.closest(".hifz-toolbar") ||
      e.target.closest(".hifz-floating-controls") ||
      e.target.closest(".hifz-audio-btn-inline") ||
      e.target.closest("#quranFloatingControls")
    ) {
      return;
    }
  if (!mushafArea || !flipContainer) return;

  const ayah = e.target.closest(".ayah-box");
  if (ayah) {
    e.stopPropagation();
    playAyahElement(ayah);
    return;
  }

  if (
    e.target.closest("#fullscreenBtn") ||
    e.target.closest(".tools-panel") ||
    e.target.closest("#surahModal") ||
    e.target.closest("#mushafModal")
  ) {
    return;
  }

  if (e.target.closest("#mushafFlipBook")) {
    return;
  }

  if (e.target.closest("#mushafArea")) {
    if (!flipBook) return;

    const rect = mushafArea.getBoundingClientRect();
    const x = e.clientX - rect.left;
    const edgeWidth = rect.width * 0.08;

    if (x > rect.width - edgeWidth) {
      flipNext();
    } else if (x < edgeWidth) {
      flipPrev();
    }
  }
});