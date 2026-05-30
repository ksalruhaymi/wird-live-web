document.addEventListener("DOMContentLoaded", function () {
  const container = document.getElementById("toast-container");
  if (!container) return;

  // افتراضيات من الحاوية (يمكن تركها فارغة)
  const DEF_DURATION = parseInt(container.dataset.defaultDuration || "4000", 10);
  const DEF_MAXW     = container.dataset.defaultMaxw || "30";   // مثال "20rem"
  const DEF_WIDTH    = container.dataset.defaultWidth || "30";   // مثال "22rem"

  const toasts = Array.from(container.querySelectorAll(".toast"));

  toasts.forEach((toast) => {
    const closeBtn   = toast.querySelector(".toast-close");
    const progress   = toast.querySelector(".toast-progress");

    // قراءة إعدادات خاصة لكل توست
    const dur        = parseInt(toast.dataset.duration || DEF_DURATION || 4000, 10);
    const maxw       = toast.dataset.maxw || DEF_MAXW;
    const width      = toast.dataset.width || DEF_WIDTH;
    const progressH  = toast.dataset.progressH || ""; // مثلاً "4px"

    // طبّق العرض/الماكس عرض إن تم تحديده
    if (maxw)  toast.style.maxWidth = maxw;
    if (width) toast.style.width    = width;

    // شريط التقدّم - ارتفاع قابل للتغيير
    if (progressH) {
      // نستخدم CSS variable لسهولة ضبط الارتفاع في كلا العنصرين
      toast.style.setProperty("--progress-h", progressH);
    }

    // دخول أنيميشن
    requestAnimationFrame(() => {
      toast.classList.remove("opacity-0", "translate-y-2");
      toast.classList.add("opacity-100", "translate-y-0");
    });

    // تحريك شريط التقدم
    if (progress) {
      progress.style.transition = `width ${dur}ms linear`;
      requestAnimationFrame(() => {
        progress.style.width = "0%";
      });
    }

    // إغلاق تلقائي
    const autoTimer = setTimeout(() => dismiss(), dur);

    // إغلاق يدوي
    closeBtn?.addEventListener("click", () => {
      clearTimeout(autoTimer);
      dismiss();
    });

    function dismiss() {
      toast.classList.remove("opacity-100", "translate-y-0");
      toast.classList.add("opacity-0", "translate-y-2");
      setTimeout(() => {
        toast.remove();
        if (!container.children.length) container.remove();
      }, 250);
    }
  });
});
