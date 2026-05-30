(function () {
  const ACTIVE_TICK_SECONDS = 15;

  function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== "") {
      const cookies = document.cookie.split(";");
      for (let cookie of cookies) {
        cookie = cookie.trim();
        if (cookie.startsWith(name + "=")) {
          cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
          break;
        }
      }
    }
    return cookieValue;
  }

  function track(type, data = {}) {
    fetch("/analytics/track-event/", {
      method: "POST",
      keepalive: true,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
        type: type,
        data: data,
        path: window.location.pathname,
      }),
    }).catch((err) => {
      console.error("Tracking failed:", err);
    });
  }

  function trackActiveDuration(seconds) {
    if (!seconds || seconds <= 0) return;

    fetch("/analytics/track-event/", {
      method: "POST",
      keepalive: true,
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": getCookie("csrftoken"),
      },
      body: JSON.stringify({
      type: "session_active",
      data: {
        active_seconds: seconds,
      },
      path: window.location.pathname,
      }),
    }).catch(function () {
      track("session_active", { active_seconds: seconds });
    });
  }

  let activeBufferSeconds = 0;
  let activeInterval = null;

  function flushActiveBuffer() {
    if (activeBufferSeconds <= 0) return;
    const value = activeBufferSeconds;
    activeBufferSeconds = 0;
    trackActiveDuration(value);
  }

  function startActiveTimer() {
    if (activeInterval) return;
    activeInterval = setInterval(function () {
      if (document.hidden) return;
      activeBufferSeconds += ACTIVE_TICK_SECONDS;
      if (activeBufferSeconds >= 60) {
        flushActiveBuffer();
      }
    }, ACTIVE_TICK_SECONDS * 1000);
  }

  function stopActiveTimer() {
    if (!activeInterval) return;
    clearInterval(activeInterval);
    activeInterval = null;
  }

  document.addEventListener("visibilitychange", function () {
    if (document.hidden) {
      flushActiveBuffer();
      return;
    }
    startActiveTimer();
  });
  window.addEventListener("beforeunload", flushActiveBuffer);
  window.addEventListener("pagehide", flushActiveBuffer);
  startActiveTimer();

  window.WirdAnalytics = {
    track: track,
  };
})();