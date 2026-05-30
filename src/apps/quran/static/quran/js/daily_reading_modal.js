// ─── Global helpers ───────────────────────────────────────────────────────────
function getCsrf() {
  const c = document.cookie.split("; ").find((r) => r.startsWith("csrftoken="));
  return c ? c.split("=")[1] : "";
}

function postJSON(url, body) {
  return fetch(url, {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-CSRFToken": getCsrf(),
      "X-Requested-With": "XMLHttpRequest",
    },
    body: JSON.stringify(body || {}),
  });
}

// ─── Toggle knob helper (uses translate-x-0 / translate-x-6, both in CSS) ────
function setToggleState(btnId, knobId, isOn) {
  const btn  = document.getElementById(btnId);
  const knob = document.getElementById(knobId);
  if (!btn || !knob) return;
  btn.classList.toggle("bg-emerald-500", isOn);
  btn.classList.toggle("bg-gray-300",    !isOn);
  btn.setAttribute("aria-pressed", isOn ? "true" : "false");
  knob.classList.toggle("translate-x-6", isOn);
  knob.classList.toggle("translate-x-0", !isOn);
}

// ─── Daily Reading Modal ──────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", function () {
  const modal      = document.getElementById("dailyReadingModal");
  const openBtns   = document.querySelectorAll("[data-open-daily-reading]");
  const closeBtn   = document.getElementById("dailyReadingCloseBtn");
  const continueBtn = document.getElementById("continueDailyReadingBtn");
  const finishBtn  = document.getElementById("finishDailyReadingBtn");
  const actionsDiv = document.getElementById("dailyReadingActions");

  if (!modal) return;

  function open() {
    modal.classList.remove("hidden");
    modal.classList.add("flex");
    document.body.classList.add("overflow-hidden");
  }
  function close() {
    modal.classList.remove("flex");
    modal.classList.add("hidden");
    document.body.classList.remove("overflow-hidden");
  }

  openBtns.forEach((b) => b.addEventListener("click", (e) => { e.preventDefault(); open(); }));
  if (closeBtn) closeBtn.addEventListener("click", close);
  modal.addEventListener("click", (e) => { if (e.target === modal) close(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") close(); });

  // Resume from URL param / localStorage
  try {
    const params = new URLSearchParams(window.location.search);
    if (params.get("open_daily_reading") === "1" || localStorage.getItem("wird_open_daily_reading") === "1") {
      open();
      localStorage.removeItem("wird_open_daily_reading");
      params.delete("open_daily_reading");
      const q = params.toString();
      window.history.replaceState({}, "", window.location.pathname + (q ? "?" + q : "") + (window.location.hash || ""));
    }
  } catch (_) {}

  if (continueBtn) continueBtn.addEventListener("click", () => { if (continueBtn.dataset.url) window.location.href = continueBtn.dataset.url; });

  // Apply tracking mode from server-rendered attribute on page load
  if (actionsDiv && actionsDiv.dataset.trackingMode) {
    applyTrackingModeUI(actionsDiv.dataset.trackingMode);
  }

  // Finish wird (manual only)
  if (finishBtn) {
    finishBtn.addEventListener("click", async function () {
      const orig = finishBtn.innerHTML;
      try {
        finishBtn.disabled = true;
        finishBtn.classList.add("opacity-70", "pointer-events-none");
        finishBtn.innerHTML = "......";

        const r    = await postJSON("/quran/khatma/complete-wird/");
        const data = await r.json();
        if (!data.ok) return;

        if (data.daily_reading) updateDailyReadingModal(data.daily_reading);
        data.finished_khatma ? showFinishedKhatmaState(data.khatma_count) : (hideFinishedKhatmaState(), updateKhatmaCountLive(data.khatma_count));
      } catch (e) {
        console.error("complete-wird error:", e);
      } finally {
        finishBtn.disabled = false;
        finishBtn.classList.remove("opacity-70", "pointer-events-none");
        finishBtn.innerHTML = orig;
      }
    });
  }

  // Auto-track page flips
  document.addEventListener("quran-page-flipped", function (event) {
    const currentPage = event?.detail?.page;
    if (!currentPage) return;
    postJSON("/quran/khatma/progress/", { current_page: currentPage })
      .then((r) => r.json())
      .then((data) => {
        if (data.ok && data.wird_status) {
          // Could show auto-completion badge here in future
        }
      })
      .catch((e) => console.error("progress error:", e));
  });

  // Save server-rendered khatma count to localStorage on load
  try {
    const el = document.getElementById("khatmaCountText");
    if (el) {
      const val = el.textContent.trim();
      if (val && val !== "0") localStorage.setItem("wird_khatma_count", val);
    }
  } catch (_) {}

  window.openDailyReadingModal  = open;
  window.closeDailyReadingModal = close;
});

// ─── Toggle tracking from daily reading modal ─────────────────────────────────
async function toggleDailyReadingTracking() {
  try {
    const r    = await postJSON("/quran/khatma/toggle-tracking/");
    const data = await r.json();
    if (!data.ok) return;
    const actionsDiv = document.getElementById("dailyReadingActions");
    if (actionsDiv) actionsDiv.dataset.trackingMode = data.tracking_mode;
    applyTrackingModeUI(data.tracking_mode);
  } catch (e) {
    console.error("toggle-tracking error:", e);
  }
}

// ─── Apply tracking mode to daily reading modal UI ───────────────────────────
function applyTrackingModeUI(trackingMode) {
  const isAuto = trackingMode === "auto";
  const finishBtn = document.getElementById("finishDailyReadingBtn");
  if (finishBtn) finishBtn.classList.toggle("hidden", isAuto);

  setToggleState("dailyReadingTrackingToggle", "dailyReadingTrackingKnob", isAuto);

  const label = document.getElementById("dailyReadingTrackingLabel");
  // label removed — toggle color communicates state
}


// ─── New Khatma Modal ─────────────────────────────────────────────────────────
let duration = 30;

function openNewKhatmaModal() {
  const m = document.getElementById("newKhatmaModal");
  if (!m) return;
  m.classList.remove("hidden");
  m.classList.add("flex");
  updateKhatmaSummary();
}

function closeNewKhatmaModal() {
  const m = document.getElementById("newKhatmaModal");
  if (!m) return;
  m.classList.remove("flex");
  m.classList.add("hidden");
}

// الأقسام بوحدة الربع (240 ربعاً في القرآن: 30 جزء × 2 حزب × 4 أرباع)
const _AMOUNT_RUB3 = [
  { type: "sub", value: "rub3",  rub3: 1  },
  { type: "sub", value: "2rub3", rub3: 2  },
  { type: "sub", value: "3rub3", rub3: 3  },
  { type: "sub", value: "hizb",  rub3: 4  },
  { type: "sub", value: "5rub3", rub3: 5  },
  { type: "sub", value: "6rub3", rub3: 6  },
  { type: "sub", value: "7rub3", rub3: 7  },
  { type: "juz", value: "juz",   rub3: 8  },
  { type: "juz", value: "2juz",  rub3: 16 },
  { type: "juz", value: "3juz",  rub3: 24 },
  { type: "juz", value: "4juz",  rub3: 32 },
  { type: "juz", value: "5juz",  rub3: 40 },
  { type: "juz", value: "6juz",  rub3: 48 },
  { type: "juz", value: "7juz",  rub3: 56 },
  { type: "juz", value: "8juz",  rub3: 64 },
  { type: "juz", value: "9juz",  rub3: 72 },
  { type: "juz", value: "10juz", rub3: 80 },
];

function autoSelectDailyAmount() {
  const needed = 240 / duration;
  let best = _AMOUNT_RUB3[0], minDiff = Infinity;
  for (const opt of _AMOUNT_RUB3) {
    const diff = Math.abs(opt.rub3 - needed);
    if (diff < minDiff) { minDiff = diff; best = opt; }
  }
  const sub = document.getElementById("khatmaAmountSub");
  const juz = document.getElementById("khatmaAmountJuz");
  if (best.type === "sub") {
    if (sub) sub.value = best.value;
    if (juz) { juz.value = "juz"; juz.disabled = true; juz.classList.add("opacity-40"); }
  } else {
    if (sub) sub.value = "";
    if (juz) { juz.value = best.value; juz.disabled = false; juz.classList.remove("opacity-40"); }
  }
  updateKhatmaSummary();
}

function changeDuration(step) {
  duration = Math.max(3, Math.min(240, duration + step));
  const dayLabel = window.khatmaDayLabel || "يوم";
  const el = document.getElementById("durationValue");
  if (el) el.textContent = duration + " " + dayLabel;
  const sd = document.getElementById("summaryDuration");
  if (sd) sd.textContent = duration + " " + dayLabel;
  autoSelectDailyAmount();
}

function getSelectedAmountType() {
  const sub = document.getElementById("khatmaAmountSub");
  const juz = document.getElementById("khatmaAmountJuz");
  return (sub && sub.value) ? sub.value : (juz ? juz.value : "juz");
}

function getSelectedAmountLabel() {
  const sub = document.getElementById("khatmaAmountSub");
  const juz = document.getElementById("khatmaAmountJuz");
  if (sub && sub.value) return sub.options[sub.selectedIndex].text;
  if (juz) return juz.options[juz.selectedIndex].text;
  return "جزء";
}

function onSubDivChange() {
  const sub = document.getElementById("khatmaAmountSub");
  const juz = document.getElementById("khatmaAmountJuz");
  if (juz) {
    juz.disabled = !!(sub && sub.value);
    juz.classList.toggle("opacity-40", !!(sub && sub.value));
  }
  updateKhatmaSummary();
}


function updateKhatmaSummary() {
  const dayLabel = window.khatmaDayLabel || "يوم";
  const start    = document.getElementById("khatmaStart");
  const ss       = document.getElementById("summaryStart");
  const sa       = document.getElementById("summaryAmount");
  const sd       = document.getElementById("summaryDuration");
  const preview  = document.getElementById("khatmaAmountPreview");

  if (ss && start) ss.textContent = start.options[start.selectedIndex].text;
  if (sa) sa.textContent = getSelectedAmountLabel();
  if (sd) sd.textContent = duration + " " + dayLabel;
  if (preview) preview.textContent = "📖 " + getSelectedAmountLabel() + " يومياً";
}

document.addEventListener("DOMContentLoaded", function () {
  const s = document.getElementById("khatmaStart");
  const j = document.getElementById("khatmaAmountJuz");
  if (s) s.addEventListener("change", updateKhatmaSummary);
  if (j) j.addEventListener("change", updateKhatmaSummary);
  updateKhatmaSummary();
});

async function submitNewKhatma() {
  const start = document.getElementById("khatmaStart");
  try {
    const r    = await postJSON("/quran/khatma/start/", {
      start_from:        start ? start.value : "beginning",
      duration_days:     duration,
      daily_amount_type: getSelectedAmountType(),
      tracking_mode:     "manual",
    });
    const data = await r.json();
    if (data.ok) window.location.reload();
    else console.error("start khatma failed", data);
  } catch (e) {
    console.error("submitNewKhatma error:", e);
  }
}


// ─── Update daily reading modal DOM from API data ────────────────────────────
function updateDailyReadingModal(r) {
  function set(id, val) { const el = document.getElementById(id); if (el && val !== undefined) el.textContent = val; }
  set("dailyReadingWirdNumber",        r.current_wird_number);
  set("dailyReadingStartSurah",        r.start_surah_name);
  set("dailyReadingStartAyah",         r.start_ayah_number);
  set("dailyReadingEndSurah",          r.end_surah_name);
  set("dailyReadingEndAyah",           r.end_ayah_number);
  set("dailyReadingCurrentAyahText",   r.current_ayah_text);
  set("dailyReadingCurrentAyahNumber", r.start_ayah_number);
  set("dailyReadingCurrentPageNumber", r.current_page);
  set("dailyReadingCurrentJuzNumber",  r.current_juz_number);
  set("dailyReadingPercentText",       r.current_khatma_percent !== undefined ? r.current_khatma_percent + "%" : undefined);
  set("dailyReadingWirdProgress",      r.current_wird_number !== undefined && r.total_wirds !== undefined
        ? r.current_wird_number + " / " + r.total_wirds : undefined);

  const pb  = document.getElementById("dailyReadingProgressBar");
  if (pb && r.current_khatma_percent !== undefined) pb.style.width = r.current_khatma_percent + "%";

  const cb  = document.getElementById("continueDailyReadingBtn");
  if (cb && r.continue_url) cb.dataset.url = r.continue_url;

  if (r.tracking_mode) applyTrackingModeUI(r.tracking_mode);
}

function showFinishedKhatmaState(khatmaCount) {
  ["dailyReadingContent", "dailyReadingActions", "dailyReadingTrackingRow"].forEach((id) => document.getElementById(id)?.classList.add("hidden"));
  document.getElementById("dailyReadingFinishState")?.classList.remove("hidden");
  updateKhatmaCountLive(khatmaCount);
}

function hideFinishedKhatmaState() {
  document.getElementById("dailyReadingFinishState")?.classList.add("hidden");
  ["dailyReadingContent", "dailyReadingActions", "dailyReadingTrackingRow"].forEach((id) => document.getElementById(id)?.classList.remove("hidden"));
}

function updateKhatmaCountLive(count) {
  const el = document.getElementById("khatmaCountText");
  if (el && count !== undefined) {
    el.textContent = String(count);
    try { localStorage.setItem("wird_khatma_count", String(count)); } catch (_) {}
  }
}

// Load khatma count from localStorage if element shows 0 and localStorage has a value
(function () {
  try {
    const saved = localStorage.getItem("wird_khatma_count");
    if (saved && saved !== "0") {
      const el = document.getElementById("khatmaCountText");
      if (el && (el.textContent.trim() === "0" || el.textContent.trim() === "")) {
        el.textContent = saved;
      }
    }
  } catch (_) {}
})();
